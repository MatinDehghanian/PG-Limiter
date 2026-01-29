"""
User Sync Module
Periodically syncs users from the panel to local database for efficient filtering.
"""

import asyncio
from datetime import datetime
from typing import Optional

from utils.logs import get_logger
from utils.types import PanelType

sync_logger = get_logger("user_sync")

# Last sync timestamp
_last_sync_time: Optional[datetime] = None
_sync_in_progress: bool = False


async def get_all_users_with_details(panel_data: PanelType, status: str | None = None) -> list[dict]:
    """
    Fetch all users from panel with their full details (groups, owner, etc.).
    Uses parallel pagination for efficiency with large user bases.
    
    Args:
        panel_data: Panel connection data
        status: Filter by user status (active/disabled/limited/expired/on_hold).
                Default is None to fetch ALL users (recommended for sync).
        
    Returns:
        List of user dictionaries with full details
    """
    import httpx
    from utils.panel_api.auth import get_token, invalidate_token_cache
    from utils.logs import log_api_request
    import time
    import random
    import traceback
    
    status_str = f" (status={status})" if status else " (all statuses)"
    sync_logger.info(f"📋 Fetching users with details from panel{status_str}...")
    max_attempts = 3
    limit = 1000  # Fetch 1000 users per page
    max_concurrent = 10  # Max parallel requests
    
    async def fetch_page(client: httpx.AsyncClient, url: str, headers: dict, offset: int) -> tuple[list, int | None]:
        """Fetch a single page of users."""
        # Build URL with offset/limit and optional status filter
        page_url = f"{url}?offset={offset}&limit={limit}"
        if status:
            page_url = f"{page_url}&status={status}"
        
        start_time = time.perf_counter()
        response = await client.get(page_url, headers=headers)
        elapsed = (time.perf_counter() - start_time) * 1000
        response.raise_for_status()
        log_api_request("GET", page_url, response.status_code, elapsed)
        
        data = response.json()
        users = []
        total = None
        if isinstance(data, dict) and "users" in data:
            users = data["users"]
            total = data.get("total")
        elif isinstance(data, list):
            users = data
            total = len(data)
        return users, total
    
    try:
        for attempt in range(max_attempts):
            sync_logger.info(f"🔄 Attempt {attempt + 1}/{max_attempts} to fetch users...")
            
            force_refresh = attempt > 0
            try:
                get_panel_token = await get_token(panel_data, force_refresh=force_refresh)
            except Exception as token_error:
                sync_logger.error(f"❌ Exception getting token: {token_error}")
                continue
            
            if isinstance(get_panel_token, ValueError):
                sync_logger.error(f"❌ Failed to get panel token: {get_panel_token}")
                continue
            
            if not get_panel_token or not hasattr(get_panel_token, 'panel_token'):
                sync_logger.error(f"❌ Invalid token response: {type(get_panel_token)}")
                continue
            
            sync_logger.info("✅ Got panel token successfully")
            token = get_panel_token.panel_token
            headers = {"Authorization": f"Bearer {token}"}
            
            for scheme in ["https", "http"]:
                url = f"{scheme}://{panel_data.panel_domain}/api/users"
                start_time = time.perf_counter()
                
                try:
                    async with httpx.AsyncClient(verify=False, timeout=60) as client:
                        # First request to get total count
                        first_page_users, total_users = await fetch_page(client, url, headers, offset=0)
                        
                        if total_users is None:
                            sync_logger.error("❌ Could not get total user count from API")
                            continue
                        
                        sync_logger.info(f"📊 Panel reports {total_users} total users{status_str}")
                        
                        # If all users fit in first page, we're done
                        if len(first_page_users) >= total_users or len(first_page_users) < limit:
                            all_users = first_page_users
                        else:
                            # Calculate remaining pages and fetch in parallel
                            offsets = list(range(limit, total_users, limit))
                            sync_logger.info(f"📥 Fetching {len(offsets)} more pages in parallel (max {max_concurrent} concurrent)...")
                            
                            semaphore = asyncio.Semaphore(max_concurrent)
                            
                            def make_fetcher(sem, cli, u, hdrs):
                                async def fetch_with_semaphore(offset: int):
                                    async with sem:
                                        users, _ = await fetch_page(cli, u, hdrs, offset)
                                        return users
                                return fetch_with_semaphore
                            
                            fetcher = make_fetcher(semaphore, client, url, headers)
                            tasks = [fetcher(offset) for offset in offsets]
                            pages = await asyncio.gather(*tasks, return_exceptions=True)
                            
                            # Combine all pages
                            all_users = first_page_users
                            for i, page in enumerate(pages):
                                if isinstance(page, Exception):
                                    sync_logger.error(f"❌ Error fetching page {i+1}: {page}")
                                    continue
                                all_users.extend(page)
                        
                        elapsed = (time.perf_counter() - start_time) * 1000
                        sync_logger.info(f"✅ Fetched {len(all_users)} users with details in {elapsed:.0f}ms")
                        return all_users
                        
                except httpx.TimeoutException as e:
                    elapsed = (time.perf_counter() - start_time) * 1000
                    sync_logger.error(f"❌ Timeout after {elapsed:.0f}ms: {e}")
                    continue
                except httpx.ConnectError as e:
                    sync_logger.error(f"❌ Connection error ({scheme}): {e}")
                    continue
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 401:
                        await invalidate_token_cache()
                        sync_logger.warning("🔑 Got 401, invalidating token cache")
                    sync_logger.error(f"❌ HTTP {e.response.status_code}: {e}")
                    continue
                except Exception as e:
                    sync_logger.error(f"❌ Unexpected error: {type(e).__name__}: {e}")
                    sync_logger.error(f"Traceback: {traceback.format_exc()}")
                    continue
            
            wait_time = min(10, random.randint(1, 3) * (attempt + 1))
            sync_logger.info(f"⏳ Waiting {wait_time}s before retry...")
            await asyncio.sleep(wait_time)
        
        sync_logger.error("❌ Failed to fetch users from panel after all attempts")
        return []
        
    except Exception as e:
        sync_logger.error(f"❌ Critical error in get_all_users_with_details: {type(e).__name__}: {e}")
        sync_logger.error(f"Traceback: {traceback.format_exc()}")
        return []


