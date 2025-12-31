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
                async with asyncio.timeout(2):  # 2 second Redis timeout
                    cached = await get_cached_isp(ip)
                    if cached:
                        logger.debug(f"ISP Redis cache hit for {ip}")
                        # Also store in memory cache
                        self.cache[ip] = cached
                        return cached
            except asyncio.TimeoutError:
                logger.warning(f"Redis cache timeout for {ip}")
            except Exception as e:
                logger.warning(f"Redis cache lookup failed for {ip}: {e}")
        
        # Check memory cache
        if ip in self.cache:
            return self.cache[ip]
        
        # Check database cache (by subnet) if enabled
        if self._db_cache:
            try:
                async with asyncio.timeout(3):  # 3 second DB cache timeout
                    cached = await self._db_cache.get_cached_isp(ip)
                    if cached:
                        # Copy to memory cache and Redis
                        self.cache[ip] = cached
                        await self._cache_isp_result(ip, cached)
                        logger.debug(f"ISP cache hit for {ip} (subnet cache)")
                        return cached
            except asyncio.TimeoutError:
                logger.warning(f"DB cache timeout for {ip}")
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
                logger.debug(f"ISP lookup for {ip} with token")
            else:
                logger.debug(f"ISP lookup for {ip} without token")
            
            session = await self._get_session()
            # Wrap entire API call in timeout
            async with asyncio.timeout(10):
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=8)) as response:
                    if response.status == 200:
                        data = await response.json()
                        # Prefer as_domain, fallback to as_name, then org
                        isp_name = data.get("as_domain") or data.get("as_name") or data.get("org", "Unknown ISP")
                        logger.debug(f"ISP detected for {ip}: {isp_name}")
                        isp_info = {
                            "ip": ip,
                            "isp": isp_name,
                            "country": data.get("country", "Unknown"),
                            "city": data.get("city", "Unknown"),
                            "region": data.get("region", "Unknown")
                        }
                        self.cache[ip] = isp_info
                        self.last_request_time = asyncio.get_event_loop().time()
                        # Save to all caches (Redis + database) - don't await, fire and forget
                        asyncio.create_task(self._cache_isp_result(ip, isp_info))
                        return isp_info
                    elif response.status == 429:
                        # Rate limited - set flag and return default
                        self.rate_limited = True
                        logger.warning(f"ISP detection rate limited for {ip}")
                    elif response.status == 403:
                        # Forbidden - try fallback API
                        logger.warning(f"ipinfo.io returned 403 for {ip}, trying fallback API...")
                        result = await self._get_isp_fallback(ip)
                        asyncio.create_task(self._cache_isp_result(ip, result))
                        return result
                    else:
                        response_text = await response.text()
                        logger.warning(f"Failed to get ISP info for {ip}: HTTP {response.status} - {response_text[:100]}")
                        
        except asyncio.TimeoutError:
            logger.warning(f"⏱️ Timeout getting ISP info for {ip}, trying fallback...")
            # Try fallback on timeout - don't wait for cache
            result = await self._get_isp_fallback(ip)
            asyncio.create_task(self._cache_isp_result(ip, result))
            return result
        except Exception as e:
            logger.warning(f"❌ Error getting ISP info for {ip}: {type(e).__name__}, trying fallback...")
            # Try fallback on any error - don't wait for cache
            result = await self._get_isp_fallback(ip)
            asyncio.create_task(self._cache_isp_result(ip, result))
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
                async with asyncio.timeout(3):  # 3 second DB timeout
                    await self._db_cache.cache_isp(
                        ip=ip,
                        isp_name=isp_info.get("isp", "Unknown ISP"),
                        country=isp_info.get("country"),
                        city=isp_info.get("city"),
                        region=isp_info.get("region"),
                    )
            except asyncio.TimeoutError:
                logger.debug(f"DB cache save timeout for {ip}")
            except Exception as e:
                logger.warning(f"Failed to save ISP to database cache: {e}")
    
    async def _cache_isp_result(self, ip: str, isp_info: Dict[str, str]):
        """Cache ISP result to Redis (primary) and database (backup) - non-blocking"""
        if isp_info.get("isp") == "Unknown ISP":
            return
        
        # Cache to Redis (7 day TTL) - with timeout
        if REDIS_CACHE_AVAILABLE:
            try:
                async with asyncio.timeout(2):  # 2 second Redis timeout
                    await cache_isp(ip, isp_info)
                    logger.debug(f"Cached ISP for {ip} in Redis")
            except asyncio.TimeoutError:
                logger.debug(f"Redis cache timeout for {ip}")
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
            # Wrap in timeout to prevent hanging
            async with asyncio.timeout(8):  # 8 second timeout for API call
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as response:
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
                            logger.debug(f"✓ Fallback API success for {ip}: {isp_info['isp']}")
                            self.cache[ip] = isp_info
                            return isp_info
                        else:
                            logger.warning(f"Fallback API returned failure for {ip}: {data.get('message', 'unknown')}")
                    elif response.status == 429:
                        logger.warning(f"Fallback API rate limited for {ip}")
                    else:
                        logger.warning(f"Fallback API HTTP {response.status} for {ip}")
        except asyncio.TimeoutError:
            logger.warning(f"Fallback API timeout for {ip}")
        except Exception as e:
            logger.warning(f"Fallback API error for {ip}: {type(e).__name__}: {str(e)[:100]}")
        
        # If all fails, return default
        default_info = {
            "ip": ip,
            "isp": "Unknown ISP",
            "country": "Unknown",
            "city": "Unknown",
            "region": "Unknown"
        }
        self.cache[ip] = default_info
        return default_info
    
    async def get_multiple_isp_info(self, ips: list[str]) -> Dict[str, Dict[str, str]]:
        """
        Get ISP information for multiple IP addresses efficiently.
        Uses semaphore to limit concurrent requests and prevent rate limiting.
        Uses subnet-based caching to reduce API calls.
        
        Args:
            ips (list[str]): List of IP addresses
            
        Returns:
            Dict[str, Dict[str, str]]: Dictionary mapping IP to ISP info
        """
        if not ips:
            return {}
        
        # Group IPs by subnet to optimize database lookups
        from db.crud.subnet_isp import SubnetISPCRUD
        subnet_to_ips = {}
        for ip in ips:
            subnet = SubnetISPCRUD.get_subnet_from_ip(ip)
            if subnet not in subnet_to_ips:
                subnet_to_ips[subnet] = []
            subnet_to_ips[subnet].append(ip)
        
        logger.info(f"📊 ISP lookup: {len(ips)} IPs across {len(subnet_to_ips)} subnets")
        
        # Check database cache for all subnets first
        if self._db_cache:
            from db.database import get_db
            cached_subnets = 0
            async with get_db() as db:
                for subnet in list(subnet_to_ips.keys()):
                    try:
                        cached = await SubnetISPCRUD.get_by_subnet(db, subnet)
                        if cached:
                            cached_subnets += 1
                            # Apply cached info to all IPs in this subnet
                            isp_info = {
                                "ip": "",
                                "isp": cached.isp or "Unknown ISP",
                                "country": cached.country or "Unknown",
                                "city": cached.city or "Unknown",
                                "region": cached.region or "Unknown"
                            }
                            for ip in subnet_to_ips[subnet]:
                                isp_info_copy = isp_info.copy()
                                isp_info_copy["ip"] = ip
                                self.cache[ip] = isp_info_copy
                            # Remove this subnet from lookup list
                            del subnet_to_ips[subnet]
                    except Exception as e:
                        logger.warning(f"Failed to check subnet cache for {subnet}: {e}")
            
            if cached_subnets > 0:
                logger.info(f"✅ Found {cached_subnets} subnets in cache, {len(subnet_to_ips)} need API lookup")
        
        # Filter out already cached IPs
        uncached_ips = []
        for subnet_ips in subnet_to_ips.values():
            for ip in subnet_ips:
                if ip not in self.cache:
                    uncached_ips.append(ip)
        
        if uncached_ips:
            logger.info(f"🔍 Fetching {len(uncached_ips)} uncached IPs from API...")
            
            # ip-api.com free tier: 45 requests/minute
            # Use smaller batches with delays to respect rate limit
            semaphore = asyncio.Semaphore(3)  # Reduced from 5 to 3 concurrent
            
            async def bounded_get_isp_info(ip: str):
                async with semaphore:
                    try:
                        logger.debug(f"🔍 Starting ISP lookup for {ip}...")
                        # Wrap in timeout to prevent individual IP from hanging
                        result = await asyncio.wait_for(
                            self.get_isp_info(ip),
                            timeout=12  # 12 second timeout per IP
                        )
                        logger.debug(f"✅ Got ISP for {ip}: {result.get('isp', 'Unknown')[:30]}")
                        # Save to database cache - with its own timeout
                        if result.get("isp") != "Unknown ISP" and self._db_cache:
                            try:
                                from db.database import get_db
                                async with asyncio.timeout(5):  # 5 second DB timeout
                                    async with get_db() as db:
                                        await SubnetISPCRUD.cache_isp(
                                            db, ip,
                                            isp=result.get("isp", "Unknown ISP"),
                                            country=result.get("country"),
                                            city=result.get("city"),
                                            region=result.get("region")
                                        )
                            except asyncio.TimeoutError:
                                logger.debug(f"DB cache timeout for {ip}")
                            except Exception as e:
                                logger.debug(f"DB cache failed for {ip}: {e}")
                        return result
                    except asyncio.TimeoutError:
                        logger.warning(f"⏱️ Timeout for {ip}, using default")
                        return {"ip": ip, "isp": "Unknown ISP", "country": "Unknown", "city": "Unknown", "region": "Unknown"}
                    except Exception as e:
                        logger.warning(f"❌ Error for {ip}: {type(e).__name__}")
                        return {"ip": ip, "isp": "Unknown ISP", "country": "Unknown", "city": "Unknown", "region": "Unknown"}
            
            # Process in smaller batches with longer delays to respect rate limits
            # 45 req/min = 1 request per 1.33 seconds
            # Use batches of 5 with 2 second delay = ~25 req/min (safe margin)
            batch_size = 5
            total_batches = (len(uncached_ips) + batch_size - 1) // batch_size
            
            for i in range(0, len(uncached_ips), batch_size):
                batch = uncached_ips[i:i + batch_size]
                batch_num = (i // batch_size) + 1
                logger.info(f"🔍 ISP batch {batch_num}/{total_batches}: {len(batch)} IPs: {batch}")
                
                try:
                    tasks = [bounded_get_isp_info(ip) for ip in batch]
                    logger.debug(f"📦 Created {len(tasks)} tasks for batch {batch_num}")
                    # Use asyncio.gather with return_exceptions to handle errors gracefully
                    results = await asyncio.wait_for(
                        asyncio.gather(*tasks, return_exceptions=True),
                        timeout=40  # 40 second timeout per batch (5 IPs * 12s + buffer)
                    )
                    logger.debug(f"📦 Batch {batch_num} gather completed")
                    # Check for exceptions in results
                    failed = sum(1 for r in results if isinstance(r, Exception))
                    if failed > 0:
                        logger.warning(f"⚠️ Batch {batch_num}: {failed}/{len(batch)} failed")
                    else:
                        logger.info(f"✅ Batch {batch_num}/{total_batches} complete")
                except asyncio.TimeoutError:
                    logger.warning(f"⚠️ Batch {batch_num} timed out after 40s, continuing...")
                except Exception as e:
                    logger.error(f"⚠️ Batch {batch_num} error: {type(e).__name__}: {e}, continuing...")
                
                # Delay between batches to respect rate limits (2 seconds)
                if i + batch_size < len(uncached_ips):
                    logger.debug(f"⏳ Waiting 2s before next batch...")
                    await asyncio.sleep(2.0)
            
            logger.info(f"✅ ISP lookup complete: processed {len(uncached_ips)} IPs")
        else:
            logger.info("✅ All IPs found in cache")
        
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
