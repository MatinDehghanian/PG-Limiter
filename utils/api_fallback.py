"""
API Fallback and Retry Utilities

This module provides reusable utilities for handling API requests with
automatic retry and fallback mechanisms.
"""

import asyncio
import functools
import time
from typing import TypeVar, Callable, Any, Optional, List
import httpx
from ssl import SSLError

from utils.logs import logger

T = TypeVar('T')


# Track API endpoint health for intelligent routing
_endpoint_health = {}


def get_endpoint_health(endpoint: str) -> dict:
    """Get health info for an endpoint."""
    if endpoint not in _endpoint_health:
        _endpoint_health[endpoint] = {
            "failures": 0,
            "successes": 0,
            "last_success": 0,
            "last_failure": 0,
            "consecutive_failures": 0,
        }
    return _endpoint_health[endpoint]


def record_success(endpoint: str):
    """Record a successful request to an endpoint."""
    health = get_endpoint_health(endpoint)
    health["successes"] += 1
    health["last_success"] = time.time()
    health["consecutive_failures"] = 0
    # Decay failure count on success
    health["failures"] = max(0, health["failures"] - 1)


def record_failure(endpoint: str, is_timeout: bool = False):
    """Record a failed request to an endpoint."""
    health = get_endpoint_health(endpoint)
    health["failures"] += 2 if is_timeout else 1
    health["last_failure"] = time.time()
    health["consecutive_failures"] += 1


def is_endpoint_healthy(endpoint: str) -> bool:
    """Check if an endpoint is considered healthy."""
    health = get_endpoint_health(endpoint)
    # Consider unhealthy if 5+ consecutive failures in last 5 minutes
    if health["consecutive_failures"] >= 5:
        if time.time() - health["last_failure"] < 300:  # 5 minutes
            return False
    return True


