"""
User Limit CRUD operations.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import UserLimit


class UserLimitCRUD:
    """CRUD operations for UserLimit table."""
    
    @staticmethod
    async def set_limit(db: AsyncSession, username: str, limit: int) -> UserLimit:
        """Set or update limit for a user."""
        result = await db.execute(select(UserLimit).where(UserLimit.username == username))
        user_limit = result.scalar_one_or_none()
        
        if user_limit:
            user_limit.limit = limit
            user_limit.updated_at = datetime.utcnow()
        else:
            user_limit = UserLimit(username=username, limit=limit)
            db.add(user_limit)
        
        await db.flush()
        return user_limit
    
    @staticmethod
    async def get_limit(db: AsyncSession, username: str) -> Optional[int]:
        """Get limit for a user. Returns None if no special limit set."""
        result = await db.execute(select(UserLimit).where(UserLimit.username == username))
        user_limit = result.scalar_one_or_none()
        return user_limit.limit if user_limit else None
    
    @staticmethod
    async def get_all(db: AsyncSession) -> dict[str, int]:
        """Get all special limits as a dictionary."""
        result = await db.execute(select(UserLimit))
        limits = result.scalars().all()
        return {ul.username: ul.limit for ul in limits}
    
    @staticmethod
    async def delete(db: AsyncSession, username: str) -> bool:
        """Remove special limit for a user (will use general limit)."""
        result = await db.execute(delete(UserLimit).where(UserLimit.username == username))
        return result.rowcount > 0
