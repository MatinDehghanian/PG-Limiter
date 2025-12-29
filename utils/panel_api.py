"""
This module contains functions to interact with the panel API.
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
# from telegram_bot.send_message import send_logs  # Temporarily disabled to prevent circular import

from utils.handel_dis_users import DISABLED_USERS, DisabledUsers
from utils.user_groups_storage import UserGroupsStorage
from utils.logs import logger
from utils.read_config import read_config
from utils.types import NodeType, PanelType, UserType

# Token cache to reduce API requests
_token_cache = {
    "token": None,
    "expires_at": 0,
    "panel_domain": None
}

# Nodes cache to reduce API requests (1 hour cache)
_nodes_cache = {
    "nodes": None,
    "expires_at": 0,
    "panel_domain": None
}

def invalidate_token_cache():
    """Invalidate the cached token (useful when getting 401 errors)"""
    _token_cache["token"] = None
    _token_cache["expires_at"] = 0
    logger.info("Token cache invalidated")

def invalidate_nodes_cache():
    """Invalidate the cached nodes list"""
    _nodes_cache["nodes"] = None
    _nodes_cache["expires_at"] = 0
    logger.info("Nodes cache invalidated")

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
    max_attempts = 5  # Reduced from 20 for faster failure detection
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
                # Most JWT tokens last much longer, but we'll be conservative
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
        await asyncio.sleep(min(30, random.randint(2, 5) * (attempt + 1)))  # Exponential backoff with cap
    message = (
        f"Failed to get token after {max_attempts} attempts. Make sure the panel is running "
        + "and the username and password are correct."
    )
    await safe_send_logs_panel(message)
    logger.error(message)
    raise ValueError(message)


async def all_user(panel_data: PanelType) -> list[UserType] | ValueError:
    """
    Get the list of all users from the panel API.

    Args:
        panel_data (PanelType): A PanelType object containing
        the username, password, and domain for the panel API.

    Returns:
        list[user]: The list of usernames of all users.

    Raises:
        ValueError: If the function fails to get the users from both the HTTP
        and HTTPS endpoints.
    """
    max_attempts = 5  # Reduced from 20 for faster failure detection
    for attempt in range(max_attempts):
        # On first attempt use cached token, on retry get fresh token
        force_refresh = attempt > 0
        get_panel_token = await get_token(panel_data, force_refresh=force_refresh)
        if isinstance(get_panel_token, ValueError):
            raise get_panel_token
        token = get_panel_token.panel_token
        headers = {
            "Authorization": f"Bearer {token}",
        }
        for scheme in ["https", "http"]:
            url = f"{scheme}://{panel_data.panel_domain}/api/users"
            try:
                async with httpx.AsyncClient(verify=False) as client:
                    response = await client.get(url, headers=headers, timeout=10)
                    response.raise_for_status()
                
                # Parse and validate JSON response
                try:
                    user_inform = response.json()
                except Exception as json_error:
                    logger.error(f"Failed to parse JSON from {url}: {json_error}")
                    logger.error(f"Response text: {response.text[:200]}")
                    continue
                
                # Validate response structure
                if not isinstance(user_inform, dict):
                    logger.error(f"Response is not a dict: {type(user_inform)}")
                    continue
                
                if "users" not in user_inform:
                    logger.error(f"Response missing 'users' key. Keys: {list(user_inform.keys())}")
                    continue
                
                return [
                    UserType(name=user["username"]) for user in user_inform["users"]
                ]
            except SSLError:
                continue
            except httpx.HTTPStatusError:
                # If we get 401 (Unauthorized), invalidate cache and retry with fresh token
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
        f"Failed to get users after {max_attempts} attempts. Make sure the panel is running "
        + "and the username and password are correct."
    )
    await safe_send_logs_panel(message)
    logger.error(message)
    raise ValueError(message)


async def enable_all_user(panel_data: PanelType) -> None | ValueError:
    """
    Enable all users on the panel.

    Args:
        panel_data (PanelType): A PanelType object containing
        the username, password, and domain for the panel API.

    Returns:
        None

    Raises:
        ValueError: If the function fails to enable the users on both the HTTP
        and HTTPS endpoints.
    """
    get_panel_token = await get_token(panel_data)
    if isinstance(get_panel_token, ValueError):
        raise get_panel_token
    token = get_panel_token.panel_token
    headers = {
        "Authorization": f"Bearer {token}",
    }
    users = await all_user(panel_data)
    if isinstance(users, ValueError):
        raise users
    for username in users:
        for scheme in ["https", "http"]:  # add this later: save what scheme is used
            url = f"{scheme}://{panel_data.panel_domain}/api/user/{username.name}"
            status = {"status": "active"}
            try:
                async with httpx.AsyncClient(verify=False) as client:
                    response = await client.put(
                        url, json=status, headers=headers, timeout=5
                    )
                    response.raise_for_status()
                message = f"Enabled user: {username.name}"
                await safe_send_logs_panel(message)
                logger.info(message)
                break
            except SSLError:
                continue
            except httpx.HTTPStatusError:
                message = f"[{response.status_code}] {response.text}"
                await safe_send_logs_panel(message)
                logger.error(message)
                continue
            except Exception as error:  # pylint: disable=broad-except
                message = f"An unexpected error occurred: {error}"
                await safe_send_logs_panel(message)
                logger.error(message)
    logger.info("Enabled all users")


async def enable_selected_users(
    panel_data: PanelType, inactive_users: set[str]
) -> None | ValueError:
    """
    Enable selected users on the panel.
    Uses either status-based or group-based enabling depending on config.

    Args:
        panel_data (PanelType): A PanelType object containing
        the username, password, and domain for the panel API.
        inactive_users (set[str]): A list of user str that are currently inactive.

    Returns:
        None

    Raises:
        ValueError: If the function fails to enable the users.
    """
    # Read config to determine disable method
    data = await read_config()
    disable_method = data.get("disable_method", "status")
    disabled_group_id = data.get("disabled_group_id", None)
    use_group_method = disable_method == "group" and disabled_group_id is not None
    
    for username in inactive_users:
        success = False
        
        if use_group_method:
            # Try group-based enabling first (restore original groups)
            groups_storage = UserGroupsStorage()
            has_saved_groups = await groups_storage.has_saved_groups(username)
            
            if has_saved_groups:
                success = await enable_user_by_group(panel_data, username)
                if success:
                    message = f"Enabled user (restored groups): {username}"
                    await safe_send_logs_panel(message)
            else:
                # Fallback to status-based enabling if no saved groups
                logger.warning(f"No saved groups for {username}, using status-based enable")
                success = await enable_user_by_status(panel_data, username)
                if success:
                    message = f"Enabled user: {username}"
                    await safe_send_logs_panel(message)
        else:
            # Use traditional status-based enabling
            success = await enable_user_by_status(panel_data, username)
            if success:
                message = f"Enabled user: {username}"
                await safe_send_logs_panel(message)
        
        if not success:
            message = f"Failed to enable user: {username}"
            await safe_send_logs_panel(message)
            logger.error(message)
            raise ValueError(message)
    
    logger.info("Enabled selected users")


async def disable_user_by_status(panel_data: PanelType, username: str) -> bool:
    """
    Disable a user by changing their status to 'disabled'.
    Traditional method.

    Args:
        panel_data (PanelType): Panel connection data.
        username (str): The username to disable.

    Returns:
        bool: True if successful, False otherwise.
    """
    max_attempts = 5
    for attempt in range(max_attempts):
        force_refresh = attempt > 0
        get_panel_token = await get_token(panel_data, force_refresh=force_refresh)
        if isinstance(get_panel_token, ValueError):
            raise get_panel_token
        token = get_panel_token.panel_token
        headers = {"Authorization": f"Bearer {token}"}
        status = {"status": "disabled"}
        
        for scheme in ["https", "http"]:
            url = f"{scheme}://{panel_data.panel_domain}/api/user/{username}"
            try:
                async with httpx.AsyncClient(verify=False) as client:
                    response = await client.put(url, json=status, headers=headers, timeout=5)
                    response.raise_for_status()
                logger.info(f"Disabled user by status: {username}")
                return True
            except SSLError:
                continue
            except httpx.HTTPStatusError:
                if response.status_code == 401:
                    invalidate_token_cache()
                continue
            except Exception as error:
                logger.error(f"Error disabling user: {error}")
                continue
        await asyncio.sleep(min(30, random.randint(2, 5) * (attempt + 1)))
    return False


async def disable_user_by_group(panel_data: PanelType, username: str, disabled_group_id: int) -> bool:
    """
    Disable a user by moving them to the disabled group and setting status to disabled.
    Saves their original groups before changing.

    Args:
        panel_data (PanelType): Panel connection data.
        username (str): The username to disable.
        disabled_group_id (int): The group ID to move user to.

    Returns:
        bool: True if successful, False otherwise.
    """
    try:
        # First, get the user's current groups
        user_data = await get_user_details(panel_data, username)
        if user_data is None:
            logger.error(f"User {username} not found")
            return False
        
        current_groups = user_data.get("group_ids", [])
        
        # Save the original groups
        groups_storage = UserGroupsStorage()
        await groups_storage.save_user_groups(username, current_groups)
        
        # Move user to disabled group only
        group_success = await update_user_groups(panel_data, username, [disabled_group_id])
        
        # Also set status to disabled
        status_success = await disable_user_by_status(panel_data, username)
        
        if group_success and status_success:
            logger.info(f"Disabled user by group: {username} (moved to group {disabled_group_id}, status disabled)")
            return True
        elif group_success:
            logger.warning(f"Disabled user by group: {username} (moved to group {disabled_group_id}, but status change failed)")
            return True  # Still consider it success if group was changed
        return False
    except Exception as error:
        logger.error(f"Error disabling user by group: {error}")
        return False


async def disable_user(panel_data: PanelType, username: UserType) -> None | ValueError:
    """
    Disable a user on the panel.
    Uses either status-based or group-based disabling depending on config.
    Skips users that don't exist in the panel (deleted users).

    Args:
        panel_data (PanelType): A PanelType object containing
        the username, password, and domain for the panel API.
        username (user): The username of the user to disable.

    Returns:
        None

    Raises:
        ValueError: If the function fails to disable the user.
    """
    # Check if user exists in panel before trying to disable
    user_exists = await check_user_exists(panel_data, username.name)
    if not user_exists:
        message = f"User {username.name} not found in panel (deleted?), skipping disable"
        logger.warning(message)
        await safe_send_logs_panel(message)
        return None  # Don't raise error, just skip
    
    # Read config to determine disable method
    data = await read_config()
    disable_method = data.get("disable_method", "status")
    disabled_group_id = data.get("disabled_group_id", None)
    
    success = False
    
    if disable_method == "group" and disabled_group_id is not None:
        # Use group-based disabling
        success = await disable_user_by_group(panel_data, username.name, disabled_group_id)
        if success:
            message = f"Disabled user (moved to disabled group): {username.name}"
            await safe_send_logs_panel(message)
    else:
        # Use traditional status-based disabling
        success = await disable_user_by_status(panel_data, username.name)
        if success:
            message = f"Disabled user: {username.name}"
            await safe_send_logs_panel(message)
    
    if success:
        dis_obj = DisabledUsers()
        await dis_obj.add_user(username.name)
        return None
    
    message = f"Failed to disable user: {username.name}"
    await safe_send_logs_panel(message)
    logger.error(message)
    raise ValueError(message)


async def enable_user_by_status(panel_data: PanelType, username: str) -> bool:
    """
    Enable a user by changing their status to 'active'.
    Traditional method.

    Args:
        panel_data (PanelType): Panel connection data.
        username (str): The username to enable.

    Returns:
        bool: True if successful, False otherwise.
    """
    max_attempts = 5
    for attempt in range(max_attempts):
        force_refresh = attempt > 0
        get_panel_token = await get_token(panel_data, force_refresh=force_refresh)
        if isinstance(get_panel_token, ValueError):
            raise get_panel_token
        token = get_panel_token.panel_token
        headers = {"Authorization": f"Bearer {token}"}
        status = {"status": "active"}
        
        for scheme in ["https", "http"]:
            url = f"{scheme}://{panel_data.panel_domain}/api/user/{username}"
            try:
                async with httpx.AsyncClient(verify=False) as client:
                    response = await client.put(url, json=status, headers=headers, timeout=5)
                    response.raise_for_status()
                logger.info(f"Enabled user by status: {username}")
                return True
            except SSLError:
                continue
            except httpx.HTTPStatusError:
                if response.status_code == 401:
                    invalidate_token_cache()
                continue
            except Exception as error:
                logger.error(f"Error enabling user: {error}")
                continue
        await asyncio.sleep(min(30, random.randint(2, 5) * (attempt + 1)))
    return False


async def enable_user_by_group(panel_data: PanelType, username: str) -> bool:
    """
    Enable a user by restoring their original groups and setting status to active.

    Args:
        panel_data (PanelType): Panel connection data.
        username (str): The username to enable.

    Returns:
        bool: True if successful, False otherwise.
    """
    try:
        # Get the user's original groups
        groups_storage = UserGroupsStorage()
        original_groups = await groups_storage.get_user_groups(username)
        
        if original_groups is None:
            logger.warning(f"No saved groups found for user {username}, cannot restore")
            return False
        
        # Restore user's original groups
        group_success = await update_user_groups(panel_data, username, original_groups)
        
        # Also set status back to active
        status_success = await enable_user_by_status(panel_data, username)
        
        if group_success and status_success:
            # Remove from storage after successful restore
            await groups_storage.remove_user(username)
            logger.info(f"Enabled user by group: {username} (restored groups {original_groups}, status active)")
            return True
        elif group_success:
            # Remove from storage even if status change failed
            await groups_storage.remove_user(username)
            logger.warning(f"Enabled user by group: {username} (restored groups {original_groups}, but status change failed)")
            return True  # Still consider it success if groups were restored
        return False
    except Exception as error:
        logger.error(f"Error enabling user by group: {error}")
        return False


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
    import time
    
    # Check cache first (unless force refresh)
    if not force_refresh and _nodes_cache["nodes"] is not None:
        current_time = time.time()
        # Check if cache is still valid and for same panel
        if (_nodes_cache["expires_at"] > current_time and 
            _nodes_cache["panel_domain"] == panel_data.panel_domain):
            time_left = int(_nodes_cache["expires_at"] - current_time)
            logger.debug(f"Using cached nodes list (expires in {time_left // 60} minutes)")
            return _nodes_cache["nodes"]
    
    max_attempts = 5  # Reduced from 20 for faster failure detection
    for attempt in range(max_attempts):
        # On first attempt use cached token, on retry get fresh token
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
                
                # Parse and validate JSON response
                try:
                    user_inform = response.json()
                except Exception as json_error:
                    logger.error(f"Failed to parse JSON from {url}: {json_error}")
                    logger.error(f"Response text: {response.text[:200]}")
                    continue
                
                # Handle both list and dict responses
                nodes_list = None
                if isinstance(user_inform, list):
                    # Old API format: direct list of nodes
                    nodes_list = user_inform
                elif isinstance(user_inform, dict):
                    # New API format: might be wrapped in a dict
                    # Try common wrapper keys
                    if "nodes" in user_inform:
                        nodes_list = user_inform["nodes"]
                    elif "data" in user_inform:
                        nodes_list = user_inform["data"]
                    else:
                        # If no wrapper, might be a single node
                        logger.warning(f"Unexpected nodes dict structure. Keys: {list(user_inform.keys())}")
                        # Try to treat the dict itself as a single node
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
                import time
                _nodes_cache["nodes"] = all_nodes
                _nodes_cache["expires_at"] = time.time() + 3600
                _nodes_cache["panel_domain"] = panel_data.panel_domain
                logger.info(f"Cached {len(all_nodes)} nodes for 1 hour")
                
                return all_nodes
            except SSLError:
                continue
            except httpx.HTTPStatusError:
                # If we get 401 (Unauthorized), invalidate cache and retry
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
        await asyncio.sleep(min(30, random.randint(2, 5) * (attempt + 1)))  # Exponential backoff with cap
    message = (
        f"Failed to get nodes after {max_attempts} attempts. Make sure the panel is running "
        + "and the username and password are correct."
    )
    await safe_send_logs_panel(message)
    logger.error(message)
    raise ValueError(message)


async def get_all_panel_users(panel_data: PanelType) -> set[str] | ValueError:
    """
    Get all usernames from the panel API.

    Args:
        panel_data (PanelType): A PanelType object containing
        the username, password, and domain for the panel API.

    Returns:
        set[str]: A set of all usernames in the panel.

    Raises:
        ValueError: If the function fails to get users from the API.
    """
    max_attempts = 5
    all_usernames = set()
    limit = 100  # Fetch 100 users per request
    
    for attempt in range(max_attempts):
        # Reset for each attempt
        all_usernames.clear()
        offset = 0
        
        force_refresh = attempt > 0
        get_panel_token = await get_token(panel_data, force_refresh=force_refresh)
        if isinstance(get_panel_token, ValueError):
            raise get_panel_token
        token = get_panel_token.panel_token
        headers = {
            "Authorization": f"Bearer {token}",
        }
        
        # Paginate through all users
        pagination_success = True
        while pagination_success:
            page_success = False
            for scheme in ["https", "http"]:
                url = f"{scheme}://{panel_data.panel_domain}/api/users?offset={offset}&limit={limit}"
                try:
                    async with httpx.AsyncClient(verify=False) as client:
                        response = await client.get(url, headers=headers, timeout=30)
                        response.raise_for_status()
                    
                    try:
                        data = response.json()
                    except Exception as json_error:
                        logger.error(f"Failed to parse JSON from {url}: {json_error}")
                        continue
                    
                    # Handle response structure
                    users = []
                    if isinstance(data, dict) and "users" in data:
                        users = data["users"]
                        total = data.get("total", len(users))
                    elif isinstance(data, list):
                        users = data
                        total = len(users)
                    else:
                        logger.error(f"Unexpected users response format: {type(data)}")
                        continue
                    
                    # Extract usernames
                    for user in users:
                        if isinstance(user, dict) and "username" in user:
                            all_usernames.add(user["username"])
                    
                    logger.debug(f"Fetched page: offset={offset}, got {len(users)} users, total so far: {len(all_usernames)}")
                    
                    # Check if we've fetched all users
                    if len(users) < limit or offset + len(users) >= total:
                        logger.info(f"Fetched {len(all_usernames)} users from panel (total in API: {total})")
                        return all_usernames
                    
                    offset += limit
                    page_success = True
                    break  # Success, continue to next page
                    
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
            
            # If we get here, both schemes failed for this page
            if not page_success:
                pagination_success = False
                logger.warning(f"Failed to fetch page at offset {offset}, will retry attempt")
                break
        
        await asyncio.sleep(min(30, random.randint(2, 5) * (attempt + 1)))
    
    message = f"Failed to get all users after {max_attempts} attempts."
    logger.error(message)
    raise ValueError(message)


async def check_user_exists(panel_data: PanelType, username: str) -> bool:
    """
    Check if a user exists in the panel.

    Args:
        panel_data (PanelType): A PanelType object containing
        the username, password, and domain for the panel API.
        username (str): The username to check.

    Returns:
        bool: True if user exists, False otherwise.
    """
    max_attempts = 3
    for attempt in range(max_attempts):
        force_refresh = attempt > 0
        get_panel_token = await get_token(panel_data, force_refresh=force_refresh)
        if isinstance(get_panel_token, ValueError):
            return False
        token = get_panel_token.panel_token
        headers = {
            "Authorization": f"Bearer {token}",
        }
        for scheme in ["https", "http"]:
            url = f"{scheme}://{panel_data.panel_domain}/api/user/{username}"
            try:
                async with httpx.AsyncClient(verify=False) as client:
                    response = await client.get(url, headers=headers, timeout=10)
                    
                    if response.status_code == 200:
                        return True
                    elif response.status_code == 404:
                        return False
                    elif response.status_code == 401:
                        invalidate_token_cache()
                        logger.warning("Got 401 error, invalidating token cache and retrying")
                        break
                    else:
                        logger.warning(f"Unexpected status {response.status_code} checking user {username}")
                        continue
                    
            except SSLError:
                continue
            except Exception as error:
                logger.error(f"Error checking user existence: {error}")
                continue
        
        await asyncio.sleep(min(10, random.randint(1, 3) * (attempt + 1)))
    
    # Default to True to avoid accidentally skipping users
    logger.warning(f"Could not verify if user {username} exists, assuming exists")
    return True


async def cleanup_deleted_users(panel_data: PanelType) -> dict:
    """
    Clean up users from limiter config that no longer exist in the panel.
    Removes deleted users from: special limits, except_users, and disabled_users.

    Args:
        panel_data (PanelType): A PanelType object containing
        the username, password, and domain for the panel API.

    Returns:
        dict: A summary of cleaned up users with keys:
            - special_limits_removed: list of usernames removed from special limits
            - except_users_removed: list of usernames removed from except_users
            - disabled_users_removed: list of usernames removed from disabled_users
            - user_groups_backup_removed: list of usernames removed from user groups backup
    """
    from utils.handel_dis_users import DisabledUsers
    
    result = {
        "special_limits_removed": [],
        "except_users_removed": [],
        "disabled_users_removed": [],
        "user_groups_backup_removed": [],
    }
    
    try:
        # Get all users from panel
        panel_users = await get_all_panel_users(panel_data)
        logger.info(f"Found {len(panel_users)} users in panel")
        
        # Safety check: if no users found, something is wrong - abort cleanup
        if len(panel_users) == 0:
            logger.error("No users found in panel - aborting cleanup to prevent data loss")
            raise ValueError("No users found in panel. API may be unreachable or returning empty data.")
        
        # Read current config
        data = await read_config()
        config_changed = False
        
        # Additional safety: check if we would remove more than 50% of special limits
        special_limits = data.get("limits", {}).get("special", {})
        if special_limits:
            users_to_remove = [u for u in special_limits.keys() if u not in panel_users]
            if len(users_to_remove) > len(special_limits) * 0.5 and len(users_to_remove) > 5:
                logger.warning(f"Would remove {len(users_to_remove)} of {len(special_limits)} special limits - this seems too many!")
                logger.warning(f"Panel returned {len(panel_users)} users. First 10: {list(panel_users)[:10]}")
                raise ValueError(f"Safety check failed: Would remove {len(users_to_remove)} of {len(special_limits)} users. This may indicate an API issue.")
        
        # Check special limits
        special_limits = data.get("limits", {}).get("special", {})
        if special_limits:
            users_to_remove = []
            for username in special_limits.keys():
                if username not in panel_users:
                    users_to_remove.append(username)
            
            for username in users_to_remove:
                del data["limits"]["special"][username]
                result["special_limits_removed"].append(username)
                config_changed = True
                logger.info(f"Removed deleted user from special limits: {username}")
        
        # Check except_users
        except_users = data.get("limits", {}).get("except_users", [])
        if except_users:
            new_except_users = [u for u in except_users if u in panel_users]
            removed = [u for u in except_users if u not in panel_users]
            if removed:
                data["limits"]["except_users"] = new_except_users
                result["except_users_removed"] = removed
                config_changed = True
                for username in removed:
                    logger.info(f"Removed deleted user from except_users: {username}")
        
        # Save config if changed
        if config_changed:
            from telegram_bot.utils import write_json_file
            await write_json_file(data)
        
        # Check disabled users
        dis_obj = DisabledUsers()
        disabled_list = list(dis_obj.disabled_users.keys())
        for username in disabled_list:
            if username not in panel_users:
                await dis_obj.remove_user(username)
                result["disabled_users_removed"].append(username)
                logger.info(f"Removed deleted user from disabled_users: {username}")
        
        # Check user groups backup
        groups_storage = UserGroupsStorage()
        saved_users = await groups_storage.get_all_users_with_saved_groups()
        for username in saved_users:
            if username not in panel_users:
                await groups_storage.remove_user(username)
                result["user_groups_backup_removed"].append(username)
                logger.info(f"Removed deleted user from user groups backup: {username}")
        
        total_removed = (
            len(result["special_limits_removed"]) +
            len(result["except_users_removed"]) +
            len(result["disabled_users_removed"]) +
            len(result["user_groups_backup_removed"])
        )
        logger.info(f"Cleanup complete. Total removed: {total_removed}")
        
        return result
        
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")
        raise


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


async def get_user_details(panel_data: PanelType, username: str) -> dict | ValueError:
    """
    Get user details including group_ids from the panel API.

    Args:
        panel_data (PanelType): A PanelType object containing
        the username, password, and domain for the panel API.
        username (str): The username to get details for.

    Returns:
        dict: The user details including group_ids.

    Raises:
        ValueError: If the function fails to get user details from the API.
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
            url = f"{scheme}://{panel_data.panel_domain}/api/user/{username}"
            try:
                async with httpx.AsyncClient(verify=False) as client:
                    response = await client.get(url, headers=headers, timeout=10)
                    response.raise_for_status()
                
                try:
                    user_data = response.json()
                except Exception as json_error:
                    logger.error(f"Failed to parse JSON from {url}: {json_error}")
                    continue
                
                return user_data
                    
            except SSLError:
                continue
            except httpx.HTTPStatusError:
                if response.status_code == 401:
                    invalidate_token_cache()
                    logger.warning("Got 401 error, invalidating token cache and retrying")
                if response.status_code == 404:
                    logger.warning(f"User {username} not found")
                    return None
                message = f"[{response.status_code}] {response.text}"
                logger.error(message)
                continue
            except Exception as error:
                message = f"An unexpected error occurred: {error}"
                logger.error(message)
                continue
        await asyncio.sleep(min(30, random.randint(2, 5) * (attempt + 1)))
    message = f"Failed to get user details for {username} after {max_attempts} attempts."
    logger.error(message)
    raise ValueError(message)


