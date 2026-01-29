"""
Panel API Request Helper with Fallback and Retry

This module provides a unified way to make panel API requests with:
- Automatic retry with exponential backoff
- Fallback between HTTPS and HTTP
- Token refresh on 401 errors
- Proper error logging
"""

import asyncio
import time
from ssl import SSLError
from typing import Optional, Any, Literal

import httpx

from utils.logs import log_api_request, get_logger
from utils.types import PanelType
from utils.panel_api.auth import get_token, invalidate_token_cache

# Module logger
request_logger = get_logger("panel_api.request")

# Track panel endpoint health
_panel_health = {
    "https_failures": 0,
    "http_failures": 0,
    "last_https_success": 0,
    "last_http_success": 0,
    "prefer_https": True,  # Start with HTTPS preference
}


def _get_scheme_order() -> list[str]:
    """Get the order of schemes to try based on recent success/failure."""
    # If HTTPS has too many failures, try HTTP first
    if _panel_health["https_failures"] >= 3 and _panel_health["http_failures"] < _panel_health["https_failures"]:
        return ["http", "https"]
    return ["https", "http"]


def _record_success(scheme: str):
    """Record a successful request."""
    _panel_health[f"{scheme}_failures"] = 0
    _panel_health[f"last_{scheme}_success"] = time.time()


def _record_failure(scheme: str):
    """Record a failed request."""
    _panel_health[f"{scheme}_failures"] = _panel_health.get(f"{scheme}_failures", 0) + 1


async def panel_request(
    panel_data: PanelType,
    method: Literal["GET", "POST", "PUT", "DELETE"],
    endpoint: str,
    token: str,
    json_data: Optional[dict] = None,
    form_data: Optional[dict] = None,
    timeout: float = 30.0,
    max_retries: int = 3,
    retry_delay: float = 1.0,
) -> tuple[Optional[httpx.Response], Optional[str]]:
    """
    Make a panel API request with automatic retry and scheme fallback.
    
    Args:
        panel_data: Panel connection data
        method: HTTP method
        endpoint: API endpoint (e.g., "/api/users")
        token: Bearer token for authorization
        json_data: JSON body for POST/PUT requests
        form_data: Form data for POST requests
        timeout: Request timeout in seconds
        max_retries: Maximum number of retry attempts
        retry_delay: Initial delay between retries (doubles each retry)
    
    Returns:
        Tuple of (response, error_message)
        - On success: (response, None)
        - On failure: (None, error_message)
    """
    headers = {"Authorization": f"Bearer {token}"}
    last_error = None
    
    for attempt in range(max_retries):
        schemes = _get_scheme_order()
        
        for scheme in schemes:
            url = f"{scheme}://{panel_data.panel_domain}{endpoint}"
            start_time = time.perf_counter()
            
            try:
                async with httpx.AsyncClient(verify=False, timeout=timeout) as client:
                    if method == "GET":
                        response = await client.get(url, headers=headers)
                    elif method == "POST":
                        if form_data:
                            response = await client.post(url, headers=headers, data=form_data)
                        else:
                            response = await client.post(url, headers=headers, json=json_data)
                    elif method == "PUT":
                        response = await client.put(url, headers=headers, json=json_data)
                    elif method == "DELETE":
                        response = await client.delete(url, headers=headers)
                    else:
                        response = await client.request(method, url, headers=headers, json=json_data)
                    
                    elapsed = (time.perf_counter() - start_time) * 1000
                    log_api_request(method, url, response.status_code, elapsed)
                    
                    # Success
                    if response.status_code in (200, 201, 204):
                        _record_success(scheme)
                        return response, None
                    
                    # Auth error - caller should refresh token
                    if response.status_code == 401:
                        _record_failure(scheme)
                        return response, "Unauthorized - token may be expired"
                    
                    # Not found
                    if response.status_code == 404:
                        _record_success(scheme)  # Server responded, just not found
                        return response, None
                    
                    # Rate limited
                    if response.status_code == 429:
                        _record_failure(scheme)
                        _record_failure(scheme)  # Double penalty for rate limit
                        last_error = f"Rate limited (429) on {url}"
                        request_logger.warning(last_error)
                        await asyncio.sleep(retry_delay * 2)
                        continue
                    
                    # Server error - retry
                    if response.status_code >= 500:
                        _record_failure(scheme)
                        last_error = f"Server error ({response.status_code}) on {url}"
                        request_logger.warning(last_error)
                        continue
                    
                    # Other errors
                    _record_failure(scheme)
                    last_error = f"HTTP {response.status_code}: {response.text[:100]}"
                    
            except SSLError as e:
                elapsed = (time.perf_counter() - start_time) * 1000
                log_api_request(method, url, None, elapsed, f"SSL Error")
                _record_failure(scheme)
                last_error = f"SSL Error on {url}: {str(e)[:50]}"
                continue
                
            except httpx.TimeoutException:
                elapsed = (time.perf_counter() - start_time) * 1000
                log_api_request(method, url, None, elapsed, "Timeout")
                _record_failure(scheme)
                _record_failure(scheme)  # Double penalty for timeout
                last_error = f"Timeout on {url}"
                request_logger.warning(last_error)
                continue
                
            except httpx.ConnectError as e:
                elapsed = (time.perf_counter() - start_time) * 1000
                log_api_request(method, url, None, elapsed, "Connection Error")
                _record_failure(scheme)
                last_error = f"Connection error on {url}: {str(e)[:50]}"
                continue
                
            except Exception as e:
                elapsed = (time.perf_counter() - start_time) * 1000
                log_api_request(method, url, None, elapsed, str(e)[:50])
                _record_failure(scheme)
                last_error = f"Error on {url}: {type(e).__name__}: {str(e)[:50]}"
                request_logger.error(last_error)
                continue
        
        # All schemes failed for this attempt, wait before retry
        if attempt < max_retries - 1:
            wait_time = retry_delay * (2 ** attempt)
            request_logger.debug(f"Retrying in {wait_time:.1f}s (attempt {attempt + 1}/{max_retries})")
            await asyncio.sleep(wait_time)
    
    return None, last_error or "All attempts failed"