async def sync_users_to_database(panel_data: PanelType) -> tuple[int, int, int]:
    """
    Sync all users from panel to local database.
    Also detects users deleted from panel and removes them from limiter.
    
    Args:
        panel_data: Panel connection data
        
    Returns:
        Tuple of (synced_count, error_count, deleted_count)
    """
    global _last_sync_time, _sync_in_progress
    
    if _sync_in_progress:
        sync_logger.warning("Sync already in progress, skipping")
        return (0, 0, 0)
    
    _sync_in_progress = True
    synced = 0
    errors = 0
    deleted = 0
    deleted_usernames = []
    
    try:
        sync_logger.info("🔄 Starting user sync from panel to database...")
        start_time = datetime.utcnow()
        
        # Fetch ALL users from panel (all statuses) to avoid losing disabled users
        users = await get_all_users_with_details(panel_data, status=None)
        
        if not users:
            sync_logger.warning("⚠️ No users fetched from panel - skipping sync entirely")
            _sync_in_progress = False
            return (0, 0, 0)
        
        sync_logger.info(f"📥 Processing {len(users)} users...")
        
        # Build set of usernames from panel
        panel_usernames = {u.get("username") for u in users if u.get("username")}
        
        if not panel_usernames:
            sync_logger.warning("⚠️ No valid usernames in panel response - skipping sync")
            _sync_in_progress = False
            return (0, 0, 0)
        
        # Import database modules here to avoid circular imports
        sync_logger.info("📂 Importing database modules...")
        from db.database import get_db
        from db.crud.users import UserCRUD
        
        sync_logger.info("📂 Opening database connection for sync...")
        
        async with get_db() as db:
            sync_logger.info("✅ Database connection opened")
            # Get existing usernames in local DB
            local_usernames = await UserCRUD.get_all_usernames(db)
            sync_logger.info(f"📊 Found {len(local_usernames)} existing users in local DB")
            
            # Sync users from panel in batches to avoid memory issues
            batch_size = 50
            total_users = len(users)
            
            for batch_start in range(0, total_users, batch_size):
                batch_end = min(batch_start + batch_size, total_users)
                batch = users[batch_start:batch_end]
                
                sync_logger.info(f"📝 Processing batch {batch_start//batch_size + 1}: users {batch_start+1}-{batch_end}/{total_users}")
                
                for user_data in batch:
                    try:
                        username = user_data.get("username")
                        if not username:
                            continue
                        
                        # Extract user details
                        status = user_data.get("status", "active")
                        
                        # Get admin/owner info
                        admin_info = user_data.get("admin", {}) or {}
                        owner_id = admin_info.get("id") if isinstance(admin_info, dict) else None
                        owner_username = admin_info.get("username") if isinstance(admin_info, dict) else None
                        
                        # Alternative: check for "created_by" field
                        if not owner_username:
                            owner_username = user_data.get("created_by")
                        
                        # Get group IDs
                        group_ids = user_data.get("group_ids") or user_data.get("groups") or []
                        if isinstance(group_ids, str):
                            group_ids = [int(g.strip()) for g in group_ids.split(",") if g.strip()]
                        
                        # Get data limits
                        data_limit = user_data.get("data_limit")
                        if data_limit:
                            data_limit = data_limit / (1024 ** 3)  # Convert to GB
                        
                        used_traffic = user_data.get("used_traffic", 0)
                        if used_traffic:
                            used_traffic = used_traffic / (1024 ** 3)  # Convert to GB
                        
                        # Get expiry
                        expire_at = None
                        expire_value = user_data.get("expire")
                        if expire_value:
                            if isinstance(expire_value, int):
                                # Unix timestamp
                                if expire_value > 0:
                                    expire_at = datetime.fromtimestamp(expire_value)
                            elif isinstance(expire_value, str):
                                # ISO datetime string
                                try:
                                    expire_at = datetime.fromisoformat(
                                        expire_value.replace("Z", "+00:00")
                                    )
                                except ValueError:
                                    pass
                        
                        # Get note
                        note = user_data.get("note")
                        
                        # Create or update in database
                        await UserCRUD.create_or_update(
                            db,
                            username=username,
                            status=status,
                            owner_id=owner_id,
                            owner_username=owner_username,
                            group_ids=group_ids,
                            data_limit=data_limit,
                            used_traffic=used_traffic,
                            expire_at=expire_at,
                            note=note,
                        )
                        synced += 1
                        
                    except Exception as e:
                        sync_logger.error(f"Error syncing user {user_data.get('username', '?')}: {e}")
                        errors += 1
                
                # Commit batch to database and flush to save memory
                await db.flush()
                sync_logger.info(f"✅ Batch committed: {synced} synced, {errors} errors so far")
            
            # SAFETY CHECKS before deleting users
            # Only delete if sync was mostly successful (less than 10% errors)
            # and we received a reasonable number of users from panel
            potentially_deleted = list(local_usernames - panel_usernames)
            error_rate = errors / max(len(users), 1)
            
            if potentially_deleted:
                # Check if auto-deletion is enabled in config
                from utils.read_config import read_config
                config = await read_config()
                auto_delete_enabled = config.get("user_sync", {}).get("auto_delete_users", False)
                
                if not auto_delete_enabled:
                    sync_logger.info(
                        f"ℹ️ Auto-deletion disabled. {len(potentially_deleted)} users not in panel but kept in local DB. "
                        f"Enable 'auto_delete_users' in config or use Telegram bot to review."
                    )
                    # Log the users that would have been deleted
                    if len(potentially_deleted) <= 20:
                        sync_logger.info(f"Users not in panel: {', '.join(potentially_deleted)}")
                    else:
                        sync_logger.info(f"Users not in panel (first 20): {', '.join(potentially_deleted[:20])}...")
                
                # Safety check 1: Don't delete if there were too many sync errors
                elif error_rate > 0.1:  # More than 10% errors
                    sync_logger.warning(
                        f"⚠️ Skipping deletion: too many sync errors ({errors}/{len(users)} = {error_rate:.1%})"
                    )
                # Safety check 2: Don't delete if panel returned significantly fewer users
                # This could indicate a pagination or API issue
                elif len(local_usernames) > 0 and len(panel_usernames) < len(local_usernames) * 0.5:
                    sync_logger.warning(
                        f"⚠️ Skipping deletion: panel returned too few users "
                        f"({len(panel_usernames)} vs {len(local_usernames)} local). "
                        f"This may indicate an API issue."
                    )
                # Safety check 3: Don't delete more than 10% of users in one sync (stricter)
                elif len(potentially_deleted) > len(local_usernames) * 0.1:
                    sync_logger.warning(
                        f"⚠️ Skipping deletion: too many users to delete "
                        f"({len(potentially_deleted)}/{len(local_usernames)} = "
                        f"{len(potentially_deleted)/len(local_usernames):.1%}). "
                        f"Manual review recommended via Telegram bot."
                    )
                # Safety check 4: Don't delete more than 50 users at once
                elif len(potentially_deleted) > 50:
                    sync_logger.warning(
                        f"⚠️ Skipping deletion: {len(potentially_deleted)} users is too many to delete at once. "
                        f"Manual review recommended via Telegram bot."
                    )
                else:
                    # All safety checks passed - proceed with deletion
                    sync_logger.info(f"🗑️ Deleting {len(potentially_deleted)} users removed from panel")
                    deleted_usernames = potentially_deleted
                    deleted = await UserCRUD.delete_many(db, deleted_usernames)
            
            await db.commit()
        
        elapsed = (datetime.utcnow() - start_time).total_seconds()
        _last_sync_time = datetime.utcnow()
        
        sync_logger.info(
            f"✅ User sync completed: {synced} synced, {deleted} deleted, "
            f"{errors} errors in {elapsed:.1f}s"
        )
        
        # Send Telegram notification for deleted users
        if deleted_usernames:
            await _notify_deleted_users(deleted_usernames)
        
    except Exception as e:
        import traceback
        sync_logger.error(f"❌ User sync failed: {type(e).__name__}: {e}")
        sync_logger.error(f"Traceback: {traceback.format_exc()}")
    finally:
        _sync_in_progress = False
    
    return (synced, errors, deleted)


