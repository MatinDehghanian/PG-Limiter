"""
Admin operations for panel API.
"""

from utils.logs import get_logger
from utils.types import PanelType
from utils.panel_api.request_helper import panel_get

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
    
    response = await panel_get(panel_data, "/api/admins", force_refresh=force_refresh)
    
    if response is None:
        message = "Failed to get admins after all retries"
        admins_logger.error(message)
        raise ValueError(message)
    
    # Check for 403 Forbidden
    if response.status_code == 403:
        admins_logger.error("Forbidden: Current user doesn't have permission to list admins")
        raise ValueError("Forbidden: Need sudo permissions to list admins")
    
    try:
        data = response.json()
    except Exception as json_error:
        admins_logger.error(f"Failed to parse JSON: {json_error}")
        raise ValueError(f"Failed to parse admins response: {json_error}")
    
    # Handle response structure - AdminsResponse has "admins" key
    admins = None
    if isinstance(data, dict) and "admins" in data:
        admins = data["admins"]
    elif isinstance(data, list):
        admins = data
    else:
        message = f"Unexpected admins response format: {type(data)}"
        admins_logger.error(message)
        raise ValueError(message)
    
    admins_logger.info(f"👔 Fetched {len(admins)} admins")
    for admin in admins:
        is_sudo = admin.get("is_sudo", False)
        admins_logger.debug(f"  └─ {admin.get('username', 'Unknown')} (sudo={is_sudo})")
    return admins
