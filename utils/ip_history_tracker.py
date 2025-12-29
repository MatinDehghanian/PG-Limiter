"""
IP History Tracker - Tracks unique IPs per user over time periods
"""

import json
import os
import time
from typing import Dict, Set, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from utils.logs import logger


@dataclass
class IPHistoryEntry:
    """Single IP history entry"""
    timestamp: float
    ip: str


@dataclass
class UserIPHistory:
    """IP history for a user"""
    username: str
    entries: List[IPHistoryEntry] = field(default_factory=list)
    
    def add_ip(self, ip: str, timestamp: float = None):
        """Add an IP to history"""
        if timestamp is None:
            timestamp = time.time()
        self.entries.append(IPHistoryEntry(timestamp=timestamp, ip=ip))
    
    def get_unique_ips_since(self, hours: int) -> Set[str]:
        """Get unique IPs seen in the last X hours"""
        cutoff_time = time.time() - (hours * 3600)
        return {entry.ip for entry in self.entries if entry.timestamp >= cutoff_time}
    
    def cleanup_old_entries(self, max_hours: int = 48):
        """Remove entries older than max_hours"""
        cutoff_time = time.time() - (max_hours * 3600)
        self.entries = [entry for entry in self.entries if entry.timestamp >= cutoff_time]


class IPHistoryTracker:
    """Tracks IP history for all users"""
    
    def __init__(self, filename=".ip_history.json"):
        self.filename = filename
        self.user_histories: Dict[str, UserIPHistory] = {}
        self.load_history()
    
    def load_history(self):
        """Load IP history from file"""
        try:
            if os.path.exists(self.filename):
                with open(self.filename, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for username, history_data in data.items():
                        user_history = UserIPHistory(username=username)
                        for entry_data in history_data.get("entries", []):
                            user_history.entries.append(
                                IPHistoryEntry(
                                    timestamp=entry_data["timestamp"],
                                    ip=entry_data["ip"]
                                )
                            )
                        self.user_histories[username] = user_history
                logger.info(f"Loaded IP history for {len(self.user_histories)} users")
        except Exception as e:
            logger.error(f"Error loading IP history: {e}")
            self.user_histories = {}
    
    async def save_history(self):
        """Save IP history to file"""
        try:
            data = {}
            for username, user_history in self.user_histories.items():
                data[username] = {
                    "username": username,
                    "entries": [
                        {
                            "timestamp": entry.timestamp,
                            "ip": entry.ip
                        }
                        for entry in user_history.entries
                    ]
                }
            
            with open(self.filename, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving IP history: {e}")
    
    async def record_user_ips(self, username: str, ips: Set[str]):
        """Record IPs for a user at current time"""
        current_time = time.time()
        
        if username not in self.user_histories:
            self.user_histories[username] = UserIPHistory(username=username)
        
        user_history = self.user_histories[username]
        
        # Add each IP
        for ip in ips:
            user_history.add_ip(ip, current_time)
        
        # Cleanup old entries (keep 48 hours)
        user_history.cleanup_old_entries(max_hours=48)
    
    async def get_users_exceeding_limits(self, hours: int, config_data: dict) -> List[Tuple[str, int, int, Set[str]]]:
        """
        Get users who exceeded their limits in the last X hours
        
        Returns:
            List of (username, unique_ip_count, limit, unique_ips)
        """
        results = []
        
        # Use new config format
        limits_config = config_data.get("limits", {})
        except_users = limits_config.get("except_users", [])
        special_limit = limits_config.get("special", {})
        general_limit = limits_config.get("general", 2)
        
        for username, user_history in self.user_histories.items():
            if username in except_users:
                continue
            
            # Get unique IPs in time period
            unique_ips = user_history.get_unique_ips_since(hours)
            ip_count = len(unique_ips)
            
            # Get user's limit
            user_limit = int(special_limit.get(username, general_limit))
            
            # Only include if exceeded limit
            if ip_count > user_limit:
                results.append((username, ip_count, user_limit, unique_ips))
        
        # Sort by IP count descending
        results.sort(key=lambda x: x[1], reverse=True)
        
        return results
    
    async def cleanup_inactive_users(self, active_users: Set[str]):
        """Remove users who are no longer active"""
        # Keep users who have entries in last 48 hours
        cutoff_time = time.time() - (48 * 3600)
        
        users_to_remove = []
        for username, user_history in self.user_histories.items():
            # Check if user has any recent entries
            has_recent = any(entry.timestamp >= cutoff_time for entry in user_history.entries)
            if not has_recent and username not in active_users:
                users_to_remove.append(username)
        
        for username in users_to_remove:
            del self.user_histories[username]
        
        if users_to_remove:
            logger.info(f"Cleaned up {len(users_to_remove)} inactive users from IP history")
    
    async def generate_report(self, hours: int, config_data: dict, isp_detector=None) -> str:
        """
        Generate a formatted report of users exceeding limits
        
        Args:
            hours: Time period (12 or 48)
            config_data: Configuration with limits
            isp_detector: Optional ISP detector for enhanced info
        """
        users_data = await self.get_users_exceeding_limits(hours, config_data)
        
        if not users_data:
            return f"📊 <b>{hours}H IP History Report</b>\n\n✅ No users exceeded their limits in the last {hours} hours."
        
        # Get ISP info if detector available
        isp_info_batch = {}
        if isp_detector:
            all_ips = set()
            for _, _, _, ips in users_data:
                all_ips.update(ips)
            if all_ips:
                isp_info_batch = await isp_detector.get_multiple_isp_info(list(all_ips))
        
        # Build report
        report_lines = [
            f"📊 <b>{hours}H IP History Report</b>",
            f"⏰ Period: Last {hours} hours",
            f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            f"🚫 <b>{len(users_data)} users exceeded limits:</b>",
            ""
        ]
        
        for username, ip_count, limit, unique_ips in users_data:
            report_lines.append(f"👤 <code>{username}</code>")
            report_lines.append(f"   📍 Unique IPs: <b>{ip_count}</b> (Limit: {limit})")
            report_lines.append(f"   ⚠️ Exceeded by: <b>{ip_count - limit}</b> IPs")
            
            # Show IPs with ISP info if available
            if isp_info_batch:
                ip_list = []
                for ip in sorted(unique_ips):
                    if ip in isp_info_batch:
                        isp_info = isp_info_batch[ip]
                        ip_with_isp = f"{ip} ({isp_info.get('isp', 'Unknown')}, {isp_info.get('country', 'Unknown')})"
                        ip_list.append(ip_with_isp)
                    else:
                        ip_list.append(ip)
                
                # Show first 5 IPs, then summarize if more
                if len(ip_list) <= 5:
                    for ip_str in ip_list:
                        report_lines.append(f"      • {ip_str}")
                else:
                    for ip_str in ip_list[:5]:
                        report_lines.append(f"      • {ip_str}")
                    report_lines.append(f"      • ... and {len(ip_list) - 5} more")
            else:
                # Simple IP list without ISP info
                ip_list = sorted(unique_ips)
                if len(ip_list) <= 5:
                    for ip in ip_list:
                        report_lines.append(f"      • {ip}")
                else:
                    for ip in ip_list[:5]:
                        report_lines.append(f"      • {ip}")
                    report_lines.append(f"      • ... and {len(ip_list) - 5} more")
            
            report_lines.append("")
        
        # Summary
        total_ips = sum(ip_count for _, ip_count, _, _ in users_data)
        report_lines.append("─────────────────────")
        report_lines.append(f"📈 <b>Summary:</b>")
        report_lines.append(f"   • Users: {len(users_data)}")
        report_lines.append(f"   • Total Unique IPs: {total_ips}")
        report_lines.append(f"   • Period: {hours}h")
        
        return "\n".join(report_lines)


# Global instance
ip_history_tracker = IPHistoryTracker()
