"""
Admin Filter Module
This module provides functionality to filter users based on their admin (owner).

Supports two modes:
- include: Only users belonging to specified admins will be limited
- exclude: Users belonging to specified admins will be whitelisted (not limited)

By default, when disabled, all users are subject to limiting.
"""

import time
from typing import Optional

from utils.logs import logger


# Cache for user admin mappings
# Format: {username: {"admin": "admin_username", "cached_at": timestamp}}
_user_admin_cache: dict[str, dict] = {}

# Cache for all admins from panel
# Format: {"admins": [{"username": "admin1", ...}, ...], "cached_at": timestamp}
_admins_cache: dict = {"admins": None, "cached_at": 0}

# Cache TTL in seconds (5 minutes)
CACHE_TTL = 300


def invalidate_user_admin_cache():
    """Invalidate the user admin cache"""
    global _user_admin_cache
    _user_admin_cache.clear()
    logger.info("User admin cache invalidated")


def invalidate_admins_cache():
    """Invalidate the admins list cache"""
    global _admins_cache
    _admins_cache = {"admins": None, "cached_at": 0}
    logger.info("Admins cache invalidated")


def get_cached_user_admin(username: str) -> Optional[str]:
    """
    Get cached admin username for a user.
    
    Args:
        username: The username to check
        
    Returns:
        Admin username if cached and valid, None otherwise
    """
    if username not in _user_admin_cache:
        return None
    
    cached = _user_admin_cache[username]
    if time.time() - cached["cached_at"] > CACHE_TTL:
        del _user_admin_cache[username]
        return None
    
    return cached["admin"]


def cache_user_admin(username: str, admin_username: str):
    """
    Cache admin username for a user.
    
    Args:
        username: The username
        admin_username: The admin username who owns this user
    """
    _user_admin_cache[username] = {
        "admin": admin_username,
        "cached_at": time.time()
    }


async def get_user_admin(panel_data, username: str) -> Optional[str]:
    """
    Get the admin (owner) for a user, using:
    1. Database cache first (from user sync)
    2. Admin patterns (prefix/postfix matching)
    3. Memory cache
    4. API as last resort
    
    Args:
        panel_data: Panel connection data
        username: The username to check
        
    Returns:
        Admin username or None if not found
    """
    # Check database cache first (from user sync)
    try:
        from utils.user_sync import get_user_from_cache
        cached_user = await get_user_from_cache(username)
        if cached_user and cached_user.get("owner_username"):
            return cached_user["owner_username"]
    except Exception:
        pass  # Fall back to other methods
    
    # Check admin patterns (prefix/postfix)
    try:
        from db.database import get_db_session
        from db.crud import AdminPatternCRUD
        
        async with get_db_session() as db:
            admin_from_pattern = await AdminPatternCRUD.find_admin_by_username(db, username)
            if admin_from_pattern:
                logger.debug(f"Found admin '{admin_from_pattern}' for user '{username}' via pattern")
                cache_user_admin(username, admin_from_pattern)
                return admin_from_pattern
    except Exception as e:
        logger.debug(f"Pattern check failed for {username}: {e}")
    
    # Check memory cache
    cached = get_cached_user_admin(username)
    if cached is not None:
        return cached
    
    # Fetch from API as last resort
    try:
        from utils.panel_api import get_user_admin as api_get_user_admin
        
        admin_username = await api_get_user_admin(panel_data, username)
        if admin_username:
            cache_user_admin(username, admin_username)
            return admin_username
        return None
    except Exception as e:
        logger.error(f"Error getting admin for user {username}: {e}")
        return None


async def get_all_admins(panel_data) -> list[dict]:
    """
    Get all admins from the panel, using cache when available.
    
    Args:
        panel_data: Panel connection data
        
    Returns:
        List of admin dictionaries
    """
    global _admins_cache
    
    # Check cache first
    if _admins_cache["admins"] is not None:
        if time.time() - _admins_cache["cached_at"] < CACHE_TTL:
            return _admins_cache["admins"]
    
    # Fetch from API
    try:
        from utils.panel_api import get_admins
        
        admins = await get_admins(panel_data)
        if admins:
            _admins_cache = {
                "admins": admins,
                "cached_at": time.time()
            }
            return admins
        return []
    except Exception as e:
        logger.error(f"Error getting admins from panel: {e}")
        return []


def get_admin_display_name(admins: list[dict], admin_username: str) -> str:
    """
    Get admin display name by username.
    
    Args:
        admins: List of admin dictionaries
        admin_username: The admin username to look up
        
    Returns:
        Admin username (formatted)
    """
    for admin in admins:
        if admin.get("username") == admin_username:
            is_sudo = admin.get("is_sudo", False)
            return f"{admin_username}{'👑' if is_sudo else ''}"
    return admin_username