def async_retry(
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 30.0,
    exponential_base: float = 2.0,
    exceptions: tuple = (Exception,),
    on_retry: Optional[Callable[[int, Exception], None]] = None,
):
    """
    Decorator for async functions that retries on failure with exponential backoff.
    
    Args:
        max_attempts: Maximum number of retry attempts
        initial_delay: Initial delay between retries in seconds
        max_delay: Maximum delay between retries
        exponential_base: Base for exponential backoff calculation
        exceptions: Tuple of exceptions to catch and retry on
        on_retry: Optional callback function(attempt, exception) called before retry
    
    Example:
        @async_retry(max_attempts=3, initial_delay=1.0)
        async def fetch_data():
            return await api_call()
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            last_exception = None
            delay = initial_delay
            
            for attempt in range(1, max_attempts + 1):
                try:
                    result = await func(*args, **kwargs)
                    return result
                except exceptions as e:
                    last_exception = e
                    
                    if attempt == max_attempts:
                        logger.warning(
                            f"[{func.__name__}] All {max_attempts} attempts failed. "
                            f"Last error: {type(e).__name__}: {str(e)[:100]}"
                        )
                        raise
                    
                    if on_retry:
                        on_retry(attempt, e)
                    
                    logger.debug(
                        f"[{func.__name__}] Attempt {attempt}/{max_attempts} failed: "
                        f"{type(e).__name__}. Retrying in {delay:.1f}s..."
                    )
                    
                    await asyncio.sleep(delay)
                    delay = min(delay * exponential_base, max_delay)
            
            raise last_exception
        
        return wrapper
    return decorator


async def fetch_with_fallback(
    urls: List[str],
    method: str = "GET",
    headers: Optional[dict] = None,
    json_data: Optional[dict] = None,
    timeout: float = 10.0,
    verify: bool = False,
    parse_json: bool = True,
) -> Optional[Any]:
    """
    Fetch from multiple URLs with automatic fallback.
    
    Tries each URL in order, falling back to the next one on failure.
    Tracks endpoint health to prioritize working endpoints.
    
    Args:
        urls: List of URLs to try in order
        method: HTTP method (GET, POST, PUT, etc.)
        headers: Request headers
        json_data: JSON body for POST/PUT requests
        timeout: Request timeout in seconds
        verify: Whether to verify SSL certificates
        parse_json: Whether to parse response as JSON
    
    Returns:
        Response data or None if all URLs fail
    
    Example:
        data = await fetch_with_fallback([
            "https://api1.example.com/data",
            "https://api2.example.com/data",
        ])
    """
    if not urls:
        return None
    
    # Sort by health (healthiest first)
    sorted_urls = sorted(
        urls,
        key=lambda u: (
            not is_endpoint_healthy(u),
            get_endpoint_health(u)["consecutive_failures"],
        )
    )
    
    last_error = None
    
    for url in sorted_urls:
        try:
            async with httpx.AsyncClient(verify=verify, timeout=timeout) as client:
                if method.upper() == "GET":
                    response = await client.get(url, headers=headers)
                elif method.upper() == "POST":
                    response = await client.post(url, headers=headers, json=json_data)
                elif method.upper() == "PUT":
                    response = await client.put(url, headers=headers, json=json_data)
                elif method.upper() == "DELETE":
                    response = await client.delete(url, headers=headers)
                else:
                    response = await client.request(method, url, headers=headers, json=json_data)
                
                if response.status_code == 200:
                    record_success(url)
                    if parse_json:
                        return response.json()
                    return response.text
                elif response.status_code == 429:
                    # Rate limited - heavy penalty
                    record_failure(url)
                    record_failure(url)
                    last_error = f"Rate limited: {url}"
                else:
                    record_failure(url)
                    last_error = f"HTTP {response.status_code}: {url}"
                    
        except httpx.TimeoutException:
            record_failure(url, is_timeout=True)
            last_error = f"Timeout: {url}"
        except SSLError:
            record_failure(url)
            last_error = f"SSL Error: {url}"
        except Exception as e:
            record_failure(url)
            last_error = f"{type(e).__name__}: {url}"
    
    logger.warning(f"All fallback URLs failed. Last error: {last_error}")
    return None


class APIClient:
    """
    API Client with built-in retry and fallback support.
    
    Example:
        client = APIClient(
            base_urls=["https://api1.example.com", "https://api2.example.com"],
            headers={"Authorization": "Bearer token"}
        )
        data = await client.get("/users")
    """
    
    def __init__(
        self,
        base_urls: List[str],
        headers: Optional[dict] = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        verify_ssl: bool = False,
    ):
        self.base_urls = base_urls
        self.headers = headers or {}
        self.timeout = timeout
        self.max_retries = max_retries
        self.verify_ssl = verify_ssl
    
    async def request(
        self,
        method: str,
        path: str,
        headers: Optional[dict] = None,
        json_data: Optional[dict] = None,
        timeout: Optional[float] = None,
    ) -> Optional[Any]:
        """Make a request with automatic fallback across base URLs."""
        urls = [f"{base.rstrip('/')}/{path.lstrip('/')}" for base in self.base_urls]
        merged_headers = {**self.headers, **(headers or {})}
        
        return await fetch_with_fallback(
            urls=urls,
            method=method,
            headers=merged_headers,
            json_data=json_data,
            timeout=timeout or self.timeout,
            verify=self.verify_ssl,
        )
    
    async def get(self, path: str, **kwargs) -> Optional[Any]:
        """Make a GET request."""
        return await self.request("GET", path, **kwargs)
    
    async def post(self, path: str, json_data: dict = None, **kwargs) -> Optional[Any]:
        """Make a POST request."""
        return await self.request("POST", path, json_data=json_data, **kwargs)
    
    async def put(self, path: str, json_data: dict = None, **kwargs) -> Optional[Any]:
        """Make a PUT request."""
        return await self.request("PUT", path, json_data=json_data, **kwargs)
    
    async def delete(self, path: str, **kwargs) -> Optional[Any]:
        """Make a DELETE request."""
        return await self.request("DELETE", path, **kwargs)


def get_health_report() -> dict:
    """Get a report of all endpoint health statuses."""
    return {
        endpoint: {
            "healthy": is_endpoint_healthy(endpoint),
            **health,
        }
        for endpoint, health in _endpoint_health.items()
    }


def reset_endpoint_health(endpoint: Optional[str] = None):
    """Reset health tracking for one or all endpoints."""
    global _endpoint_health
    if endpoint:
        if endpoint in _endpoint_health:
            del _endpoint_health[endpoint]
    else:
        _endpoint_health = {}
