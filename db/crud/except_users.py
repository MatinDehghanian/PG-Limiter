"""
Except User CRUD operations (whitelist).
"""

from typing import Optional, List

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import ExceptUser


class ExceptUserCRUD:
    """CRUD operations for ExceptUser table (whitelist)."""
    
    @staticmethod
    async def add(db: AsyncSession, username: str, reason: Optional[str] = None, created_by: Optional[str] = None) -> ExceptUser:
        """Add user to exception list."""
        result = await db.execute(select(ExceptUser).where(ExceptUser.username == username))
        except_user = result.scalar_one_or_none()
        
        if except_user:
            except_user.reason = reason
            except_user.created_by = created_by
        else:
            except_user = ExceptUser(username=username, reason=reason, created_by=created_by)
            db.add(except_user)
        
        await db.flush()
        return except_user
    
    @staticmethod
    async def remove(db: AsyncSession, username: str) -> bool:
        """Remove user from exception list."""
        result = await db.execute(delete(ExceptUser).where(ExceptUser.username == username))
        return result.rowcount > 0
    
    @staticmethod
    async def is_excepted(db: AsyncSession, username: str) -> bool:
        """Check if user is in exception list."""
        result = await db.execute(select(ExceptUser).where(ExceptUser.username == username))
        return result.scalar_one_or_none() is not None
    
    @staticmethod
    async def get_all(db: AsyncSession) -> List[str]:
        """Get all excepted usernames."""
        result = await db.execute(select(ExceptUser))
        return [eu.username for eu in result.scalars().all()]
    
    @staticmethod
    async def get_all_with_details(db: AsyncSession) -> List[ExceptUser]:
        """Get all excepted users with full details."""
        result = await db.execute(select(ExceptUser))
        return result.scalars().all()
