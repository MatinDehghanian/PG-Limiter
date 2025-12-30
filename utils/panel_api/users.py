"""
User operations for panel API.
"""

import asyncio
import random
import time
from ssl import SSLError

import httpx

from utils.handel_dis_users import DisabledUsers
from utils.user_groups_storage import UserGroupsStorage
from utils.logs import logger, log_api_request, log_user_action, get_logger
from utils.read_config import read_config
from utils.types import PanelType, UserType
from utils.panel_api.auth import get_token, invalidate_token_cache, safe_send_logs_panel

# Module logger
users_logger = get_logger("panel_api.users")


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
    users_logger.debug("📋 Fetching all users from panel...")
    max_attempts = 5
    for attempt in range(max_attempts):
        users_logger.debug(f"📋 Attempt {attempt + 1}/{max_attempts}")
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
                    users_logger.error(f"Failed to parse JSON from {url}: {json_error}")
                    users_logger.debug(f"Response text: {response.text[:200]}")
                    continue
                
                if not isinstance(user_inform, dict):
                    users_logger.error(f"Response is not a dict: {type(user_inform)}")
                    continue
                
                if "users" not in user_inform:
                    users_logger.error(f"Response missing 'users' key. Keys: {list(user_inform.keys())}")
                    continue
                
                users = [
                    UserType(name=user["username"]) for user in user_inform["users"]
                ]
                users_logger.info(f"📋 Fetched {len(users)} users [{elapsed:.0f}ms]")
                return users
            except SSLError:
                elapsed = (time.perf_counter() - start_time) * 1000
                log_api_request("GET", url, None, elapsed, "SSL Error")
                continue
            except httpx.HTTPStatusError:
                elapsed = (time.perf_counter() - start_time) * 1000
                if response.status_code == 401:
                    await invalidate_token_cache()
                    users_logger.warning("Got 401 error, invalidating token cache and retrying")
                log_api_request("GET", url, response.status_code, elapsed, f"HTTP {response.status_code}")
                message = f"[{response.status_code}] {response.text}"
                await safe_send_logs_panel(message)
                users_logger.error(message)
                continue
            except httpx.TimeoutException:
                elapsed = (time.perf_counter() - start_time) * 1000
                log_api_request("GET", url, None, elapsed, "Timeout")
                users_logger.warning(f"Timeout fetching users from {url}")
                continue
            except Exception as error:  # pylint: disable=broad-except
                elapsed = (time.perf_counter() - start_time) * 1000
                log_api_request("GET", url, None, elapsed, str(error))
                message = f"An unexpected error occurred: {error}"
                await safe_send_logs_panel(message)
                users_logger.error(message)
                continue
        wait_time = min(30, random.randint(2, 5) * (attempt + 1))
        users_logger.debug(f"Waiting {wait_time}s before retry...")
        await asyncio.sleep(wait_time)
    message = (
        f"Failed to get users after {max_attempts} attempts. Make sure the panel is running "
        + "and the username and password are correct."
    )
    await safe_send_logs_panel(message)
    users_logger.error(message)
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
    users_logger.debug("📋 Fetching all panel users with pagination...")
    max_attempts = 5
    all_usernames = set()
    limit = 100
    
    for attempt in range(max_attempts):
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
        
        pagination_success = True
        while pagination_success:
            page_success = False
            for scheme in ["https", "http"]:
                url = f"{scheme}://{panel_data.panel_domain}/api/users?offset={offset}&limit={limit}"
                start_time = time.perf_counter()
                try:
                    async with httpx.AsyncClient(verify=False) as client:
                        response = await client.get(url, headers=headers, timeout=30)
                        elapsed = (time.perf_counter() - start_time) * 1000
                        response.raise_for_status()
                    
                    log_api_request("GET", url, response.status_code, elapsed)
                    
                    try:
                        data = response.json()
                    except Exception as json_error:
                        users_logger.error(f"Failed to parse JSON from {url}: {json_error}")
                        continue
                    
                    users = []
                    if isinstance(data, dict) and "users" in data:
                        users = data["users"]
                        total = data.get("total", len(users))
                    elif isinstance(data, list):
                        users = data
                        total = len(users)
                    else:
                        users_logger.error(f"Unexpected users response format: {type(data)}")
                        continue
                    
                    for user in users:
                        if isinstance(user, dict) and "username" in user:
                            all_usernames.add(user["username"])
                    
                    users_logger.debug(f"📋 Page fetched: offset={offset}, got {len(users)} users, total: {len(all_usernames)}")
                    
                    if len(users) < limit or offset + len(users) >= total:
                        users_logger.info(f"📋 Fetched {len(all_usernames)} users from panel (total: {total})")
                        return all_usernames
                    
                    offset += limit
                    page_success = True
                    break
                    
                except SSLError:
                    elapsed = (time.perf_counter() - start_time) * 1000
                    log_api_request("GET", url, None, elapsed, "SSL Error")
                    continue
                except httpx.HTTPStatusError:
                    elapsed = (time.perf_counter() - start_time) * 1000
                    if response.status_code == 401:
                        await invalidate_token_cache()
                        users_logger.warning("Got 401 error, invalidating token cache and retrying")
                    log_api_request("GET", url, response.status_code, elapsed, f"HTTP {response.status_code}")
                    message = f"[{response.status_code}] {response.text}"
                    users_logger.error(message)
                    continue
                except httpx.TimeoutException:
                    elapsed = (time.perf_counter() - start_time) * 1000
                    log_api_request("GET", url, None, elapsed, "Timeout")
                    users_logger.warning(f"Timeout fetching page at offset {offset}")
                    continue
                except Exception as error:
                    elapsed = (time.perf_counter() - start_time) * 1000
                    log_api_request("GET", url, None, elapsed, str(error))
                    message = f"An unexpected error occurred: {error}"
                    users_logger.error(message)
                    continue
            
            if not page_success:
                pagination_success = False
                users_logger.warning(f"Failed to fetch page at offset {offset}, will retry attempt")
                break
        
        wait_time = min(30, random.randint(2, 5) * (attempt + 1))
        users_logger.debug(f"Waiting {wait_time}s before retry...")
        await asyncio.sleep(wait_time)
    
    message = f"Failed to get all users after {max_attempts} attempts."
    users_logger.error(message)
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
    users_logger.debug(f"👤 Checking if user exists: {username}")
    max_attempts = 3
    for attempt in range(max_attempts):
        force_refresh = attempt > 0
        get_panel_token = await get_token(panel_data, force_refresh=force_refresh)
        if isinstance(get_panel_token, ValueError):
            users_logger.error(f"Failed to get token while checking user {username}")
            return False
        token = get_panel_token.panel_token
        headers = {
            "Authorization": f"Bearer {token}",
        }
        for scheme in ["https", "http"]:
            url = f"{scheme}://{panel_data.panel_domain}/api/user/{username}"
            start_time = time.perf_counter()
            try:
                async with httpx.AsyncClient(verify=False) as client:
                    response = await client.get(url, headers=headers, timeout=10)
                    elapsed = (time.perf_counter() - start_time) * 1000
                    
                    if response.status_code == 200:
                        log_api_request("GET", url, 200, elapsed)
                        users_logger.debug(f"👤 User {username} exists [{elapsed:.0f}ms]")
                        return True
                    elif response.status_code == 404:
                        log_api_request("GET", url, 404, elapsed)
                        users_logger.debug(f"👤 User {username} not found [{elapsed:.0f}ms]")
                        return False
                    elif response.status_code == 401:
                        log_api_request("GET", url, 401, elapsed, "Unauthorized")
                        await invalidate_token_cache()
                        users_logger.warning("Got 401 error, invalidating token cache and retrying")
                        break
                    else:
                        log_api_request("GET", url, response.status_code, elapsed)
                        users_logger.warning(f"Unexpected status {response.status_code} checking user {username}")
                        continue
                    
            except SSLError:
                elapsed = (time.perf_counter() - start_time) * 1000
                log_api_request("GET", url, None, elapsed, "SSL Error")
                continue
            except httpx.TimeoutException:
                elapsed = (time.perf_counter() - start_time) * 1000
                log_api_request("GET", url, None, elapsed, "Timeout")
                users_logger.warning(f"Timeout checking user {username}")
                continue
            except Exception as error:
                elapsed = (time.perf_counter() - start_time) * 1000
                log_api_request("GET", url, None, elapsed, str(error))
                users_logger.error(f"Error checking user existence: {error}")
                continue
        
        wait_time = min(10, random.randint(1, 3) * (attempt + 1))
        await asyncio.sleep(wait_time)
    
    users_logger.warning(f"Could not verify if user {username} exists, assuming exists")
    return True


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
    users_logger.debug(f"👤 Getting details for user: {username}")
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
            start_time = time.perf_counter()
            try:
                async with httpx.AsyncClient(verify=False) as client:
                    response = await client.get(url, headers=headers, timeout=10)
                    elapsed = (time.perf_counter() - start_time) * 1000
                    response.raise_for_status()
                
                log_api_request("GET", url, response.status_code, elapsed)
                
                try:
                    user_data = response.json()
                except Exception as json_error:
                    users_logger.error(f"Failed to parse JSON from {url}: {json_error}")
                    continue
                
                users_logger.debug(f"👤 Got details for {username}: groups={user_data.get('group_ids', [])} [{elapsed:.0f}ms]")
                return user_data
                    
            except SSLError:
                elapsed = (time.perf_counter() - start_time) * 1000
                log_api_request("GET", url, None, elapsed, "SSL Error")
                continue
            except httpx.HTTPStatusError:
                elapsed = (time.perf_counter() - start_time) * 1000
                if response.status_code == 401:
                    await invalidate_token_cache()
                    users_logger.warning("Got 401 error, invalidating token cache and retrying")
                if response.status_code == 404:
                    log_api_request("GET", url, 404, elapsed)
                    users_logger.warning(f"User {username} not found")
                    return None
                log_api_request("GET", url, response.status_code, elapsed, f"HTTP {response.status_code}")
                message = f"[{response.status_code}] {response.text}"
                users_logger.error(message)
                continue
            except httpx.TimeoutException:
                elapsed = (time.perf_counter() - start_time) * 1000
                log_api_request("GET", url, None, elapsed, "Timeout")
                users_logger.warning(f"Timeout getting details for {username}")
                continue
            except Exception as error:
                elapsed = (time.perf_counter() - start_time) * 1000
                log_api_request("GET", url, None, elapsed, str(error))
                message = f"An unexpected error occurred: {error}"
                users_logger.error(message)
                continue
        wait_time = min(30, random.randint(2, 5) * (attempt + 1))
        await asyncio.sleep(wait_time)
    message = f"Failed to get user details for {username} after {max_attempts} attempts."
    users_logger.error(message)
    raise ValueError(message)