async def _notify_deleted_users(usernames: list[str]) -> None:
    """Send Telegram notification for users deleted from panel."""
    try:
        from telegram_bot.send_message import send_logs
        
        if len(usernames) <= 10:
            user_list = "\n".join(f"• <code>{u}</code>" for u in usernames)
        else:
            user_list = "\n".join(f"• <code>{u}</code>" for u in usernames[:10])
            user_list += f"\n... and {len(usernames) - 10} more"
        
        message = (
            "🗑️ <b>Users Deleted from Panel</b>\n\n"
            "The following users were deleted from panel and "
            "have been removed from PG-Limiter:\n\n"
            f"{user_list}\n\n"
            f"📊 Total: {len(usernames)} users"
        )
        
        await send_logs(message)
        sync_logger.info(f"📤 Sent notification for {len(usernames)} deleted users")
        
    except Exception as e:
        sync_logger.error(f"Failed to send deletion notification: {e}")


async def get_user_from_cache(username: str) -> Optional[dict]:
    """
    Get user data from local database cache.
    
    Args:
        username: The username to look up
        
    Returns:
        User dict with group_ids and owner_username, or None if not found
    """
    try:
        from db.database import get_db
        from db.crud.users import UserCRUD
        
        async with get_db() as db:
            user = await UserCRUD.get_by_username(db, username)
            if user:
                return {
                    "username": user.username,
                    "status": user.status,
                    "owner_id": user.owner_id,
                    "owner_username": user.owner_username,
                    "group_ids": user.group_ids or [],
                    "data_limit": user.data_limit,
                    "used_traffic": user.used_traffic,
                    "expire_at": user.expire_at,
                    "last_synced_at": user.last_synced_at,
                }
        return None
    except Exception as e:
        sync_logger.error(f"Error getting user from cache: {e}")
        return None


