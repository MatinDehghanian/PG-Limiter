"""
UserWarning dataclass for tracking user warnings and behavior analysis.
"""

import time
from typing import Dict, Optional, Set
from dataclasses import dataclass

from utils.logs import logger


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
    active_monitoring_task: Optional[object] = None
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
            if ip not in self.ip_first_seen:
                self.ip_first_seen[ip] = timestamp
            self.ip_last_seen[ip] = timestamp
            self.ip_seen_count[ip] = self.ip_seen_count.get(ip, 0) + 1
        
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
            last_seen = self.ip_last_seen.get(ip, 0)
            if current_time - last_seen > 120:
                continue
            
            duration = self.get_ip_active_duration(ip)
            seen_count = self.ip_seen_count.get(ip, 0)
            
            if duration >= min_duration_seconds or seen_count >= 2:
                persistent_ips.add(ip)
        
        return persistent_ips
    
    def get_device_count(self, min_duration_seconds: int = 120) -> int:
        """Get the count of confirmed devices (IPs active for min duration)."""
        return len(self.get_persistent_devices(min_duration_seconds))
    
    def get_ip_activity_summary(self) -> str:
        """Get a summary of IP activity for debugging/display."""
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
            dict with analysis results
        """
        analysis = {
            'same_ip_multi_inbound': False,
            'multi_ip_same_inbound': False,
            'pattern_type': 'unknown',
            'details': []
        }
        
        if not self.ip_to_inbounds:
            return analysis
        
        for ip, inbounds in self.ip_to_inbounds.items():
            if len(inbounds) > 1:
                analysis['same_ip_multi_inbound'] = True
                analysis['details'].append(f"IP {ip} uses {len(inbounds)} inbounds: {inbounds}")
        
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
        
        if analysis['same_ip_multi_inbound'] and not analysis['multi_ip_same_inbound']:
            analysis['pattern_type'] = 'single_device_switching'
        elif analysis['multi_ip_same_inbound'] and not analysis['same_ip_multi_inbound']:
            analysis['pattern_type'] = 'multi_device'
        elif analysis['same_ip_multi_inbound'] and analysis['multi_ip_same_inbound']:
            analysis['pattern_type'] = 'mixed'
        
        return analysis
    
    def detect_isp_change_pattern(self) -> str:
        """
        Detect ISP change patterns to identify SIM card swap vs multi-device.
        
        Returns:
            str: "sim_swap", "multi_device", "single_isp", or "unknown"
        """
        if len(self.isp_names) <= 1:
            return "single_isp"
        
        if len(self.ip_subnets) == len(self.ips) and len(self.isp_names) <= 2:
            if self.connection_details:
                if len(self.ips) == 2 and len(self.isp_names) == 2:
                    return "sim_swap"
            return "possible_sim_swap"
        
        if len(self.ip_subnets) < len(self.ips):
            return "multi_device"
        
        return "unknown"
    
    def calculate_trust_score(self) -> float:
        """
        Calculate trust score based on multiple behavioral factors.
        Score ranges from -100 (very suspicious/multi-device) to 100 (trustworthy/single device)
        
        Returns:
            float: Trust score (-100 to 100)
        """
        score = 50.0
        ip_count = len(self.ips)
        
        # Factor 1: IP-Inbound Pattern Analysis
        ip_pattern = self.analyze_ip_inbound_pattern()
        
        if ip_pattern['same_ip_multi_inbound']:
            score += 20
            logger.debug(f"Trust [{self.username}]: +20 (same IP, multiple inbounds)")
        
        if ip_pattern['multi_ip_same_inbound']:
            score -= 30
            logger.debug(f"Trust [{self.username}]: -30 (multiple IPs, same inbound)")
        
        inbound_count = len(self.inbound_protocols)
        if inbound_count > 1 and ip_count > 1 and not ip_pattern['same_ip_multi_inbound']:
            penalty = min(inbound_count, ip_count) * 15
            score -= penalty
            logger.debug(f"Trust [{self.username}]: -{penalty} ({inbound_count} inbounds, {ip_count} IPs)")
        
        # Factor 2: ISP/Network Pattern
        isp_pattern = self.detect_isp_change_pattern()
        self.isp_change_pattern = isp_pattern
        
        subnet_count = len(self.ip_subnets)
        isp_count = len(self.isp_names)
        
        if subnet_count > 1 and isp_count == 1:
            penalty = (subnet_count - 1) * 15
            score -= penalty
            logger.debug(f"Trust [{self.username}]: -{penalty} ({subnet_count} subnets, same ISP)")
        
        if isp_pattern in ("sim_swap", "possible_sim_swap"):
            score -= 8
            logger.debug(f"Trust [{self.username}]: -8 (possible SIM swap)")
        elif isp_pattern == "multi_device":
            score -= 25
            logger.debug(f"Trust [{self.username}]: -25 (multi-device ISP pattern)")
        
        # Factor 3: Warning History
        if self.previous_warnings_12h > 0:
            penalty = self.previous_warnings_12h * 20
            score -= penalty
            logger.debug(f"Trust [{self.username}]: -{penalty} ({self.previous_warnings_12h} disables in 12h)")
        
        additional_24h = max(0, self.previous_warnings_24h - self.previous_warnings_12h)
        if additional_24h > 0:
            penalty = additional_24h * 10
            score -= penalty
            logger.debug(f"Trust [{self.username}]: -{penalty} ({additional_24h} disables in 24h)")
        
        # Factor 4: IP Count Severity
        if ip_count > 2:
            penalty = (ip_count - 2) * 10
            score -= penalty
            logger.debug(f"Trust [{self.username}]: -{penalty} ({ip_count} IPs, excess penalty)")
        
        score = max(-100.0, min(100.0, score))
        logger.info(f"Trust score for {self.username}: {score:.0f}")
        return score
    
    def get_trust_level(self) -> str:
        """Get human-readable trust level based on score."""
        if self.trust_score >= 40:
            return "🟢 TRUSTED"
        elif self.trust_score >= 20:
            return "🟢 HIGH"
        elif self.trust_score >= 0:
            return "🟡 MEDIUM"
        elif self.trust_score >= -25:
            return "🟠 LOW"
        elif self.trust_score >= -50:
            return "🔴 SUSPICIOUS"
        else:
            return "🔴 CRITICAL"
    
    def get_behavior_summary(self) -> str:
        """Get a human-readable summary of detected behavior patterns."""
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