async def get_user_admin(panel_data: PanelType, username: str) -> str | None:
    """
    Get the admin (owner) username for a specific user.

    Args:
        panel_data (PanelType): Panel connection data.
        username (str): The username to check.

    Returns:
        str | None: The admin username who owns this user, or None if not found.
    """
    users_logger.debug(f"👤 Getting admin for user: {username}")
    try:
        user_details = await get_user_details(panel_data, username)
        if user_details and "admin" in user_details:
            admin_info = user_details["admin"]
            if isinstance(admin_info, dict) and "username" in admin_info:
                admin_name = admin_info["username"]
                users_logger.debug(f"👤 User {username} owned by admin: {admin_name}")
                return admin_name
            elif isinstance(admin_info, str):
                users_logger.debug(f"👤 User {username} owned by admin: {admin_info}")
                return admin_info
        users_logger.debug(f"👤 No admin found for user: {username}")
        return None
    except Exception as e:
        users_logger.error(f"Error getting admin for user {username}: {e}")
        return None


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
    users_logger.info(f"👥 Updating groups for user {username} to {group_ids}")
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
            start_time = time.perf_counter()
            try:
                async with httpx.AsyncClient(verify=False) as client:
                    response = await client.put(
                        url, json=payload, headers=headers, timeout=10
                    )
                    elapsed = (time.perf_counter() - start_time) * 1000
                    response.raise_for_status()
                log_api_request("PUT", url, response.status_code, elapsed)
                log_user_action("UPDATE_GROUPS", username, f"groups={group_ids}", success=True)
                users_logger.info(f"👥 Updated groups for user {username} to {group_ids} [{elapsed:.0f}ms]")
                return True
                    
            except SSLError:
                elapsed = (time.perf_counter() - start_time) * 1000
                log_api_request("PUT", url, None, elapsed, "SSL Error")
                continue
            except httpx.HTTPStatusError:
                elapsed = (time.perf_counter() - start_time) * 1000
                if response.status_code == 401:
                    await invalidate_token_cache()
                    users_logger.warning("Got 401 error, invalidating token cache and retrying")
                log_api_request("PUT", url, response.status_code, elapsed, f"HTTP {response.status_code}")
                message = f"[{response.status_code}] {response.text}"
                users_logger.error(message)
                continue
            except httpx.TimeoutException:
                elapsed = (time.perf_counter() - start_time) * 1000
                log_api_request("PUT", url, None, elapsed, "Timeout")
                users_logger.warning(f"Timeout updating groups for {username}")
                continue
            except Exception as error:
                elapsed = (time.perf_counter() - start_time) * 1000
                log_api_request("PUT", url, None, elapsed, str(error))
                message = f"An unexpected error occurred: {error}"
                users_logger.error(message)
                continue
        wait_time = min(30, random.randint(2, 5) * (attempt + 1))
        await asyncio.sleep(wait_time)
    message = f"Failed to update groups for user {username} after {max_attempts} attempts."
    log_user_action("UPDATE_GROUPS", username, message, success=False)
    users_logger.error(message)
    return False


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
    users_logger.info("✅ Enabling all users...")
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
    
    enabled_count = 0
    failed_count = 0
    for username in users:
        for scheme in ["https", "http"]:
            url = f"{scheme}://{panel_data.panel_domain}/api/user/{username.name}"
            status = {"status": "active"}
            start_time = time.perf_counter()
            try:
                async with httpx.AsyncClient(verify=False) as client:
                    response = await client.put(
                        url, json=status, headers=headers, timeout=5
                    )
                    elapsed = (time.perf_counter() - start_time) * 1000
                    response.raise_for_status()
                log_api_request("PUT", url, response.status_code, elapsed)
                log_user_action("ENABLE", username.name, success=True)
                message = f"Enabled user: {username.name}"
                await safe_send_logs_panel(message)
                users_logger.debug(message)
                enabled_count += 1
                break
            except SSLError:
                continue
            except httpx.HTTPStatusError:
                elapsed = (time.perf_counter() - start_time) * 1000
                log_api_request("PUT", url, response.status_code, elapsed, f"HTTP {response.status_code}")
                message = f"[{response.status_code}] {response.text}"
                await safe_send_logs_panel(message)
                log_user_action("ENABLE", username.name, message, success=False)
                users_logger.error(message)
                failed_count += 1
                continue
            except Exception as error:  # pylint: disable=broad-except
                elapsed = (time.perf_counter() - start_time) * 1000
                log_api_request("PUT", url, None, elapsed, str(error))
                message = f"An unexpected error occurred: {error}"
                await safe_send_logs_panel(message)
                log_user_action("ENABLE", username.name, message, success=False)
                users_logger.error(message)
                failed_count += 1
    users_logger.info(f"✅ Enabled all users: {enabled_count} success, {failed_count} failed")