async def fetch_and_sync_single_user(username: str, panel_data: Optional[PanelType] = None) -> Optional[dict]:
    """
    Fetch a single user from the panel API and sync to local database.
    This is useful when a new user appears in active connections before the regular sync.
    
    Args:
        username: The username to fetch
        panel_data: Panel connection data (will be fetched from config if not provided)
        
    Returns:
        User dict if found and synced, None otherwise
    """
    try:
        sync_logger.info(f"🔄 Fetching single user from panel: {username}")
        
        # Validate username
        if not username or not username.strip():
            sync_logger.warning("⚠️ Cannot fetch user with empty username")
            return None
        
        # Get panel_data from config if not provided
        if panel_data is None:
            from utils.read_config import read_config
            config = await read_config()
            panel_config = config.get("panel", {})
            panel_data = PanelType(
                panel_username=panel_config.get("username", ""),
                panel_password=panel_config.get("password", ""),
                panel_domain=panel_config.get("domain", ""),
            )
        
        # Validate panel_data has required fields
        if not panel_data.panel_domain:
            sync_logger.error("❌ Panel domain is not configured - cannot fetch user from panel")
            return None
        
        # Fetch user details from panel
        from utils.panel_api import get_user_details
        user_data = await get_user_details(panel_data, username)
        
        if user_data is None:
            sync_logger.warning(f"⚠️ User {username} not found in panel")
            return None
        
        if isinstance(user_data, ValueError):
            sync_logger.error(f"❌ Error fetching user {username}: {user_data}")
            return None
        
        # Extract user details (same logic as sync_users_to_database)
        status = user_data.get("status", "active")
        
        # Get admin/owner info
        admin_info = user_data.get("admin", {}) or {}
        owner_id = admin_info.get("id") if isinstance(admin_info, dict) else None
        owner_username = admin_info.get("username") if isinstance(admin_info, dict) else None
        
        # Alternative: check for "created_by" field
        if not owner_username:
            owner_username = user_data.get("created_by")
        
        # Get group IDs
        group_ids = user_data.get("group_ids") or user_data.get("groups") or []
        if isinstance(group_ids, str):
            group_ids = [int(g.strip()) for g in group_ids.split(",") if g.strip()]
        
        # Get data limits
        data_limit = user_data.get("data_limit")
        if data_limit:
            data_limit = data_limit / (1024 ** 3)  # Convert to GB
        
        used_traffic = user_data.get("used_traffic", 0)
        if used_traffic:
            used_traffic = used_traffic / (1024 ** 3)  # Convert to GB
        
        # Get expiry
        expire_at = None
        expire_value = user_data.get("expire")
        if expire_value:
            if isinstance(expire_value, int):
                # Unix timestamp
                if expire_value > 0:
                    expire_at = datetime.fromtimestamp(expire_value)
            elif isinstance(expire_value, str):
                # ISO datetime string
                try:
                    expire_at = datetime.fromisoformat(
                        expire_value.replace("Z", "+00:00")
                    )
                except ValueError:
                    pass
        
        # Get note
        note = user_data.get("note")
        
        # Save to database
        from db.database import get_db
        from db.crud.users import UserCRUD
        
        async with get_db() as db:
            user = await UserCRUD.create_or_update(
                db,
                username=username,
                status=status,
                owner_id=owner_id,
                owner_username=owner_username,
                group_ids=group_ids,
                data_limit=data_limit,
                used_traffic=used_traffic,
                expire_at=expire_at,
                note=note,
            )
            await db.commit()
            
            sync_logger.info(f"✅ User {username} synced from panel to database")
            
            return {
                "username": user.username,
                "status": user.status,
                "owner_id": user.owner_id,
                "owner_username": user.owner_username,
                "group_ids": user.group_ids or [],
                "data_limit": user.data_limit,
                "used_traffic": user.used_traffic,
                "expire_at": user.expire_at,
            }
            
    except Exception as e:
        sync_logger.error(f"❌ Error fetching/syncing user {username}: {e}")
        import traceback
        sync_logger.error(f"Traceback: {traceback.format_exc()}")
        return None


