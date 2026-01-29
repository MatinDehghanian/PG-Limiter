"""
This module contains functions to parse and validate logs.
"""

import ipaddress
import random
import re
import sys
import time

from utils.check_usage import ACTIVE_USERS
from utils.read_config import read_config
from utils.types import ConnectionInfo, DeviceInfo, UserType

try:
    import httpx
except ImportError:
    print("Module 'httpx' is not installed use: 'pip install httpx' to install it")
    sys.exit()

INVALID_EMAILS = [
    "API]",
    "Found",
    "(normal)",
    "timeout",
    "EOF",
    "address",
    "INFO",
    "request",
]
INVALID_IPS = {
    "1.1.1.1",
    "8.8.8.8",
}
VALID_IPS = []
CACHE = {}

# API endpoints with fallback order (from most reliable to least)
API_ENDPOINTS = [
    {"url": "http://ip-api.com/json/{ip}?fields=countryCode", "key": "countryCode", "name": "ip-api.com"},
    {"url": "https://ipinfo.io/{ip}/json", "key": "country", "name": "ipinfo.io"},
    {"url": "https://api.iplocation.net/?ip={ip}", "key": "country_code2", "name": "iplocation.net"},
    {"url": "https://ipapi.co/{ip}/country", "key": None, "name": "ipapi.co"},
]

# Track failed endpoints to prioritize working ones
_endpoint_failures = {endpoint["name"]: 0 for endpoint in API_ENDPOINTS}
_endpoint_last_success = {endpoint["name"]: 0 for endpoint in API_ENDPOINTS}


async def remove_id_from_username(username: str) -> str:
    """
    Remove the ID from the start of the username.
    Args:
        username (str): The username string from which to remove the ID.

    Returns:
        str: The username with the ID removed.
    """
    return re.sub(r"^\d+\.", "", username)


async def check_ip(ip_address: str) -> None | str:
    """
    Check the geographical location of an IP address with fallback through multiple APIs.

    Get the location of the IP address.
    The result is cached to avoid unnecessary requests for the same IP address.
    Uses fallback mechanism - if one API fails, tries the next one.

    Args:
        ip_address (str): The IP address to check.

    Returns:
        str: The country code of the IP address location, or None
    """
    global _endpoint_failures, _endpoint_last_success
    
    if ip_address in CACHE:
        return CACHE[ip_address]
    
    # Sort endpoints by reliability (fewer failures first, recent success preferred)
    current_time = time.time()
    sorted_endpoints = sorted(
        API_ENDPOINTS,
        key=lambda e: (
            _endpoint_failures.get(e["name"], 0),
            -(current_time - _endpoint_last_success.get(e["name"], 0))
        )
    )
    
    last_error = None
    for endpoint in sorted_endpoints:
        url = endpoint["url"].format(ip=ip_address)
        key = endpoint["key"]
        name = endpoint["name"]
        
        try:
            async with httpx.AsyncClient(verify=False, timeout=5) as client:
                resp = await client.get(url, timeout=3)
                
                if resp.status_code == 200:
                    if key is None:
                        # Direct text response (like ipapi.co/country)
                        country = resp.text.strip()
                    else:
                        info = resp.json()
                        country = info.get(key)
                    
                    if country and len(country) == 2:  # Valid country code
                        CACHE[ip_address] = country
                        _endpoint_failures[name] = max(0, _endpoint_failures.get(name, 0) - 1)
                        _endpoint_last_success[name] = current_time
                        return country
                elif resp.status_code == 429:
                    # Rate limited - increase failure count
                    _endpoint_failures[name] = _endpoint_failures.get(name, 0) + 3
                else:
                    _endpoint_failures[name] = _endpoint_failures.get(name, 0) + 1
                    
        except httpx.TimeoutException:
            _endpoint_failures[name] = _endpoint_failures.get(name, 0) + 2
            last_error = f"Timeout on {name}"
        except Exception as e:
            _endpoint_failures[name] = _endpoint_failures.get(name, 0) + 1
            last_error = f"{name}: {type(e).__name__}"
    
    # All endpoints failed
    return None