async def enable_user_by_status(panel_data: PanelType, username: str) -> bool:
    """
    Enable a user by changing their status to 'active'.

    Args:
        panel_data (PanelType): Panel connection data.
        username (str): The username to enable.

    Returns:
        bool: True if successful, False otherwise.
    """
    users_logger.debug(f"✅ Enabling user by status: {username}")
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
            start_time = time.perf_counter()
            try:
                async with httpx.AsyncClient(verify=False) as client:
                    response = await client.put(url, json=status, headers=headers, timeout=5)
                    elapsed = (time.perf_counter() - start_time) * 1000
                    response.raise_for_status()
                log_api_request("PUT", url, response.status_code, elapsed)
                log_user_action("ENABLE", username, "status=active", success=True)
                users_logger.info(f"✅ Enabled user by status: {username} [{elapsed:.0f}ms]")
                return True
            except SSLError:
                elapsed = (time.perf_counter() - start_time) * 1000
                log_api_request("PUT", url, None, elapsed, "SSL Error")
                continue
            except httpx.HTTPStatusError:
                elapsed = (time.perf_counter() - start_time) * 1000
                if response.status_code == 401:
                    await invalidate_token_cache()
                log_api_request("PUT", url, response.status_code, elapsed, f"HTTP {response.status_code}")
                continue
            except httpx.TimeoutException:
                elapsed = (time.perf_counter() - start_time) * 1000
                log_api_request("PUT", url, None, elapsed, "Timeout")
                continue
            except Exception as error:
                elapsed = (time.perf_counter() - start_time) * 1000
                log_api_request("PUT", url, None, elapsed, str(error))
                users_logger.error(f"Error enabling user: {error}")
                continue
        wait_time = min(30, random.randint(2, 5) * (attempt + 1))
        await asyncio.sleep(wait_time)
    log_user_action("ENABLE", username, "Failed after max attempts", success=False)
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
    users_logger.debug(f"✅ Enabling user by group restore: {username}")
    try:
        groups_storage = UserGroupsStorage()
        original_groups = await groups_storage.get_user_groups(username)
        
        if original_groups is None:
            users_logger.warning(f"No saved groups found for user {username}, cannot restore")
            return False
        
        users_logger.debug(f"👥 Restoring original groups for {username}: {original_groups}")
        group_success = await update_user_groups(panel_data, username, original_groups)
        status_success = await enable_user_by_status(panel_data, username)
        
        if group_success and status_success:
            await groups_storage.remove_user(username)
            log_user_action("ENABLE", username, f"restored groups {original_groups}, status active", success=True)
            users_logger.info(f"✅ Enabled user by group: {username} (restored groups {original_groups}, status active)")
            return True
        elif group_success:
            await groups_storage.remove_user(username)
            log_user_action("ENABLE", username, f"restored groups {original_groups}, status change failed", success=True)
            users_logger.warning(f"✅ Enabled user by group: {username} (restored groups {original_groups}, but status change failed)")
            return True
        log_user_action("ENABLE", username, "Failed to restore groups", success=False)
        return False
    except Exception as error:
        users_logger.error(f"Error enabling user by group: {error}")
        log_user_action("ENABLE", username, str(error), success=False)
        return False


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
    users_logger.info(f"✅ Enabling {len(inactive_users)} selected users...")
    data = await read_config()
    disable_method = data.get("disable_method", "status")
    disabled_group_id = data.get("disabled_group_id", None)
    use_group_method = disable_method == "group" and disabled_group_id is not None
    
    users_logger.debug(f"Using enable method: {'group' if use_group_method else 'status'}")
    
    enabled_count = 0
    failed_count = 0
    
    for username in inactive_users:
        success = False
        
        if use_group_method:
            groups_storage = UserGroupsStorage()
            has_saved_groups = await groups_storage.has_saved_groups(username)
            
            if has_saved_groups:
                success = await enable_user_by_group(panel_data, username)
                if success:
                    message = f"Enabled user (restored groups): {username}"
                    await safe_send_logs_panel(message)
                    enabled_count += 1
            else:
                users_logger.warning(f"No saved groups for {username}, using status-based enable")
                success = await enable_user_by_status(panel_data, username)
                if success:
                    message = f"Enabled user: {username}"
                    await safe_send_logs_panel(message)
                    enabled_count += 1
        else:
            success = await enable_user_by_status(panel_data, username)
            if success:
                message = f"Enabled user: {username}"
                await safe_send_logs_panel(message)
                enabled_count += 1
        
        if not success:
            message = f"Failed to enable user: {username}"
            await safe_send_logs_panel(message)
            users_logger.error(message)
            failed_count += 1
            raise ValueError(message)
    
    users_logger.info(f"✅ Enabled selected users: {enabled_count} success, {failed_count} failed")


