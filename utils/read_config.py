"""
Configuration module for PG-Limiter.
Reads settings from:
- Environment variables (.env) for static settings
- Database for dynamic settings that can be changed via Telegram
- Redis cache for fast access (with fallback to in-memory)
"""

import os
from typing import Any, Dict, List, Optional

from utils.logs import get_logger

# Try to import Redis cache
try:
    from utils.redis_cache import (
        get_cached_config, cache_config, invalidate_config as redis_invalidate_config
    )
    REDIS_CACHE_AVAILABLE = True
except ImportError:
    REDIS_CACHE_AVAILABLE = False

# Module logger
config_logger = get_logger("read_config")

# Try to import database module
try:
    from db import get_db, ConfigCRUD, UserLimitCRUD, ExceptUserCRUD
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False

# In-memory cache fallback
_config_cache: Dict[str, Any] = {}
_cache_loaded = False


async def invalidate_config_cache():
    """Invalidate configuration cache (Redis and in-memory)."""
    global _config_cache, _cache_loaded
    
    if REDIS_CACHE_AVAILABLE:
        try:
            await redis_invalidate_config()
            config_logger.debug("🔧 Redis config cache invalidated")
        except Exception as e:
            config_logger.warning(f"Failed to invalidate Redis config cache: {e}")
    
    _config_cache = {}
    _cache_loaded = False
    config_logger.info("🔧 Configuration cache invalidated")


def _parse_admin_ids(admin_ids_str: str) -> List[int]:
    """Parse comma-separated admin IDs into list of integers."""
    if not admin_ids_str:
        return []
    try:
        return [int(id.strip()) for id in admin_ids_str.split(",") if id.strip()]
    except ValueError:
        return []


def _get_env(key: str, default: Any = None, cast_type: type = str) -> Any:
    """Get environment variable with type casting."""
    value = os.environ.get(key, default)
    if value is None or value == "":
        return default
    
    if cast_type == bool:
        return str(value).lower() in ("true", "1", "yes", "on")
    elif cast_type == int:
        try:
            return int(value)
        except (ValueError, TypeError):
            return default
    elif cast_type == float:
        try:
            return float(value)
        except (ValueError, TypeError):
            return default
    
    return value


def load_env_config() -> Dict[str, Any]:
    """Load configuration from environment variables."""
    return {
        # Panel settings (from ENV only)
        "panel": {
            "domain": _get_env("PANEL_DOMAIN", ""),
            "username": _get_env("PANEL_USERNAME", "admin"),
            "password": _get_env("PANEL_PASSWORD", ""),
        },
        # Telegram settings (from ENV only)
        "telegram": {
            "bot_token": _get_env("BOT_TOKEN", ""),
            "admins": _parse_admin_ids(_get_env("ADMIN_IDS", "")),
        },
        # Limiter settings (from ENV - defaults)
        "limits": {
            "general": _get_env("GENERAL_LIMIT", 2, int),
            "special": {},  # Loaded from DB
        },
        "except_users": [],  # Loaded from DB
        # Monitoring settings (from ENV)
        "check_interval": _get_env("CHECK_INTERVAL", 60, int),
        "time_to_active_users": _get_env("TIME_TO_ACTIVE_USERS", 900, int),
        "country_code": _get_env("COUNTRY_CODE", ""),
        # API settings (from ENV)
        "api": {
            "enabled": _get_env("API_ENABLED", False, bool),
            "host": _get_env("API_HOST", "0.0.0.0"),
            "port": _get_env("API_PORT", 8080, int),
            "username": _get_env("API_USERNAME", "admin"),
            "password": _get_env("API_PASSWORD", ""),
        },
        # Database
        "database_url": _get_env(
            "DATABASE_URL",
            "sqlite+aiosqlite:///./data/pg_limiter.db"
        ),
    }


