"""
Node operations for panel API.
"""

import asyncio
import random
import time
from ssl import SSLError

import httpx

from utils.logs import logger, log_api_request, get_logger
from utils.types import PanelType, NodeType
from utils.panel_api.auth import get_token, invalidate_token_cache, safe_send_logs_panel

# Try to import Redis cache
try:
    from utils.redis_cache import (
        get_cached_nodes, cache_nodes, invalidate_nodes as redis_invalidate_nodes
    )
    REDIS_CACHE_AVAILABLE = True
except ImportError:
    REDIS_CACHE_AVAILABLE = False

# Module logger
nodes_logger = get_logger("panel_api.nodes")

# Fallback in-memory nodes cache (1 hour cache)
_nodes_cache = {
    "nodes": None,
    "expires_at": 0,
    "panel_domain": None
}


async def invalidate_nodes_cache():
    """Invalidate the cached nodes list"""
    if REDIS_CACHE_AVAILABLE:
        try:
            await redis_invalidate_nodes(_nodes_cache.get("panel_domain", "default"))
        except Exception as e:
            nodes_logger.warning(f"Failed to invalidate Redis nodes cache: {e}")
    
    _nodes_cache["nodes"] = None
    _nodes_cache["expires_at"] = 0
    nodes_logger.info("🖥️ Nodes cache invalidated")