async def disable_user_by_status(panel_data: PanelType, username: str) -> bool:
    """
    Disable a user by changing their status to 'disabled'.

    Args:
        panel_data (PanelType): Panel connection data.
        username (str): The username to disable.

    Returns:
        bool: True if successful, False otherwise.
    """
    users_logger.debug(f"🚫 Disabling user by status: {username}")
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
            start_time = time.perf_counter()
            try:
                async with httpx.AsyncClient(verify=False) as client:
                    response = await client.put(url, json=status, headers=headers, timeout=5)
                    elapsed = (time.perf_counter() - start_time) * 1000
                    response.raise_for_status()
                log_api_request("PUT", url, response.status_code, elapsed)
                log_user_action("DISABLE", username, "status=disabled", success=True)
                users_logger.info(f"🚫 Disabled user by status: {username} [{elapsed:.0f}ms]")
                return True
            except SSLError:
                elapsed = (time.perf_counter() - start_time) * 1000
                log_api_request("PUT", url, None, elapsed, "SSL Error")
                continue
            except httpx.HTTPStatusError:
                elapsed = (time.perf_counter() - start_time) * 1000
                if response.status_code == 401:
                    await invalidate_token_cache()
                log_api_request("PUT", url, response.status_code, elapsed, f"HTTP {response.status_code}")
                continue
            except httpx.TimeoutException:
                elapsed = (time.perf_counter() - start_time) * 1000
                log_api_request("PUT", url, None, elapsed, "Timeout")
                continue
            except Exception as error:
                elapsed = (time.perf_counter() - start_time) * 1000
                log_api_request("PUT", url, None, elapsed, str(error))
                users_logger.error(f"Error disabling user: {error}")
                continue
        wait_time = min(30, random.randint(2, 5) * (attempt + 1))
        await asyncio.sleep(wait_time)
    log_user_action("DISABLE", username, "Failed after max attempts", success=False)
    return False