async def get_last_sync_time() -> Optional[datetime]:
    """Get the last sync timestamp."""
    return _last_sync_time


async def is_sync_needed(sync_interval_minutes: int) -> bool:
    """
    Check if a sync is needed based on interval.
    
    Args:
        sync_interval_minutes: Sync interval in minutes
        
    Returns:
        True if sync is needed
    """
    if _last_sync_time is None:
        return True
    
    elapsed = (datetime.utcnow() - _last_sync_time).total_seconds()
    return elapsed >= sync_interval_minutes * 60


async def run_user_sync_loop(panel_data: PanelType):
    """
    Run the user sync loop. This should be started as a background task.
    
    Args:
        panel_data: Panel connection data
    """
    from utils.read_config import read_config
    
    sync_logger.info("🚀 Starting user sync background loop...")
    
    # Delay initial sync to allow other startup operations to complete
    # This reduces memory pressure during startup
    sync_logger.info("⏳ Waiting 30 seconds before initial user sync...")
    await asyncio.sleep(30)
    
    # Initial sync
    sync_logger.info("🔄 Running initial user sync...")
    await sync_users_to_database(panel_data)
    
    while True:
        try:
            config = await read_config()
            sync_interval = config.get("user_sync_interval", 5)  # Default 5 minutes
            
            # Wait for interval
            await asyncio.sleep(sync_interval * 60)
            
            # Check if sync is needed
            if await is_sync_needed(sync_interval):
                await sync_users_to_database(panel_data)
                
        except asyncio.CancelledError:
            sync_logger.info("User sync loop cancelled")
            break
        except Exception as e:
            sync_logger.error(f"Error in user sync loop: {e}")
            await asyncio.sleep(60)  # Wait before retry


