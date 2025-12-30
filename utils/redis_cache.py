"""
Redis Cache Module for PG-Limiter.
Provides centralized caching with Redis for all application caches.

Replaces:
- Token cache (30 min TTL)
- Nodes cache (1 hour TTL)
- Config cache (5 min TTL)
- ISP/Subnet cache (7 days TTL)
- User data cache (5 min TTL)
"""

import os
import json
import asyncio
from typing import Any, Dict, List, Optional, Set
from datetime import timedelta

from utils.logs import get_logger

redis_logger = get_logger("redis_cache")

# Try to import redis
try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    redis_logger.warning("⚠️ redis package not installed, falling back to in-memory cache")
    REDIS_AVAILABLE = False


# Redis connection settings
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD", None)
REDIS_SSL = os.environ.get("REDIS_SSL", "false").lower() == "true"

# Cache TTL settings (in seconds)
CACHE_TTL = {
    "token": 1800,           # 30 minutes
    "nodes": 3600,           # 1 hour
    "config": 300,           # 5 minutes
    "isp": 604800,           # 7 days
    "user_data": 300,        # 5 minutes
    "panel_users": 60,       # 1 minute
    "disabled_users": 30,    # 30 seconds
    "violations": 300,       # 5 minutes
    "default": 300,          # 5 minutes default
}

# Cache key prefixes
CACHE_PREFIX = "pg_limiter:"


class InMemoryCache:
    """Fallback in-memory cache when Redis is not available."""
    
    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
        redis_logger.info("📦 Using in-memory cache (Redis not available)")
    
    async def get(self, key: str) -> Optional[str]:
        """Get value from cache."""
        async with self._lock:
            import time
            entry = self._cache.get(key)
            if entry and (entry["expires_at"] == 0 or entry["expires_at"] > time.time()):
                return entry["value"]
            elif entry:
                del self._cache[key]
            return None
    
    async def set(self, key: str, value: str, ex: Optional[int] = None) -> bool:
        """Set value in cache with optional expiration."""
        async with self._lock:
            import time
            expires_at = 0 if ex is None else time.time() + ex
            self._cache[key] = {"value": value, "expires_at": expires_at}
            return True
    
    async def delete(self, key: str) -> int:
        """Delete key from cache."""
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                return 1
            return 0
    
    async def exists(self, key: str) -> int:
        """Check if key exists."""
        value = await self.get(key)
        return 1 if value is not None else 0
    
    async def keys(self, pattern: str) -> List[str]:
        """Get keys matching pattern."""
        async with self._lock:
            import fnmatch
            import time
            # Clean expired entries first
            current_time = time.time()
            expired = [k for k, v in self._cache.items() 
                      if v["expires_at"] != 0 and v["expires_at"] <= current_time]
            for k in expired:
                del self._cache[k]
            
            # Match pattern (convert Redis pattern to fnmatch)
            pattern = pattern.replace("*", "*")
            return [k for k in self._cache if fnmatch.fnmatch(k, pattern)]
    
    async def ttl(self, key: str) -> int:
        """Get TTL for key."""
        async with self._lock:
            import time
            entry = self._cache.get(key)
            if not entry:
                return -2
            if entry["expires_at"] == 0:
                return -1
            remaining = int(entry["expires_at"] - time.time())
            return remaining if remaining > 0 else -2
    
    async def flushdb(self) -> bool:
        """Flush all keys."""
        async with self._lock:
            self._cache.clear()
            return True
    
    async def ping(self) -> bool:
        """Check connection (always True for in-memory)."""
        return True
    
    async def close(self):
        """Close connection (no-op for in-memory)."""
        self._cache.clear()
    
    async def incr(self, key: str) -> int:
        """Increment value."""
        async with self._lock:
            import time
            entry = self._cache.get(key)
            if entry and (entry["expires_at"] == 0 or entry["expires_at"] > time.time()):
                try:
                    new_val = int(entry["value"]) + 1
                    entry["value"] = str(new_val)
                    return new_val
                except ValueError:
                    return 1
            self._cache[key] = {"value": "1", "expires_at": 0}
            return 1
    
    async def hset(self, name: str, key: str, value: str) -> int:
        """Set hash field."""
        async with self._lock:
            if name not in self._cache:
                self._cache[name] = {"value": {}, "expires_at": 0}
            entry = self._cache[name]
            if not isinstance(entry["value"], dict):
                entry["value"] = {}
            is_new = key not in entry["value"]
            entry["value"][key] = value
            return 1 if is_new else 0
    
    async def hget(self, name: str, key: str) -> Optional[str]:
        """Get hash field."""
        async with self._lock:
            entry = self._cache.get(name)
            if entry and isinstance(entry["value"], dict):
                return entry["value"].get(key)
            return None
    
    async def hgetall(self, name: str) -> Dict[str, str]:
        """Get all hash fields."""
        async with self._lock:
            entry = self._cache.get(name)
            if entry and isinstance(entry["value"], dict):
                return entry["value"].copy()
            return {}
    
    async def hdel(self, name: str, *keys: str) -> int:
        """Delete hash fields."""
        async with self._lock:
            entry = self._cache.get(name)
            if entry and isinstance(entry["value"], dict):
                count = 0
                for key in keys:
                    if key in entry["value"]:
                        del entry["value"][key]
                        count += 1
                return count
            return 0


