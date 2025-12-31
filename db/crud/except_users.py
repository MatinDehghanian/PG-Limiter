"""
Except User CRUD operations (whitelist).

DEPRECATED: This module is kept for backward compatibility.
New code should use UserCRUD.set_excepted(), is_excepted(), etc.
"""

from typing import Optional, List

from sqlalchemy.ext.asyncio import AsyncSession

from db.crud.users import UserCRUD
from db.models import User
from utils.logs import get_logger

db_except_logger = get_logger("db.except")


class ExceptUserCRUD:
    """
    DEPRECATED: CRUD operations for ExceptUser (whitelist).
    Use UserCRUD.set_excepted(), is_excepted() instead.
    This class now delegates to UserCRUD methods for backward compatibility.
    """
    
    @staticmethod
    async def add(
        db: AsyncSession,
        username: str,
        reason: Optional[str] = None,
        created_by: Optional[str] = None
    ) -> Optional[User]:
        """Add user to exception list. Delegates to UserCRUD."""
        db_except_logger.debug(f"[DEPRECATED] add -> UserCRUD.set_excepted")
        return await UserCRUD.set_excepted(
            db, username, excepted=True, reason=reason, excepted_by=created_by
        )
    
    @staticmethod
    async def remove(db: AsyncSession, username: str) -> bool:
        """Remove user from exception list. Delegates to UserCRUD."""
        db_except_logger.debug(f"[DEPRECATED] remove -> UserCRUD.set_excepted(False)")
        result = await UserCRUD.set_excepted(db, username, excepted=False)
        return result is not None
    
    @staticmethod
    async def is_excepted(db: AsyncSession, username: str) -> bool:
        """Check if user is in exception list. Delegates to UserCRUD."""
        db_except_logger.debug(f"[DEPRECATED] is_excepted -> UserCRUD.is_excepted")
        return await UserCRUD.is_excepted(db, username)
    
    @staticmethod
    async def get_all(db: AsyncSession) -> List[str]:
        """Get all excepted usernames. Delegates to UserCRUD."""
        db_except_logger.debug(f"[DEPRECATED] get_all -> UserCRUD.get_all_excepted")
        return await UserCRUD.get_all_excepted(db)
    
    @staticmethod
    async def get_all_with_details(db: AsyncSession) -> List[User]:
        """Get all excepted users with full details. Delegates to UserCRUD."""
        db_except_logger.debug(f"[DEPRECATED] get_all_with_details -> UserCRUD.get_all_excepted_with_details")
        return await UserCRUD.get_all_excepted_with_details(db)
