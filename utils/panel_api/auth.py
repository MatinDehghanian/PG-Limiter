"""
Authentication and token management for panel API.
"""

import asyncio
import random
import sys
from ssl import SSLError

try:
    import httpx
except ImportError:
    print("Module 'httpx' is not installed use: 'pip install httpx' to install it")
    sys.exit()

from utils.logs import logger
from utils.types import PanelType

# Token cache to reduce API requests
_token_cache = {
    "token": None,
    "expires_at": 0,
    "panel_domain": None
}


def invalidate_token_cache():
    """Invalidate the cached token (useful when getting 401 errors)"""
    _token_cache["token"] = None
    _token_cache["expires_at"] = 0
    logger.info("Token cache invalidated")


async def safe_send_logs_panel(message: str):
    """Safely send logs from panel_api, handling import errors gracefully"""
    try:
        from telegram_bot.send_message import send_logs
        await send_logs(message)
    except ImportError as e:
        logger.warning(f"Could not import send_logs: {e}")
    except Exception as e:
        logger.error(f"Failed to send telegram message: {e}")


async def get_token(panel_data: PanelType, force_refresh: bool = False) -> PanelType | ValueError:
    """
    Get access token from the panel API with caching to reduce API requests.
    Tokens are cached for 30 minutes to minimize unnecessary API calls.
    
    Args:
        panel_data (PanelType): A PanelType object containing
        the username, password, and domain for the panel API.
        force_refresh (bool): Force getting a new token even if cached one exists.

    Returns:
        PanelType: The panel data with access token set.

    Raises:
        ValueError: If the function fails to get a token from both the HTTP
        and HTTPS endpoints.
    """
    import time
    
    current_time = time.time()
    
    # Check if we have a valid cached token
    if (not force_refresh and 
        _token_cache["token"] is not None and 
        _token_cache["panel_domain"] == panel_data.panel_domain and
        current_time < _token_cache["expires_at"]):
        panel_data.panel_token = _token_cache["token"]
        logger.debug("Using cached token (expires in %d seconds)", 
                    int(_token_cache["expires_at"] - current_time))
        return panel_data
    
    # Need to fetch a new token
    payload = {
        "username": f"{panel_data.panel_username}",
        "password": f"{panel_data.panel_password}",
    }
    max_attempts = 5
    for attempt in range(max_attempts):
        for scheme in ["https", "http"]:
            url = f"{scheme}://{panel_data.panel_domain}/api/admin/token"
            try:
                async with httpx.AsyncClient(verify=False) as client:
                    response = await client.post(url, data=payload, timeout=5)
                    response.raise_for_status()
                
                # Try to parse JSON response
                try:
                    json_obj = response.json()
                except Exception as json_error:
                    logger.error(f"Failed to parse JSON from {url}: {json_error}")
                    logger.error(f"Response text: {response.text[:200]}")
                    continue
                
                # Check if response is a dict and has access_token
                if not isinstance(json_obj, dict):
                    logger.error(f"Response is not a dict: {type(json_obj)} - {json_obj}")
                    continue
                
                if "access_token" not in json_obj:
                    logger.error(f"Response missing 'access_token' key. Keys: {list(json_obj.keys())}")
                    continue
                    
                token = json_obj["access_token"]
                
                # Cache the token for 30 minutes (1800 seconds)
                _token_cache["token"] = token
                _token_cache["expires_at"] = current_time + 1800
                _token_cache["panel_domain"] = panel_data.panel_domain
                
                panel_data.panel_token = token
                logger.info("Fetched new token (cached for 30 minutes)")
                return panel_data
            except httpx.HTTPStatusError:
                message = f"[{response.status_code}] {response.text}"
                await safe_send_logs_panel(message)
                logger.error(message)
                continue
            except SSLError:
                continue
            except Exception as error:  # pylint: disable=broad-except
                message = f"An unexpected error occurred: {error}"
                await safe_send_logs_panel(message)
                logger.error(message)
                continue
        await asyncio.sleep(min(30, random.randint(2, 5) * (attempt + 1)))
    message = (
        f"Failed to get token after {max_attempts} attempts. Make sure the panel is running "
        + "and the username and password are correct."
    )
    await safe_send_logs_panel(message)
    logger.error(message)
    raise ValueError(message)