async def should_limit_user_by_admin(panel_data, username: str, config_data: dict) -> tuple[bool, str]:
    """
    Check if a user should be subject to limiting based on admin filter settings.
    
    Args:
        panel_data: Panel connection data
        username: The username to check
        config_data: Configuration data with admin_filter settings
        
    Returns:
        Tuple of (should_limit: bool, reason: str)
        - (True, "") if user should be limited
        - (False, reason) if user should be skipped
    """
    admin_filter = config_data.get("admin_filter", {})
    
    # Check if filtering is enabled
    if not admin_filter.get("enabled", False):
        return (True, "")  # No filtering, limit all users
    
    filter_mode = admin_filter.get("mode", "include")
    filter_admin_usernames = admin_filter.get("admin_usernames", [])
    
    # If no admins specified, treat as disabled
    if not filter_admin_usernames:
        return (True, "")  # No admins specified, limit all users
    
    # Get user's admin
    user_admin = await get_user_admin(panel_data, username)
    
    if user_admin is None:
        # If we can't determine the admin, default to limiting
        logger.warning(f"Could not determine admin for user {username}, defaulting to limit")
        return (True, "")
    
    # Check if user's admin is in the filter list
    user_in_filter_admins = user_admin in filter_admin_usernames
    
    if filter_mode == "include":
        # Include mode: only limit users belonging to specified admins
        if user_in_filter_admins:
            return (True, "")
        else:
            return (False, f"User's admin ({user_admin}) not in monitored admins")
    else:
        # Exclude mode: skip users belonging to specified admins (whitelist)
        if user_in_filter_admins:
            return (False, f"User's admin ({user_admin}) in whitelisted admins")
        else:
            return (True, "")


async def batch_filter_users_by_admin(panel_data, usernames: list[str], config_data: dict) -> tuple[set[str], set[str]]:
    """
    Filter a batch of users based on admin settings.
    
    Args:
        panel_data: Panel connection data
        usernames: List of usernames to filter
        config_data: Configuration data
        
    Returns:
        Tuple of (users_to_limit, users_skipped)
    """
    admin_filter = config_data.get("admin_filter", {})
    
    # If filtering is disabled, return all users as to_limit
    if not admin_filter.get("enabled", False):
        return (set(usernames), set())
    
    filter_admin_usernames = admin_filter.get("admin_usernames", [])
    if not filter_admin_usernames:
        return (set(usernames), set())
    
    users_to_limit = set()
    users_skipped = set()
    
    for username in usernames:
        should_limit, _ = await should_limit_user_by_admin(panel_data, username, config_data)
        if should_limit:
            users_to_limit.add(username)
        else:
            users_skipped.add(username)
    
    if users_skipped:
        logger.info(f"Admin filter: {len(users_skipped)} users skipped, {len(users_to_limit)} users monitored")
    
    return (users_to_limit, users_skipped)


def get_admin_filter_status_text(config_data: dict, admins: list[dict] = None) -> str:
    """
    Get a human-readable status text for admin filter settings.
    
    Args:
        config_data: Configuration data with admin_filter settings
        admins: Optional list of admin dicts for display formatting
        
    Returns:
        Status text describing current admin filter configuration
    """
    admin_filter = config_data.get("admin_filter", {})
    
    enabled = admin_filter.get("enabled", False)
    mode = admin_filter.get("mode", "include")
    admin_usernames = admin_filter.get("admin_usernames", [])
    
    # Build status lines
    lines = []
    lines.append(f"<b>Status:</b> {'✅ Enabled' if enabled else '❌ Disabled'}")
    lines.append(f"<b>Mode:</b> {mode.title()}")
    
    if mode == "include":
        lines.append("<i>Only users of specified admins will be limited</i>")
    else:
        lines.append("<i>Users of specified admins will NOT be limited</i>")
    
    # Show configured admins
    if admin_usernames:
        admin_display = []
        for username in admin_usernames:
            # Check if admin exists and get details
            admin_info = ""
            if admins:
                for admin in admins:
                    if admin.get("username") == username:
                        if admin.get("is_sudo"):
                            admin_info = " 👑"
                        break
            admin_display.append(f"<code>{username}</code>{admin_info}")
        lines.append(f"\n<b>Configured Admins:</b> {', '.join(admin_display)}")
    else:
        lines.append("\n<b>Configured Admins:</b> <i>None (all users monitored)</i>")
    
    return "\n".join(lines)
