"""
Database Handler Module
This module provides database-backed replacements for JSON-based utilities.
It integrates with the db module to provide persistent storage for:
- Disabled users
- ISP caching (by subnet)
- Violation history
- Configuration
"""

import asyncio
import time
from typing import Dict, List, Optional, Set

from utils.logs import logger

# Try to import database module, fall back to JSON if not available
try:
    from db import (
        init_db,
        get_db,
        DisabledUserCRUD,
        SubnetISPCRUD,
        ViolationHistoryCRUD,
        ConfigCRUD,
    )
    DB_AVAILABLE = True
    logger.info("Database module loaded successfully")
except ImportError as e:
    DB_AVAILABLE = False
    logger.warning(f"Database module not available ({e}), falling back to JSON storage")


class DBDisabledUsers:
    """
    Database-backed disabled users management.
    Provides the same interface as DisabledUsers class but uses SQLite.
    """

    def __init__(self):
        self._initialized = False
        self._cache: Set[str] = set()  # In-memory cache for quick lookups
        self._cache_timestamps: Dict[str, float] = {}
        self._cache_enable_at: Dict[str, float] = {}
        self._original_groups: Dict[str, List[str]] = {}
        self._punishment_steps: Dict[str, int] = {}

    async def _ensure_initialized(self):
        """Ensure database is initialized"""
        if not self._initialized:
            await init_db()
            await self._load_cache()
            self._initialized = True

    async def _load_cache(self):
        """Load disabled users into memory cache"""
        async with get_db() as session:
            users = await DisabledUserCRUD.get_all(session)
            self._cache = {u.username for u in users}
            self._cache_timestamps = {u.username: u.disabled_at for u in users}
            self._cache_enable_at = {
                u.username: u.enable_at for u in users if u.enable_at
            }
            self._original_groups = {
                u.username: u.original_groups for u in users if u.original_groups
            }
            self._punishment_steps = {
                u.username: u.punishment_step for u in users if u.punishment_step is not None
            }
        logger.info(f"Loaded {len(self._cache)} disabled users from database")

    async def add_user(
        self,
        username: str,
        duration_seconds: int = 0,
        original_groups: Optional[List[str]] = None,
        punishment_step: Optional[int] = None,
    ):
        """
        Add a user to disabled users.

        Args:
            username: Username to disable
            duration_seconds: Custom duration (0 = use default)
            original_groups: User's original groups before disabling
            punishment_step: Which punishment step was applied
        """
        await self._ensure_initialized()

        current_time = time.time()
        enable_at = current_time + duration_seconds if duration_seconds > 0 else None

        async with get_db() as session:
            await DisabledUserCRUD.add(
                session,
                username=username,
                disabled_at=current_time,
                enable_at=enable_at,
                original_groups=original_groups,
                punishment_step=punishment_step,
            )

        # Update cache
        self._cache.add(username)
        self._cache_timestamps[username] = current_time
        if enable_at:
            self._cache_enable_at[username] = enable_at
        elif username in self._cache_enable_at:
            del self._cache_enable_at[username]
        if original_groups:
            self._original_groups[username] = original_groups
        if punishment_step is not None:
            self._punishment_steps[username] = punishment_step

        enable_time = time.strftime(
            "%H:%M:%S", time.localtime(enable_at if enable_at else current_time + 1800)
        )
        logger.info(
            f"User {username} disabled at {time.strftime('%H:%M:%S', time.localtime(current_time))}, "
            f"will be enabled at {enable_time}"
        )

    async def remove_user(self, username: str):
        """Remove a user from disabled users"""
        await self._ensure_initialized()

        async with get_db() as session:
            await DisabledUserCRUD.remove(session, username)

        # Update cache
        self._cache.discard(username)
        self._cache_timestamps.pop(username, None)
        self._cache_enable_at.pop(username, None)
        self._original_groups.pop(username, None)
        self._punishment_steps.pop(username, None)

        logger.info(f"User {username} removed from disabled users")

    async def get_users_to_enable(self, default_time_to_active: int) -> List[str]:
        """
        Get list of users ready to be enabled.

        Args:
            default_time_to_active: Default seconds before enabling

        Returns:
            List of usernames ready to enable
        """
        await self._ensure_initialized()

        async with get_db() as session:
            users = await DisabledUserCRUD.get_users_to_enable(
                session, default_time_to_active
            )

        return [u.username for u in users]

    def get_user_remaining_time(self, username: str, default_time_to_active: int) -> int:
        """
        Get remaining disable time in seconds.

        Returns:
            Remaining seconds, 0 if ready, -1 if not disabled
        """
        if username not in self._cache:
            return -1

        current_time = time.time()
        disabled_time = self._cache_timestamps.get(username, current_time)

        if username in self._cache_enable_at:
            enable_at = self._cache_enable_at[username]
            remaining = enable_at - current_time
        else:
            elapsed = current_time - disabled_time
            remaining = default_time_to_active - elapsed

        return max(0, int(remaining))

    def get_original_groups(self, username: str) -> Optional[List[str]]:
        """Get user's original groups before disabling"""
        return self._original_groups.get(username)

    def get_punishment_step(self, username: str) -> Optional[int]:
        """Get user's applied punishment step"""
        return self._punishment_steps.get(username)

    def is_disabled(self, username: str) -> bool:
        """Check if user is disabled"""
        return username in self._cache

    @property
    def disabled_users(self) -> Set[str]:
        """Get set of disabled usernames"""
        return self._cache.copy()

    async def read_and_clear_users(self) -> Set[str]:
        """Clear all disabled users and return their usernames"""
        await self._ensure_initialized()

        users = self._cache.copy()

        async with get_db() as session:
            for username in users:
                await DisabledUserCRUD.remove(session, username)

        self._cache.clear()
        self._cache_timestamps.clear()
        self._cache_enable_at.clear()
        self._original_groups.clear()
        self._punishment_steps.clear()

        return users


