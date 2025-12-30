"""
Group operations for panel API.
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
groups_logger = get_logger("panel_api.groups")


async def get_groups(panel_data: PanelType) -> list[dict] | ValueError:
    """
    Get all groups from the panel API.

    Args:
        panel_data (PanelType): A PanelType object containing
        the username, password, and domain for the panel API.

    Returns:
        list[dict]: The list of groups with id, name, and other info.

    Raises:
        ValueError: If the function fails to get groups from the API.
    """
    groups_logger.debug("👥 Fetching groups from panel...")
    max_attempts = 5
    for attempt in range(max_attempts):
        groups_logger.debug(f"👥 Attempt {attempt + 1}/{max_attempts}")
        force_refresh = attempt > 0
        get_panel_token = await get_token(panel_data, force_refresh=force_refresh)
        if isinstance(get_panel_token, ValueError):
            raise get_panel_token
        token = get_panel_token.panel_token
        headers = {
            "Authorization": f"Bearer {token}",
        }
        for scheme in ["https", "http"]:
            url = f"{scheme}://{panel_data.panel_domain}/api/groups"
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
                    groups_logger.error(f"Failed to parse JSON from {url}: {json_error}")
                    continue
                
                # Handle response structure
                groups = None
                if isinstance(data, dict) and "groups" in data:
                    groups = data["groups"]
                elif isinstance(data, list):
                    groups = data
                else:
                    groups_logger.error(f"Unexpected groups response format: {type(data)}")
                    continue
                
                groups_logger.info(f"👥 Fetched {len(groups)} groups [{elapsed:.0f}ms]")
                for group in groups:
                    groups_logger.debug(f"  └─ {group.get('name', 'Unknown')} (id={group.get('id', '?')})")
                return groups
                    
            except SSLError:
                elapsed = (time.perf_counter() - start_time) * 1000
                log_api_request("GET", url, None, elapsed, "SSL Error")
                continue
            except httpx.HTTPStatusError:
                elapsed = (time.perf_counter() - start_time) * 1000
                if response.status_code == 401:
                    await invalidate_token_cache()
                    groups_logger.warning("Got 401 error, invalidating token cache and retrying")
                log_api_request("GET", url, response.status_code, elapsed, f"HTTP {response.status_code}")
                message = f"[{response.status_code}] {response.text}"
                groups_logger.error(message)
                continue
            except httpx.TimeoutException:
                elapsed = (time.perf_counter() - start_time) * 1000
                log_api_request("GET", url, None, elapsed, "Timeout")
                groups_logger.warning(f"Timeout fetching groups from {url}")
                continue
            except Exception as error:
                elapsed = (time.perf_counter() - start_time) * 1000
                log_api_request("GET", url, None, elapsed, str(error))
                message = f"An unexpected error occurred: {error}"
                groups_logger.error(message)
                continue
        wait_time = min(30, random.randint(2, 5) * (attempt + 1))
        groups_logger.debug(f"Waiting {wait_time}s before retry...")
        await asyncio.sleep(wait_time)
    message = f"Failed to get groups after {max_attempts} attempts."
    groups_logger.error(message)
    raise ValueError(message)
