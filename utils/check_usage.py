"""
This module checks if a user (name and IP address)
appears more than two times in the ACTIVE_USERS list.
Enhanced with warning system and ISP detection.
"""

import asyncio
import ipaddress
from collections import Counter

from telegram_bot.send_message import send_logs, send_user_message, send_active_users_log
from utils.logs import logger
from utils.panel_api import disable_user
from utils.read_config import read_config, get_config_value
from utils.types import PanelType, UserType, EnhancedUserInfo
from utils.warning_system import EnhancedWarningSystem
from utils.isp_detector import ISPDetector
from utils.ip_history_tracker import ip_history_tracker
from utils.user_group_filter import should_limit_user, get_filter_status_text
from utils.admin_filter import should_limit_user_by_admin

ACTIVE_USERS: dict[str, UserType] | dict = {}

# Initialize warning system and ISP detector
warning_system = EnhancedWarningSystem()
isp_detector = None  # Will be initialized when needed


def group_ips_by_subnet(ip_list: list[str]) -> tuple[list[str], dict[str, list[str]]]:
    """
    Group IPs by their /24 subnet and return formatted representations.
    Shows individual IPs when 2 or fewer, shows subnet.x (count) when more than 2.

    Args:
        ip_list (list[str]): List of IP addresses

    Returns:
        tuple[list[str], dict[str, list[str]]]: 
            - List of formatted subnet representations
            - Dictionary mapping formatted representations to actual IPs
    """
    subnet_groups = {}
    ip_mapping = {}

    for ip in ip_list:
        try:
            # Parse the IP address
            ip_obj = ipaddress.ip_address(ip)

            # For IPv4, group by /24 subnet (first 3 octets)
            if ip_obj.version == 4:
                # Get the network address for /24 subnet
                network = ipaddress.ip_network(f"{ip}/24", strict=False)
                subnet_base = network.network_address.exploded.rsplit('.', 1)[0]
                subnet_key = f"{subnet_base}.x"
            else:
                # For IPv6, use the full IP as is (less common for CDN scenarios)
                subnet_key = str(ip_obj)

            if subnet_key not in subnet_groups:
                subnet_groups[subnet_key] = []
            subnet_groups[subnet_key].append(ip)

        except ValueError:
            # If IP parsing fails, treat as individual IP
            subnet_key = ip
            if subnet_key not in subnet_groups:
                subnet_groups[subnet_key] = []
            subnet_groups[subnet_key].append(ip)

    # Format the output based on count
    formatted_results = []
    
    for subnet_key, ips in subnet_groups.items():
        if len(ips) <= 2:
            # Show individual IPs when 2 or fewer
            for ip in ips:
                formatted_results.append(ip)
                ip_mapping[ip] = [ip]
        else:
            # Show subnet.x (count) when more than 2
            formatted_subnet = f"{subnet_key} ({len(ips)})"
            formatted_results.append(formatted_subnet)
            ip_mapping[formatted_subnet] = ips
    
    return formatted_results, ip_mapping


def _build_ip_details(user_info: EnhancedUserInfo, original_user: UserType, show_enhanced_details: bool) -> tuple[list[str], int]:
    """
    Build IP details with connection info for a user.
    
    Args:
        user_info: Enhanced user information
        original_user: Original user data with device info
        show_enhanced_details: Whether to show detailed connection info
        
    Returns:
        Tuple of (list of formatted IP detail strings, device count)
        Device count = unique (IP, inbound) combinations
    """
    device_count = 0
    unique_devices = set()  # Track unique (IP, inbound) combinations
    
    if not original_user or not original_user.device_info or not original_user.device_info.connections:
        # Fallback: count IPs as devices if no connection info
        return [], len(user_info.formatted_ips)
    
    # Count unique devices (IP + inbound combinations)
    for conn in original_user.device_info.connections:
        unique_devices.add((conn.ip, conn.inbound_protocol))
    device_count = len(unique_devices)
    
    if not show_enhanced_details:
        return [], device_count
    
    ip_details = []
    
    # Group connections by IP
    ip_to_connections = {}
    for conn in original_user.device_info.connections:
        if conn.ip in user_info.user.ip:
            if conn.ip not in ip_to_connections:
                ip_to_connections[conn.ip] = []
            ip_to_connections[conn.ip].append(conn)
    
    # Create mapping of raw IP to formatted IP with ISP info
    raw_to_formatted = {}
    for formatted_ip in user_info.formatted_ips:
        if ' (' in formatted_ip:
            raw_ip = formatted_ip.split(' (')[0]
        else:
            raw_ip = formatted_ip.split(' ')[0]
        raw_to_formatted[raw_ip] = formatted_ip
    
    # Build details for each IP with inbound info
    for ip, connections in ip_to_connections.items():
        formatted_ip = raw_to_formatted.get(ip, ip)
        
        # Get unique inbounds for this IP
        unique_inbounds = list(set(c.inbound_protocol for c in connections))
        node_info = f"{connections[0].node_name}({connections[0].node_id})"
        
        if len(unique_inbounds) == 1:
            ip_details.append(f"  • {formatted_ip} → {node_info} | {unique_inbounds[0]}")
        else:
            # Multiple inbounds on same IP = multiple devices
            inbounds_str = ", ".join(unique_inbounds)
            ip_details.append(f"  • {formatted_ip} → {node_info} | [{inbounds_str}]")
    
    return ip_details, device_count


