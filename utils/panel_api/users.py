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


async def _fetch_users_page(
    client: httpx.AsyncClient,
    url: str,
    headers: dict,
    offset: int,
    limit: int,
) -> tuple[list[dict], int | None]:
    """Fetch a single page of users. Returns (users_list, total_count)."""
    page_url = f"{url}?offset={offset}&limit={limit}"
    start_time = time.perf_counter()
    
    response = await client.get(page_url, headers=headers, timeout=60)
    elapsed = (time.perf_counter() - start_time) * 1000
    response.raise_for_status()
    
    log_api_request("GET", page_url, response.status_code, elapsed)
    
    data = response.json()
    if not isinstance(data, dict) or "users" not in data:
        return [], None
    
    return data["users"], data.get("total")


async def all_user(panel_data: PanelType) -> list[UserType] | ValueError:
    """
    Get the list of all users from the panel API with parallel pagination.

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
    limit = 1000  # Fetch 1000 users per page
    max_concurrent = 10  # Max parallel requests
    
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
            
            try:
                async with httpx.AsyncClient(verify=False) as client:
                    # First request to get total count
                    start_time = time.perf_counter()
                    first_page_users, total_users = await _fetch_users_page(
                        client, url, headers, offset=0, limit=limit
                    )
                    
                    if total_users is None:
                        users_logger.error("Could not get total user count from API")
                        continue
                    
                    users_logger.info(f"📊 Panel reports {total_users} total users")
                    
                    # If all users fit in first page, we're done
                    if len(first_page_users) >= total_users or len(first_page_users) < limit:
                        all_user_data = first_page_users
                    else:
                        # Calculate remaining pages needed
                        remaining = total_users - len(first_page_users)
                        offsets = list(range(limit, total_users, limit))
                        
                        users_logger.info(f"📥 Fetching {len(offsets)} more pages in parallel (max {max_concurrent} concurrent)...")
                        
                        # Fetch remaining pages in parallel with semaphore
                        semaphore = asyncio.Semaphore(max_concurrent)
                        
                        def make_fetcher(sem, cli, u, hdrs):
                            async def fetch_with_semaphore(offset: int):
                                async with sem:
                                    users, _ = await _fetch_users_page(cli, u, hdrs, offset, limit)
                                    return users
                            return fetch_with_semaphore
                        
                        fetcher = make_fetcher(semaphore, client, url, headers)
                        tasks = [fetcher(offset) for offset in offsets]
                        pages = await asyncio.gather(*tasks, return_exceptions=True)
                        
                        # Combine all pages
                        all_user_data = first_page_users
                        for i, page in enumerate(pages):
                            if isinstance(page, Exception):
                                users_logger.error(f"Error fetching page {i+1}: {page}")
                                continue
                            all_user_data.extend(page)
                    
                    elapsed = (time.perf_counter() - start_time) * 1000
                    
                    # Convert to UserType objects
                    users = []
                    for user_data in all_user_data:
                        admin_info = user_data.get("admin")
                        admin_username = admin_info.get("username") if isinstance(admin_info, dict) else None
                        user = UserType(
                            name=user_data["username"],
                            panel_status=user_data.get("status"),
                            data_limit=user_data.get("data_limit"),
                            used_traffic=user_data.get("used_traffic"),
                            lifetime_used_traffic=user_data.get("lifetime_used_traffic"),
                            expire=user_data.get("expire"),
                            group_ids=user_data.get("group_ids"),
                            online_at=user_data.get("online_at"),
                            admin_username=admin_username,
                        )
                        users.append(user)
                    
                    users_logger.info(f"📋 Fetched all {len(users)} users in {elapsed:.0f}ms")
                    return users
                    
            except SSLError:
                elapsed = (time.perf_counter() - start_time) * 1000
                log_api_request("GET", url, None, elapsed, "SSL Error")
                continue
            except httpx.HTTPStatusError as e:
                elapsed = (time.perf_counter() - start_time) * 1000
                if e.response.status_code == 401:
                    await invalidate_token_cache()
                    users_logger.warning("Got 401 error, invalidating token cache and retrying")
                log_api_request("GET", url, e.response.status_code, elapsed, f"HTTP {e.response.status_code}")
                message = f"[{e.response.status_code}] {e.response.text}"
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


async def get_all_panel_users(
    panel_data: PanelType,
    status: str | None = None,
    admin: list[str] | None = None,
    group: list[int] | None = None,
    search: str | None = None,
) -> set[str] | ValueError:
    """
    Get all usernames from the panel API with optional filtering.

    Args:
        panel_data (PanelType): A PanelType object containing
            the username, password, and domain for the panel API.
        status (str | None): Filter by user status (active/disabled/limited/expired/on_hold).
        admin (list[str] | None): Filter by admin username(s).
        group (list[int] | None): Filter by group ID(s).
        search (str | None): Search query for usernames.

    Returns:
        set[str]: A set of all usernames matching the filters.

    Raises:
        ValueError: If the function fails to get users from the API.
    """
    filter_desc = []
    if status:
        filter_desc.append(f"status={status}")
    if admin:
        filter_desc.append(f"admin={admin}")
    if group:
        filter_desc.append(f"group={group}")
    if search:
        filter_desc.append(f"search={search}")
    filter_str = f" ({', '.join(filter_desc)})" if filter_desc else ""
    users_logger.debug(f"📋 Fetching panel users with pagination{filter_str}...")
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
                # Build query parameters
                params = [f"offset={offset}", f"limit={limit}"]
                if status:
                    params.append(f"status={status}")
                if admin:
                    for a in admin:
                        params.append(f"admin={a}")
                if group:
                    for g in group:
                        params.append(f"group={g}")
                if search:
                    params.append(f"search={search}")
                query_string = "&".join(params)
                url = f"{scheme}://{panel_data.panel_domain}/api/users?{query_string}"
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
    from utils.panel_api.request_helper import panel_get
    
    max_attempts = 3
    for attempt in range(max_attempts):
        force_refresh = attempt > 0
        
        response = await panel_get(
            panel_data,
            f"/api/user/{username}",
            force_refresh=force_refresh,
            timeout=10.0,
            max_retries=2
        )
        
        if response is not None:
            if response.status_code == 200:
                users_logger.debug(f"👤 User {username} exists")
                return True
            elif response.status_code == 404:
                users_logger.debug(f"👤 User {username} not found")
                return False
            elif response.status_code == 401:
                await invalidate_token_cache()
                users_logger.warning("Got 401 error, invalidating token cache and retrying")
                continue
        
        users_logger.warning(f"Attempt {attempt + 1}/{max_attempts} failed")
        
        if attempt < max_attempts - 1:
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
    from utils.panel_api.request_helper import panel_get
    
    users_logger.debug(f"👤 Getting details for user: {username}")
    max_attempts = 3
    
    for attempt in range(max_attempts):
        force_refresh = attempt > 0
        
        response = await panel_get(
            panel_data, 
            f"/api/user/{username}",
            force_refresh=force_refresh,
            timeout=10.0,
            max_retries=2
        )
        
        if response is not None:
            if response.status_code == 200:
                try:
                    user_data = response.json()
                    users_logger.debug(f"👤 Got details for {username}: groups={user_data.get('group_ids', [])}")
                    return user_data
                except Exception as json_error:
                    users_logger.error(f"Failed to parse JSON for {username}: {json_error}")
            elif response.status_code == 404:
                users_logger.warning(f"User {username} not found")
                return None
            elif response.status_code == 401:
                await invalidate_token_cache()
                users_logger.warning("Got 401 error, invalidating token cache and retrying")
                continue
        
        users_logger.warning(f"Attempt {attempt + 1}/{max_attempts} failed")
        
        if attempt < max_attempts - 1:
            wait_time = min(10, random.randint(1, 3) * (attempt + 1))
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
    from utils.panel_api.request_helper import panel_put
    
    users_logger.info(f"👥 Updating groups for user {username} to {group_ids}")
    max_attempts = 3
    
    for attempt in range(max_attempts):
        force_refresh = attempt > 0
        payload = {"group_ids": group_ids}
        
        response = await panel_put(
            panel_data,
            f"/api/user/{username}",
            json_data=payload,
            force_refresh=force_refresh,
            timeout=15.0,
            max_retries=2
        )
        
        if response is not None:
            if response.status_code in (200, 201):
                log_user_action("UPDATE_GROUPS", username, f"groups={group_ids}", success=True)
                users_logger.info(f"👥 Updated groups for user {username} to {group_ids}")
                return True
            elif response.status_code == 401:
                await invalidate_token_cache()
                users_logger.warning("Got 401 error, retrying...")
                continue
            elif response.status_code == 404:
                users_logger.warning(f"User {username} not found")
                return False
        
        users_logger.warning(f"Attempt {attempt + 1}/{max_attempts} failed")
        
        if attempt < max_attempts - 1:
            wait_time = min(10, random.randint(1, 3) * (attempt + 1))
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


async def enable_user_by_status(panel_data: PanelType, username: str) -> tuple[bool, bool]:
    """
    Enable a user by changing their status to 'active'.

    Args:
        panel_data (PanelType): Panel connection data.
        username (str): The username to enable.

    Returns:
        tuple[bool, bool]: (success, not_found)
            - success: True if user was successfully enabled
            - not_found: True if user doesn't exist (404), should be removed from disabled list
    """
    from utils.panel_api.request_helper import panel_put
    
    users_logger.debug(f"✅ Enabling user by status: {username}")
    max_attempts = 3
    
    for attempt in range(max_attempts):
        force_refresh = attempt > 0
        status = {"status": "active"}
        
        response = await panel_put(
            panel_data,
            f"/api/user/{username}",
            json_data=status,
            force_refresh=force_refresh,
            timeout=10.0,
            max_retries=2
        )
        
        if response is not None:
            if response.status_code in (200, 201):
                log_user_action("ENABLE", username, "status=active", success=True)
                users_logger.info(f"✅ Enabled user by status: {username}")
                return (True, False)  # success, not deleted
            elif response.status_code == 401:
                await invalidate_token_cache()
                users_logger.warning("Got 401 error, retrying...")
                continue
            elif response.status_code == 404:
                users_logger.warning(f"User {username} not found (deleted from panel)")
                log_user_action("ENABLE", username, "User not found (deleted)", success=False)
                return (False, True)  # failed, user was deleted
        
        users_logger.warning(f"Attempt {attempt + 1}/{max_attempts} failed")
        
        if attempt < max_attempts - 1:
            wait_time = min(10, random.randint(1, 3) * (attempt + 1))
            await asyncio.sleep(wait_time)
    
    log_user_action("ENABLE", username, "Failed after max attempts", success=False)
    return (False, False)  # failed, but user might still exist


async def enable_user_by_group(panel_data: PanelType, username: str) -> tuple[bool, bool]:
    """
    Enable a user by restoring their original groups and setting status to active.
    Combines both operations into a single API request.
    
    Tries to get original groups from:
    1. JSON file backup (.user_groups_backup.json)
    2. Database (User.original_groups field)
    3. Falls back to removing from disabled group without restoring groups

    Args:
        panel_data (PanelType): Panel connection data.
        username (str): The username to enable.

    Returns:
        tuple[bool, bool]: (success, not_found)
            - success: True if user was successfully enabled
            - not_found: True if user doesn't exist (404), should be removed from disabled list
    """
    users_logger.debug(f"✅ Enabling user by group restore: {username}")
    try:
        # Try 1: Get from JSON file storage
        groups_storage = UserGroupsStorage()
        original_groups = await groups_storage.get_user_groups(username)
        groups_source = "json"
        
        # Try 2: If not in JSON, try database
        if original_groups is None:
            users_logger.debug(f"📦 No groups in JSON for {username}, checking database...")
            try:
                from db.database import get_db_session
                from db.crud import UserCRUD
                
                async with get_db_session() as db:
                    user_record = await UserCRUD.get_disabled_record(db, username)
                    if user_record and user_record.original_groups:
                        original_groups = user_record.original_groups
                        groups_source = "database"
                        users_logger.info(f"📦 Found original groups in database for {username}: {original_groups}")
            except Exception as db_error:
                users_logger.debug(f"Could not check database for groups: {db_error}")
        
        if original_groups is None:
            users_logger.warning(f"No saved groups found for user {username} in JSON or database, will try to remove from disabled group")
            # Get config to check if user is in disabled group
            data = await read_config()
            disabled_group_id = data.get("disabled_group_id", None)
            
            # Always get current user details to check their group status
            user_data = await get_user_details(panel_data, username)
            if user_data is None:
                # User doesn't exist in panel (404)
                users_logger.warning(f"User {username} not found (deleted from panel)")
                # Clean up from JSON storage if exists
                await groups_storage.remove_user(username)
                return (False, True)  # failed, user was deleted
            
            current_groups = user_data.get("group_ids", []) or []
            
            if disabled_group_id is not None and disabled_group_id in current_groups:
                # User is in disabled group - remove them from it
                users_logger.info(f"👥 User {username} is in disabled group {disabled_group_id}, removing...")
                new_groups = [g for g in current_groups if g != disabled_group_id]
                # Combined API call: set both group_ids and status in one request
                success, not_found = await _update_user_groups_and_status(panel_data, username, new_groups, "active")
                if not_found:
                    await groups_storage.remove_user(username)
                    return (False, True)
                if success:
                    log_user_action("ENABLE", username, f"removed from disabled group {disabled_group_id}, status active (no saved groups)", success=True)
                    users_logger.info(f"✅ Enabled user: {username} (removed from disabled group, status active)")
                    return (True, False)
                else:
                    users_logger.error(f"❌ Failed to remove {username} from disabled group")
                    return (False, False)
            else:
                # User is NOT in disabled group - just update status and keep current groups
                users_logger.info(f"👥 User {username} not in disabled group (current groups: {current_groups}), updating status only")
                success, not_found = await _update_user_groups_and_status(panel_data, username, current_groups, "active")
                if not_found:
                    await groups_storage.remove_user(username)
                    return (False, True)
                if success:
                    log_user_action("ENABLE", username, f"status active, kept existing groups {current_groups}", success=True)
                    users_logger.info(f"✅ Enabled user: {username} (status active, groups unchanged)")
                    return (True, False)
                else:
                    users_logger.error(f"❌ Failed to enable {username}")
                    return (False, False)
        
        # We have original_groups - restore them
        # But first, ensure we don't accidentally restore the disabled group
        data = await read_config()
        disabled_group_id = data.get("disabled_group_id", None)
        
        # Filter out the disabled group from original_groups if present
        if disabled_group_id is not None and disabled_group_id in original_groups:
            users_logger.warning(f"⚠️ Removing disabled_group_id {disabled_group_id} from original_groups for {username}")
            original_groups = [g for g in original_groups if g != disabled_group_id]
        
        users_logger.debug(f"👥 Restoring original groups for {username} (from {groups_source}): {original_groups}")
        # Combined API call: set both group_ids and status in one request
        success, not_found = await _update_user_groups_and_status(panel_data, username, original_groups, "active")
        
        if not_found:
            # User was deleted - clean up from storage
            await groups_storage.remove_user(username)
            log_user_action("ENABLE", username, "User not found (deleted)", success=False)
            return (False, True)
        
        if success:
            # Clean up from JSON storage
            await groups_storage.remove_user(username)
            log_user_action("ENABLE", username, f"restored groups {original_groups} (from {groups_source}), status active", success=True)
            users_logger.info(f"✅ Enabled user by group: {username} (restored groups {original_groups}, status active)")
            return (True, False)
        log_user_action("ENABLE", username, "Failed to restore groups", success=False)
        return (False, False)
    except Exception as error:
        users_logger.error(f"Error enabling user by group: {error}")
        log_user_action("ENABLE", username, str(error), success=False)
        return (False, False)


async def _update_user_groups_and_status(panel_data: PanelType, username: str, group_ids: list[int], status: str) -> tuple[bool, bool]:
    """
    Internal helper to update both user groups and status in a single API call.
    
    Args:
        panel_data: Panel connection data.
        username: The username to update.
        group_ids: List of group IDs to set.
        status: Status to set ("active" or "disabled").
    
    Returns:
        tuple[bool, bool]: (success, not_found)
            - success: True if successful
            - not_found: True if user doesn't exist (404)
    """
    max_attempts = 5
    for attempt in range(max_attempts):
        force_refresh = attempt > 0
        get_panel_token = await get_token(panel_data, force_refresh=force_refresh)
        if isinstance(get_panel_token, ValueError):
            raise get_panel_token
        token = get_panel_token.panel_token
        headers = {"Authorization": f"Bearer {token}"}
        payload = {"group_ids": group_ids, "status": status}
        
        for scheme in ["https", "http"]:
            url = f"{scheme}://{panel_data.panel_domain}/api/user/{username}"
            start_time = time.perf_counter()
            try:
                async with httpx.AsyncClient(verify=False) as client:
                    response = await client.put(url, json=payload, headers=headers, timeout=10)
                    elapsed = (time.perf_counter() - start_time) * 1000
                    
                    # Check for 404 before raise_for_status
                    if response.status_code == 404:
                        log_api_request("PUT", url, 404, elapsed, "User not found")
                        users_logger.warning(f"User {username} not found (deleted from panel)")
                        return (False, True)  # failed, user was deleted
                    
                    response.raise_for_status()
                log_api_request("PUT", url, response.status_code, elapsed)
                users_logger.debug(f"Updated user {username}: groups={group_ids}, status={status} [{elapsed:.0f}ms]")
                return (True, False)  # success, not deleted
            except SSLError:
                elapsed = (time.perf_counter() - start_time) * 1000
                log_api_request("PUT", url, None, elapsed, "SSL Error")
                continue
            except httpx.HTTPStatusError:
                elapsed = (time.perf_counter() - start_time) * 1000
                if response.status_code == 401:
                    await invalidate_token_cache()
                elif response.status_code == 404:
                    log_api_request("PUT", url, 404, elapsed, "User not found")
                    users_logger.warning(f"User {username} not found (deleted from panel)")
                    return (False, True)  # failed, user was deleted
                log_api_request("PUT", url, response.status_code, elapsed, f"HTTP {response.status_code}")
                continue
            except httpx.TimeoutException:
                elapsed = (time.perf_counter() - start_time) * 1000
                log_api_request("PUT", url, None, elapsed, "Timeout")
                continue
            except Exception as error:
                elapsed = (time.perf_counter() - start_time) * 1000
                log_api_request("PUT", url, None, elapsed, str(error))
                users_logger.error(f"Error updating user: {error}")
                continue
        wait_time = min(30, random.randint(2, 5) * (attempt + 1))
        await asyncio.sleep(wait_time)
    return (False, False)  # failed, but user might still exist


async def enable_selected_users(
    panel_data: PanelType, inactive_users: set[str]
) -> dict[str, list[str]]:
    """
    Enable selected users on the panel.
    Uses either status-based or group-based enabling depending on config.

    Args:
        panel_data (PanelType): A PanelType object containing
        the username, password, and domain for the panel API.
        inactive_users (set[str]): A list of user str that are currently inactive.

    Returns:
        dict with 'enabled', 'failed', and 'not_found' lists of usernames.
        - enabled: Users successfully enabled
        - failed: Users that failed but might still exist (retry later)
        - not_found: Users that were deleted from panel (should be removed from disabled list)
    """
    users_logger.info(f"✅ Enabling {len(inactive_users)} selected users...")
    data = await read_config()
    disable_method = data.get("disable_method", "status")
    disabled_group_id = data.get("disabled_group_id", None)
    use_group_method = disable_method == "group" and disabled_group_id is not None
    
    users_logger.debug(f"Using enable method: {'group' if use_group_method else 'status'}")
    
    enabled_users: list[str] = []
    failed_users: list[str] = []
    not_found_users: list[str] = []  # Users deleted from panel
    
    for username in inactive_users:
        try:
            if use_group_method:
                # Always try group-based enable when using group method
                # enable_user_by_group now handles cases with and without saved groups
                success, not_found = await enable_user_by_group(panel_data, username)
                if not_found:
                    message = f"User {username} was deleted from panel, removing from disabled list"
                    await safe_send_logs_panel(message)
                    users_logger.warning(message)
                    not_found_users.append(username)
                elif success:
                    message = f"Enabled user (group method): {username}"
                    await safe_send_logs_panel(message)
                    enabled_users.append(username)
                else:
                    message = f"Failed to enable user: {username}"
                    await safe_send_logs_panel(message)
                    users_logger.error(message)
                    failed_users.append(username)
            else:
                success, not_found = await enable_user_by_status(panel_data, username)
                if not_found:
                    message = f"User {username} was deleted from panel, removing from disabled list"
                    await safe_send_logs_panel(message)
                    users_logger.warning(message)
                    not_found_users.append(username)
                elif success:
                    message = f"Enabled user: {username}"
                    await safe_send_logs_panel(message)
                    enabled_users.append(username)
                else:
                    message = f"Failed to enable user: {username}"
                    await safe_send_logs_panel(message)
                    users_logger.error(message)
                    failed_users.append(username)
        except Exception as e:
            message = f"Failed to enable user {username}: {e}"
            await safe_send_logs_panel(message)
            users_logger.error(message)
            failed_users.append(username)
    
    users_logger.info(f"✅ Enabled selected users: {len(enabled_users)} success, {len(failed_users)} failed, {len(not_found_users)} not found")
    return {"enabled": enabled_users, "failed": failed_users, "not_found": not_found_users}


async def disable_user_by_status(panel_data: PanelType, username: str) -> bool:
    """
    Disable a user by changing their status to 'disabled'.

    Args:
        panel_data (PanelType): Panel connection data.
        username (str): The username to disable.

    Returns:
        bool: True if successful, False otherwise.
    """
    from utils.panel_api.request_helper import panel_put
    
    users_logger.debug(f"🚫 Disabling user by status: {username}")
    max_attempts = 3
    
    for attempt in range(max_attempts):
        force_refresh = attempt > 0
        status = {"status": "disabled"}
        
        response = await panel_put(
            panel_data,
            f"/api/user/{username}",
            json_data=status,
            force_refresh=force_refresh,
            timeout=10.0,
            max_retries=2
        )
        
        if response is not None:
            if response.status_code in (200, 201):
                log_user_action("DISABLE", username, "status=disabled", success=True)
                users_logger.info(f"🚫 Disabled user by status: {username}")
                return True
            elif response.status_code == 401:
                await invalidate_token_cache()
                users_logger.warning("Got 401 error, retrying...")
                continue
            elif response.status_code == 404:
                users_logger.warning(f"User {username} not found")
                return False
        
        users_logger.warning(f"Attempt {attempt + 1}/{max_attempts} failed")
        
        if attempt < max_attempts - 1:
            wait_time = min(10, random.randint(1, 3) * (attempt + 1))
            await asyncio.sleep(wait_time)
    
    log_user_action("DISABLE", username, "Failed after max attempts", success=False)
    return False


async def disable_user_by_group(panel_data: PanelType, username: str, disabled_group_id: int) -> bool:
    """
    Disable a user by moving them to the disabled group and setting status to disabled.
    Combines both operations into a single API request.
    Saves original groups to both JSON file and database for redundancy.

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
        
        current_groups = user_data.get("group_ids", []) or []
        
        # IMPORTANT: Filter out the disabled_group_id from saved groups
        # This prevents saving the disabled group as an "original" group
        original_groups_to_save = [g for g in current_groups if g != disabled_group_id]
        
        users_logger.debug(f"👥 Saving current groups for {username}: {original_groups_to_save} (filtered from {current_groups})")
        
        # Save to JSON file (primary backup)
        groups_storage = UserGroupsStorage()
        await groups_storage.save_user_groups(username, original_groups_to_save)
        
        # Also save to database (secondary backup for redundancy)
        try:
            from db.database import get_db_session
            from db.crud import UserCRUD
            
            async with get_db_session() as db:
                user_record = await UserCRUD.get_by_username(db, username)
                if user_record:
                    user_record.original_groups = original_groups_to_save
                    await db.commit()
                    users_logger.debug(f"📦 Saved groups to database for {username}: {current_groups}")
        except Exception as db_error:
            users_logger.warning(f"Could not save groups to database (JSON backup exists): {db_error}")
        
        # Combined API call: set both group_ids and status in one request
        max_attempts = 5
        for attempt in range(max_attempts):
            force_refresh = attempt > 0
            get_panel_token = await get_token(panel_data, force_refresh=force_refresh)
            if isinstance(get_panel_token, ValueError):
                raise get_panel_token
            token = get_panel_token.panel_token
            headers = {"Authorization": f"Bearer {token}"}
            # Combine group_ids and status in a single payload
            payload = {"group_ids": [disabled_group_id], "status": "disabled"}
            
            for scheme in ["https", "http"]:
                url = f"{scheme}://{panel_data.panel_domain}/api/user/{username}"
                start_time = time.perf_counter()
                try:
                    async with httpx.AsyncClient(verify=False) as client:
                        response = await client.put(url, json=payload, headers=headers, timeout=10)
                        elapsed = (time.perf_counter() - start_time) * 1000
                        response.raise_for_status()
                    log_api_request("PUT", url, response.status_code, elapsed)
                    log_user_action("DISABLE", username, f"moved to group {disabled_group_id}, status disabled", success=True)
                    users_logger.info(f"🚫 Disabled user by group: {username} (moved to group {disabled_group_id}, status disabled) [{elapsed:.0f}ms]")
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
    Handles partial success - removes only successfully enabled users from disabled list.
    Also removes users that were deleted from the panel to stop retry loops.
    Waits for panel to be available during restarts.
    """
    from utils.panel_api.request_helper import is_panel_available, wait_for_panel
    
    users_logger.info("🔄 Starting disabled user enable loop...")
    while True:
        await asyncio.sleep(30)
        
        try:
            # Check if panel is available, wait if not
            if not is_panel_available():
                users_logger.warning("⏳ Panel unavailable, waiting for it to come back...")
                if not await wait_for_panel(panel_data):
                    users_logger.error("❌ Panel still unavailable after waiting, skipping this cycle")
                    continue
            
            data = await read_config()
            time_to_active = data.get("monitoring", {}).get("time_to_active_users", 1800)
            
            dis_obj = DisabledUsers()
            users_to_enable = await dis_obj.get_users_to_enable(time_to_active)
            
            if users_to_enable:
                users_logger.info(f"✅ Enabling {len(users_to_enable)} users: {users_to_enable}")
                result = await enable_selected_users(panel_data, set(users_to_enable))
                
                # Remove successfully enabled users from disabled list
                enabled = result.get("enabled", [])
                failed = result.get("failed", [])
                not_found = result.get("not_found", [])
                
                for username in enabled:
                    await dis_obj.remove_user(username)
                    users_logger.info(f"✅ User {username} has been re-enabled")
                
                # Remove users that were deleted from panel (404) to stop retry loops
                for username in not_found:
                    await dis_obj.remove_user(username)
                    users_logger.info(f"🗑️ User {username} was deleted from panel, removed from disabled list")
                
                # Log failed users but don't remove them - they will be retried next cycle
                if failed:
                    users_logger.warning(f"⚠️ Failed to enable {len(failed)} users (will retry): {failed}")
        except Exception as e:
            users_logger.error(f"Error in enable_dis_user loop: {e}")
        except Exception as e:
            users_logger.error(f"Error in enable_dis_user loop: {e}")


async def cleanup_deleted_users(panel_data: PanelType) -> dict:
    """
    DISABLED: This function is currently disabled as it was incorrectly removing valid users.
    
    The function was checking against old JSON config format while special limits
    are now stored in the database, causing it to incorrectly identify users
    as "deleted" when they actually exist.
    
    Use the Telegram bot's "Review Pending Deletions" feature instead:
    Settings -> User Sync Settings -> Review Pending Deletions
    
    Args:
        panel_data (PanelType): A PanelType object containing
        the username, password, and domain for the panel API.

    Returns:
        dict: Empty result as function is disabled.
    """
    users_logger.warning("⚠️ cleanup_deleted_users is DISABLED - use Telegram bot instead")
    users_logger.warning("📱 Telegram: Settings -> User Sync -> Review Pending Deletions")
    return {
        "special_limits_removed": [],
        "except_users_removed": [],
        "disabled_users_removed": [],
        "user_groups_backup_removed": [],
        "error": "Function disabled - was removing valid users. Use Telegram bot instead."
    }


async def fix_stuck_disabled_users(panel_data: PanelType) -> dict:
    """
    Find and fix users who are stuck in the disabled group.
    
    This handles cases where users are in the disabled group but:
    - Have "active" status (should be disabled or restored)
    - Were not properly tracked in the disabled users list
    - Have their previous groups saved but not restored
    
    Args:
        panel_data (PanelType): Panel connection data.
        
    Returns:
        dict: Results with 'fixed', 'failed', and 'not_in_disabled_group' lists.
    """
    users_logger.info("🔍 Scanning for users stuck in disabled group...")
    
    data = await read_config()
    disabled_group_id = data.get("disabled_group_id", None)
    
    if disabled_group_id is None:
        users_logger.warning("⚠️ No disabled_group_id configured, cannot scan for stuck users")
        return {
            "fixed": [],
            "failed": [],
            "found_in_disabled_group": [],
            "error": "disabled_group_id not configured"
        }
    
    # Get all users from panel
    all_users = await all_user(panel_data)
    if isinstance(all_users, ValueError):
        users_logger.error(f"Failed to get users: {all_users}")
        return {
            "fixed": [],
            "failed": [],
            "found_in_disabled_group": [],
            "error": str(all_users)
        }
    
    # Find users in the disabled group
    stuck_users = []
    for user in all_users:
        user_groups = getattr(user, 'group_ids', []) or []
        if disabled_group_id in user_groups:
            stuck_users.append(user)
    
    users_logger.info(f"📋 Found {len(stuck_users)} users in disabled group {disabled_group_id}")
    
    if not stuck_users:
        return {
            "fixed": [],
            "failed": [],
            "found_in_disabled_group": [],
            "message": "No users found in disabled group"
        }
    
    fixed_users = []
    failed_users = []
    
    for user in stuck_users:
        username = user.name
        users_logger.info(f"🔧 Fixing stuck user: {username}")
        
        try:
            # Try to enable the user (this will restore groups if available)
            success, not_found = await enable_user_by_group(panel_data, username)
            
            if not_found:
                # User was deleted from panel
                dis_obj = DisabledUsers()
                await dis_obj.remove_user(username)
                users_logger.info(f"🗑️ User {username} was deleted from panel")
                continue
            
            if success:
                # Also remove from disabled users tracking if present
                dis_obj = DisabledUsers()
                await dis_obj.remove_user(username)
                
                fixed_users.append(username)
                users_logger.info(f"✅ Fixed stuck user: {username}")
            else:
                failed_users.append(username)
                users_logger.error(f"❌ Failed to fix stuck user: {username}")
        except Exception as e:
            failed_users.append(username)
            users_logger.error(f"❌ Error fixing stuck user {username}: {e}")
    
    users_logger.info(f"✅ Fix complete: {len(fixed_users)} fixed, {len(failed_users)} failed")
    
    return {
        "fixed": fixed_users,
        "failed": failed_users,
        "found_in_disabled_group": [u.name for u in stuck_users],
        "disabled_group_id": disabled_group_id
    }


async def get_users_in_disabled_group(panel_data: PanelType) -> list[str]:
    """
    Get list of usernames that are currently in the disabled group.
    
    Args:
        panel_data (PanelType): Panel connection data.
        
    Returns:
        list[str]: List of usernames in disabled group.
    """
    data = await read_config()
    disabled_group_id = data.get("disabled_group_id", None)
    
    if disabled_group_id is None:
        users_logger.warning("⚠️ No disabled_group_id configured")
        return []
    
    all_users = await all_user(panel_data)
    if isinstance(all_users, ValueError):
        users_logger.error(f"Failed to get users: {all_users}")
        return []
    
    stuck_users = []
    for user in all_users:
        user_groups = getattr(user, 'group_ids', []) or []
        if disabled_group_id in user_groups:
            stuck_users.append(user.name)
    
    return stuck_users
