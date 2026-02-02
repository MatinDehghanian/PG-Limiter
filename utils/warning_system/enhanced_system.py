"""
Enhanced Warning System for Limiter
This module provides a warning system with monitoring periods for users who exceed limits
"""

import asyncio
import json
import os
import time
import ipaddress
from typing import Dict, Optional, Set
from datetime import datetime

from utils.logs import logger, log_monitoring_event, get_logger
from utils.types import PanelType, UserType
from utils.warning_system.user_warning import UserWarning
from utils.warning_system.helpers import (
    safe_send_logs,
    safe_send_warning_log,
    safe_send_monitoring_log,
    safe_send_disable_notification,
    safe_disable_user_with_punishment,
)

# Module logger
warning_logger = get_logger("warning_system")


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
        self.warning_history: Dict[str, list] = {}
        self.monitoring_period = 180  # 3 minutes in seconds
        self.load_warnings()
        self.load_warning_history()
        warning_logger.debug(f"⚠️ EnhancedWarningSystem initialized (monitoring_period={self.monitoring_period}s)")
    
    def load_warning_history(self):
        """Load warning history from file"""
        try:
            if os.path.exists(self.history_filename):
                with open(self.history_filename, "r", encoding="utf-8") as file:
                    self.warning_history = json.load(file)
                    self.cleanup_old_warning_history()
                    warning_logger.debug(f"⚠️ Loaded warning history for {len(self.warning_history)} users")
        except Exception as e:
            warning_logger.error(f"Error loading warning history: {e}")
            self.warning_history = {}
    
    async def save_warning_history(self):
        """Save warning history to file"""
        try:
            with open(self.history_filename, "w", encoding="utf-8") as file:
                json.dump(self.warning_history, file, indent=2)
            warning_logger.debug(f"⚠️ Saved warning history ({len(self.warning_history)} users)")
        except Exception as e:
            warning_logger.error(f"Error saving warning history: {e}")
    
    def cleanup_old_warning_history(self):
        """Remove warnings older than 24 hours from history"""
        current_time = time.time()
        twenty_four_hours_ago = current_time - (24 * 60 * 60)
        
        for username in list(self.warning_history.keys()):
            self.warning_history[username] = [
                ts for ts in self.warning_history[username] 
                if ts > twenty_four_hours_ago
            ]
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
                        monitoring_history = []
                        if 'monitoring_history' in warning_data:
                            for snapshot in warning_data['monitoring_history']:
                                monitoring_history.append({
                                    'timestamp': snapshot['timestamp'],
                                    'ips': set(snapshot['ips']),
                                    'ip_count': snapshot['ip_count']
                                })
                        
                        ip_to_inbounds = {}
                        if 'ip_to_inbounds' in warning_data:
                            for ip, inbounds in warning_data['ip_to_inbounds'].items():
                                ip_to_inbounds[ip] = set(inbounds)
                        
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
                    warning_logger.debug(f"⚠️ Loaded {len(self.warnings)} active warnings from file")
        except Exception as e:
            warning_logger.error(f"Error loading warnings: {e}")
    
    async def save_warnings(self):
        """Save warnings to file"""
        try:
            data = {}
            for username, warning in self.warnings.items():
                monitoring_history_serializable = []
                for snapshot in warning.monitoring_history:
                    monitoring_history_serializable.append({
                        'timestamp': snapshot['timestamp'],
                        'ips': list(snapshot['ips']),
                        'ip_count': snapshot['ip_count']
                    })
                
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
            warning_logger.debug(f"⚠️ Saved {len(data)} warnings to file")
                
        except Exception as e:
            warning_logger.error(f"Error saving warnings: {e}")
    
    async def add_warning(self, username: str, ip_count: int, ips: Set[str], user_limit: int = None, 
                         user_data: 'UserType' = None, isp_info: dict = None,
                         panel_data: 'PanelType' = None) -> str:
        """
        Add a warning for a user with trust score calculation.
        May instantly disable user if trust score is very low.
        
        Returns:
            str: "new" if new warning, "updated" if existing, "instant_disabled" if instantly disabled
        """
        current_time = time.time()
        warning_logger.info(f"⚠️ Processing warning for user: {username} (ip_count={ip_count}, limit={user_limit})")
        
        if username in self.warnings:
            warning = self.warnings[username]
            if warning.is_monitoring_active():
                warning.ip_count = ip_count
                warning.ips = ips
                warning.update_ip_activity(ips, current_time)
                
                if user_data and user_data.device_info:
                    warning.inbound_protocols = user_data.device_info.inbound_protocols
                    warning.ip_to_inbounds = self._extract_ip_to_inbounds(user_data)
                if isp_info:
                    warning.isp_names = set(info.get('isp', 'Unknown') for info in isp_info.values())
                    warning.ip_subnets = self._extract_subnets(ips)
                
                warning.trust_score = warning.calculate_trust_score()
                
                await self.save_warnings()
                warning_logger.debug(f"⚠️ Updated existing warning for {username} (trust={warning.trust_score:.0f})")
                log_monitoring_event("warning_updated", username, {"ip_count": ip_count, "trust_score": warning.trust_score})
                return "updated"
            else:
                del self.warnings[username]
                warning_logger.debug(f"⚠️ Removed expired warning for {username}")
        
        previous_warnings_12h = self.count_recent_warnings(username, hours=12)
        previous_warnings_24h = self.count_recent_warnings(username, hours=24)
        warning_logger.debug(f"⚠️ User {username} history: {previous_warnings_12h} in 12h, {previous_warnings_24h} in 24h")
        
        inbound_protocols = set()
        isp_names = set()
        ip_subnets = self._extract_subnets(ips)
        ip_to_inbounds = {}
        connection_details = []
        
        if user_data and user_data.device_info:
            inbound_protocols = user_data.device_info.inbound_protocols
            ip_to_inbounds = self._extract_ip_to_inbounds(user_data)
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
        
        same_ip_multiple_inbounds = any(len(inbounds) > 1 for inbounds in ip_to_inbounds.values())
        
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
        
        warning.trust_score = warning.calculate_trust_score()
        trust_level = warning.get_trust_level()
        behavior_summary = warning.get_behavior_summary()
        
        # INSTANT DISABLE: If trust score is very low, skip monitoring
        if warning.trust_score <= self.INSTANT_DISABLE_THRESHOLD and panel_data:
            warning_logger.warning(f"⚡ INSTANT DISABLE triggered for {username} (trust={warning.trust_score:.0f} <= {self.INSTANT_DISABLE_THRESHOLD})")
            time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            limit_text = f"User limit: <code>{user_limit}</code>\n" if user_limit else ""
            
            await self.add_to_warning_history(username)
            
            try:
                punishment_result = await safe_disable_user_with_punishment(panel_data, UserType(name=username, ip=[]))
                
                if punishment_result["action"] == "warning":
                    await safe_send_warning_log(
                        f"⚠️ <b>WARNING (Instant)</b> - {time_str}\n\n"
                        f"User: <code>{username}</code>\n"
                        f"Active IPs: <code>{ip_count}</code>\n"
                        f"{limit_text}"
                        f"Trust Level: {trust_level} (<code>{warning.trust_score:.0f}</code>)\n"
                        f"Behavior: <code>{behavior_summary}</code>\n\n"
                        f"📊 Violation #{punishment_result['violation_count']} in time window\n"
                        f"⚡ Next violation will result in disable.",
                    )
                    warning_logger.warning(f"⚠️ WARNING (instant): User {username} - violation #{punishment_result['violation_count']}")
                    log_monitoring_event("instant_warning", username, {"violation": punishment_result['violation_count'], "trust": warning.trust_score})
                    return "warning"
                elif punishment_result["action"] == "disabled":
                    duration_text = ""
                    if punishment_result["duration_minutes"] > 0:
                        duration_text = f"Duration: <code>{punishment_result['duration_minutes']} minutes</code>\n"
                    else:
                        duration_text = "Duration: <code>Until manual enable</code>\n"
                    
                    await safe_send_disable_notification(
                        f"🚫 <b>INSTANT DISABLE</b> - {time_str}\n\n"
                        f"User: <code>{username}</code>\n"
                        f"Active IPs: <code>{ip_count}</code>\n"
                        f"{limit_text}"
                        f"Trust Level: {trust_level} (<code>{warning.trust_score:.0f}</code>)\n"
                        f"Behavior: <code>{behavior_summary}</code>\n\n"
                        f"📊 Violation #{punishment_result['violation_count']} (Step {punishment_result['step_index'] + 1})\n"
                        f"{duration_text}"
                        f"⚡ <b>Monitoring skipped</b> - Trust score too low (≤{self.INSTANT_DISABLE_THRESHOLD})",
                        username
                    )
                elif punishment_result["action"] == "revoked":
                    revoke_note = "✅ Subscription revoked" if punishment_result.get("revoke_success", False) else "⚠️ Revoke failed"
                    
                    await safe_send_disable_notification(
                        f"🔄 <b>INSTANT REVOKE + DISABLE</b> - {time_str}\n\n"
                        f"User: <code>{username}</code>\n"
                        f"Active IPs: <code>{ip_count}</code>\n"
                        f"{limit_text}"
                        f"Trust Level: {trust_level} (<code>{warning.trust_score:.0f}</code>)\n"
                        f"Behavior: <code>{behavior_summary}</code>\n\n"
                        f"📊 Violation #{punishment_result['violation_count']} (Step {punishment_result['step_index'] + 1})\n"
                        f"{revoke_note} (UUID changed)\n"
                        f"Duration: <code>Until manual enable</code>\n"
                        f"⚡ <b>Monitoring skipped</b> - Trust score too low (≤{self.INSTANT_DISABLE_THRESHOLD})",
                        username
                    )
                
                warning_logger.info(f"🚫 INSTANT DISABLE: User {username} disabled immediately (trust={warning.trust_score:.0f})")
                log_monitoring_event("instant_disabled", username, {"trust": warning.trust_score, "duration_min": punishment_result.get("duration_minutes", 0)})
                return "instant_disabled"
                
            except Exception as e:
                warning_logger.error(f"Failed to instant disable user {username}: {e}")
        
        # NORMAL WARNING: Start 3-minute monitoring period
        warning.update_ip_activity(ips, current_time)
        
        self.warnings[username] = warning
        await self.save_warnings()
        
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
        
        await safe_send_warning_log(
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
                ip_obj = ipaddress.ip_address(ip)
                if ip_obj.version == 4:
                    network = ipaddress.ip_network(f"{ip}/24", strict=False)
                    subnet_base = str(network.network_address).rsplit('.', 1)[0]
                    subnets.add(f"{subnet_base}.x")
                else:
                    subnets.add(ip)
            except ValueError:
                subnets.add(ip)
        return subnets
    
    async def check_persistent_violations(self, panel_data: PanelType, all_users_actual_ips: Dict[str, Set[str]], config_data: dict) -> tuple[Set[str], Set[str]]:
        """
        Check for users who still violate limits after 3-minute warning period.
        Uses device counting: only IPs active for 2+ minutes count as devices.
        
        Returns:
            Tuple[Set[str], Set[str]]: (disabled_users, warned_users) - sets of users who were disabled or warned
        """
        disabled_users = set()
        warned_users = set()  # Track users who received warnings to prevent double processing
        users_to_remove = []
        
        limits_config = config_data.get("limits", {})
        special_limit = limits_config.get("special", {})
        limit_number = limits_config.get("general", 2)
        
        warning_logger.debug(f"⚠️ Checking {len(self.warnings)} active warnings for persistent violations")
        
        for username, warning in self.warnings.items():
            if not warning.is_monitoring_active():
                warning_logger.debug(f"⚠️ Monitoring ended for {username}")
                if warning.active_monitoring_task and not warning.active_monitoring_task.done():
                    warning.active_monitoring_task.cancel()
                
                user_limit_number = int(special_limit.get(username, limit_number))
                trust_score = warning.trust_score
                trust_level = warning.get_trust_level()
                
                if username in all_users_actual_ips:
                    current_ips = all_users_actual_ips[username]
                    
                    persistent_devices = warning.get_persistent_devices(self.MIN_DEVICE_DURATION)
                    device_count = len(persistent_devices)
                    
                    current_persistent = current_ips.intersection(persistent_devices)
                    activity_summary = warning.get_ip_activity_summary()
                    
                    warning_logger.info(f"⚠️ User {username}: {device_count} devices (limit: {user_limit_number}), trust={trust_score:.0f}")
                    
                    time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    if device_count > user_limit_number:
                        warning_logger.warning(f"🚫 User {username} exceeds limit: {device_count} > {user_limit_number}")
                        try:
                            punishment_result = await safe_disable_user_with_punishment(
                                panel_data, UserType(name=username, ip=[])
                            )
                            
                            await self.add_to_warning_history(username)
                            
                            if punishment_result["action"] == "warning":
                                await safe_send_warning_log(
                                    f"⚠️ <b>WARNING</b> - {time_str}\n\n"
                                    f"User: <code>{username}</code>\n"
                                    f"Confirmed Devices: <code>{device_count}</code> (active 2+ min)\n"
                                    f"User limit: <code>{user_limit_number}</code>\n"
                                    f"Trust Level: {trust_level} (<code>{trust_score:.0f}</code>)\n\n"
                                    f"📊 Violation #{punishment_result['violation_count']} in time window\n"
                                    f"⚡ Next violation will result in disable."
                                )
                                warning_logger.warning(f"⚠️ WARNING: User {username} - {device_count} devices (limit: {user_limit_number}) - violation #{punishment_result['violation_count']}")
                                log_monitoring_event("persistent_warning", username, {"devices": device_count, "limit": user_limit_number, "violation": punishment_result['violation_count']})
                                warned_users.add(username)  # Track warned users to prevent double processing
                            elif punishment_result["action"] == "disabled":
                                disabled_users.add(username)
                                
                                duration_text = ""
                                if punishment_result["duration_minutes"] > 0:
                                    duration_text = f"Duration: <code>{punishment_result['duration_minutes']} minutes</code>\n"
                                else:
                                    duration_text = "Duration: <code>Until manual enable</code>\n"
                                
                                await safe_send_disable_notification(
                                    f"🚫 <b>USER DISABLED</b> - {time_str}\n\n"
                                    f"User: <code>{username}</code>\n"
                                    f"Confirmed Devices: <code>{device_count}</code> (active 2+ min)\n"
                                    f"Current IPs: <code>{len(current_ips)}</code>\n"
                                    f"User limit: <code>{user_limit_number}</code>\n"
                                    f"Trust Level: {trust_level} (<code>{trust_score:.0f}</code>)\n\n"
                                    f"📊 Violation #{punishment_result['violation_count']} (Step {punishment_result['step_index'] + 1})\n"
                                    f"{duration_text}"
                                    f"📊 IP Activity:\n<code>{activity_summary}</code>",
                                    username
                                )
                                
                                warning_logger.warning(f"🚫 Disabled user {username}: {device_count} devices (limit: {user_limit_number}) - step {punishment_result['step_index'] + 1}")
                                log_monitoring_event("user_disabled", username, {"devices": device_count, "limit": user_limit_number, "duration_min": punishment_result.get("duration_minutes", 0)})
                            elif punishment_result["action"] == "revoked":
                                disabled_users.add(username)
                                
                                revoke_note = "✅ Subscription revoked" if punishment_result.get("revoke_success", False) else "⚠️ Revoke failed"
                                
                                await safe_send_disable_notification(
                                    f"🔄 <b>SUBSCRIPTION REVOKED + DISABLED</b> - {time_str}\n\n"
                                    f"User: <code>{username}</code>\n"
                                    f"Confirmed Devices: <code>{device_count}</code> (active 2+ min)\n"
                                    f"Current IPs: <code>{len(current_ips)}</code>\n"
                                    f"User limit: <code>{user_limit_number}</code>\n"
                                    f"Trust Level: {trust_level} (<code>{trust_score:.0f}</code>)\n\n"
                                    f"📊 Violation #{punishment_result['violation_count']} (Step {punishment_result['step_index'] + 1})\n"
                                    f"{revoke_note} (UUID changed)\n"
                                    f"Duration: <code>Until manual enable</code>\n"
                                    f"📊 IP Activity:\n<code>{activity_summary}</code>",
                                    username
                                )
                                
                                warning_logger.warning(f"🔄 Revoked + disabled user {username}: {device_count} devices (limit: {user_limit_number}) - step {punishment_result['step_index'] + 1}")
                                log_monitoring_event("user_revoked", username, {"devices": device_count, "limit": user_limit_number, "revoke_success": punishment_result.get("revoke_success", False)})
                            else:
                                warning_logger.error(f"Punishment action error for {username}: {punishment_result['message']}")
                            
                        except Exception as e:
                            warning_logger.error(f"Failed to disable user {username}: {e}")
                            await safe_send_logs(f"❌ <b>Error:</b> Failed to disable user {username}: {e}")
                    
                    elif len(current_ips) > user_limit_number and device_count <= user_limit_number:
                        warning_logger.info(f"✅ User {username}: {len(current_ips)} IPs but only {device_count} devices - no action")
                        log_monitoring_event("monitoring_cleared", username, {"ips": len(current_ips), "devices": device_count, "limit": user_limit_number})
                        await safe_send_monitoring_log(
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
                        warning_logger.info(f"✅ User {username} is now within limits ({device_count} devices, limit: {user_limit_number})")
                        log_monitoring_event("monitoring_ended", username, {"devices": device_count, "limit": user_limit_number})
                        await safe_send_monitoring_log(
                            f"✅ <b>MONITORING ENDED</b> - {time_str}\n\n"
                            f"User: <code>{username}</code>\n"
                            f"Confirmed Devices: <code>{device_count}</code>\n"
                            f"User limit: <code>{user_limit_number}</code>\n\n"
                            f"User is now compliant with device limits."
                        )
                else:
                    warning_logger.info(f"ℹ️ User {username} not found in current logs - monitoring ended")
                    log_monitoring_event("monitoring_ended", username, {"reason": "user_inactive"})
                    await safe_send_monitoring_log(
                        f"ℹ️ <b>MONITORING ENDED</b> - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                        f"User: <code>{username}</code>\n"
                        f"Reason: <code>User not found in current logs</code>\n\n"
                        f"User is no longer active."
                    )
                
                users_to_remove.append(username)
        
        for username in users_to_remove:
            del self.warnings[username]
        
        if users_to_remove:
            await self.save_warnings()
        
        return disabled_users, warned_users
    
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
            await safe_send_monitoring_log(message)
    
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
            warning_logger.info(f"🧹 Cleaned up {len(expired_users)} expired warnings")
    
    async def start_monitoring_task(self, username: str, panel_data: PanelType):
        """
        Start a background monitoring task for a user.
        Currently disabled to prevent circular import issues.
        """
        warning_logger.debug(f"📍 Monitoring for {username} handled through periodic checks")
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