async def check_ip_used() -> dict:
    """
    Check active users and display them.
    1. Shows all active users with device count >= general_limit in ONE combined message
    2. Sends SEPARATE action messages for users who don't have special limit set
       (for setting their limit via inline buttons)
    3. Respects group filter and admin filter settings
    """
    global isp_detector
    
    config_data = await read_config()
    general_limit = config_data.get("limits", {}).get("general", 2)
    except_users = config_data.get("except_users", [])  # except_users is at root level
    show_enhanced_details = config_data.get("display", {}).get("show_enhanced_details", True)
    
    # Read special limits from database instead of config
    from db.database import get_db
    from db.crud import UserCRUD
    async with get_db() as db:
        special_limit = await UserCRUD.get_all_special_limits(db)
    
    # Get panel data for filter checks
    panel_config = config_data.get("panel", {})
    panel_data = PanelType(
        panel_config.get("username", ""),
        panel_config.get("password", ""),
        panel_config.get("domain", "")
    )
    
    # Initialize ISP detector with token from config
    if isp_detector is None:
        ipinfo_token = config_data.get("api", {}).get("ipinfo_token", "")
        use_fallback_api = config_data.get("api", {}).get("use_fallback_isp_api", False)
        logger.info(f"Loading IPINFO_TOKEN from config: {'Present' if ipinfo_token else 'NOT FOUND'}")
        if use_fallback_api:
            logger.info("Using fallback ISP API (ip-api.com) for all requests")
        isp_detector = ISPDetector(token=ipinfo_token if ipinfo_token else None, use_fallback_only=use_fallback_api)
    
    logger.info(f"📊 Processing {len(ACTIVE_USERS)} active users...")
    
    all_users_log = {}
    enhanced_users_info = {}
    filtered_users = set()  # Users filtered out by group/admin filters
    
    # Collect all unique IPs for batch ISP lookup
    all_ips = set()
    ip_mappings = {}
    all_actual_ips = set()
    
    for email in list(ACTIVE_USERS.keys()):
        data = ACTIVE_USERS[email]
        
        # Add ALL IPs for total count
        for ip in data.ip:
            all_actual_ips.add(ip)
        
        # Include all unique IPs for this user
        all_unique_ips = list(set(data.ip))
        
        # Group IPs by subnet
        subnet_ips, ip_mapping = group_ips_by_subnet(all_unique_ips)
        all_users_log[email] = subnet_ips
        ip_mappings[email] = ip_mapping
        
        for ip in all_unique_ips:
            all_ips.add(ip)
    
    logger.info(f"📊 Collected {len(all_ips)} unique IPs from {len(all_users_log)} users")
    
    # Get ISP information for all IPs
    if all_ips:
        logger.info(f"🔍 Looking up ISP info for {len(all_ips)} IPs...")
        isp_info_batch = await isp_detector.get_multiple_isp_info(list(all_ips))
        logger.info(f"✅ ISP lookup complete: {len(isp_info_batch)} results")
    else:
        isp_info_batch = {}
        logger.info("📊 No IPs to look up (no active connections)")
    
    # Pre-filter users based on group and admin filter settings
    # This ensures we don't show logs or send action messages for filtered users
    logger.debug("🔍 Applying user filters...")
    for email in list(ACTIVE_USERS.keys()):
        # Check group filter
        should_limit_group, _ = await should_limit_user(panel_data, email, config_data)
        if not should_limit_group:
            filtered_users.add(email)
            continue
        
        # Check admin filter
        should_limit_admin, _ = await should_limit_user_by_admin(panel_data, email, config_data)
        if not should_limit_admin:
            filtered_users.add(email)
            continue
    
    if filtered_users:
        logger.info(f"Filters applied: {len(filtered_users)} users excluded from monitoring")
    
    # Create enhanced user info with ISP details (only for non-filtered users)
    for email, formatted_ips in all_users_log.items():
        if not formatted_ips:
            continue
        
        # Skip filtered users
        if email in filtered_users:
            continue
            
        ip_mapping = ip_mappings.get(email, {})
        enhanced_formatted_ips = []
        actual_ips_for_counting = []
        
        for formatted_ip in formatted_ips:
            actual_ips = ip_mapping.get(formatted_ip, [formatted_ip])
            actual_ips_for_counting.extend(actual_ips)
            
            if len(actual_ips) == 1:
                ip = actual_ips[0]
                if ip in isp_info_batch:
                    isp_info = isp_info_batch[ip]
                    enhanced_ip = isp_detector.format_ip_with_isp(ip, isp_info)
                else:
                    enhanced_ip = ip
                enhanced_formatted_ips.append(enhanced_ip)
            else:
                first_ip = actual_ips[0]
                if first_ip in isp_info_batch:
                    isp_info = isp_info_batch[first_ip]
                    enhanced_ip = f"{formatted_ip} ({isp_info['isp']}, {isp_info['country']})"
                else:
                    enhanced_ip = formatted_ip
                enhanced_formatted_ips.append(enhanced_ip)
        
        is_monitored = warning_system.is_user_being_monitored(email)
        time_remaining = 0
        if is_monitored and email in warning_system.warnings:
            time_remaining = warning_system.warnings[email].time_remaining()
        
        enhanced_users_info[email] = EnhancedUserInfo(
            user=UserType(name=email, ip=actual_ips_for_counting),
            formatted_ips=enhanced_formatted_ips,
            is_being_monitored=is_monitored,
            warning_time_remaining=time_remaining
        )
    
    total_ips = len(all_actual_ips)
    
    # Calculate device counts for all users
    all_user_device_counts = {}
    total_devices = 0
    
    for email, user_info in enhanced_users_info.items():
        if not user_info.user.ip:
            all_user_device_counts[email] = 0
            continue
        
        original_user = ACTIVE_USERS.get(email)
        _, device_count = _build_ip_details(user_info, original_user, show_enhanced_details)
        all_user_device_counts[email] = device_count
        total_devices += device_count
    
    logger.info("Number of all active ips: %s, devices: %s", str(total_ips), str(total_devices))
    
    # Sort users by device count (descending)
    sorted_users = sorted(
        enhanced_users_info.items(),
        key=lambda x: all_user_device_counts.get(x[0], 0),
        reverse=True
    )
    
    # Build combined message for all users with >= general_limit devices
    combined_message_parts = []
    users_needing_limit = []  # Users without special limit who need action messages
    users_shown = 0
    
    for email, user_info in sorted_users:
        if not user_info.user.ip:
            continue
        
        original_user = ACTIVE_USERS.get(email)
        ip_count = len(user_info.formatted_ips)
        device_count = all_user_device_counts.get(email, 0)
        
        # Get user's limit (special or general)
        user_limit = special_limit.get(email, general_limit)
        has_special_limit = email in special_limit
        is_except = email in except_users
        
        # Skip users who are not exceeding their limit
        # A user violates when device_count > user_limit
        if device_count <= user_limit:
            continue
        
        users_shown += 1
        
        # Build IP details
        ip_details, _ = _build_ip_details(user_info, original_user, show_enhanced_details)
        
        # Build status indicators
        status_text = ""
        if user_info.is_being_monitored:
            minutes = user_info.warning_time_remaining // 60
            seconds = user_info.warning_time_remaining % 60
            status_text = f" ⚠️ {minutes}m{seconds}s"
        
        # Build limit indicator
        if is_except:
            limit_indicator = "🔓"
        elif has_special_limit:
            limit_indicator = f"🎯{user_limit}"
        else:
            limit_indicator = f"📊{user_limit}"
            # Add to list of users needing limit setting
            users_needing_limit.append({
                "email": email,
                "device_count": device_count,
                "ip_count": ip_count
            })
        
        # Build user block with IP details for combined message
        # Format: 👤 Username
        #         📱 2 🌐 2 🎯 2
        #         • IP details...
        
        # Build limit indicator
        if is_except:
            limit_str = "🔓"
        elif has_special_limit:
            limit_str = f"🎯 {user_limit}"
        else:
            limit_str = f"📊 {user_limit}"
        
        user_header = f"👤 <b>{email}</b>{status_text}\n   📱 {device_count} 🌐 {ip_count} {limit_str}"
        
        # Add IP details
        if ip_details:
            ip_lines = "\n".join(f"  {detail}" for detail in ip_details)
            user_block = f"{user_header}\n{ip_lines}"
        else:
            ip_lines = "\n".join(f"  • {ip}" for ip in user_info.formatted_ips)
            user_block = f"{user_header}\n{ip_lines}"
        
        combined_message_parts.append(user_block)
    
    # Send combined message with all users
    if combined_message_parts:
        header = (
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 <b>Active Users Report</b>\n"
            f"👥 Users: {users_shown} | 📱 Devices: {total_devices} | 🌐 IPs: {total_ips}\n"
            f"📏 General limit: {general_limit}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
        )
        
        # Split into chunks if too long (Telegram limit ~4096 chars)
        full_message = header + "\n\n".join(combined_message_parts)
        
        if len(full_message) > 4000:
            # Send in chunks
            await send_active_users_log(header)
            chunk = ""
            for block in combined_message_parts:
                if len(chunk) + len(block) + 2 > 3900:
                    await send_active_users_log(chunk)
                    await asyncio.sleep(0.3)
                    chunk = block
                else:
                    chunk = chunk + "\n\n" + block if chunk else block
            if chunk:
                await send_active_users_log(chunk)
        else:
            await send_active_users_log(full_message)
    
    # Send SEPARATE action messages for users who need limit setting
    # (users without special limit and not in except list)
    if users_needing_limit:
        await asyncio.sleep(1)  # Small delay after combined message
        
        for user_data in users_needing_limit:
            email = user_data["email"]
            device_count = user_data["device_count"]
            ip_count = user_data["ip_count"]
            
            action_message = (
                f"⚙️ <b>Set Limit for: {email}</b>\n"
                f"📱 Devices: {device_count} | 🌐 IPs: {ip_count}\n"
                f"No special limit set - using general limit ({general_limit})"
            )
            
            try:
                # Send with inline buttons (has_special_limit=False, is_except=False)
                await send_user_message(action_message, email, device_count, False, False, general_limit)
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.error(f"Failed to send action message for user {email}: {e}")
    
    # Send monitoring summary
    monitoring_summary = await warning_system.generate_monitoring_summary()
    if monitoring_summary:
        try:
            await asyncio.sleep(1)
            await send_active_users_log(monitoring_summary)
        except Exception as e:
            logger.error(f"Failed to send monitoring summary: {e}")
    
    return all_users_log