class DBSubnetISPCache:
    """
    Database-backed ISP cache by /24 subnet.
    Caches ISP info by subnet to reduce API calls.
    """

    def __init__(self):
        self._initialized = False
        self._memory_cache: Dict[str, Dict[str, str]] = {}  # Subnet -> ISP info

    async def _ensure_initialized(self):
        if not self._initialized:
            try:
                import asyncio
                async with asyncio.timeout(10):  # 10 second timeout for DB init
                    await init_db()
                self._initialized = True
            except asyncio.TimeoutError:
                logger.warning("DB initialization timeout, skipping cache")
            except Exception as e:
                logger.warning(f"DB initialization failed: {e}")

    @staticmethod
    def _get_subnet(ip: str) -> str:
        """Extract /24 subnet from IP (e.g., 192.168.1.5 -> 192.168.1.0/24)"""
        parts = ip.split(".")
        if len(parts) == 4:
            return f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"
        return ip

    async def get_cached_isp(self, ip: str) -> Optional[Dict[str, str]]:
        """
        Get cached ISP info for an IP's subnet.

        Args:
            ip: IP address

        Returns:
            ISP info dict if cached, None otherwise
        """
        import asyncio
        
        try:
            async with asyncio.timeout(3):  # 3 second timeout for cache lookup
                await self._ensure_initialized()
        except asyncio.TimeoutError:
            logger.debug(f"DB init timeout in get_cached_isp for {ip}")
            return None
        except Exception:
            return None

        subnet = self._get_subnet(ip)

        # Check memory cache first
        if subnet in self._memory_cache:
            return self._memory_cache[subnet]

        # Check database with timeout
        try:
            async with asyncio.timeout(3):  # 3 second timeout for DB query
                async with get_db() as session:
                    cached = await SubnetISPCRUD.get_by_ip(session, ip)
                    if cached:
                        isp_info = {
                            "ip": ip,
                            "isp": cached.isp,
                            "country": cached.country or "Unknown",
                            "city": cached.city or "Unknown",
                            "region": cached.region or "Unknown",
                        }
                        self._memory_cache[subnet] = isp_info
                        return isp_info
        except asyncio.TimeoutError:
            logger.debug(f"DB query timeout in get_cached_isp for {ip}")
        except Exception as e:
            logger.debug(f"DB error in get_cached_isp: {e}")

        return None

    async def cache_isp(
        self,
        ip: str,
        isp_name: str,
        country: Optional[str] = None,
        city: Optional[str] = None,
        region: Optional[str] = None,
    ):
        """
        Cache ISP info for an IP's subnet. Non-blocking with timeout.

        Args:
            ip: IP address
            isp_name: ISP name
            country: Country code
            city: City name
            region: Region name
        """
        import asyncio
        
        try:
            async with asyncio.timeout(3):  # 3 second timeout for init
                await self._ensure_initialized()
        except asyncio.TimeoutError:
            logger.debug(f"DB init timeout in cache_isp for {ip}")
            return
        except Exception:
            return

        subnet = self._get_subnet(ip)

        # Update memory cache first (always succeeds)
        self._memory_cache[subnet] = {
            "ip": ip,
            "isp": isp_name,
            "country": country or "Unknown",
            "city": city or "Unknown",
            "region": region or "Unknown",
        }

        # Save to database with timeout
        try:
            async with asyncio.timeout(3):  # 3 second timeout for DB save
                async with get_db() as session:
                    await SubnetISPCRUD.cache_isp(
                        session,
                        ip=ip,
                        isp=isp_name,
                        country=country,
                        city=city,
                        region=region,
                    )
        except asyncio.TimeoutError:
            logger.debug(f"DB save timeout in cache_isp for {ip}")
        except Exception as e:
            logger.debug(f"DB error in cache_isp: {e}")

        logger.debug(f"Cached ISP for subnet {subnet}: {isp_name}")

    async def get_all_cached_subnets(self) -> Dict[str, Dict[str, str]]:
        """Get all cached subnet ISP info"""
        await self._ensure_initialized()

        # Need to add get_all method to SubnetISPCRUD
        # For now, return memory cache
        return self._memory_cache.copy()

    def clear_memory_cache(self):
        """Clear only the in-memory cache"""
        self._memory_cache.clear()