async def is_valid_ip(ip: str) -> bool:
    """
    Check if a string is a valid IP address.

    This function uses the ipaddress module to try to create an IP address object from the string.

    Args:
        ip (str): The string to check.

    Returns:
        bool: True if the string is a valid IP address, False otherwise.
    """
    try:
        ip_obj = ipaddress.ip_address(ip)
        return not ip_obj.is_private
    except ValueError:
        return False


IP_V6_REGEX = re.compile(r"\[([0-9a-fA-F:]+)\]:\d+\s+accepted")
IP_V4_REGEX = re.compile(r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})")
EMAIL_REGEX = re.compile(r"email:\s*([A-Za-z0-9._%+-]+)")
INBOUND_REGEX = re.compile(r"\[([^\]]+)\s+>>\s+[^\]]+\]")
# Regex for X-Forwarded-For header in logs (Cloudflare and other CDNs)
# Format examples:
#   xForwardedFor: 1.2.3.4
#   X-Forwarded-For: 1.2.3.4
#   xff: 1.2.3.4
XFF_REGEX = re.compile(r"(?:xForwardedFor|X-Forwarded-For|xff):\s*(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})")
# Alternative regex for when Xray logs real IP in different format
# Some Xray configs show: from 1.2.3.4 (via CDN)
XRAY_REAL_IP_REGEX = re.compile(r"from\s+(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\s+\(via")

# Global storage for current node information (will be set by the calling function)
CURRENT_NODE_INFO = {"node_id": None, "node_name": None}

# Global CDN configuration (loaded from config)
CDN_CONFIG = {
    "cdn_inbounds": [],  # List of inbound names that use CDN
    "cdn_provider": "cloudflare",  # CDN provider type
    "use_xff": True  # Whether to extract real IP from X-Forwarded-For
}


async def set_current_node_info(node_id: int, node_name: str) -> None:
    """
    Set the current node information for log parsing.

    Args:
        node_id (int): The ID of the current node
        node_name (str): The name of the current node
    """
    global CURRENT_NODE_INFO
    CURRENT_NODE_INFO = {"node_id": node_id, "node_name": node_name}


async def update_cdn_config() -> None:
    """
    Update the CDN configuration from the config file.
    Should be called periodically to refresh CDN settings.
    """
    global CDN_CONFIG
    try:
        data = await read_config()
        CDN_CONFIG["cdn_inbounds"] = data.get("cdn_inbounds", [])
        CDN_CONFIG["cdn_provider"] = data.get("cdn_provider", "cloudflare")
        CDN_CONFIG["use_xff"] = data.get("cdn_use_xff", True)
    except Exception:
        pass  # Keep existing config on error


async def update_user_device_info_with_node(user: UserType, ip: str, inbound_protocol: str, node_id: int, node_name: str) -> None:
    """
    Update user's device information with new connection data using specific node info.

    Args:
        user (UserType): The user to update
        ip (str): The IP address
        inbound_protocol (str): The inbound protocol used
        node_id (int): The ID of the node
        node_name (str): The name of the node
    """
    current_time = time.time()

    # Check if this connection already exists
    existing_connection = None
    for conn in user.device_info.connections:
        if conn.ip == ip and conn.node_id == node_id and conn.inbound_protocol == inbound_protocol:
            existing_connection = conn
            break

    if existing_connection:
        # Update existing connection
        existing_connection.last_seen = current_time
        existing_connection.connection_count += 1
    else:
        # Create new connection
        new_connection = ConnectionInfo(
            ip=ip,
            node_id=node_id,
            node_name=node_name,
            inbound_protocol=inbound_protocol,
            last_seen=current_time
        )
        user.device_info.connections.append(new_connection)

    # Update sets for device analysis
    user.device_info.unique_ips.add(ip)
    user.device_info.unique_nodes.add(node_id)
    user.device_info.inbound_protocols.add(inbound_protocol)

    # Determine if user is using multiple devices
    # Consider it multi-device if:
    # 1. More than 2 unique IPs, or
    # 2. Using different inbound protocols simultaneously, or
    # 3. Active connections from different nodes at the same time
    user.device_info.is_multi_device = (
        len(user.device_info.unique_ips) > 2 or
        len(user.device_info.inbound_protocols) > 1 or
        len(user.device_info.unique_nodes) > 1
    )