async def check_users_usage(panel_data: PanelType):
    """
    Enhanced function to check usage with warning system and ISP detection
    """
    global isp_detector
    
    config_data = await read_config()
    all_users_log = await check_ip_used()
    
    # Use new config format
    limits_config = config_data.get("limits", {})
    api_config = config_data.get("api", {})
    
    except_users = config_data.get("except_users", [])  # except_users is at root level
    limit_number = limits_config.get("general", 2)
    
    # Read special limits from database instead of config
    from db.database import get_db
    from db.crud import UserCRUD
    async with get_db() as db:
        special_limit = await UserCRUD.get_all_special_limits(db)
    
    # Initialize ISP detector if not already done
    if isp_detector is None:
        ipinfo_token = api_config.get("ipinfo_token", "")
        use_fallback_api = api_config.get("use_fallback_isp_api", False)
        logger.info(f"[check_users_usage] Loading ipinfo_token: {'Present' if ipinfo_token else 'NOT FOUND'}")
        if ipinfo_token:
            logger.info(f"[check_users_usage] Token preview: {ipinfo_token[:20]}...")
        if use_fallback_api:
            logger.info("[check_users_usage] Using fallback ISP API (ip-api.com) for all requests")
        isp_detector = ISPDetector(token=ipinfo_token if ipinfo_token else None, use_fallback_only=use_fallback_api)
    
    logger.info("📊 Building user info from active connections...")
    
    # Build user info with actual unique IP counts for ALL active users
    # This is critical for warning system to work correctly
    all_users_actual_ips = {}  # Maps username to set of actual unique IPs
    all_users_data = {}  # Maps username to UserType with full data
    all_ips_for_isp_lookup = set()  # Collect all IPs for batch ISP lookup
    
    for email in list(ACTIVE_USERS.keys()):
        data = ACTIVE_USERS[email]
        # Get ALL unique IPs for this user (not just filtered ones)
        unique_ips = set(data.ip)
        all_users_actual_ips[email] = unique_ips
        all_users_data[email] = data
        
        # Add to ISP lookup set
        all_ips_for_isp_lookup.update(unique_ips)
    
    logger.info(f"📊 Found {len(all_users_actual_ips)} active users with {len(all_ips_for_isp_lookup)} unique IPs")
    
    # Batch fetch ISP info for all IPs
    logger.info(f"🔍 Looking up ISP info for {len(all_ips_for_isp_lookup)} IPs...")
    isp_info_batch = await isp_detector.get_multiple_isp_info(list(all_ips_for_isp_lookup))
    logger.info(f"✅ ISP lookup complete")
    
    # Record IPs to history tracker for long-term tracking
    logger.debug("📝 Recording IPs to history tracker...")
    for username, unique_ips in all_users_actual_ips.items():
        await ip_history_tracker.record_user_ips(username, unique_ips)
    
    # Save history periodically
    await ip_history_tracker.save_history()
    
    # Cleanup inactive users from history
    await ip_history_tracker.cleanup_inactive_users(set(all_users_actual_ips.keys()))
    
    # Check for users who still violate limits after warning period
    # Pass actual IPs, not formatted display strings
    disabled_users, warned_users = await warning_system.check_persistent_violations(
        panel_data, all_users_actual_ips, config_data
    )
    
    # Combine disabled and warned users to skip them in the loop
    # This prevents double processing in the same cycle
    processed_users = disabled_users | warned_users
    
    # Check current violations for ALL users (not just those in all_users_log)
    # Track users skipped due to group filter or admin filter
    group_filtered_users = set()
    admin_filtered_users = set()
    
    for user_name, unique_ips in all_users_actual_ips.items():
        if user_name not in except_users and user_name not in processed_users:
            # Check group filter - skip users not in monitored groups
            should_limit, skip_reason = await should_limit_user(panel_data, user_name, config_data)
            if not should_limit:
                group_filtered_users.add(user_name)
                continue
            
            # Check admin filter - skip users whose admin is not monitored
            should_limit_admin, admin_skip_reason = await should_limit_user_by_admin(panel_data, user_name, config_data)
            if not should_limit_admin:
                admin_filtered_users.add(user_name)
                continue
            
            user_limit_number = int(special_limit.get(user_name, limit_number))
            
            if len(unique_ips) > user_limit_number:
                # Get user data and ISP info for this user
                user_data = all_users_data.get(user_name)
                user_isp_info = {ip: isp_info_batch.get(ip, {}) for ip in unique_ips if ip in isp_info_batch}
                
                # Check if user is already being monitored
                if warning_system.is_user_being_monitored(user_name):
                    # User is being monitored, update their IP count and activity tracking
                    result = await warning_system.add_warning(
                        user_name, len(unique_ips), unique_ips, user_limit_number,
                        user_data=user_data, isp_info=user_isp_info, panel_data=panel_data
                    )
                    logger.info(f"Updated monitoring for user {user_name} with {len(unique_ips)} IPs")
                else:
                    # New violation - may start monitoring or instant disable
                    result = await warning_system.add_warning(
                        user_name, len(unique_ips), unique_ips, user_limit_number,
                        user_data=user_data, isp_info=user_isp_info, panel_data=panel_data
                    )
                    
                    if result == "instant_disabled":
                        disabled_users.add(user_name)
                        logger.warning(f"User {user_name} instantly disabled due to low trust score")
                    elif result == "new":
                        message = (
                            f"User {user_name} has {len(unique_ips)} active ips (limit: {user_limit_number}). "
                            f"Warning issued - monitoring for 3 minutes."
                        )
                        logger.warning(message)
    
    # Log group filter stats if any users were filtered
    if group_filtered_users:
        logger.debug(f"Group filter: {len(group_filtered_users)} users skipped")
    
    # Log admin filter stats if any users were filtered
    if admin_filtered_users:
        logger.debug(f"Admin filter: {len(admin_filtered_users)} users skipped")
    
    # Clean up expired warnings
    await warning_system.cleanup_expired_warnings()
    
    # Send monitoring status every few cycles (optional)
    # await warning_system.send_monitoring_status()
    
    ACTIVE_USERS.clear()
    all_users_log.clear()


async def run_check_users_usage(panel_data: PanelType) -> None:
    """run check_ip_used() function and then run check_users_usage()"""
    while True:
        await check_users_usage(panel_data)
        data = await read_config()
        check_interval = data.get("monitoring", {}).get("check_interval", 60)
        await asyncio.sleep(int(check_interval))