async def get_pending_deletions(panel_data: PanelType) -> dict:
    """
    Get the list of users that would be deleted during sync.
    This allows manual review before force-deleting.
    
    Args:
        panel_data: Panel connection data
        
    Returns:
        Dictionary with pending deletions info:
        {
            "pending_deletions": ["user1", "user2", ...],
            "local_count": 100,
            "panel_count": 80,
            "deletion_percentage": 20.0,
            "safe_to_delete": True/False,
            "reason": "reason if not safe"
        }
    """
    from db.database import get_db
    from db.crud import UserCRUD
    
    result = {
        "pending_deletions": [],
        "local_count": 0,
        "panel_count": 0,
        "deletion_percentage": 0.0,
        "safe_to_delete": True,
        "reason": ""
    }
    
    try:
        # Get ALL users from panel (not just active) for proper deletion comparison
        users = await get_all_users_with_details(panel_data, status=None)
        panel_usernames = {u.get("username") for u in users if u.get("username")}
        result["panel_count"] = len(panel_usernames)
        
        # Get local users
        async with get_db() as db:
            local_users = await UserCRUD.get_all(db)
            local_usernames = {u.username for u in local_users}
            result["local_count"] = len(local_usernames)
        
        # Find users to delete
        pending = list(local_usernames - panel_usernames)
        result["pending_deletions"] = sorted(pending)
        
        if local_usernames:
            result["deletion_percentage"] = (len(pending) / len(local_usernames)) * 100
        
        # Check safety
        if len(pending) > len(local_usernames) * 0.2:
            result["safe_to_delete"] = False
            result["reason"] = f"Would delete more than 20% of users ({result['deletion_percentage']:.1f}%)"
        elif len(panel_usernames) < len(local_usernames) * 0.5:
            result["safe_to_delete"] = False
            result["reason"] = f"Panel returned significantly fewer users ({len(panel_usernames)} vs {len(local_usernames)})"
            
    except Exception as e:
        sync_logger.error(f"Error getting pending deletions: {e}")
        result["reason"] = f"Error: {e}"
        result["safe_to_delete"] = False
    
    return result


async def force_delete_users(usernames: list[str]) -> tuple[int, list[str]]:
    """
    Force delete specific users from local database.
    Use after manual review of pending deletions.
    
    Args:
        usernames: List of usernames to delete
        
    Returns:
        Tuple of (deleted_count, errors)
    """
    from db.database import get_db
    from db.crud import UserCRUD
    
    deleted = 0
    errors = []
    
    async with get_db() as db:
        for username in usernames:
            try:
                result = await UserCRUD.delete(db, username)
                if result:
                    deleted += 1
                else:
                    errors.append(f"{username}: not found")
            except Exception as e:
                errors.append(f"{username}: {e}")
        
        await db.commit()
    
    if deleted:
        await _notify_deleted_users(usernames[:deleted])
    
    return deleted, errors
