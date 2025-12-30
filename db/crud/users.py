"""
User CRUD operations.
"""

from datetime import datetime
from typing import Optional, List

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import User
from utils.logs import logger


class UserCRUD:
    """CRUD operations for Users table."""
    
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
        """Create or update a user."""
        result = await db.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()
        
        if user:
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
        result = await db.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_all(db: AsyncSession) -> List[User]:
        """Get all users."""
        result = await db.execute(select(User))
        return result.scalars().all()
    
    @staticmethod
    async def get_by_owner(db: AsyncSession, owner_id: int) -> List[User]:
        """Get users by owner/admin ID."""
        result = await db.execute(select(User).where(User.owner_id == owner_id))
        return result.scalars().all()
    
    @staticmethod
    async def get_by_owner_username(db: AsyncSession, owner_username: str) -> List[User]:
        """Get users by owner/admin username."""
        result = await db.execute(select(User).where(User.owner_username == owner_username))
        return result.scalars().all()
    
    @staticmethod
    async def get_by_group(db: AsyncSession, group_id: int) -> List[User]:
        """Get users in a specific group."""
        result = await db.execute(select(User))
        users = result.scalars().all()
        return [u for u in users if group_id in (u.group_ids or [])]
    
    @staticmethod
    async def get_by_status(db: AsyncSession, status: str) -> List[User]:
        """Get users by status."""
        result = await db.execute(select(User).where(User.status == status))
        return result.scalars().all()
    
    @staticmethod
    async def delete(db: AsyncSession, username: str) -> bool:
        """Delete a user."""
        result = await db.execute(delete(User).where(User.username == username))
        return result.rowcount > 0
    
    @staticmethod
    async def bulk_sync(db: AsyncSession, users_data: List[dict]) -> int:
        """
        Bulk sync users from panel data.
        Creates new users and updates existing ones.
        Returns count of synced users.
        """
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
        logger.info(f"Synced {count} users to database")
        return count