async def load_db_config() -> Dict[str, Any]:
    """Load dynamic configuration from database."""
    if not DB_AVAILABLE:
        return {}
    
    try:
        async with get_db() as session:
            # Load all config from database
            db_config = await ConfigCRUD.get_all(session)
            
            # Load special limits
            special_limits = await UserLimitCRUD.get_all(session)
            
            # Load except users
            except_users = await ExceptUserCRUD.get_all(session)
        
        return {
            "db_config": db_config,
            "special_limits": special_limits,
            "except_users": except_users,
        }
    except Exception:
        return {}


def get_config_sync() -> Dict[str, Any]:
    """Get configuration synchronously (ENV only, for startup)."""
    return load_env_config()


async def read_config(check_required_elements: bool = False) -> Dict[str, Any]:
    """
    Read and return merged configuration from ENV and DB.
    Uses Redis cache when available for fast access.
    
    Args:
        check_required_elements: If True, validate required settings
        
    Returns:
        Complete configuration dictionary
    """
    global _config_cache, _cache_loaded
    
    # Try Redis cache first
    if REDIS_CACHE_AVAILABLE and not check_required_elements:
        try:
            cached = await get_cached_config()
            if cached:
                config_logger.debug("🔧 Using Redis cached config")
                return cached
        except Exception as e:
            config_logger.warning(f"Redis config cache error: {e}")
    
    # Check in-memory cache
    if _cache_loaded and _config_cache and not check_required_elements:
        config_logger.debug("🔧 Using in-memory cached config")
        return _config_cache
    
    config_logger.debug("🔧 Loading fresh configuration...")
    
    # Load ENV config
    env_config = load_env_config()
    
    # Load DB config
    db_data = await load_db_config()
    
    # Merge configurations
    config = env_config.copy()
    
    # Add special limits from DB
    if "special_limits" in db_data:
        config["limits"]["special"] = db_data["special_limits"]
    
    # Add except users from DB
    if "except_users" in db_data:
        config["except_users"] = db_data["except_users"]
    
    # Merge DB config (dynamic settings changeable via Telegram)
    db_config = db_data.get("db_config", {})
    
    # Dynamic settings from DB (override ENV values if set in DB)
    if "check_interval" in db_config:
        try:
            config["check_interval"] = int(db_config["check_interval"])
        except (ValueError, TypeError):
            pass
    
    if "time_to_active_users" in db_config:
        try:
            config["time_to_active_users"] = int(db_config["time_to_active_users"])
        except (ValueError, TypeError):
            pass
    
    if "country_code" in db_config:
        config["country_code"] = db_config["country_code"]
    
    if "general_limit" in db_config:
        try:
            config["limits"]["general"] = int(db_config["general_limit"])
        except (ValueError, TypeError):
            pass
    
    config["disable_method"] = db_config.get("disable_method", "status")
    config["disabled_group_id"] = db_config.get("disabled_group_id")
    if config["disabled_group_id"]:
        try:
            config["disabled_group_id"] = int(config["disabled_group_id"])
        except (ValueError, TypeError):
            config["disabled_group_id"] = None
    
    config["enhanced_details"] = db_config.get("enhanced_details", "true").lower() == "true"
    config["show_single_ip_users"] = db_config.get("show_single_ip_users", "false").lower() == "true"
    config["ipinfo_token"] = db_config.get("ipinfo_token", "")
    
    # Punishment system settings
    config["punishment"] = {
        "enabled": db_config.get("punishment_enabled", "true").lower() == "true",
        "window_hours": int(db_config.get("punishment_window_hours", "168")),
    }
    
    # Group filter settings
    config["group_filter"] = {
        "enabled": db_config.get("group_filter_enabled", "false").lower() == "true",
        "mode": db_config.get("group_filter_mode", "include"),
        "group_ids": [],
    }
    group_ids_str = db_config.get("group_filter_ids", "")
    if group_ids_str:
        try:
            config["group_filter"]["group_ids"] = [
                int(x.strip()) for x in group_ids_str.split(",") if x.strip()
            ]
        except ValueError:
            pass
    
    # Admin filter settings
    config["admin_filter"] = {
        "enabled": db_config.get("admin_filter_enabled", "false").lower() == "true",
        "mode": db_config.get("admin_filter_mode", "include"),
        "admin_usernames": [],
    }
    admin_usernames_str = db_config.get("admin_filter_usernames", "")
    if admin_usernames_str:
        config["admin_filter"]["admin_usernames"] = [
            x.strip() for x in admin_usernames_str.split(",") if x.strip()
        ]
    
    # Validate required elements
    if check_required_elements:
        if not config["panel"]["domain"]:
            raise ValueError("PANEL_DOMAIN is not set in environment")
        if not config["panel"]["password"]:
            raise ValueError("PANEL_PASSWORD is not set in environment")
        if not config["telegram"]["bot_token"]:
            raise ValueError("BOT_TOKEN is not set in environment")
        if not config["telegram"]["admins"]:
            raise ValueError("ADMIN_IDS is not set in environment")
    
    _config_cache = config
    _cache_loaded = True
    
    # Store in Redis cache
    if REDIS_CACHE_AVAILABLE:
        try:
            await cache_config(config)
            config_logger.debug("🔧 Config stored in Redis cache")
        except Exception as e:
            config_logger.warning(f"Failed to cache config in Redis: {e}")
    
    return config


