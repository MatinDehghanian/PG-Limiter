"""
Enhanced Warning System for Limiter
This module provides a warning system with monitoring periods for users who exceed limits
"""

import asyncio
import json
import os
import time
from typing import Dict, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from utils.logs import logger
from utils.types import PanelType, UserType


async def safe_send_logs(message: str):
    """Safely send logs, handling import errors gracefully"""
    try:
        from telegram_bot.send_message import send_logs
        await send_logs(message)
    except ImportError as e:
        logger.warning(f"Telegram not configured: {e}")
    except Exception as e:
        logger.error(f"Failed to send telegram message: {e}")


async def safe_send_disable_notification(message: str, username: str):
    """Safely send disable notification with enable button"""
    try:
        from telegram_bot.send_message import send_disable_notification
        await send_disable_notification(message, username)
    except ImportError as e:
        logger.warning(f"Telegram not configured: {e}")
        # Fallback to regular logs
        await safe_send_logs(message)
    except Exception as e:
        logger.error(f"Failed to send disable notification: {e}")
        # Fallback to regular logs
        await safe_send_logs(message)


async def safe_disable_user(panel_data: PanelType, user: 'UserType'):
    """Safely disable user, handling import errors gracefully"""
    try:
        from utils.panel_api import disable_user
        await disable_user(panel_data, user)
    except ImportError as e:
        logger.error(f"Failed to import disable_user: {e}")
    except Exception as e:
        logger.error(f"Failed to disable user {user.name}: {e}")

