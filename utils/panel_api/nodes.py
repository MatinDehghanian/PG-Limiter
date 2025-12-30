"""
Node operations for panel API.
"""

import asyncio
import random
import time
from ssl import SSLError

import httpx

from utils.logs import logger
from utils.types import PanelType, NodeType
from utils.panel_api.auth import get_token, invalidate_token_cache, safe_send_logs_panel

# Nodes cache to reduce API requests (1 hour cache)
_nodes_cache = {
    "nodes": None,
    "expires_at": 0,
    "panel_domain": None
}


def invalidate_nodes_cache():
    """Invalidate the cached nodes list"""
    _nodes_cache["nodes"] = None
    _nodes_cache["expires_at"] = 0
    logger.info("Nodes cache invalidated")


async def get_nodes(panel_data: PanelType, force_refresh: bool = False) -> list[NodeType] | ValueError:
    """
    Get the IDs of all nodes from the panel API.
    Results are cached for 1 hour to reduce API calls.

    Args:
        panel_data (PanelType): A PanelType object containing
        the username, password, and domain for the panel API.
        force_refresh (bool): If True, bypass cache and fetch fresh nodes

    Returns:
        list[NodeType]: The list of IDs and other information of all nodes.

    Raises:
        ValueError: If the function fails to get the nodes from both the HTTP
        and HTTPS endpoints.
    """
    # Check cache first (unless force refresh)
    if not force_refresh and _nodes_cache["nodes"] is not None:
        current_time = time.time()
        # Check if cache is still valid and for same panel
        if (_nodes_cache["expires_at"] > current_time and 
            _nodes_cache["panel_domain"] == panel_data.panel_domain):
            time_left = int(_nodes_cache["expires_at"] - current_time)
            logger.debug(f"Using cached nodes list (expires in {time_left // 60} minutes)")
            return _nodes_cache["nodes"]
    
    max_attempts = 5
    for attempt in range(max_attempts):
        force_refresh_token = attempt > 0
        get_panel_token = await get_token(panel_data, force_refresh=force_refresh_token)
        if isinstance(get_panel_token, ValueError):
            raise get_panel_token
        token = get_panel_token.panel_token
        headers = {
            "Authorization": f"Bearer {token}",
        }
        all_nodes = []
        for scheme in ["https", "http"]:
            url = f"{scheme}://{panel_data.panel_domain}/api/nodes"
            try:
                async with httpx.AsyncClient(verify=False) as client:
                    response = await client.get(url, headers=headers, timeout=10)
                    response.raise_for_status()
                
                try:
                    user_inform = response.json()
                except Exception as json_error:
                    logger.error(f"Failed to parse JSON from {url}: {json_error}")
                    logger.error(f"Response text: {response.text[:200]}")
                    continue
                
                # Handle both list and dict responses
                nodes_list = None
                if isinstance(user_inform, list):
                    nodes_list = user_inform
                elif isinstance(user_inform, dict):
                    if "nodes" in user_inform:
                        nodes_list = user_inform["nodes"]
                    elif "data" in user_inform:
                        nodes_list = user_inform["data"]
                    else:
                        logger.warning(f"Unexpected nodes dict structure. Keys: {list(user_inform.keys())}")
                        if "id" in user_inform and "name" in user_inform:
                            nodes_list = [user_inform]
                        else:
                            logger.error(f"Cannot parse nodes from dict: {user_inform}")
                            continue
                else:
                    logger.error(f"Nodes response is neither list nor dict: {type(user_inform)}")
                    continue
                
                if not nodes_list or not isinstance(nodes_list, list):
                    logger.error(f"Failed to extract nodes list from response")
                    continue
                
                for node in nodes_list:
                    all_nodes.append(
                        NodeType(
                            node_id=node["id"],
                            node_name=node["name"],
                            node_ip=node["address"],
                            status=node["status"],
                            message=node.get("message", ""),
                        )
                    )
                
                # Cache the nodes list for 1 hour (3600 seconds)
                _nodes_cache["nodes"] = all_nodes
                _nodes_cache["expires_at"] = time.time() + 3600
                _nodes_cache["panel_domain"] = panel_data.panel_domain
                logger.info(f"Cached {len(all_nodes)} nodes for 1 hour")
                
                return all_nodes
            except SSLError:
                continue
            except httpx.HTTPStatusError:
                if response.status_code == 401:
                    invalidate_token_cache()
                    logger.warning("Got 401 error, invalidating token cache and retrying")
                message = f"[{response.status_code}] {response.text}"
                await safe_send_logs_panel(message)
                logger.error(message)
                continue
            except Exception as error:  # pylint: disable=broad-except
                message = f"An unexpected error occurred: {error}"
                await safe_send_logs_panel(message)
                logger.error(message)
                continue
        await asyncio.sleep(min(30, random.randint(2, 5) * (attempt + 1)))
    message = (
        f"Failed to get nodes after {max_attempts} attempts. Make sure the panel is running "
        + "and the username and password are correct."
    )
    await safe_send_logs_panel(message)
    logger.error(message)
    raise ValueError(message)
