"""
Group operations for panel API.
"""

from utils.logs import get_logger
from utils.types import PanelType
from utils.panel_api.request_helper import panel_get

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
    
    response = await panel_get(panel_data, "/api/groups")
    
    if response is None:
        message = "Failed to get groups after all retries"
        groups_logger.error(message)
        raise ValueError(message)
    
    try:
        data = response.json()
    except Exception as json_error:
        groups_logger.error(f"Failed to parse JSON: {json_error}")
        raise ValueError(f"Failed to parse groups response: {json_error}")
    
    # Handle response structure
    groups = None
    if isinstance(data, dict) and "groups" in data:
        groups = data["groups"]
    elif isinstance(data, list):
        groups = data
    else:
        message = f"Unexpected groups response format: {type(data)}"
        groups_logger.error(message)
        raise ValueError(message)
    
    groups_logger.info(f"👥 Fetched {len(groups)} groups")
    for group in groups:
        groups_logger.debug(f"  └─ {group.get('name', 'Unknown')} (id={group.get('id', '?')})")
    return groups