async def _get_token_for_request(panel_data: PanelType, force_refresh: bool = False) -> Optional[str]:
    """Get a valid token for making requests."""
    try:
        token_result = await get_token(panel_data, force_refresh=force_refresh)
        if isinstance(token_result, ValueError):
            request_logger.error(f"Failed to get token: {token_result}")
            return None
        return token_result.panel_token
    except Exception as e:
        request_logger.error(f"Token acquisition error: {e}")
        return None


async def panel_get(
    panel_data: PanelType,
    endpoint: str,
    force_refresh: bool = False,
    **kwargs
) -> Optional[httpx.Response]:
    """
    Convenience wrapper for GET requests with automatic token handling.
    
    Args:
        panel_data: Panel connection data
        endpoint: API endpoint (e.g., "/api/users")
        force_refresh: Force token refresh
        **kwargs: Additional arguments passed to panel_request
    
    Returns:
        Response on success, None on failure
    """
    token = await _get_token_for_request(panel_data, force_refresh)
    if not token:
        return None
    
    response, error = await panel_request(panel_data, "GET", endpoint, token, **kwargs)
    
    # On 401, retry with fresh token
    if response and response.status_code == 401 and not force_refresh:
        await invalidate_token_cache()
        token = await _get_token_for_request(panel_data, force_refresh=True)
        if token:
            response, error = await panel_request(panel_data, "GET", endpoint, token, **kwargs)
    
    return response


async def panel_post(
    panel_data: PanelType,
    endpoint: str,
    json_data: Optional[dict] = None,
    force_refresh: bool = False,
    **kwargs
) -> Optional[httpx.Response]:
    """
    Convenience wrapper for POST requests with automatic token handling.
    
    Args:
        panel_data: Panel connection data
        endpoint: API endpoint
        json_data: JSON body for the request
        force_refresh: Force token refresh
        **kwargs: Additional arguments passed to panel_request
    
    Returns:
        Response on success, None on failure
    """
    token = await _get_token_for_request(panel_data, force_refresh)
    if not token:
        return None
    
    response, error = await panel_request(panel_data, "POST", endpoint, token, json_data=json_data, **kwargs)
    
    # On 401, retry with fresh token
    if response and response.status_code == 401 and not force_refresh:
        await invalidate_token_cache()
        token = await _get_token_for_request(panel_data, force_refresh=True)
        if token:
            response, error = await panel_request(panel_data, "POST", endpoint, token, json_data=json_data, **kwargs)
    
    return response


async def panel_put(
    panel_data: PanelType,
    endpoint: str,
    json_data: Optional[dict] = None,
    force_refresh: bool = False,
    **kwargs
) -> Optional[httpx.Response]:
    """
    Convenience wrapper for PUT requests with automatic token handling.
    
    Args:
        panel_data: Panel connection data
        endpoint: API endpoint
        json_data: JSON body for the request
        force_refresh: Force token refresh
        **kwargs: Additional arguments passed to panel_request
    
    Returns:
        Response on success, None on failure
    """
    token = await _get_token_for_request(panel_data, force_refresh)
    if not token:
        return None
    
    response, error = await panel_request(panel_data, "PUT", endpoint, token, json_data=json_data, **kwargs)
    
    # On 401, retry with fresh token
    if response and response.status_code == 401 and not force_refresh:
        await invalidate_token_cache()
        token = await _get_token_for_request(panel_data, force_refresh=True)
        if token:
            response, error = await panel_request(panel_data, "PUT", endpoint, token, json_data=json_data, **kwargs)
    
    return response


async def panel_delete(
    panel_data: PanelType,
    endpoint: str,
    force_refresh: bool = False,
    **kwargs
) -> Optional[httpx.Response]:
    """
    Convenience wrapper for DELETE requests with automatic token handling.
    
    Args:
        panel_data: Panel connection data
        endpoint: API endpoint
        force_refresh: Force token refresh
        **kwargs: Additional arguments passed to panel_request
    
    Returns:
        Response on success, None on failure
    """
    token = await _get_token_for_request(panel_data, force_refresh)
    if not token:
        return None
    
    response, error = await panel_request(panel_data, "DELETE", endpoint, token, **kwargs)
    
    # On 401, retry with fresh token
    if response and response.status_code == 401 and not force_refresh:
        await invalidate_token_cache()
        token = await _get_token_for_request(panel_data, force_refresh=True)
        if token:
            response, error = await panel_request(panel_data, "DELETE", endpoint, token, **kwargs)
    
    return response


def get_panel_health() -> dict:
    """Get current panel endpoint health status."""
    return {
        "https": {
            "failures": _panel_health["https_failures"],
            "last_success": _panel_health["last_https_success"],
        },
        "http": {
            "failures": _panel_health["http_failures"],
            "last_success": _panel_health["last_http_success"],
        },
        "preferred_scheme": _get_scheme_order()[0],
    }


def reset_panel_health():
    """Reset panel health tracking."""
    global _panel_health
    _panel_health = {
        "https_failures": 0,
        "http_failures": 0,
        "last_https_success": 0,
        "last_http_success": 0,
        "prefer_https": True,
    }