@dataclass
class UserWarning:
    """
    Represents a warning for a user who exceeded limits
    """
    username: str
    ip_count: int
    ips: Set[str]
    warning_time: float
    monitoring_end_time: float
    warned: bool = False
    # Enhanced monitoring fields
    monitoring_history: list = None
    active_monitoring_task: Optional[asyncio.Task] = None
    # IP activity tracking - tracks how long each IP has been active
    ip_first_seen: Dict[str, float] = None  # IP -> first seen timestamp
    ip_last_seen: Dict[str, float] = None   # IP -> last seen timestamp
    ip_seen_count: Dict[str, int] = None    # IP -> number of times seen in checks
    # Trust score fields
    trust_score: float = 0.0  # Higher = more trustworthy, Lower = more suspicious
    inbound_protocols: Set[str] = None
    isp_names: Set[str] = None
    ip_subnets: Set[str] = None
    previous_warnings_12h: int = 0  # Count of disables in last 12 hours
    previous_warnings_24h: int = 0  # Count of disables in last 24 hours
    # Enhanced detection fields
    ip_to_inbounds: Dict = None  # Maps IP -> set of inbounds used
    same_ip_multiple_inbounds: bool = False  # True if same IP uses different inbounds (likely 1 device)
    isp_change_pattern: str = None  # "sim_swap" or "multi_device" or None
    connection_details: list = None  # List of connection info for analysis
    
    def __post_init__(self):
        if self.monitoring_history is None:
            self.monitoring_history = []
        if self.ip_first_seen is None:
            self.ip_first_seen = {}
        if self.ip_last_seen is None:
            self.ip_last_seen = {}
        if self.ip_seen_count is None:
            self.ip_seen_count = {}
        if self.inbound_protocols is None:
            self.inbound_protocols = set()
        if self.isp_names is None:
            self.isp_names = set()
        if self.ip_subnets is None:
            self.ip_subnets = set()
        if self.ip_to_inbounds is None:
            self.ip_to_inbounds = {}
        if self.connection_details is None:
            self.connection_details = []
    
    def is_monitoring_active(self) -> bool:
        """Check if the monitoring period is still active"""
        return time.time() < self.monitoring_end_time
    
    def time_remaining(self) -> int:
        """Get remaining monitoring time in seconds"""
        remaining = self.monitoring_end_time - time.time()
        return max(0, int(remaining))
    
    def update_ip_activity(self, current_ips: Set[str], timestamp: float = None):
        """
        Update IP activity tracking. Called each check cycle during monitoring.
        Tracks first seen, last seen, and seen count for each IP.
        """
        if timestamp is None:
            timestamp = time.time()
        
        for ip in current_ips:
            # Track first time we see this IP
            if ip not in self.ip_first_seen:
                self.ip_first_seen[ip] = timestamp
            # Always update last seen
            self.ip_last_seen[ip] = timestamp
            # Increment seen count
            self.ip_seen_count[ip] = self.ip_seen_count.get(ip, 0) + 1
        
        # Also add to monitoring history for backwards compatibility
        if len(self.monitoring_history) < 20:
            self.monitoring_history.append({
                'timestamp': timestamp,
                'ips': current_ips.copy(),
                'ip_count': len(current_ips)
            })
    
    def get_ip_active_duration(self, ip: str) -> float:
        """
        Get how long an IP has been active (in seconds).
        Returns the duration between first and last seen.
        """
        if ip not in self.ip_first_seen or ip not in self.ip_last_seen:
            return 0.0
        return self.ip_last_seen[ip] - self.ip_first_seen[ip]
    
    def get_persistent_devices(self, min_duration_seconds: int = 120) -> Set[str]:
        """
        Get IPs that have been active for at least min_duration_seconds (default 2 min).
        These are considered "confirmed devices".
        
        Args:
            min_duration_seconds: Minimum active duration to count as device (default 120s = 2 min)
            
        Returns:
            Set of IPs that qualify as persistent devices
        """
        persistent_ips = set()
        current_time = time.time()
        
        for ip in self.ip_first_seen:
            # Check if IP was seen recently (within last check cycle + buffer)
            last_seen = self.ip_last_seen.get(ip, 0)
            if current_time - last_seen > 120:  # IP not seen in last 2 minutes, skip
                continue
            
            # Calculate active duration
            duration = self.get_ip_active_duration(ip)
            seen_count = self.ip_seen_count.get(ip, 0)
            
            # IP is a persistent device if:
            # 1. Active for at least min_duration_seconds, OR
            # 2. Seen in at least 2 check cycles (indicates persistence across checks)
            if duration >= min_duration_seconds or seen_count >= 2:
                persistent_ips.add(ip)
        
        return persistent_ips
    
    def get_device_count(self, min_duration_seconds: int = 120) -> int:
        """
        Get the count of confirmed devices (IPs active for min duration).
        """
        return len(self.get_persistent_devices(min_duration_seconds))
    
    def get_ip_activity_summary(self) -> str:
        """
        Get a summary of IP activity for debugging/display.
        """
        lines = []
        current_time = time.time()
        
        for ip in self.ip_first_seen:
            duration = self.get_ip_active_duration(ip)
            seen_count = self.ip_seen_count.get(ip, 0)
            last_seen = self.ip_last_seen.get(ip, 0)
            is_recent = (current_time - last_seen) < 120
            
            status = "✅" if duration >= 120 or seen_count >= 2 else "⏳"
            if not is_recent:
                status = "❌"
            
            lines.append(f"{status} {ip}: {duration:.0f}s active, seen {seen_count}x")
        
        return "\n".join(lines) if lines else "No IP activity recorded"
    
    def analyze_ip_inbound_pattern(self) -> dict:
        """
        Analyze IP to inbound patterns to detect device behavior.
        
        Returns:
            dict with analysis results:
            - same_ip_multi_inbound: True if same IP uses multiple inbounds (likely 1 device)
            - multi_ip_same_inbound: True if multiple IPs use same inbound (likely multi-device)
            - pattern_type: "single_device_switching" or "multi_device" or "mixed" or "unknown"
        """
        analysis = {
            'same_ip_multi_inbound': False,
            'multi_ip_same_inbound': False,
            'pattern_type': 'unknown',
            'details': []
        }
        
        if not self.ip_to_inbounds:
            return analysis
        
        # Check if any IP uses multiple inbounds
        for ip, inbounds in self.ip_to_inbounds.items():
            if len(inbounds) > 1:
                analysis['same_ip_multi_inbound'] = True
                analysis['details'].append(f"IP {ip} uses {len(inbounds)} inbounds: {inbounds}")
        
        # Check if multiple IPs use the same inbound
        inbound_to_ips = {}
        for ip, inbounds in self.ip_to_inbounds.items():
            for inbound in inbounds:
                if inbound not in inbound_to_ips:
                    inbound_to_ips[inbound] = set()
                inbound_to_ips[inbound].add(ip)
        
        for inbound, ips in inbound_to_ips.items():
            if len(ips) > 1:
                analysis['multi_ip_same_inbound'] = True
                analysis['details'].append(f"Inbound '{inbound}' used by {len(ips)} IPs")
        
        # Determine pattern type
        if analysis['same_ip_multi_inbound'] and not analysis['multi_ip_same_inbound']:
            # Same IP switches between inbounds = likely 1 device
            analysis['pattern_type'] = 'single_device_switching'
        elif analysis['multi_ip_same_inbound'] and not analysis['same_ip_multi_inbound']:
            # Multiple IPs on same inbound = likely multi-device
            analysis['pattern_type'] = 'multi_device'
        elif analysis['same_ip_multi_inbound'] and analysis['multi_ip_same_inbound']:
            # Mixed pattern
            analysis['pattern_type'] = 'mixed'
        
        return analysis
    
    def detect_isp_change_pattern(self) -> str:
        """
        Detect ISP change patterns to identify SIM card swap vs multi-device.
        
        Returns:
            str: "sim_swap" (likely 1 user changing cellular) or 
                 "multi_device" (likely multiple devices) or
                 "single_isp" (single ISP, normal usage) or
                 "unknown"
        """
        if len(self.isp_names) <= 1:
            return "single_isp"
        
        # If multiple ISPs but IPs appear sequentially (not simultaneously), likely SIM swap
        # For now, we use a heuristic: if 2 ISPs and both are cellular-like, likely SIM swap
        
        # Check subnet patterns - if different subnets but same number of IPs, more likely SIM swap
        if len(self.ip_subnets) == len(self.ips) and len(self.isp_names) <= 2:
            # Each IP is in its own subnet, and only 1-2 ISPs
            # This could be SIM swap or multi-device
            
            # If we have connection details, check if IPs were used at different times
            if self.connection_details:
                # Check for overlapping usage patterns
                # For now, assume if only 2 IPs and 2 different ISPs, it's likely SIM swap
                if len(self.ips) == 2 and len(self.isp_names) == 2:
                    return "sim_swap"
            
            return "possible_sim_swap"
        
        # Multiple IPs in same subnet with same ISP = more likely multi-device
        if len(self.ip_subnets) < len(self.ips):
            return "multi_device"
        
        return "unknown"
    
    def calculate_trust_score(self) -> float:
        """
        Calculate trust score based on multiple behavioral factors.
        Score ranges from -100 (very suspicious/multi-device) to 100 (trustworthy/single device)
        
        Key Factors:
        1. IP-Inbound Pattern Analysis:
           - Same IP using multiple inbounds: +20 (likely single device switching protocols)
           - Multiple IPs on same inbound: -30 (likely multiple devices)
           - Different IPs with different inbounds: -25 per pair (strongly suggests multi-device)
        
        2. ISP/Network Pattern:
           - Single ISP with multiple subnets: -15 per extra subnet
           - Multiple ISPs: -10 if sequential (possible SIM swap), -25 if simultaneous
        
        3. Warning History (only counts actual disables, not monitoring starts):
           - Disabled in last 12h: -20 per disable
           - Disabled in last 24h (beyond 12h): -10 per disable
        
        4. IP Count Severity:
           - Excess IPs beyond limit: -10 per extra IP
        
        Base score: 50 (neutral)
        
        Returns:
            float: Trust score (-100 to 100)
        """
        score = 50.0  # Neutral starting point
        ip_count = len(self.ips)
        
        # === Factor 1: IP-Inbound Pattern Analysis ===
        ip_pattern = self.analyze_ip_inbound_pattern()
        
        # Bonus: Same IP using multiple inbounds (strong indicator of single device)
        if ip_pattern['same_ip_multi_inbound']:
            score += 20
            logger.debug(f"Trust [{self.username}]: +20 (same IP, multiple inbounds)")
        
        # Penalty: Multiple IPs on same inbound (strong indicator of multiple devices)
        if ip_pattern['multi_ip_same_inbound']:
            score -= 30
            logger.debug(f"Trust [{self.username}]: -30 (multiple IPs, same inbound)")
        
        # Heavy penalty: Different IPs with different inbounds (very likely multi-device)
        inbound_count = len(self.inbound_protocols)
        if inbound_count > 1 and ip_count > 1 and not ip_pattern['same_ip_multi_inbound']:
            penalty = min(inbound_count, ip_count) * 15
            score -= penalty
            logger.debug(f"Trust [{self.username}]: -{penalty} ({inbound_count} inbounds, {ip_count} IPs)")
        
        # === Factor 2: ISP/Network Pattern ===
        isp_pattern = self.detect_isp_change_pattern()
        self.isp_change_pattern = isp_pattern
        
        subnet_count = len(self.ip_subnets)
        isp_count = len(self.isp_names)
        
        # Same ISP but different subnets (moderately suspicious)
        if subnet_count > 1 and isp_count == 1:
            penalty = (subnet_count - 1) * 15
            score -= penalty
            logger.debug(f"Trust [{self.username}]: -{penalty} ({subnet_count} subnets, same ISP)")
        
        # Multiple ISPs pattern
        if isp_pattern in ("sim_swap", "possible_sim_swap"):
            score -= 8  # Light penalty for possible SIM swap
            logger.debug(f"Trust [{self.username}]: -8 (possible SIM swap)")
        elif isp_pattern == "multi_device":
            score -= 25  # Heavy penalty for clear multi-device pattern
            logger.debug(f"Trust [{self.username}]: -25 (multi-device ISP pattern)")
        
        # === Factor 3: Warning History (repeat offender detection) ===
        # Only counts actual disables (not monitoring starts)
        # -20 for disables in last 12 hours
        if self.previous_warnings_12h > 0:
            penalty = self.previous_warnings_12h * 20
            score -= penalty
            logger.debug(f"Trust [{self.username}]: -{penalty} ({self.previous_warnings_12h} disables in 12h)")
        
        # Additional warnings in 24h window (beyond 12h warnings)
        additional_24h = max(0, self.previous_warnings_24h - self.previous_warnings_12h)
        if additional_24h > 0:
            penalty = additional_24h * 10
            score -= penalty
            logger.debug(f"Trust [{self.username}]: -{penalty} ({additional_24h} disables in 24h)")
        
        # === Factor 4: IP Count Severity ===
        # More IPs = more suspicious (basic heuristic)
        if ip_count > 2:
            penalty = (ip_count - 2) * 10
            score -= penalty
            logger.debug(f"Trust [{self.username}]: -{penalty} ({ip_count} IPs, excess penalty)")
        
        # Clamp score between -100 and 100
        score = max(-100.0, min(100.0, score))
        
        logger.info(f"Trust score for {self.username}: {score:.0f}")
        return score
    
    def get_trust_level(self) -> str:
        """
        Get human-readable trust level based on score.
        
        Returns:
            str: Trust level description with emoji indicator
        """
        if self.trust_score >= 40:
            return "🟢 TRUSTED"  # Likely single device
        elif self.trust_score >= 20:
            return "🟢 HIGH"  # Probably legitimate
        elif self.trust_score >= 0:
            return "🟡 MEDIUM"  # Neutral/uncertain
        elif self.trust_score >= -25:
            return "🟠 LOW"  # Suspicious behavior
        elif self.trust_score >= -50:
            return "🔴 SUSPICIOUS"  # Likely multi-device
        else:
            return "🔴 CRITICAL"  # Definite multi-device abuse
    
    def get_behavior_summary(self) -> str:
        """
        Get a human-readable summary of detected behavior patterns.
        
        Returns:
            str: Behavior summary
        """
        patterns = []
        
        ip_pattern = self.analyze_ip_inbound_pattern()
        if ip_pattern['pattern_type'] == 'single_device_switching':
            patterns.append("📱 Single device switching protocols")
        elif ip_pattern['pattern_type'] == 'multi_device':
            patterns.append("📲📲 Multiple devices detected")
        elif ip_pattern['pattern_type'] == 'mixed':
            patterns.append("🔀 Mixed device pattern")
        
        if self.isp_change_pattern == "sim_swap" or self.isp_change_pattern == "possible_sim_swap":
            patterns.append("📶 Possible SIM card change")
        elif self.isp_change_pattern == "multi_device":
            patterns.append("🌐 Multiple ISPs (different locations)")
        
        if self.previous_warnings_12h > 0:
            patterns.append(f"⚠️ {self.previous_warnings_12h} disables in 12h")
        elif self.previous_warnings_24h > 0:
            patterns.append(f"⚠️ {self.previous_warnings_24h} disables in 24h")
        
        return " | ".join(patterns) if patterns else "No specific pattern detected"