async def disable_user_by_group(panel_data: PanelType, username: str, disabled_group_id: int) -> bool:
    """
    Disable a user by moving them to the disabled group and setting status to disabled.

    Args:
        panel_data (PanelType): Panel connection data.
        username (str): The username to disable.
        disabled_group_id (int): The group ID to move user to.

    Returns:
        bool: True if successful, False otherwise.
    """
    users_logger.debug(f"🚫 Disabling user by group: {username} -> group {disabled_group_id}")
    try:
        user_data = await get_user_details(panel_data, username)
        if user_data is None:
            users_logger.error(f"User {username} not found")
            return False
        
        current_groups = user_data.get("group_ids", [])
        users_logger.debug(f"👥 Saving current groups for {username}: {current_groups}")
        
        groups_storage = UserGroupsStorage()
        await groups_storage.save_user_groups(username, current_groups)
        
        group_success = await update_user_groups(panel_data, username, [disabled_group_id])
        status_success = await disable_user_by_status(panel_data, username)
        
        if group_success and status_success:
            log_user_action("DISABLE", username, f"moved to group {disabled_group_id}, status disabled", success=True)
            users_logger.info(f"🚫 Disabled user by group: {username} (moved to group {disabled_group_id}, status disabled)")
            return True
        elif group_success:
            log_user_action("DISABLE", username, f"moved to group {disabled_group_id}, status change failed", success=True)
            users_logger.warning(f"🚫 Disabled user by group: {username} (moved to group {disabled_group_id}, but status change failed)")
            return True
        log_user_action("DISABLE", username, "Failed to move to disabled group", success=False)
        return False
    except Exception as error:
        users_logger.error(f"Error disabling user by group: {error}")
        log_user_action("DISABLE", username, str(error), success=False)
        return False


