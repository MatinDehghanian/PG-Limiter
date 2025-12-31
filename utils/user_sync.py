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


async def get_all_users_with_details(panel_data: PanelType) -> list[dict]:
    """
    Fetch all users from panel with their full details (groups, owner, etc.).
    
    Args:
        panel_data: Panel connection data
        
    Returns:
        List of user dictionaries with full details
    """
    import httpx
    from utils.panel_api.auth import get_token, invalidate_token_cache
    from utils.logs import log_api_request
    import time
    import random
    
    sync_logger.info("📋 Fetching all users with details from panel...")
    max_attempts = 3
    all_users = []
    limit = 100
    
    for attempt in range(max_attempts):
        all_users.clear()
        offset = 0
        
        force_refresh = attempt > 0
        get_panel_token = await get_token(panel_data, force_refresh=force_refresh)
        if isinstance(get_panel_token, ValueError):
            sync_logger.error(f"Failed to get panel token: {get_panel_token}")
            continue
        
        token = get_panel_token.panel_token
        headers = {"Authorization": f"Bearer {token}"}
        
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
                        sync_logger.error(f"Failed to parse JSON: {json_error}")
                        continue
                    
                    users = []
                    total = 0
                    if isinstance(data, dict) and "users" in data:
                        users = data["users"]
                        total = data.get("total", len(users))
                    elif isinstance(data, list):
                        users = data
                        total = len(users)
                    
                    all_users.extend(users)
                    
                    sync_logger.debug(
                        f"📋 Page fetched: offset={offset}, got {len(users)} users, "
                        f"total collected: {len(all_users)}"
                    )
                    
                    if len(users) < limit or offset + len(users) >= total:
                        sync_logger.info(f"✅ Fetched {len(all_users)} users with details from panel")
                        return all_users
                    
                    offset += limit
                    page_success = True
                    break
                    
                except httpx.HTTPStatusError as e:
                    elapsed = (time.perf_counter() - start_time) * 1000
                    if e.response.status_code == 401:
                        await invalidate_token_cache()
                        sync_logger.warning("Got 401, invalidating token cache")
                    log_api_request("GET", url, e.response.status_code, elapsed)
                    continue
                except Exception as e:
                    elapsed = (time.perf_counter() - start_time) * 1000
                    log_api_request("GET", url, None, elapsed, str(e))
                    sync_logger.error(f"Error fetching users: {e}")
                    continue
            
            if not page_success:
                pagination_success = False
        
        if all_users:
            return all_users
        
        wait_time = min(10, random.randint(1, 3) * (attempt + 1))
        await asyncio.sleep(wait_time)
    
    sync_logger.error("Failed to fetch users from panel after all attempts")
    return all_users


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
        from db.database import get_db
        from db.crud.users import UserCRUD
        
        sync_logger.info("🔄 Starting user sync from panel to database...")
        start_time = datetime.utcnow()
        
        # Fetch all users from panel
        users = await get_all_users_with_details(panel_data)
        
        if not users:
            sync_logger.warning("⚠️ No users fetched from panel - skipping sync entirely")
            return (0, 0, 0)
        
        sync_logger.info(f"📥 Processing {len(users)} users...")
        
        # Build set of usernames from panel
        panel_usernames = {u.get("username") for u in users if u.get("username")}
        
        if not panel_usernames:
            sync_logger.warning("⚠️ No valid usernames in panel response - skipping sync")
            return (0, 0, 0)
        
        async with get_db() as db:
            # Get existing usernames in local DB
            local_usernames = await UserCRUD.get_all_usernames(db)
            
            # Sync users from panel FIRST (before any deletion logic)
            for user_data in users:
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
            
            # SAFETY CHECKS before deleting users
            # Only delete if sync was mostly successful (less than 10% errors)
            # and we received a reasonable number of users from panel
            potentially_deleted = list(local_usernames - panel_usernames)
            
            if potentially_deleted:
                # Safety check 1: Don't delete if there were too many sync errors
                error_rate = errors / max(len(users), 1)
                if error_rate > 0.1:  # More than 10% errors
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
                # Safety check 3: Don't delete more than 20% of users in one sync
                elif len(potentially_deleted) > len(local_usernames) * 0.2:
                    sync_logger.warning(
                        f"⚠️ Skipping deletion: too many users to delete "
                        f"({len(potentially_deleted)}/{len(local_usernames)} = "
                        f"{len(potentially_deleted)/len(local_usernames):.1%}). "
                        f"Manual review recommended."
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
        sync_logger.error(f"User sync failed: {e}")
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
    
    # Initial sync
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