async def get_nodes(
    panel_data: PanelType,
    force_refresh: bool = False,
    enabled_only: bool = True,
) -> list[NodeType] | ValueError:
    """
    Get the IDs of all nodes from the panel API.
    Results are cached for 1 hour in Redis (or in-memory fallback).

    Args:
        panel_data (PanelType): A PanelType object containing
            the username, password, and domain for the panel API.
        force_refresh (bool): If True, bypass cache and fetch fresh nodes.
        enabled_only (bool): If True (default), only fetch enabled nodes.

    Returns:
        list[NodeType]: The list of IDs and other information of all nodes.

    Raises:
        ValueError: If the function fails to get the nodes from both the HTTP
        and HTTPS endpoints.
    """
    # Try Redis cache first
    if not force_refresh and REDIS_CACHE_AVAILABLE:
        try:
            cached_nodes = await get_cached_nodes(panel_data.panel_domain)
            if cached_nodes:
                # Convert cached dicts back to NodeType objects
                nodes_list = [
                    NodeType(
                        node_id=n["node_id"],
                        node_name=n["node_name"],
                        node_ip=n["node_ip"],
                        status=n["status"],
                        message=n.get("message", ""),
                    )
                    for n in cached_nodes
                ]
                nodes_logger.debug(f"🖥️ Using Redis cached nodes list ({len(nodes_list)} nodes)")
                return nodes_list
        except Exception as e:
            nodes_logger.warning(f"Redis cache error: {e}, falling back to in-memory")
    
    # Fallback: Check in-memory cache
    if not force_refresh and _nodes_cache["nodes"] is not None:
        current_time = time.time()
        # Check if cache is still valid and for same panel
        if (_nodes_cache["expires_at"] > current_time and 
            _nodes_cache["panel_domain"] == panel_data.panel_domain):
            time_left = int(_nodes_cache["expires_at"] - current_time)
            nodes_logger.debug(f"🖥️ Using in-memory cached nodes list (expires in {time_left // 60} minutes)")
            return _nodes_cache["nodes"]
    
    nodes_logger.info(f"🖥️ Fetching nodes from panel (force_refresh={force_refresh})...")
    max_attempts = 5
    for attempt in range(max_attempts):
        nodes_logger.debug(f"🖥️ Attempt {attempt + 1}/{max_attempts}")
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
            # Build URL with optional enabled filter
            base_url = f"{scheme}://{panel_data.panel_domain}/api/nodes"
            if enabled_only:
                url = f"{base_url}?enabled=true"
            else:
                url = base_url
            start_time = time.perf_counter()
            try:
                async with httpx.AsyncClient(verify=False) as client:
                    response = await client.get(url, headers=headers, timeout=10)
                    elapsed = (time.perf_counter() - start_time) * 1000
                    response.raise_for_status()
                
                log_api_request("GET", url, response.status_code, elapsed)
                
                try:
                    user_inform = response.json()
                except Exception as json_error:
                    nodes_logger.error(f"Failed to parse JSON from {url}: {json_error}")
                    nodes_logger.debug(f"Response text: {response.text[:200]}")
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
                        nodes_logger.warning(f"Unexpected nodes dict structure. Keys: {list(user_inform.keys())}")
                        if "id" in user_inform and "name" in user_inform:
                            nodes_list = [user_inform]
                        else:
                            nodes_logger.error(f"Cannot parse nodes from dict: {user_inform}")
                            continue
                else:
                    nodes_logger.error(f"Nodes response is neither list nor dict: {type(user_inform)}")
                    continue
                
                if not nodes_list or not isinstance(nodes_list, list):
                    nodes_logger.error(f"Failed to extract nodes list from response")
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
                # Store in Redis if available
                if REDIS_CACHE_AVAILABLE:
                    try:
                        # Convert NodeType objects to dicts for JSON serialization
                        nodes_dicts = [
                            {
                                "node_id": n.node_id,
                                "node_name": n.node_name,
                                "node_ip": n.node_ip,
                                "status": n.status,
                                "message": n.message,
                            }
                            for n in all_nodes
                        ]
                        await cache_nodes(panel_data.panel_domain, nodes_dicts)
                        nodes_logger.debug("🖥️ Nodes cached in Redis")
                    except Exception as e:
                        nodes_logger.warning(f"Failed to cache nodes in Redis: {e}")
                
                # Always store in in-memory cache as fallback
                _nodes_cache["nodes"] = all_nodes
                _nodes_cache["expires_at"] = time.time() + 3600
                _nodes_cache["panel_domain"] = panel_data.panel_domain
                
                nodes_logger.info(f"🖥️ Fetched {len(all_nodes)} nodes (cached for 1 hour) [{elapsed:.0f}ms]")
                for node in all_nodes:
                    nodes_logger.debug(f"  └─ {node.node_name} (id={node.node_id}, status={node.status})")
                
                return all_nodes
            except SSLError:
                elapsed = (time.perf_counter() - start_time) * 1000
                log_api_request("GET", url, None, elapsed, "SSL Error")
                continue
            except httpx.HTTPStatusError:
                elapsed = (time.perf_counter() - start_time) * 1000
                if response.status_code == 401:
                    await invalidate_token_cache()
                    nodes_logger.warning("Got 401 error, invalidating token cache and retrying")
                log_api_request("GET", url, response.status_code, elapsed, f"HTTP {response.status_code}")
                message = f"[{response.status_code}] {response.text}"
                await safe_send_logs_panel(message)
                nodes_logger.error(message)
                continue
            except httpx.TimeoutException:
                elapsed = (time.perf_counter() - start_time) * 1000
                log_api_request("GET", url, None, elapsed, "Timeout")
                nodes_logger.warning(f"Timeout fetching nodes from {url}")
                continue
            except Exception as error:  # pylint: disable=broad-except
                elapsed = (time.perf_counter() - start_time) * 1000
                log_api_request("GET", url, None, elapsed, str(error))
                message = f"An unexpected error occurred: {error}"
                await safe_send_logs_panel(message)
                nodes_logger.error(message)
                continue
        wait_time = min(30, random.randint(2, 5) * (attempt + 1))
        nodes_logger.debug(f"Waiting {wait_time}s before retry...")
        await asyncio.sleep(wait_time)
    message = (
        f"Failed to get nodes after {max_attempts} attempts. Make sure the panel is running "
        + "and the username and password are correct."
    )
    await safe_send_logs_panel(message)
    nodes_logger.error(message)
    raise ValueError(message)
