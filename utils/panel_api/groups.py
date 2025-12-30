"""
Group operations for panel API.
"""

import asyncio
import random
from ssl import SSLError

import httpx

from utils.logs import logger
from utils.types import PanelType
from utils.panel_api.auth import get_token, invalidate_token_cache


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
    max_attempts = 5
    for attempt in range(max_attempts):
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
            try:
                async with httpx.AsyncClient(verify=False) as client:
                    response = await client.get(url, headers=headers, timeout=10)
                    response.raise_for_status()
                
                try:
                    data = response.json()
                except Exception as json_error:
                    logger.error(f"Failed to parse JSON from {url}: {json_error}")
                    continue
                
                # Handle response structure
                if isinstance(data, dict) and "groups" in data:
                    return data["groups"]
                elif isinstance(data, list):
                    return data
                else:
                    logger.error(f"Unexpected groups response format: {type(data)}")
                    continue
                    
            except SSLError:
                continue
            except httpx.HTTPStatusError:
                if response.status_code == 401:
                    invalidate_token_cache()
                    logger.warning("Got 401 error, invalidating token cache and retrying")
                message = f"[{response.status_code}] {response.text}"
                logger.error(message)
                continue
            except Exception as error:
                message = f"An unexpected error occurred: {error}"
                logger.error(message)
                continue
        await asyncio.sleep(min(30, random.randint(2, 5) * (attempt + 1)))
    message = f"Failed to get groups after {max_attempts} attempts."
    logger.error(message)
    raise ValueError(message)