async def disable_user(panel_data: PanelType, username: UserType, duration_seconds: int = 0) -> None | ValueError:
    """
    Disable a user on the panel.
    Uses either status-based or group-based disabling depending on config.

    Args:
        panel_data (PanelType): A PanelType object containing
        the username, password, and domain for the panel API.
        username (user): The username of the user to disable.
        duration_seconds (int): Optional custom disable duration in seconds.

    Returns:
        None

    Raises:
        ValueError: If the function fails to disable the user.
    """
    users_logger.info(f"🚫 Disabling user: {username.name} (duration={duration_seconds}s)")
    
    user_exists = await check_user_exists(panel_data, username.name)
    if not user_exists:
        message = f"User {username.name} not found in panel (deleted?), skipping disable"
        users_logger.warning(message)
        await safe_send_logs_panel(message)
        return None
    
    data = await read_config()
    disable_method = data.get("disable_method", "status")
    disabled_group_id = data.get("disabled_group_id", None)
    
    users_logger.debug(f"Using disable method: {disable_method} (disabled_group_id={disabled_group_id})")
    
    success = False
    
    if disable_method == "group" and disabled_group_id is not None:
        success = await disable_user_by_group(panel_data, username.name, disabled_group_id)
        if success:
            message = f"Disabled user (moved to disabled group): {username.name}"
            await safe_send_logs_panel(message)
    else:
        success = await disable_user_by_status(panel_data, username.name)
        if success:
            message = f"Disabled user: {username.name}"
            await safe_send_logs_panel(message)
    
    if success:
        dis_obj = DisabledUsers()
        await dis_obj.add_user(username.name, duration_seconds)
        users_logger.info(f"🚫 User {username.name} added to disabled users list")
        return None
    
    message = f"Failed to disable user: {username.name}"
    await safe_send_logs_panel(message)
    users_logger.error(message)
    raise ValueError(message)