async def update_user_device_info(user: UserType, ip: str, inbound_protocol: str) -> None:
    """
    Update user's device information with new connection data.

    Args:
        user (UserType): The user to update
        ip (str): The IP address
        inbound_protocol (str): The inbound protocol used
    """
    # Use global node info (backward compatibility)
    node_id = CURRENT_NODE_INFO["node_id"]
    node_name = CURRENT_NODE_INFO["node_name"]
    
    await update_user_device_info_with_node(user, ip, inbound_protocol, node_id, node_name)


async def parse_logs(log: str, node_id: int = None, node_name: str = None) -> dict[str, UserType] | dict:  # pylint: disable=too-many-branches
    """
    Asynchronously parse logs to extract and validate IP addresses, emails, and inbound protocols.

    Args:
        log (str): The log to parse.
        node_id (int): The ID of the node that generated this log
        node_name (str): The name of the node that generated this log

    Returns:
        dict[str, UserType]: Dictionary of users with their connection information
    """
    # Use provided node info or fall back to global (for backward compatibility)
    current_node_id = node_id if node_id is not None else CURRENT_NODE_INFO.get("node_id")
    current_node_name = node_name if node_name is not None else CURRENT_NODE_INFO.get("node_name")
    
    data = await read_config()
    if data.get("INVALID_IPS"):
        INVALID_IPS.update(data.get("INVALID_IPS"))
    
    # Update CDN config from settings
    cdn_inbounds = data.get("cdn_inbounds", [])
    use_xff = data.get("cdn_use_xff", True)
    
    lines = log.splitlines()
    for line in lines:
        if "accepted" not in line:
            continue
        if "BLOCK]" in line:
            continue
        
        # Extract inbound protocol first (needed for CDN check)
        inbound_match = INBOUND_REGEX.search(line)
        inbound_protocol = "Unknown"
        if inbound_match:
            inbound_protocol = inbound_match.group(1).strip()
        
        # Extract IP address
        ip_v6_match = IP_V6_REGEX.search(line)
        ip_v4_match = IP_V4_REGEX.search(line)
        email_match = EMAIL_REGEX.search(line)
        
        if ip_v6_match:
            ip = ip_v6_match.group(1)
        elif ip_v4_match:
            ip = ip_v4_match.group(1)
        else:
            continue
        
        # Check if this inbound is a CDN inbound - if so, try to get real IP from X-Forwarded-For
        is_cdn_inbound = inbound_protocol in cdn_inbounds
        if is_cdn_inbound and use_xff:
            # Try to extract real IP from X-Forwarded-For header
            xff_match = XFF_REGEX.search(line)
            if xff_match:
                real_ip = xff_match.group(1)
                # Use the real IP from X-Forwarded-For instead of CDN edge IP
                ip = real_ip
            else:
                # Try alternative Xray real IP format
                real_ip_match = XRAY_REAL_IP_REGEX.search(line)
                if real_ip_match:
                    ip = real_ip_match.group(1)
        
        # Get IP location from config (new format)
        ip_location = data.get("monitoring", {}).get("ip_location", "IR")
        
        # Validate IP
        if ip not in VALID_IPS:
            is_valid_ip_test = await is_valid_ip(ip)
            if is_valid_ip_test and ip not in INVALID_IPS:
                if ip_location != "None":
                    country = await check_ip(ip)
                    if country and country == ip_location:
                        VALID_IPS.append(ip)
                    elif country and country != ip_location:
                        INVALID_IPS.add(ip)
                        continue
            else:
                continue
        
        # Extract email
        if email_match:
            email = email_match.group(1)
            email = await remove_id_from_username(email)
            if email in INVALID_EMAILS:
                continue
        else:
            continue

        # Update user information
        user = ACTIVE_USERS.get(email)
        if user:
            # Add IP if not already present
            if ip not in user.ip:
                user.ip.append(ip)
            # Update device info with the specific node info
            await update_user_device_info_with_node(user, ip, inbound_protocol, current_node_id, current_node_name)
        else:
            # Create new user
            user = UserType(name=email, ip=[ip])
            await update_user_device_info_with_node(user, ip, inbound_protocol, current_node_id, current_node_name)
            ACTIVE_USERS[email] = user

    return ACTIVE_USERS