async def save_config_value(key: str, value: Any) -> bool:
    """
    Save a dynamic configuration value to database.
    
    Args:
        key: Configuration key
        value: Value to save
        
    Returns:
        True if successful
    """
    if not DB_AVAILABLE:
        return False
    
    try:
        async with get_db() as session:
            await ConfigCRUD.set(session, key, str(value))
        await invalidate_config_cache()
        return True
    except Exception:
        return False


async def delete_config_value(key: str) -> bool:
    """Delete a configuration value from database."""
    if not DB_AVAILABLE:
        return False
    
    try:
        async with get_db() as session:
            await ConfigCRUD.delete(session, key)
        await invalidate_config_cache()
        return True
    except Exception:
        return False


async def get_config_value_from_db(key: str, default: Any = None) -> Any:
    """Get a single config value from database."""
    if not DB_AVAILABLE:
        return default
    
    try:
        async with get_db() as session:
            value = await ConfigCRUD.get(session, key, default)
            return value
    except Exception:
        return default


def get_config_value(config: dict, key: str, default: Any = None) -> Any:
    """
    Get config value by key name.
    Supports both old flat keys and new structure.
    """
    key_map = {
        "PANEL_DOMAIN": lambda c: c.get("panel", {}).get("domain"),
        "PANEL_USERNAME": lambda c: c.get("panel", {}).get("username"),
        "PANEL_PASSWORD": lambda c: c.get("panel", {}).get("password"),
        "BOT_TOKEN": lambda c: c.get("telegram", {}).get("bot_token"),
        "ADMINS": lambda c: c.get("telegram", {}).get("admins"),
        "GENERAL_LIMIT": lambda c: c.get("limits", {}).get("general"),
        "SPECIAL_LIMIT": lambda c: c.get("limits", {}).get("special"),
        "SPECIAL_LIMITS": lambda c: c.get("limits", {}).get("special"),
        "EXCEPT_USERS": lambda c: c.get("except_users"),
        "CHECK_INTERVAL": lambda c: c.get("check_interval"),
        "TIME_TO_ACTIVE_USERS": lambda c: c.get("time_to_active_users"),
        "COUNTRY_CODE": lambda c: c.get("country_code"),
        "IP_LOCATION": lambda c: c.get("country_code"),  # Alias
        "DISABLE_METHOD": lambda c: c.get("disable_method"),
        "DISABLED_GROUP_ID": lambda c: c.get("disabled_group_id"),
        "ENHANCED_DETAILS": lambda c: c.get("enhanced_details"),
        "SHOW_SINGLE_IP_USERS": lambda c: c.get("show_single_ip_users"),
        "IPINFO_TOKEN": lambda c: c.get("ipinfo_token"),
    }
    
    if key in key_map:
        value = key_map[key](config)
        return value if value is not None else default
    
    return config.get(key, default)


# Compatibility aliases
async def get_config(*args, **kwargs):
    """Alias for read_config for backward compatibility."""
    return await read_config(*args, **kwargs)
