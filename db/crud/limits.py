"""
User Limit CRUD operations.

DEPRECATED: This module is kept for backward compatibility.
New code should use UserCRUD.set_special_limit(), get_special_limit(), etc.
"""

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from db.crud.users import UserCRUD
from utils.logs import get_logger

db_limits_logger = get_logger("db.limits")


class UserLimitCRUD:
    """
    DEPRECATED: CRUD operations for UserLimit.
    Use UserCRUD.set_special_limit(), get_special_limit() instead.
    This class now delegates to UserCRUD methods for backward compatibility.
    """
    
    @staticmethod
    async def set_limit(db: AsyncSession, username: str, limit: int):
        """Set or update limit for a user. Delegates to UserCRUD."""
        db_limits_logger.debug(f"[DEPRECATED] set_limit -> UserCRUD.set_special_limit")
        return await UserCRUD.set_special_limit(db, username, limit)
    
    # Alias for consistency
    set = set_limit
    
    @staticmethod
    async def get_limit(db: AsyncSession, username: str) -> Optional[int]:
        """Get limit for a user. Delegates to UserCRUD."""
        db_limits_logger.debug(f"[DEPRECATED] get_limit -> UserCRUD.get_special_limit")
        return await UserCRUD.get_special_limit(db, username)
    
    @staticmethod
    async def get_all(db: AsyncSession) -> dict[str, int]:
        """Get all special limits as a dictionary. Delegates to UserCRUD."""
        db_limits_logger.debug(f"[DEPRECATED] get_all -> UserCRUD.get_all_special_limits")
        return await UserCRUD.get_all_special_limits(db)
    
    @staticmethod
    async def delete(db: AsyncSession, username: str) -> bool:
        """Remove special limit for a user. Delegates to UserCRUD."""
        db_limits_logger.debug(f"[DEPRECATED] delete -> UserCRUD.set_special_limit(None)")
        result = await UserCRUD.set_special_limit(db, username, None)
        return result is not None