class RedisCache:
    """
    Redis cache wrapper with automatic connection management.
    Falls back to in-memory cache if Redis is not available.
    """
    
    _instance: Optional["RedisCache"] = None
    _client: Optional[Any] = None
    _fallback: Optional[InMemoryCache] = None
    _connected: bool = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    async def connect(self) -> bool:
        """Connect to Redis server."""
        if self._connected:
            return True
        
        if not REDIS_AVAILABLE:
            redis_logger.warning("⚠️ redis-py not installed, using in-memory cache")
            self._fallback = InMemoryCache()
            self._connected = True
            return True
        
        try:
            redis_logger.info(f"🔌 Connecting to Redis: {REDIS_URL}")
            
            # Create Redis client
            self._client = redis.from_url(
                REDIS_URL,
                password=REDIS_PASSWORD,
                decode_responses=True,
                ssl=REDIS_SSL,
            )
            
            # Test connection
            await self._client.ping()
            
            redis_logger.info("✅ Connected to Redis successfully")
            self._connected = True
            return True
            
        except Exception as e:
            redis_logger.warning(f"⚠️ Failed to connect to Redis: {e}, using in-memory cache")
            self._fallback = InMemoryCache()
            self._client = None
            self._connected = True
            return True
    
    async def disconnect(self):
        """Disconnect from Redis."""
        if self._client:
            await self._client.close()
            self._client = None
        self._connected = False
        redis_logger.info("📴 Disconnected from Redis")
    
    @property
    def client(self):
        """Get the active client (Redis or fallback)."""
        return self._client if self._client else self._fallback
    
    def is_redis(self) -> bool:
        """Check if using real Redis."""
        return self._client is not None
    
    # Helper methods for common operations
    async def get_json(self, key: str) -> Optional[Any]:
        """Get and deserialize JSON value."""
        full_key = f"{CACHE_PREFIX}{key}"
        try:
            value = await self.client.get(full_key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            redis_logger.error(f"❌ Redis get error for {key}: {e}")
            return None
    
    async def set_json(self, key: str, value: Any, ttl_key: str = "default") -> bool:
        """Serialize and set JSON value with TTL."""
        full_key = f"{CACHE_PREFIX}{key}"
        ttl = CACHE_TTL.get(ttl_key, CACHE_TTL["default"])
        try:
            await self.client.set(full_key, json.dumps(value), ex=ttl)
            redis_logger.debug(f"💾 Cached {key} (TTL: {ttl}s)")
            return True
        except Exception as e:
            redis_logger.error(f"❌ Redis set error for {key}: {e}")
            return False
    
    async def delete_key(self, key: str) -> bool:
        """Delete a key."""
        full_key = f"{CACHE_PREFIX}{key}"
        try:
            await self.client.delete(full_key)
            redis_logger.debug(f"🗑️ Deleted cache key: {key}")
            return True
        except Exception as e:
            redis_logger.error(f"❌ Redis delete error for {key}: {e}")
            return False
    
    async def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching pattern."""
        full_pattern = f"{CACHE_PREFIX}{pattern}"
        try:
            keys = await self.client.keys(full_pattern)
            if keys:
                count = 0
                for key in keys:
                    await self.client.delete(key)
                    count += 1
                redis_logger.debug(f"🗑️ Deleted {count} keys matching {pattern}")
                return count
            return 0
        except Exception as e:
            redis_logger.error(f"❌ Redis delete pattern error for {pattern}: {e}")
            return 0
    
    async def exists(self, key: str) -> bool:
        """Check if key exists."""
        full_key = f"{CACHE_PREFIX}{key}"
        try:
            return await self.client.exists(full_key) > 0
        except Exception as e:
            redis_logger.error(f"❌ Redis exists error for {key}: {e}")
            return False
    
    async def get_ttl(self, key: str) -> int:
        """Get remaining TTL for key."""
        full_key = f"{CACHE_PREFIX}{key}"
        try:
            return await self.client.ttl(full_key)
        except Exception as e:
            redis_logger.error(f"❌ Redis TTL error for {key}: {e}")
            return -2
    
    async def increment(self, key: str) -> int:
        """Increment a counter."""
        full_key = f"{CACHE_PREFIX}{key}"
        try:
            return await self.client.incr(full_key)
        except Exception as e:
            redis_logger.error(f"❌ Redis incr error for {key}: {e}")
            return 0
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        try:
            if self.is_redis():
                info = await self._client.info("memory")
                keys_count = await self._client.dbsize()
                return {
                    "type": "redis",
                    "connected": True,
                    "keys_count": keys_count,
                    "used_memory": info.get("used_memory_human", "N/A"),
                    "url": REDIS_URL.split("@")[-1] if "@" in REDIS_URL else REDIS_URL,
                }
            else:
                # Get cache size from fallback
                cache_size = 0
                if self._fallback and hasattr(self._fallback, "_cache"):
                    cache_size = len(getattr(self._fallback, "_cache", {}))
                return {
                    "type": "in-memory",
                    "connected": True,
                    "keys_count": cache_size,
                    "used_memory": "N/A",
                }
        except Exception as e:
            return {
                "type": "unknown",
                "connected": False,
                "error": str(e),
            }


# Global cache instance
_cache: Optional[RedisCache] = None


async def get_cache() -> RedisCache:
    """Get or create the global cache instance."""
    global _cache
    if _cache is None:
        _cache = RedisCache()
        await _cache.connect()
    return _cache


async def close_cache():
    """Close the cache connection."""
    global _cache
    if _cache:
        await _cache.disconnect()
        _cache = None


# Specific cache helpers for different data types

async def cache_token(panel_domain: str, token: str) -> bool:
    """Cache authentication token."""
    cache = await get_cache()
    key = f"token:{panel_domain}"
    return await cache.set_json(key, {"token": token}, ttl_key="token")


async def get_cached_token(panel_domain: str) -> Optional[str]:
    """Get cached authentication token."""
    cache = await get_cache()
    key = f"token:{panel_domain}"
    data = await cache.get_json(key)
    return data.get("token") if data else None


async def invalidate_token(panel_domain: str) -> bool:
    """Invalidate cached token."""
    cache = await get_cache()
    key = f"token:{panel_domain}"
    return await cache.delete_key(key)


async def cache_nodes(panel_domain: str, nodes: List[Dict]) -> bool:
    """Cache nodes list."""
    cache = await get_cache()
    key = f"nodes:{panel_domain}"
    return await cache.set_json(key, nodes, ttl_key="nodes")


async def get_cached_nodes(panel_domain: str) -> Optional[List[Dict]]:
    """Get cached nodes list."""
    cache = await get_cache()
    key = f"nodes:{panel_domain}"
    return await cache.get_json(key)


async def invalidate_nodes(panel_domain: str) -> bool:
    """Invalidate cached nodes."""
    cache = await get_cache()
    key = f"nodes:{panel_domain}"
    return await cache.delete_key(key)


async def cache_config(config: Dict) -> bool:
    """Cache configuration."""
    cache = await get_cache()
    return await cache.set_json("config", config, ttl_key="config")


async def get_cached_config() -> Optional[Dict]:
    """Get cached configuration."""
    cache = await get_cache()
    return await cache.get_json("config")


async def invalidate_config() -> bool:
    """Invalidate cached configuration."""
    cache = await get_cache()
    return await cache.delete_key("config")


async def cache_isp(subnet: str, isp_data: Dict) -> bool:
    """Cache ISP data for subnet."""
    cache = await get_cache()
    key = f"isp:{subnet}"
    return await cache.set_json(key, isp_data, ttl_key="isp")


async def get_cached_isp(subnet: str) -> Optional[Dict]:
    """Get cached ISP data for subnet."""
    cache = await get_cache()
    key = f"isp:{subnet}"
    data = await cache.get_json(key)
    if data:
        # Increment hit count
        await cache.increment(f"isp_hits:{subnet}")
    return data


async def cache_panel_users(panel_domain: str, users: List[Dict]) -> bool:
    """Cache panel users list."""
    cache = await get_cache()
    key = f"panel_users:{panel_domain}"
    return await cache.set_json(key, users, ttl_key="panel_users")


async def get_cached_panel_users(panel_domain: str) -> Optional[List[Dict]]:
    """Get cached panel users."""
    cache = await get_cache()
    key = f"panel_users:{panel_domain}"
    return await cache.get_json(key)


async def invalidate_panel_users(panel_domain: str) -> bool:
    """Invalidate cached panel users."""
    cache = await get_cache()
    key = f"panel_users:{panel_domain}"
    return await cache.delete_key(key)


async def cache_disabled_users(users: Dict[str, float]) -> bool:
    """Cache disabled users dict."""
    cache = await get_cache()
    return await cache.set_json("disabled_users", users, ttl_key="disabled_users")


async def get_cached_disabled_users() -> Optional[Dict[str, float]]:
    """Get cached disabled users."""
    cache = await get_cache()
    return await cache.get_json("disabled_users")


async def add_disabled_user(username: str, timestamp: float) -> bool:
    """Add a user to disabled cache."""
    cache = await get_cache()
    users = await get_cached_disabled_users() or {}
    users[username] = timestamp
    return await cache_disabled_users(users)


async def remove_disabled_user(username: str) -> bool:
    """Remove a user from disabled cache."""
    cache = await get_cache()
    users = await get_cached_disabled_users() or {}
    if username in users:
        del users[username]
        return await cache_disabled_users(users)
    return True


async def get_cache_stats() -> Dict[str, Any]:
    """Get comprehensive cache statistics."""
    cache = await get_cache()
    stats = await cache.get_stats()
    
    # Add category counts
    try:
        client = cache.client
        stats["categories"] = {
            "tokens": len(await client.keys(f"{CACHE_PREFIX}token:*")),
            "nodes": len(await client.keys(f"{CACHE_PREFIX}nodes:*")),
            "isp": len(await client.keys(f"{CACHE_PREFIX}isp:*")),
            "panel_users": len(await client.keys(f"{CACHE_PREFIX}panel_users:*")),
        }
    except Exception:
        stats["categories"] = {}
    
    return stats