async def disable_user_with_punishment(panel_data: PanelType, username: UserType) -> dict:
    """
    Disable a user using the smart punishment system.
    Applies escalating punishments based on violation history.

    Args:
        panel_data (PanelType): A PanelType object containing
        the username, password, and domain for the panel API.
        username (UserType): The username of the user to disable.

    Returns:
        dict: Result containing action, step_index, violation_count, duration_minutes, message
    """
    from utils.punishment_system import get_punishment_for_user, record_user_violation
    
    users_logger.info(f"⚖️ Processing punishment for user: {username.name}")
    
    user_exists = await check_user_exists(panel_data, username.name)
    if not user_exists:
        message = f"User {username.name} not found in panel (deleted?), skipping"
        users_logger.warning(message)
        return {
            "action": "skipped",
            "step_index": 0,
            "violation_count": 0,
            "duration_minutes": 0,
            "message": message
        }
    
    data = await read_config()
    punishment, step_index, violation_count = await get_punishment_for_user(username.name, data)
    
    users_logger.debug(f"⚖️ Punishment for {username.name}: step={step_index}, violations={violation_count}, type={punishment.step_type if punishment else 'none'}")
    
    punishment_enabled = data.get("punishment", {}).get("enabled", True)
    
    if not punishment_enabled:
        users_logger.debug(f"⚖️ Punishment system disabled, using simple disable for {username.name}")
        try:
            await disable_user(panel_data, username)
            return {
                "action": "disabled",
                "step_index": 0,
                "violation_count": 0,
                "duration_minutes": 0,
                "message": f"User {username.name} disabled (punishment system disabled)"
            }
        except ValueError as e:
            return {
                "action": "error",
                "step_index": 0,
                "violation_count": 0,
                "duration_minutes": 0,
                "message": str(e)
            }
    
    if punishment.is_warning():
        await record_user_violation(username.name, step_index, 0)
        message = (f"⚠️ Warning #{violation_count + 1} for {username.name}\n"
                   f"Next violation will result in: {punishment.get_display_text() if step_index + 1 >= len(data.get('punishment', {}).get('steps', [])) else 'disable'}")
        users_logger.info(f"⚠️ Warning issued to {username.name} (violation #{violation_count + 1})")
        return {
            "action": "warning",
            "step_index": step_index,
            "violation_count": violation_count + 1,
            "duration_minutes": 0,
            "message": message
        }
    
    duration_seconds = punishment.get_duration_seconds()
    
    try:
        await disable_user(panel_data, username, duration_seconds)
        await record_user_violation(username.name, step_index, punishment.duration_minutes)
        
        if punishment.is_unlimited_disable():
            message = f"🚫 User {username.name} disabled permanently (violation #{violation_count + 1})"
            users_logger.info(f"🚫 Permanent disable for {username.name} (violation #{violation_count + 1})")
        else:
            message = f"🔒 User {username.name} disabled for {punishment.duration_minutes} minutes (violation #{violation_count + 1})"
            users_logger.info(f"🔒 Timed disable for {username.name}: {punishment.duration_minutes}min (violation #{violation_count + 1})")
        
        return {
            "action": "disabled",
            "step_index": step_index,
            "violation_count": violation_count + 1,
            "duration_minutes": punishment.duration_minutes,
            "message": message
        }
    except ValueError as e:
        users_logger.error(f"⚖️ Punishment failed for {username.name}: {e}")
        return {
            "action": "error",
            "step_index": step_index,
            "violation_count": violation_count,
            "duration_minutes": 0,
            "message": str(e)
        }