class DBViolationHistory:
    """
    Database-backed violation history for punishment system.
    """

    def __init__(self):
        self._initialized = False

    async def _ensure_initialized(self):
        if not self._initialized:
            await init_db()
            self._initialized = True

    async def record_violation(
        self,
        username: str,
        step_applied: int,
        duration_minutes: int,
    ):
        """Record a new violation"""
        await self._ensure_initialized()

        async with get_db() as session:
            await ViolationHistoryCRUD.add(
                session,
                username=username,
                step_applied=step_applied,
                disable_duration=duration_minutes,
            )

        logger.info(f"Recorded violation for {username} (step {step_applied})")

    async def get_violation_count(
        self, username: str, window_hours: int = 168
    ) -> int:
        """
        Get violation count within time window.

        Args:
            username: Username to check
            window_hours: Time window in hours (default 7 days)

        Returns:
            Number of violations in window
        """
        await self._ensure_initialized()

        async with get_db() as session:
            return await ViolationHistoryCRUD.get_violation_count(
                session, username, window_hours=window_hours
            )

    async def get_user_violations(self, username: str, limit: int = 10) -> List[dict]:
        """Get recent violations for a user"""
        await self._ensure_initialized()

        async with get_db() as session:
            violations = await ViolationHistoryCRUD.get_user_violations(
                session, username, window_hours=24*365  # Get all within a year
            )
            result = []
            for v in violations[:limit]:
                result.append({
                    "username": v.username,
                    "timestamp": v.timestamp,
                    "step_applied": v.step_applied,
                    "duration_minutes": v.disable_duration,
                    "enabled_at": v.enabled_at,
                })
            return result

    async def clear_user_history(self, username: str):
        """Clear all violations for a user"""
        await self._ensure_initialized()

        async with get_db() as session:
            await ViolationHistoryCRUD.clear_user(session, username)

        logger.info(f"Cleared violation history for {username}")

    async def clear_all_history(self):
        """Clear all violation history"""
        await self._ensure_initialized()

        async with get_db() as session:
            await ViolationHistoryCRUD.clear_all(session)

        logger.info("Cleared all violation history")

    async def cleanup_old(self, window_hours: int = 168):
        """Remove violations older than window"""
        await self._ensure_initialized()

        days = window_hours // 24

        async with get_db() as session:
            await ViolationHistoryCRUD.cleanup_old(session, days=days)


class DBConfig:
    """
    Database-backed configuration storage.
    """

    def __init__(self):
        self._initialized = False
        self._cache: Dict[str, str] = {}

    async def _ensure_initialized(self):
        if not self._initialized:
            await init_db()
            await self._load_cache()
            self._initialized = True

    async def _load_cache(self):
        """Load config into memory cache"""
        async with get_db() as session:
            self._cache = await ConfigCRUD.get_all(session)

    async def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Get config value"""
        await self._ensure_initialized()
        return self._cache.get(key, default)

    async def set(self, key: str, value: str):
        """Set config value"""
        await self._ensure_initialized()

        async with get_db() as session:
            await ConfigCRUD.set(session, key, value)

        self._cache[key] = value

    async def delete(self, key: str):
        """Delete config value"""
        await self._ensure_initialized()

        async with get_db() as session:
            await ConfigCRUD.delete(session, key)

        self._cache.pop(key, None)

    async def get_all(self) -> Dict[str, str]:
        """Get all config values"""
        await self._ensure_initialized()
        return self._cache.copy()


# ============================================================================
# Singleton instances
# ============================================================================

_db_disabled_users: Optional[DBDisabledUsers] = None
_db_subnet_cache: Optional[DBSubnetISPCache] = None
_db_violation_history: Optional[DBViolationHistory] = None
_db_config: Optional[DBConfig] = None


def get_db_disabled_users() -> DBDisabledUsers:
    """Get or create the database-backed disabled users handler"""
    global _db_disabled_users
    if _db_disabled_users is None:
        _db_disabled_users = DBDisabledUsers()
    return _db_disabled_users


def get_db_subnet_cache() -> DBSubnetISPCache:
    """Get or create the database-backed subnet ISP cache"""
    global _db_subnet_cache
    if _db_subnet_cache is None:
        _db_subnet_cache = DBSubnetISPCache()
    return _db_subnet_cache


def get_db_violation_history() -> DBViolationHistory:
    """Get or create the database-backed violation history"""
    global _db_violation_history
    if _db_violation_history is None:
        _db_violation_history = DBViolationHistory()
    return _db_violation_history


def get_db_config() -> DBConfig:
    """Get or create the database-backed config"""
    global _db_config
    if _db_config is None:
        _db_config = DBConfig()
    return _db_config
