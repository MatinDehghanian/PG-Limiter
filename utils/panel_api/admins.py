"""
Admin operations for panel API.
"""

import asyncio
import random
import time
from ssl import SSLError

import httpx

from utils.logs import logger, log_api_request, get_logger
from utils.types import PanelType
from utils.panel_api.auth import get_token, invalidate_token_cache

# Module logger
admins_logger = get_logger("panel_api.admins")


async def get_admins(panel_data: PanelType, force_refresh: bool = False) -> list[dict] | ValueError:
    """
    Get all admins from the panel API.

    Args:
        panel_data (PanelType): A PanelType object containing
        the username, password, and domain for the panel API.
        force_refresh (bool): If True, bypass cache.

    Returns:
        list[dict]: List of admin details including id, username, is_sudo, etc.

    Raises:
        ValueError: If the function fails to get admins from the API.
    """
    admins_logger.debug(f"👔 Fetching admins from panel (force_refresh={force_refresh})...")
    max_attempts = 5
    for attempt in range(max_attempts):
        admins_logger.debug(f"👔 Attempt {attempt + 1}/{max_attempts}")
        force_token_refresh = attempt > 0 or force_refresh
        get_panel_token = await get_token(panel_data, force_refresh=force_token_refresh)
        if isinstance(get_panel_token, ValueError):
            raise get_panel_token
        token = get_panel_token.panel_token
        headers = {
            "Authorization": f"Bearer {token}",
        }
        for scheme in ["https", "http"]:
            url = f"{scheme}://{panel_data.panel_domain}/api/admins"
            start_time = time.perf_counter()
            try:
                async with httpx.AsyncClient(verify=False) as client:
                    response = await client.get(url, headers=headers, timeout=10)
                    elapsed = (time.perf_counter() - start_time) * 1000
                    response.raise_for_status()
                
                log_api_request("GET", url, response.status_code, elapsed)
                
                try:
                    data = response.json()
                except Exception as json_error:
                    admins_logger.error(f"Failed to parse JSON from {url}: {json_error}")
                    continue
                
                # Handle response structure - AdminsResponse has "admins" key
                admins = None
                if isinstance(data, dict) and "admins" in data:
                    admins = data["admins"]
                elif isinstance(data, list):
                    admins = data
                else:
                    admins_logger.error(f"Unexpected admins response format: {type(data)}")
                    continue
                
                admins_logger.info(f"👔 Fetched {len(admins)} admins [{elapsed:.0f}ms]")
                for admin in admins:
                    is_sudo = admin.get("is_sudo", False)
                    admins_logger.debug(f"  └─ {admin.get('username', 'Unknown')} (sudo={is_sudo})")
                return admins
                    
            except SSLError:
                elapsed = (time.perf_counter() - start_time) * 1000
                log_api_request("GET", url, None, elapsed, "SSL Error")
                continue
            except httpx.HTTPStatusError:
                elapsed = (time.perf_counter() - start_time) * 1000
                if response.status_code == 401:
                    await invalidate_token_cache()
                    admins_logger.warning("Got 401 error, invalidating token cache and retrying")
                elif response.status_code == 403:
                    log_api_request("GET", url, 403, elapsed, "Forbidden")
                    admins_logger.error("Forbidden: Current user doesn't have permission to list admins")
                    raise ValueError("Forbidden: Need sudo permissions to list admins")
                log_api_request("GET", url, response.status_code, elapsed, f"HTTP {response.status_code}")
                message = f"[{response.status_code}] {response.text}"
                admins_logger.error(message)
                continue
            except httpx.TimeoutException:
                elapsed = (time.perf_counter() - start_time) * 1000
                log_api_request("GET", url, None, elapsed, "Timeout")
                admins_logger.warning(f"Timeout fetching admins from {url}")
                continue
            except Exception as error:
                elapsed = (time.perf_counter() - start_time) * 1000
                log_api_request("GET", url, None, elapsed, str(error))
                message = f"An unexpected error occurred: {error}"
                admins_logger.error(message)
                continue
        wait_time = min(30, random.randint(2, 5) * (attempt + 1))
        admins_logger.debug(f"Waiting {wait_time}s before retry...")
        await asyncio.sleep(wait_time)
    message = f"Failed to get admins after {max_attempts} attempts."
    admins_logger.error(message)
    raise ValueError(message)
