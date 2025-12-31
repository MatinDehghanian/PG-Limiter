"""
Consolidated User CRUD operations.
Handles all user-related operations including exceptions, limits, and disable status.
"""

import time
from datetime import datetime
from typing import Optional, List

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import User
from utils.logs import get_logger

db_users_logger = get_logger("db.users")


class UserCRUD:
    """
    Consolidated CRUD operations for Users table.
    Includes methods for panel sync, exceptions, limits, and disable status.
    """
    
    # ==================== Core User Methods ====================
    
    @staticmethod
    async def create_or_update(
        db: AsyncSession,
        username: str,
        status: str = "active",
        owner_id: Optional[int] = None,
        owner_username: Optional[str] = None,
        group_ids: Optional[List[int]] = None,
        data_limit: Optional[float] = None,
        used_traffic: float = 0,
        expire_at: Optional[datetime] = None,
        note: Optional[str] = None,
    ) -> User:
        """Create or update a user from panel sync."""
        db_users_logger.debug(f"📝 Creating/updating user: {username}")
        result = await db.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()
        
        if user:
            db_users_logger.debug(f"✏️ Updating existing user: {username}")
            user.status = status
            user.owner_id = owner_id
            user.owner_username = owner_username
            user.group_ids = group_ids or []
            user.data_limit = data_limit
            user.used_traffic = used_traffic
            user.expire_at = expire_at
            user.note = note
            user.last_synced_at = datetime.utcnow()
        else:
            db_users_logger.debug(f"➕ Creating new user: {username}")
            user = User(
                username=username,
                status=status,
                owner_id=owner_id,
                owner_username=owner_username,
                group_ids=group_ids or [],
                data_limit=data_limit,
                used_traffic=used_traffic,
                expire_at=expire_at,
                note=note,
            )
            db.add(user)
        
        await db.flush()
        return user
    
    @staticmethod
    async def get_by_username(db: AsyncSession, username: str) -> Optional[User]:
        """Get user by username."""
        db_users_logger.debug(f"🔍 Getting user by username: {username}")
        result = await db.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()
        if user:
            db_users_logger.debug(f"✅ Found user: {username}")
        else:
            db_users_logger.debug(f"⚠️ User not found: {username}")
        return user
    
    @staticmethod
    async def get_all(db: AsyncSession) -> List[User]:
        """Get all users."""
        db_users_logger.debug("📋 Getting all users from database")
        result = await db.execute(select(User))
        users = list(result.scalars().all())
        db_users_logger.debug(f"✅ Retrieved {len(users)} users")
        return users
    
    @staticmethod
    async def get_all_usernames(db: AsyncSession) -> set[str]:
        """Get all usernames as a set."""
        db_users_logger.debug("�� Getting all usernames")
        result = await db.execute(select(User.username))
        usernames = {row[0] for row in result.fetchall()}
        db_users_logger.debug(f"✅ Retrieved {len(usernames)} usernames")
        return usernames
    
    @staticmethod
    async def get_by_owner(db: AsyncSession, owner_id: int) -> List[User]:
        """Get users by owner/admin ID."""
        db_users_logger.debug(f"🔍 Getting users by owner ID: {owner_id}")
        result = await db.execute(select(User).where(User.owner_id == owner_id))
        users = list(result.scalars().all())
        db_users_logger.debug(f"✅ Found {len(users)} users for owner ID {owner_id}")
        return users
    
    @staticmethod
    async def get_by_owner_username(db: AsyncSession, owner_username: str) -> List[User]:
        """Get users by owner/admin username."""
        db_users_logger.debug(f"🔍 Getting users by owner username: {owner_username}")
        result = await db.execute(select(User).where(User.owner_username == owner_username))
        users = list(result.scalars().all())
        db_users_logger.debug(f"✅ Found {len(users)} users for owner {owner_username}")
        return users
    
    @staticmethod
    async def get_by_group(db: AsyncSession, group_id: int) -> List[User]:
        """Get users in a specific group."""
        db_users_logger.debug(f"🔍 Getting users by group ID: {group_id}")
        result = await db.execute(select(User))
        users = result.scalars().all()
        filtered = [u for u in users if group_id in (u.group_ids or [])]
        db_users_logger.debug(f"✅ Found {len(filtered)} users in group {group_id}")
        return filtered
    
    @staticmethod
    async def get_by_status(db: AsyncSession, status: str) -> List[User]:
        """Get users by status."""
        db_users_logger.debug(f"🔍 Getting users by status: {status}")
        result = await db.execute(select(User).where(User.status == status))
        users = list(result.scalars().all())
        db_users_logger.debug(f"✅ Found {len(users)} users with status {status}")
        return users
    
    @staticmethod
    async def delete(db: AsyncSession, username: str) -> bool:
        """Delete a user."""
        db_users_logger.debug(f"🗑️ Deleting user: {username}")
        result = await db.execute(delete(User).where(User.username == username))
        deleted = result.rowcount > 0
        if deleted:
            db_users_logger.info(f"✅ Deleted user: {username}")
        else:
            db_users_logger.warning(f"⚠️ User not found for deletion: {username}")
        return deleted
    
    @staticmethod
    async def delete_many(db: AsyncSession, usernames: List[str]) -> int:
        """Delete multiple users. Returns count of deleted users."""
        if not usernames:
            return 0
        db_users_logger.debug(f"🗑️ Deleting {len(usernames)} users")
        result = await db.execute(delete(User).where(User.username.in_(usernames)))
        deleted = result.rowcount
        db_users_logger.info(f"✅ Deleted {deleted} users")
        return deleted
    
    # ==================== Exception/Whitelist Methods ====================
    
    @staticmethod
    async def set_excepted(
        db: AsyncSession,
        username: str,
        excepted: bool = True,
        reason: Optional[str] = None,
        excepted_by: Optional[str] = None,
    ) -> Optional[User]:
        """Set user exception status."""
        db_users_logger.debug(f"📝 Setting exception for {username}: {excepted}")
        result = await db.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()
        
        if not user:
            db_users_logger.warning(f"⚠️ User {username} not found for exception")
            return None
        
        user.is_excepted = excepted
        user.exception_reason = reason if excepted else None
        user.excepted_by = excepted_by if excepted else None
        user.excepted_at = datetime.utcnow() if excepted else None
        
        await db.flush()
        action = "added to" if excepted else "removed from"
        db_users_logger.info(f"✅ User {username} {action} exception list")
        return user
    
    @staticmethod
    async def is_excepted(db: AsyncSession, username: str) -> bool:
        """Check if user is in exception list."""
        db_users_logger.debug(f"🔍 Checking if excepted: {username}")
        result = await db.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()
        return user.is_excepted if user else False
    
    @staticmethod
    async def get_all_excepted(db: AsyncSession) -> List[str]:
        """Get all excepted usernames."""
        db_users_logger.debug("📋 Getting all excepted usernames")
        result = await db.execute(select(User).where(User.is_excepted == True))  # noqa: E712
        users = [u.username for u in result.scalars().all()]
        db_users_logger.debug(f"✅ Found {len(users)} excepted users")
        return users
    
    @staticmethod
    async def get_all_excepted_with_details(db: AsyncSession) -> List[User]:
        """Get all excepted users with full details."""
        db_users_logger.debug("📋 Getting all excepted users with details")
        result = await db.execute(select(User).where(User.is_excepted == True))  # noqa: E712
        users = list(result.scalars().all())
        db_users_logger.debug(f"✅ Retrieved {len(users)} excepted users")
        return users
    
    # ==================== Special Limit Methods ====================
    
    @staticmethod
    async def set_special_limit(db: AsyncSession, username: str, limit: Optional[int]) -> Optional[User]:
        """Set or remove special limit for a user. Pass None to remove."""
        db_users_logger.debug(f"📝 Setting special limit for {username}: {limit}")
        result = await db.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()
        
        if not user:
            db_users_logger.warning(f"⚠️ User {username} not found for limit")
            return None
        
        user.special_limit = limit
        user.special_limit_updated_at = datetime.utcnow() if limit is not None else None
        
        await db.flush()
        if limit is not None:
            db_users_logger.info(f"✅ Special limit set for {username}: {limit}")
        else:
            db_users_logger.info(f"✅ Special limit removed for {username}")
        return user
    
    @staticmethod
    async def get_special_limit(db: AsyncSession, username: str) -> Optional[int]:
        """Get special limit for a user. Returns None if no special limit set."""
        db_users_logger.debug(f"🔍 Getting limit for user: {username}")
        result = await db.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()
        if user and user.special_limit is not None:
            db_users_logger.debug(f"✅ Found limit for {username}: {user.special_limit}")
            return user.special_limit
        db_users_logger.debug(f"ℹ️ No special limit for {username}")
        return None
    
    @staticmethod
    async def get_all_special_limits(db: AsyncSession) -> dict[str, int]:
        """Get all special limits as a dictionary."""
        db_users_logger.debug("📋 Getting all special limits")
        result = await db.execute(select(User).where(User.special_limit.isnot(None)))
        users = result.scalars().all()
        limits_dict = {u.username: u.special_limit for u in users}
        db_users_logger.debug(f"✅ Retrieved {len(limits_dict)} special limits")
        return limits_dict
    
    @staticmethod
    async def get_all_with_special_limits(db: AsyncSession) -> List[User]:
        """Get all users that have special limits."""
        db_users_logger.debug("📋 Getting all users with special limits")
        result = await db.execute(select(User).where(User.special_limit.isnot(None)))
        users = list(result.scalars().all())
        db_users_logger.debug(f"✅ Found {len(users)} users with special limits")
        return users
    
    # ==================== Disable Status Methods ====================
    
    @staticmethod
    async def set_disabled(
        db: AsyncSession,
        username: str,
        disabled: bool = True,
        disabled_at: Optional[float] = None,
        enable_at: Optional[float] = None,
        original_groups: Optional[List[int]] = None,
        reason: Optional[str] = None,
        punishment_step: int = 0,
    ) -> Optional[User]:
        """Set user disable status by limiter."""
        db_users_logger.debug(f"📝 Setting disabled for {username}: {disabled}")
        result = await db.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()
        
        if not user:
            db_users_logger.warning(f"⚠️ User {username} not found for disable")
            return None
        
        if disabled:
            if disabled_at is None:
                disabled_at = time.time()
            user.is_disabled_by_limiter = True
            user.disabled_at = disabled_at
            user.enable_at = enable_at
            user.original_groups = original_groups or []
            user.disable_reason = reason
            user.punishment_step = punishment_step
            db_users_logger.info(f"🚫 User {username} disabled (step={punishment_step})")
        else:
            user.is_disabled_by_limiter = False
            user.disabled_at = None
            user.enable_at = None
            user.original_groups = []
            user.disable_reason = None
            # Keep punishment_step for history
            db_users_logger.info(f"✅ User {username} enabled")
        
        await db.flush()
        return user
    
    @staticmethod
    async def is_disabled_by_limiter(db: AsyncSession, username: str) -> bool:
        """Check if user is disabled by limiter."""
        db_users_logger.debug(f"🔍 Checking if disabled: {username}")
        result = await db.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()
        return user.is_disabled_by_limiter if user else False
    
    @staticmethod
    async def get_disabled_record(db: AsyncSession, username: str) -> Optional[User]:
        """Get disabled user record if user is disabled by limiter."""
        db_users_logger.debug(f"🔍 Getting disabled record for: {username}")
        result = await db.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()
        if user and user.is_disabled_by_limiter:
            return user
        return None
    
    @staticmethod
    async def get_all_disabled(db: AsyncSession) -> List[User]:
        """Get all users disabled by limiter."""
        db_users_logger.debug("📋 Getting all disabled users")
        result = await db.execute(
            select(User).where(User.is_disabled_by_limiter == True)  # noqa: E712
        )
        users = list(result.scalars().all())
        db_users_logger.debug(f"✅ Found {len(users)} disabled users")
        return users
    
    @staticmethod
    async def get_all_disabled_dict(db: AsyncSession) -> dict[str, float]:
        """Get all disabled users as {username: disabled_timestamp} dict."""
        db_users_logger.debug("📋 Getting disabled users as dict")
        result = await db.execute(
            select(User).where(User.is_disabled_by_limiter == True)  # noqa: E712
        )
        users = result.scalars().all()
        return {u.username: u.disabled_at for u in users if u.disabled_at}
    
    @staticmethod
    async def get_users_to_enable(db: AsyncSession, time_to_active: int) -> List[str]:
        """
        Get users that should be re-enabled based on time_to_active.
        
        Args:
            time_to_active: Seconds after which to re-enable users
            
        Returns:
            List of usernames to re-enable
        """
        db_users_logger.debug(f"🔍 Getting users to re-enable (time_to_active={time_to_active}s)")
        current_time = time.time()
        cutoff = current_time - time_to_active
        
        result = await db.execute(
            select(User).where(User.is_disabled_by_limiter == True)  # noqa: E712
        )
        disabled_users = result.scalars().all()
        
        users_to_enable = []
        for user in disabled_users:
            if user.enable_at is not None:
                # User has specific enable time
                if current_time >= user.enable_at:
                    users_to_enable.append(user.username)
            elif user.disabled_at and user.disabled_at <= cutoff:
                # Use global time_to_active
                users_to_enable.append(user.username)
        
        db_users_logger.debug(f"✅ Found {len(users_to_enable)} users to re-enable")
        return users_to_enable
    
    # ==================== Bulk Operations ====================
    
    @staticmethod
    async def bulk_sync(db: AsyncSession, users_data: List[dict]) -> int:
        """
        Bulk sync users from panel data.
        Creates new users and updates existing ones.
        Returns count of synced users.
        """
        db_users_logger.info(f"🔄 Starting bulk sync for {len(users_data)} users")
        count = 0
        for data in users_data:
            await UserCRUD.create_or_update(
                db,
                username=data.get("username"),
                status=data.get("status", "active"),
                owner_id=data.get("owner_id") or data.get("admin_id"),
                owner_username=data.get("owner_username") or data.get("admin_username"),
                group_ids=data.get("group_ids") or data.get("groups") or [],
                data_limit=data.get("data_limit"),
                used_traffic=data.get("used_traffic", 0),
                expire_at=data.get("expire_at"),
                note=data.get("note"),
            )
            count += 1
        
        await db.flush()
        db_users_logger.info(f"✅ Synced {count} users to database")
        return count