class EnhancedWarningSystem:
    """
    Enhanced warning system that monitors users for 3 minutes after warning.
    Counts IPs as devices only if active for 2+ minutes during monitoring.
    Instantly disables users with very low trust scores (skip monitoring).
    """
    
    # Trust score threshold for instant disable (skip monitoring)
    INSTANT_DISABLE_THRESHOLD = -60
    # Minimum duration (seconds) for an IP to count as a device
    MIN_DEVICE_DURATION = 120  # 2 minutes
    
    def __init__(self, filename=".user_warnings.json", history_filename=".warning_history.json"):
        self.filename = filename
        self.history_filename = history_filename
        self.warnings: Dict[str, UserWarning] = {}
        self.warning_history: Dict[str, list] = {}  # Username -> list of timestamps
        self.monitoring_period = 180  # 3 minutes in seconds
        self.load_warnings()
        self.load_warning_history()
    
    def load_warning_history(self):
        """Load warning history from file"""
        try:
            if os.path.exists(self.history_filename):
                with open(self.history_filename, "r", encoding="utf-8") as file:
                    self.warning_history = json.load(file)
                    # Keep warnings up to 12 hours for trust score calculation
                    self.cleanup_old_warning_history()
        except Exception as e:
            logger.error(f"Error loading warning history: {e}")
            self.warning_history = {}
    
    async def save_warning_history(self):
        """Save warning history to file"""
        try:
            with open(self.history_filename, "w", encoding="utf-8") as file:
                json.dump(self.warning_history, file, indent=2)
        except Exception as e:
            logger.error(f"Error saving warning history: {e}")
    
    def cleanup_old_warning_history(self):
        """Remove warnings older than 24 hours from history"""
        current_time = time.time()
        twenty_four_hours_ago = current_time - (24 * 60 * 60)
        
        for username in list(self.warning_history.keys()):
            # Filter out old warnings (keep 24 hours)
            self.warning_history[username] = [
                ts for ts in self.warning_history[username] 
                if ts > twenty_four_hours_ago
            ]
            # Remove user if no recent warnings
            if not self.warning_history[username]:
                del self.warning_history[username]
    
    def count_recent_warnings(self, username: str, hours: int = 12) -> int:
        """Count disables for user in last X hours"""
        current_time = time.time()
        cutoff_time = current_time - (hours * 60 * 60)
        warnings = self.warning_history.get(username, [])
        return len([ts for ts in warnings if ts > cutoff_time])
    
    async def add_to_warning_history(self, username: str):
        """Add current warning to history"""
        current_time = time.time()
        if username not in self.warning_history:
            self.warning_history[username] = []
        self.warning_history[username].append(current_time)
        await self.save_warning_history()
    
    def load_warnings(self):
        """Load warnings from file"""
        try:
            if os.path.exists(self.filename):
                with open(self.filename, "r", encoding="utf-8") as file:
                    data = json.load(file)
                    for username, warning_data in data.items():
                        # Convert monitoring_history back to the expected format
                        monitoring_history = []
                        if 'monitoring_history' in warning_data:
                            for snapshot in warning_data['monitoring_history']:
                                monitoring_history.append({
                                    'timestamp': snapshot['timestamp'],
                                    'ips': set(snapshot['ips']),
                                    'ip_count': snapshot['ip_count']
                                })
                        
                        # Load ip_to_inbounds
                        ip_to_inbounds = {}
                        if 'ip_to_inbounds' in warning_data:
                            for ip, inbounds in warning_data['ip_to_inbounds'].items():
                                ip_to_inbounds[ip] = set(inbounds)
                        
                        # Load IP activity tracking
                        ip_first_seen = warning_data.get("ip_first_seen", {})
                        ip_last_seen = warning_data.get("ip_last_seen", {})
                        ip_seen_count = warning_data.get("ip_seen_count", {})
                        
                        warning = UserWarning(
                            username=warning_data["username"],
                            ip_count=warning_data["ip_count"],
                            ips=set(warning_data["ips"]),
                            warning_time=warning_data["warning_time"],
                            monitoring_end_time=warning_data["monitoring_end_time"],
                            warned=warning_data.get("warned", False),
                            ip_first_seen=ip_first_seen,
                            ip_last_seen=ip_last_seen,
                            ip_seen_count=ip_seen_count,
                            trust_score=warning_data.get("trust_score", 0.0),
                            inbound_protocols=set(warning_data.get("inbound_protocols", [])),
                            isp_names=set(warning_data.get("isp_names", [])),
                            ip_subnets=set(warning_data.get("ip_subnets", [])),
                            previous_warnings_12h=warning_data.get("previous_warnings_12h", 0),
                            previous_warnings_24h=warning_data.get("previous_warnings_24h", 0),
                            ip_to_inbounds=ip_to_inbounds,
                            same_ip_multiple_inbounds=warning_data.get("same_ip_multiple_inbounds", False),
                            isp_change_pattern=warning_data.get("isp_change_pattern"),
                            connection_details=warning_data.get("connection_details", [])
                        )
                        warning.monitoring_history = monitoring_history
                        self.warnings[username] = warning
        except Exception as e:
            logger.error(f"Error loading warnings: {e}")
    
    async def save_warnings(self):
        """Save warnings to file"""
        try:
            data = {}
            for username, warning in self.warnings.items():
                # Convert monitoring_history to serializable format
                monitoring_history_serializable = []
                for snapshot in warning.monitoring_history:
                    monitoring_history_serializable.append({
                        'timestamp': snapshot['timestamp'],
                        'ips': list(snapshot['ips']),
                        'ip_count': snapshot['ip_count']
                    })
                
                # Convert ip_to_inbounds to serializable format
                ip_to_inbounds_serializable = {}
                if warning.ip_to_inbounds:
                    for ip, inbounds in warning.ip_to_inbounds.items():
                        ip_to_inbounds_serializable[ip] = list(inbounds)
                
                data[username] = {
                    "username": warning.username,
                    "ip_count": warning.ip_count,
                    "ips": list(warning.ips),
                    "warning_time": warning.warning_time,
                    "monitoring_end_time": warning.monitoring_end_time,
                    "warned": warning.warned,
                    "monitoring_history": monitoring_history_serializable,
                    "ip_first_seen": warning.ip_first_seen,
                    "ip_last_seen": warning.ip_last_seen,
                    "ip_seen_count": warning.ip_seen_count,
                    "trust_score": warning.trust_score,
                    "inbound_protocols": list(warning.inbound_protocols),
                    "isp_names": list(warning.isp_names),
                    "ip_subnets": list(warning.ip_subnets),
                    "previous_warnings_12h": warning.previous_warnings_12h,
                    "previous_warnings_24h": warning.previous_warnings_24h,
                    "ip_to_inbounds": ip_to_inbounds_serializable,
                    "same_ip_multiple_inbounds": warning.same_ip_multiple_inbounds,
                    "isp_change_pattern": warning.isp_change_pattern,
                    "connection_details": warning.connection_details
                }
            
            with open(self.filename, "w", encoding="utf-8") as file:
                json.dump(data, file, indent=2)
                
        except Exception as e:
            logger.error(f"Error saving warnings: {e}")
    
    async def add_warning(self, username: str, ip_count: int, ips: Set[str], user_limit: int = None, 
                         user_data: 'UserType' = None, isp_info: dict = None,
                         panel_data: 'PanelType' = None) -> str:
        """
        Add a warning for a user with trust score calculation.
        May instantly disable user if trust score is very low.
        
        Args:
            username (str): Username
            ip_count (int): Number of active IPs
            ips (Set[str]): Set of IP addresses
            user_limit (int): User's specific limit (optional)
            user_data (UserType): User data with device info (optional)
            isp_info (dict): ISP information for IPs (optional)
            panel_data (PanelType): Panel data for instant disable (optional)
            
        Returns:
            str: "new" if new warning, "updated" if existing, "instant_disabled" if instantly disabled
        """
        current_time = time.time()
        
        if username in self.warnings:
            # User is already being monitored
            warning = self.warnings[username]
            if warning.is_monitoring_active():
                # Update IP count and IPs
                warning.ip_count = ip_count
                warning.ips = ips
                
                # Update IP activity tracking
                warning.update_ip_activity(ips, current_time)
                
                # Update trust score factors if new data provided
                if user_data and user_data.device_info:
                    warning.inbound_protocols = user_data.device_info.inbound_protocols
                    # Update ip_to_inbounds mapping
                    warning.ip_to_inbounds = self._extract_ip_to_inbounds(user_data)
                if isp_info:
                    warning.isp_names = set(info.get('isp', 'Unknown') for info in isp_info.values())
                    warning.ip_subnets = self._extract_subnets(ips)
                
                # Recalculate trust score
                warning.trust_score = warning.calculate_trust_score()
                
                await self.save_warnings()
                return "updated"
            else:
                # Previous monitoring period expired, create new warning
                del self.warnings[username]
        
        # Count recent disables in last 12 hours and 24 hours
        previous_warnings_12h = self.count_recent_warnings(username, hours=12)
        previous_warnings_24h = self.count_recent_warnings(username, hours=24)
        
        # Extract trust score factors
        inbound_protocols = set()
        isp_names = set()
        ip_subnets = self._extract_subnets(ips)
        ip_to_inbounds = {}
        connection_details = []
        
        if user_data and user_data.device_info:
            inbound_protocols = user_data.device_info.inbound_protocols
            ip_to_inbounds = self._extract_ip_to_inbounds(user_data)
            # Store connection details for analysis
            for conn in user_data.device_info.connections:
                connection_details.append({
                    'ip': conn.ip,
                    'node_id': conn.node_id,
                    'node_name': conn.node_name,
                    'inbound_protocol': conn.inbound_protocol,
                    'last_seen': conn.last_seen
                })
        
        if isp_info:
            isp_names = set(info.get('isp', 'Unknown') for info in isp_info.values())
        
        # Check for same IP using multiple inbounds
        same_ip_multiple_inbounds = any(len(inbounds) > 1 for inbounds in ip_to_inbounds.values())
        
        # Create new warning (temporarily to calculate trust score)
        warning = UserWarning(
            username=username,
            ip_count=ip_count,
            ips=ips,
            warning_time=current_time,
            monitoring_end_time=current_time + self.monitoring_period,
            warned=True,
            inbound_protocols=inbound_protocols,
            isp_names=isp_names,
            ip_subnets=ip_subnets,
            previous_warnings_12h=previous_warnings_12h,
            previous_warnings_24h=previous_warnings_24h,
            ip_to_inbounds=ip_to_inbounds,
            same_ip_multiple_inbounds=same_ip_multiple_inbounds,
            connection_details=connection_details
        )
        
        # Calculate trust score (this will also set isp_change_pattern)
        warning.trust_score = warning.calculate_trust_score()
        trust_level = warning.get_trust_level()
        behavior_summary = warning.get_behavior_summary()
        
        # ═══════════════════════════════════════════════════════════════
        # INSTANT DISABLE: If trust score is very low, skip monitoring
        # ═══════════════════════════════════════════════════════════════
        if warning.trust_score <= self.INSTANT_DISABLE_THRESHOLD and panel_data:
            time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            limit_text = f"User limit: <code>{user_limit}</code>\n" if user_limit else ""
            
            # Add to warning history before disabling
            await self.add_to_warning_history(username)
            
            try:
                await safe_disable_user(panel_data, UserType(name=username, ip=[]))
                
                await safe_send_disable_notification(
                    f"🚫 <b>INSTANT DISABLE</b> - {time_str}\n\n"
                    f"User: <code>{username}</code>\n"
                    f"Active IPs: <code>{ip_count}</code>\n"
                    f"{limit_text}"
                    f"Trust Level: {trust_level} (<code>{warning.trust_score:.0f}</code>)\n"
                    f"Behavior: <code>{behavior_summary}</code>\n\n"
                    f"⚡ <b>Monitoring skipped</b> - Trust score too low (≤{self.INSTANT_DISABLE_THRESHOLD})\n"
                    f"User disabled immediately due to clear multi-device abuse.",
                    username
                )
                
                logger.warning(f"INSTANT DISABLE: User {username} disabled immediately (trust: {warning.trust_score:.0f})")
                return "instant_disabled"
                
            except Exception as e:
                logger.error(f"Failed to instant disable user {username}: {e}")
                # Fall through to normal warning if disable fails
        
        # ═══════════════════════════════════════════════════════════════
        # NORMAL WARNING: Start 3-minute monitoring period
        # Note: We do NOT add to warning history here - only when actually disabled
        # This way, users who are found "not guilty" won't have their trust score reduced
        # ═══════════════════════════════════════════════════════════════
        
        # Initialize IP activity tracking with current IPs
        warning.update_ip_activity(ips, current_time)
        
        self.warnings[username] = warning
        await self.save_warnings()
        
        # Build trust factor details
        trust_details = []
        if same_ip_multiple_inbounds:
            trust_details.append(f"📱 Same IP uses multiple inbounds (likely 1 device)")
        elif len(inbound_protocols) > 1:
            trust_details.append(f"🔴 {len(inbound_protocols)} different inbounds with different IPs")
        
        if warning.isp_change_pattern == "sim_swap" or warning.isp_change_pattern == "possible_sim_swap":
            trust_details.append(f"📶 Possible SIM card change detected")
        elif warning.isp_change_pattern == "multi_device":
            trust_details.append(f"📲 Multi-device ISP pattern")
        
        if len(ip_subnets) > 1 and len(isp_names) == 1:
            trust_details.append(f"🟠 {len(ip_subnets)} subnets, same ISP")
        
        if previous_warnings_12h > 0:
            trust_details.append(f"⚠️ {previous_warnings_12h} disables in last 12h")
        elif previous_warnings_24h > 0:
            trust_details.append(f"⚠️ {previous_warnings_24h} disables in last 24h")
        
        trust_info = "\n".join([f"  • {detail}" for detail in trust_details]) if trust_details else "  • No suspicious patterns"
        
        time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        limit_text = f"User limit: <code>{user_limit}</code>\n" if user_limit else ""
        
        await safe_send_logs(
            f"⚠️ <b>WARNING</b> - {time_str}\n\n"
            f"User: <code>{username}</code>\n"
            f"Active IPs: <code>{ip_count}</code>\n"
            f"{limit_text}"
            f"Trust Level: {trust_level} (<code>{warning.trust_score:.0f}</code>)\n"
            f"Behavior: <code>{behavior_summary}</code>\n"
            f"Trust Factors:\n{trust_info}\n\n"
            f"📡 Monitoring for: <code>3 minutes</code>\n"
            f"IPs active for 2+ min will be counted as devices.\n"
            f"If devices exceed limit after 3 min, user will be disabled."
        )
        
        logger.warning(f"Warning issued for user {username} with {ip_count} active IPs (limit: {user_limit}, trust: {warning.trust_score:.0f})")
        return "new"
    
    def _extract_ip_to_inbounds(self, user_data: 'UserType') -> Dict[str, Set[str]]:
        """Extract IP to inbound protocol mapping from user data"""
        ip_to_inbounds = {}
        if user_data and user_data.device_info and user_data.device_info.connections:
            for conn in user_data.device_info.connections:
                ip = conn.ip
                if ip not in ip_to_inbounds:
                    ip_to_inbounds[ip] = set()
                ip_to_inbounds[ip].add(conn.inbound_protocol)
        return ip_to_inbounds
    
    def _extract_subnets(self, ips: Set[str]) -> Set[str]:
        """Extract /24 subnets from IP addresses"""
        subnets = set()
        for ip in ips:
            try:
                import ipaddress
                ip_obj = ipaddress.ip_address(ip)
                if ip_obj.version == 4:
                    network = ipaddress.ip_network(f"{ip}/24", strict=False)
                    subnet_base = str(network.network_address).rsplit('.', 1)[0]
                    subnets.add(f"{subnet_base}.x")
                else:
                    subnets.add(ip)  # IPv6 - use full IP
            except ValueError:
                subnets.add(ip)
        return subnets
    
    async def check_persistent_violations(self, panel_data: PanelType, all_users_actual_ips: Dict[str, Set[str]], config_data: dict) -> Set[str]:
        """
        Check for users who still violate limits after 3-minute warning period.
        Uses device counting: only IPs active for 2+ minutes count as devices.
        
        Args:
            panel_data (PanelType): Panel data
            all_users_actual_ips (Dict[str, Set[str]]): Current users and their actual unique IPs
            config_data (dict): Configuration data with limits
            
        Returns:
            Set[str]: Set of users who were disabled
        """
        disabled_users = set()
        users_to_remove = []
        
        # Use new config format
        limits_config = config_data.get("limits", {})
        special_limit = limits_config.get("special", {})
        limit_number = limits_config.get("general", 2)
        
        for username, warning in self.warnings.items():
            if not warning.is_monitoring_active():
                # Cancel monitoring task if still running
                if warning.active_monitoring_task and not warning.active_monitoring_task.done():
                    warning.active_monitoring_task.cancel()
                
                # Monitoring period expired - time to make decision
                user_limit_number = int(special_limit.get(username, limit_number))
                trust_score = warning.trust_score
                trust_level = warning.get_trust_level()
                
                if username in all_users_actual_ips:
                    current_ips = all_users_actual_ips[username]
                    
                    # ═══════════════════════════════════════════════════════════════
                    # DEVICE COUNTING: Only count IPs active for 2+ minutes as devices
                    # ═══════════════════════════════════════════════════════════════
                    persistent_devices = warning.get_persistent_devices(self.MIN_DEVICE_DURATION)
                    device_count = len(persistent_devices)
                    
                    # Also count current IPs that match persistent ones
                    current_persistent = current_ips.intersection(persistent_devices)
                    
                    # Get activity summary for logging
                    activity_summary = warning.get_ip_activity_summary()
                    
                    time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    # Check if DEVICE count exceeds limit (not just IP count)
                    if device_count > user_limit_number:
                        # User has more persistent devices than allowed - DISABLE
                        try:
                            await safe_disable_user(panel_data, UserType(name=username, ip=[]))
                            disabled_users.add(username)
                            
                            # Add to warning history ONLY when user is actually disabled
                            # This ensures users who are monitored but found "not guilty" don't get penalized
                            await self.add_to_warning_history(username)
                            
                            await safe_send_disable_notification(
                                f"🚫 <b>USER DISABLED</b> - {time_str}\n\n"
                                f"User: <code>{username}</code>\n"
                                f"Confirmed Devices: <code>{device_count}</code> (active 2+ min)\n"
                                f"Current IPs: <code>{len(current_ips)}</code>\n"
                                f"User limit: <code>{user_limit_number}</code>\n"
                                f"Trust Level: {trust_level} (<code>{trust_score:.0f}</code>)\n\n"
                                f"📊 IP Activity:\n<code>{activity_summary}</code>\n\n"
                                f"User exceeded device limit after 3-minute monitoring.",
                                username
                            )
                            
                            logger.warning(f"Disabled user {username}: {device_count} devices (limit: {user_limit_number})")
                            
                        except Exception as e:
                            logger.error(f"Failed to disable user {username}: {e}")
                            await safe_send_logs(f"❌ <b>Error:</b> Failed to disable user {username}: {e}")
                    
                    elif len(current_ips) > user_limit_number and device_count <= user_limit_number:
                        # Has many IPs but not enough persistent devices - NO ACTION
                        # This means IPs are temporary/changing
                        logger.info(f"User {username}: {len(current_ips)} IPs but only {device_count} devices - no action")
                        await safe_send_logs(
                            f"✅ <b>MONITORING ENDED - NO ACTION</b> - {time_str}\n\n"
                            f"User: <code>{username}</code>\n"
                            f"Current IPs: <code>{len(current_ips)}</code>\n"
                            f"Confirmed Devices: <code>{device_count}</code> (active 2+ min)\n"
                            f"User limit: <code>{user_limit_number}</code>\n"
                            f"Trust Level: {trust_level} (<code>{trust_score:.0f}</code>)\n\n"
                            f"📊 IP Activity:\n<code>{activity_summary}</code>\n\n"
                            f"IPs were temporary - not enough persistent devices to violate."
                        )
                    
                    else:
                        # User is now within limits
                        logger.info(f"User {username} is now within limits ({device_count} devices, limit: {user_limit_number})")
                        await safe_send_logs(
                            f"✅ <b>MONITORING ENDED</b> - {time_str}\n\n"
                            f"User: <code>{username}</code>\n"
                            f"Confirmed Devices: <code>{device_count}</code>\n"
                            f"User limit: <code>{user_limit_number}</code>\n\n"
                            f"User is now compliant with device limits."
                        )
                else:
                    # User not found in current logs
                    logger.info(f"User {username} not found in current logs - monitoring ended")
                    await safe_send_logs(
                        f"ℹ️ <b>MONITORING ENDED</b> - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                        f"User: <code>{username}</code>\n"
                        f"Reason: <code>User not found in current logs</code>\n\n"
                        f"User is no longer active."
                    )
                
                users_to_remove.append(username)
        
        # Remove expired warnings
        for username in users_to_remove:
            del self.warnings[username]
        
        if users_to_remove:
            await self.save_warnings()
        
        return disabled_users
    
    async def send_monitoring_status(self):
        """Send status of currently monitored users"""
        if not self.warnings:
            return
        
        active_warnings = []
        for username, warning in self.warnings.items():
            if warning.is_monitoring_active():
                remaining = warning.time_remaining()
                minutes = remaining // 60
                seconds = remaining % 60
                active_warnings.append(
                    f"• <code>{username}</code> - {minutes}m {seconds}s remaining"
                )
        
        if active_warnings:
            message = "🔍 <b>Currently Monitoring Users:</b>\n\n" + "\n".join(active_warnings)
            await safe_send_logs(message)
    
    def get_monitoring_users(self) -> Set[str]:
        """Get set of users currently being monitored"""
        return {username for username, warning in self.warnings.items() if warning.is_monitoring_active()}
    
    def is_user_being_monitored(self, username: str) -> bool:
        """Check if a user is currently being monitored"""
        return username in self.warnings and self.warnings[username].is_monitoring_active()
    
    async def cleanup_expired_warnings(self):
        """Clean up expired warnings"""
        expired_users = []
        for username, warning in self.warnings.items():
            if not warning.is_monitoring_active():
                expired_users.append(username)
        
        for username in expired_users:
            del self.warnings[username]
        
        if expired_users:
            await self.save_warnings()
            logger.info(f"Cleaned up {len(expired_users)} expired warnings")
    
    async def start_monitoring_task(self, username: str, panel_data: PanelType):
        """
        Start a background monitoring task for a user.
        Currently disabled to prevent circular import issues.
        The core functionality still works through periodic checks.
        
        Args:
            username: The username to monitor
            panel_data: Panel data for API calls
        """
        # Monitoring task is disabled - using periodic checks instead
        logger.debug(f"Monitoring for {username} handled through periodic checks")
        return

    async def generate_monitoring_summary(self) -> Optional[str]:
        """
        Generate a concise monitoring summary for users being monitored.
        Returns a formatted message or None if no monitoring is active.
        """
        if not self.warnings:
            return None
        
        active_warnings = {
            user: warning for user, warning in self.warnings.items() 
            if warning.is_monitoring_active()
        }
        
        if not active_warnings:
            return None
        
        summary_lines = ["📊 <b>Active Monitoring (3 min)</b>", "─" * 25]
        
        for user, warning in active_warnings.items():
            time_left = warning.time_remaining()
            minutes = time_left // 60
            seconds = time_left % 60
            trust_level = warning.get_trust_level()
            
            # Get confirmed devices (IPs active for 2+ min)
            confirmed_devices = warning.get_device_count(self.MIN_DEVICE_DURATION)
            
            summary_lines.append(
                f"👤 <code>{user}</code>\n"
                f"   ⏱ {minutes}m{seconds}s | 📍 {warning.ip_count} IPs | 📱 {confirmed_devices} devices\n"
                f"   {trust_level}"
            )
        
        summary_lines.append(f"\n📈 Total: {len(active_warnings)} users monitored")
        
        return "\n".join(summary_lines)

# Global instance to be imported by other modules
warning_system = EnhancedWarningSystem()