async def update_user_groups(panel_data: PanelType, username: str, group_ids: list[int]) -> bool:
    """
    Update user's group_ids in the panel.

    Args:
        panel_data (PanelType): A PanelType object containing
        the username, password, and domain for the panel API.
        username (str): The username to update.
        group_ids (list[int]): The list of group IDs to set for the user.

    Returns:
        bool: True if successful, False otherwise.
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
        payload = {"group_ids": group_ids}
        for scheme in ["https", "http"]:
            url = f"{scheme}://{panel_data.panel_domain}/api/user/{username}"
            try:
                async with httpx.AsyncClient(verify=False) as client:
                    response = await client.put(
                        url, json=payload, headers=headers, timeout=10
                    )
                    response.raise_for_status()
                logger.info(f"Updated groups for user {username} to {group_ids}")
                return True
                    
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
    message = f"Failed to update groups for user {username} after {max_attempts} attempts."
    logger.error(message)
    return False


async def enable_dis_user(panel_data: PanelType):
    """
    Enable disabled users individually based on when each was disabled.
    Each user is enabled after 'time_to_active_users' seconds from their disable time.
    Checks every 30 seconds for users ready to be enabled.
    """
    while True:
        # Check every 30 seconds for users ready to be enabled
        await asyncio.sleep(30)
        
        try:
            data = await read_config()
            time_to_active = data.get("monitoring", {}).get("time_to_active_users", 1800)
            
            # Create new DisabledUsers object each time to get fresh data from file
            dis_obj = DisabledUsers()
            
            # Get users who have been disabled for longer than time_to_active
            users_to_enable = await dis_obj.get_users_to_enable(time_to_active)
            
            if users_to_enable:
                logger.info(f"Enabling {len(users_to_enable)} users: {users_to_enable}")
                # Enable each user individually
                await enable_selected_users(panel_data, set(users_to_enable))
                
                # Remove enabled users from disabled list
                for username in users_to_enable:
                    await dis_obj.remove_user(username)
                    logger.info(f"User {username} has been re-enabled")
        except Exception as e:
            logger.error(f"Error in enable_dis_user loop: {e}")
