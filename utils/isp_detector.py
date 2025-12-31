"""
ISP Detection Module
This module provides functionality to detect ISP information for IP addresses
Uses Redis cache when available for fast lookups, with fallback to in-memory and database.
"""

import asyncio
import aiohttp
from typing import Dict, Optional
from utils.logs import logger

# Try to import Redis cache
try:
    from utils.redis_cache import get_cached_isp, cache_isp
    REDIS_CACHE_AVAILABLE = True
except ImportError:
    REDIS_CACHE_AVAILABLE = False

# Try to import database-backed subnet cache
try:
    from utils.db_handler import get_db_subnet_cache, DB_AVAILABLE
except ImportError:
    DB_AVAILABLE = False
    get_db_subnet_cache = None


class ISPDetector:
    """
    A class to detect ISP information for IP addresses
    """
    
    def __init__(self, token: Optional[str] = None, use_fallback_only: bool = False, use_db_cache: bool = True):
        """
        Initialize the ISP detector with an optional ipinfo token
        
        Args:
            token (Optional[str]): ipinfo.io API token (optional for basic usage)
            use_fallback_only (bool): If True, use only ip-api.com instead of ipinfo.io
            use_db_cache (bool): If True, use database-backed subnet cache for persistence
        """
        self.token = token
        # Auto-enable fallback if no token provided (ipinfo.io rate limits quickly without token)
        self.use_fallback_only = use_fallback_only or (not token)
        self.use_db_cache = use_db_cache and DB_AVAILABLE
        self.cache = {}  # Simple cache to avoid repeated API calls
        self.rate_limit_delay = 1  # 1 second delay between requests
        self.last_request_time = 0
        self.rate_limited = False  # Track if we're rate limited
        self._session = None  # Shared aiohttp session
        self._db_cache = get_db_subnet_cache() if self.use_db_cache else None
        
        if self.use_db_cache:
            logger.info("ISPDetector initialized with database-backed subnet cache")
        if self.use_fallback_only:
            logger.info("ISPDetector using ip-api.com (fallback mode - no token configured)")
        elif token:
            logger.info(f"ISPDetector initialized with token: {token[:20]}...")
    
    async def _get_session(self):
        """Get or create the shared aiohttp session"""
        if self._session is None or self._session.closed:
            # Create session with connection limits
            connector = aiohttp.TCPConnector(limit=10, limit_per_host=5)
            self._session = aiohttp.ClientSession(connector=connector)
        return self._session
    
    async def close(self):
        """Close the aiohttp session"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
    
    async def get_isp_info(self, ip: str) -> Dict[str, str]:
        """
        Get ISP information for a given IP address.
        Checks Redis cache first, then memory, then database, finally API.
        
        Args:
            ip (str): IP address to lookup
            
        Returns:
            Dict[str, str]: Dictionary containing ISP information
        """
        # Check Redis cache first (fastest)
        if REDIS_CACHE_AVAILABLE:
            try:
                cached = await get_cached_isp(ip)
                if cached:
                    logger.debug(f"ISP Redis cache hit for {ip}")
                    # Also store in memory cache
                    self.cache[ip] = cached
                    return cached
            except Exception as e:
                logger.warning(f"Redis cache lookup failed for {ip}: {e}")
        
        # Check memory cache
        if ip in self.cache:
            return self.cache[ip]
        
        # Check database cache (by subnet) if enabled
        if self._db_cache:
            try:
                cached = await self._db_cache.get_cached_isp(ip)
                if cached:
                    # Copy to memory cache and Redis
                    self.cache[ip] = cached
                    await self._cache_isp_result(ip, cached)
                    logger.debug(f"ISP cache hit for {ip} (subnet cache)")
                    return cached
            except Exception as e:
                logger.warning(f"Database cache lookup failed: {e}")
        
        # If use_fallback_only is enabled, skip ipinfo.io and use ip-api.com directly
        if self.use_fallback_only:
            result = await self._get_isp_fallback(ip)
            await self._cache_isp_result(ip, result)
            return result
        
        # If we're rate limited, return default info immediately
        if self.rate_limited:
            default_info = {
                "ip": ip,
                "isp": "Unknown ISP",
                "country": "Unknown",
                "city": "Unknown",
                "region": "Unknown"
            }
            self.cache[ip] = default_info
            return default_info
            
        # Rate limiting
        current_time = asyncio.get_event_loop().time()
        if current_time - self.last_request_time < self.rate_limit_delay:
            await asyncio.sleep(self.rate_limit_delay - (current_time - self.last_request_time))
        
        try:
            # Try ipinfo.io API first
            url = f"https://ipinfo.io/{ip}/json"
            headers = {}
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"
                logger.info(f"ISP lookup for {ip} with token: {self.token[:20]}...")
            else:
                logger.warning(f"ISP lookup for {ip} WITHOUT token - may be rate limited")
            
            session = await self._get_session()
            async with session.get(url, headers=headers, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    # Prefer as_domain, fallback to as_name, then org
                    isp_name = data.get("as_domain") or data.get("as_name") or data.get("org", "Unknown ISP")
                    logger.info(f"ISP detected for {ip}: {isp_name}")
                    isp_info = {
                        "ip": ip,
                        "isp": isp_name,
                        "country": data.get("country", "Unknown"),
                        "city": data.get("city", "Unknown"),
                        "region": data.get("region", "Unknown")
                    }
                    self.cache[ip] = isp_info
                    self.last_request_time = asyncio.get_event_loop().time()
                    # Save to all caches (Redis + database)
                    await self._cache_isp_result(ip, isp_info)
                    return isp_info
                elif response.status == 429:
                    # Rate limited - set flag and return default
                    self.rate_limited = True
                    logger.warning(f"ISP detection rate limited for {ip}")
                elif response.status == 403:
                    # Forbidden - try fallback API
                    logger.warning(f"ipinfo.io returned 403 for {ip}, trying fallback API...")
                    result = await self._get_isp_fallback(ip)
                    await self._cache_isp_result(ip, result)
                    return result
                else:
                    response_text = await response.text()
                    logger.warning(f"Failed to get ISP info for {ip}: HTTP {response.status} - {response_text}")
                        
        except asyncio.TimeoutError:
            logger.error(f"Timeout getting ISP info for {ip}")
            # Try fallback on timeout
            result = await self._get_isp_fallback(ip)
            await self._cache_isp_result(ip, result)
            return result
        except Exception as e:
            logger.error(f"Error getting ISP info for {ip}: {type(e).__name__}: {e}")
            # Try fallback on any error
            result = await self._get_isp_fallback(ip)
            await self._cache_isp_result(ip, result)
            return result
        
        # Return default info if lookup fails
        default_info = {
            "ip": ip,
            "isp": "Unknown ISP",
            "country": "Unknown",
            "city": "Unknown",
            "region": "Unknown"
        }
        self.cache[ip] = default_info
        return default_info
    
    async def _save_to_db_cache(self, ip: str, isp_info: Dict[str, str]):
        """Save ISP info to database cache (by subnet)"""
        if self._db_cache and isp_info.get("isp") != "Unknown ISP":
            try:
                await self._db_cache.cache_isp(
                    ip=ip,
                    isp_name=isp_info.get("isp", "Unknown ISP"),
                    country=isp_info.get("country"),
                    city=isp_info.get("city"),
                    region=isp_info.get("region"),
                )
            except Exception as e:
                logger.warning(f"Failed to save ISP to database cache: {e}")
    
    async def _cache_isp_result(self, ip: str, isp_info: Dict[str, str]):
        """Cache ISP result to Redis (primary) and database (backup)"""
        if isp_info.get("isp") == "Unknown ISP":
            return
        
        # Cache to Redis (7 day TTL)
        if REDIS_CACHE_AVAILABLE:
            try:
                await cache_isp(ip, isp_info)
                logger.debug(f"Cached ISP for {ip} in Redis")
            except Exception as e:
                logger.warning(f"Failed to cache ISP in Redis: {e}")
        
        # Also save to database as backup
        await self._save_to_db_cache(ip, isp_info)
    
    async def _get_isp_fallback(self, ip: str) -> Dict[str, str]:
        """
        Fallback method to get ISP info using alternative free APIs
        
        Args:
            ip (str): IP address to lookup
            
        Returns:
            Dict[str, str]: ISP information dictionary
        """
        # Try ip-api.com (free, no token needed, 45 req/min)
        try:
            url = f"http://ip-api.com/json/{ip}?fields=status,message,country,countryCode,region,regionName,city,isp,org,as,asname"
            
            session = await self._get_session()
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("status") == "success":
                        # Prefer asname, fallback to isp, then org
                        isp_name = data.get("asname") or data.get("isp") or data.get("org", "Unknown ISP")
                        isp_info = {
                            "ip": ip,
                            "isp": isp_name,
                            "country": data.get("countryCode", "Unknown"),
                            "city": data.get("city", "Unknown"),
                            "region": data.get("regionName", "Unknown")
                        }
                        logger.info(f"✓ Fallback API success for {ip}: {isp_info['isp']}")
                        self.cache[ip] = isp_info
                        return isp_info
                    else:
                        logger.warning(f"Fallback API returned failure status for {ip}")
        except Exception as e:
            logger.error(f"Fallback API failed for {ip}: {e}")
        
        # If all fails, return default
        default_info = {
            "ip": ip,
            "isp": "Unknown ISP",
            "country": "Unknown",
            "city": "Unknown",
            "region": "Unknown"
        }
        return default_info
    
    async def get_multiple_isp_info(self, ips: list[str]) -> Dict[str, Dict[str, str]]:
        """
        Get ISP information for multiple IP addresses efficiently.
        Uses semaphore to limit concurrent requests and prevent rate limiting.
        
        Args:
            ips (list[str]): List of IP addresses
            
        Returns:
            Dict[str, Dict[str, str]]: Dictionary mapping IP to ISP info
        """
        if not ips:
            return {}
        
        # Filter out already cached IPs
        uncached_ips = [ip for ip in ips if ip not in self.cache]
        
        logger.info(f"📊 ISP lookup: {len(ips)} total, {len(ips) - len(uncached_ips)} cached, {len(uncached_ips)} to fetch")
        
        if uncached_ips:
            # Limit concurrent requests to avoid overwhelming the API
            semaphore = asyncio.Semaphore(5)
            
            async def bounded_get_isp_info(ip: str):
                async with semaphore:
                    try:
                        return await self.get_isp_info(ip)
                    except Exception as e:
                        logger.error(f"Error getting ISP for {ip}: {e}")
                        return {"ip": ip, "isp": "Unknown ISP", "country": "Unknown", "city": "Unknown", "region": "Unknown"}
            
            # Process in batches of 10 to be gentle on API
            batch_size = 10
            total_batches = (len(uncached_ips) + batch_size - 1) // batch_size
            
            for i in range(0, len(uncached_ips), batch_size):
                batch = uncached_ips[i:i + batch_size]
                batch_num = (i // batch_size) + 1
                logger.info(f"🔍 ISP batch {batch_num}/{total_batches}: processing {len(batch)} IPs...")
                
                tasks = [bounded_get_isp_info(ip) for ip in batch]
                try:
                    await asyncio.wait_for(
                        asyncio.gather(*tasks, return_exceptions=True),
                        timeout=30  # 30 second timeout per batch
                    )
                except asyncio.TimeoutError:
                    logger.warning(f"⚠️ ISP batch {batch_num} timed out after 30s")
                
                # Small delay between batches if we have more
                if i + batch_size < len(uncached_ips):
                    await asyncio.sleep(0.5)
            
            logger.info(f"✅ ISP lookup complete: processed {len(uncached_ips)} IPs")
        
        # Build result from cache
        def default_info(ip_addr):
            return {"ip": ip_addr, "isp": "Unknown ISP", "country": "Unknown", "city": "Unknown", "region": "Unknown"}
        return {ip: self.cache.get(ip, default_info(ip)) for ip in ips}
    
    def format_ip_with_isp(self, ip: str, isp_info: Dict[str, str]) -> str:
        """
        Format IP address with ISP information
        
        Args:
            ip (str): IP address
            isp_info (Dict[str, str]): ISP information dictionary
            
        Returns:
            str: Formatted string with IP and ISP info
        """
        isp = isp_info.get("isp", "Unknown ISP")
        country = isp_info.get("country", "Unknown")
        
        # If ISP information is unavailable or unknown, just return the IP
        if isp == "Unknown ISP" and country == "Unknown":
            return ip
        
        # Clean up ISP name (remove common prefixes)
        if isp.startswith("AS"):
            # Remove AS number prefix
            parts = isp.split(" ", 1)
            if len(parts) > 1:
                isp = parts[1]
        
        return f"{ip} ({isp}, {country})"
    
    def clear_cache(self):
        """Clear the ISP cache"""
        self.cache.clear()