async def enable_dis_user(panel_data: PanelType):
    """
    Enable disabled users individually based on when each was disabled.
    Each user is enabled after 'time_to_active_users' seconds from their disable time.
    """
    users_logger.info("🔄 Starting disabled user enable loop...")
    while True:
        await asyncio.sleep(30)
        
        try:
            data = await read_config()
            time_to_active = data.get("monitoring", {}).get("time_to_active_users", 1800)
            
            dis_obj = DisabledUsers()
            users_to_enable = await dis_obj.get_users_to_enable(time_to_active)
            
            if users_to_enable:
                users_logger.info(f"✅ Enabling {len(users_to_enable)} users: {users_to_enable}")
                await enable_selected_users(panel_data, set(users_to_enable))
                
                for username in users_to_enable:
                    await dis_obj.remove_user(username)
                    users_logger.info(f"✅ User {username} has been re-enabled")
        except Exception as e:
            users_logger.error(f"Error in enable_dis_user loop: {e}")


async def cleanup_deleted_users(panel_data: PanelType) -> dict:
    """
    Clean up users from limiter config that no longer exist in the panel.

    Args:
        panel_data (PanelType): A PanelType object containing
        the username, password, and domain for the panel API.

    Returns:
        dict: A summary of cleaned up users with keys for each category.
    """
    users_logger.info("🧹 Starting cleanup of deleted users...")
    result = {
        "special_limits_removed": [],
        "except_users_removed": [],
        "disabled_users_removed": [],
        "user_groups_backup_removed": [],
    }
    
    try:
        panel_users = await get_all_panel_users(panel_data)
        users_logger.info(f"🧹 Found {len(panel_users)} users in panel")
        
        if len(panel_users) == 0:
            users_logger.error("No users found in panel - aborting cleanup to prevent data loss")
            raise ValueError("No users found in panel. API may be unreachable or returning empty data.")
        
        data = await read_config()
        config_changed = False
        
        special_limits = data.get("limits", {}).get("special", {})
        if special_limits:
            users_to_remove = [u for u in special_limits.keys() if u not in panel_users]
            if len(users_to_remove) > len(special_limits) * 0.5 and len(users_to_remove) > 5:
                users_logger.warning(f"Would remove {len(users_to_remove)} of {len(special_limits)} special limits - this seems too many!")
                users_logger.warning(f"Panel returned {len(panel_users)} users. First 10: {list(panel_users)[:10]}")
                raise ValueError(f"Safety check failed: Would remove {len(users_to_remove)} of {len(special_limits)} users.")
        
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
                users_logger.info(f"🧹 Removed deleted user from special limits: {username}")
        
        except_users = data.get("limits", {}).get("except_users", [])
        if except_users:
            new_except_users = [u for u in except_users if u in panel_users]
            removed = [u for u in except_users if u not in panel_users]
            if removed:
                data["limits"]["except_users"] = new_except_users
                result["except_users_removed"] = removed
                config_changed = True
                for username in removed:
                    users_logger.info(f"🧹 Removed deleted user from except_users: {username}")
        
        if config_changed:
            from telegram_bot.utils import write_json_file
            await write_json_file(data)
            users_logger.info("🧹 Config file updated")
        
        dis_obj = DisabledUsers()
        disabled_list = list(dis_obj.disabled_users.keys())
        for username in disabled_list:
            if username not in panel_users:
                await dis_obj.remove_user(username)
                result["disabled_users_removed"].append(username)
                users_logger.info(f"🧹 Removed deleted user from disabled_users: {username}")
        
        groups_storage = UserGroupsStorage()
        saved_users = await groups_storage.get_all_users_with_saved_groups()
        for username in saved_users:
            if username not in panel_users:
                await groups_storage.remove_user(username)
                result["user_groups_backup_removed"].append(username)
                users_logger.info(f"🧹 Removed deleted user from user groups backup: {username}")
        
        total_removed = (
            len(result["special_limits_removed"]) +
            len(result["except_users_removed"]) +
            len(result["disabled_users_removed"]) +
            len(result["user_groups_backup_removed"])
        )
        users_logger.info(f"🧹 Cleanup complete. Total removed: {total_removed}")
        
        return result
        
    except Exception as e:
        users_logger.error(f"Error during cleanup: {e}")
        raise
