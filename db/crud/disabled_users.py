"""
Disabled User CRUD operations.

DEPRECATED: This module is kept for backward compatibility.
New code should use UserCRUD.set_disabled(), is_disabled_by_limiter(), etc.
"""

from typing import Optional, List

from sqlalchemy.ext.asyncio import AsyncSession

from db.crud.users import UserCRUD
from db.models import User
from utils.logs import get_logger

db_disabled_logger = get_logger("db.disabled")


class DisabledUserCRUD:
    """
    DEPRECATED: CRUD operations for DisabledUser.
    Use UserCRUD.set_disabled(), is_disabled_by_limiter() instead.
    This class now delegates to UserCRUD methods for backward compatibility.
    """
    
    @staticmethod
    async def add(
        db: AsyncSession,
        username: str,
        disabled_at: Optional[float] = None,
        enable_at: Optional[float] = None,
        original_groups: Optional[List[int]] = None,
        reason: Optional[str] = None,
        punishment_step: int = 0,
    ) -> Optional[User]:
        """Add user to disabled list. Delegates to UserCRUD."""
        db_disabled_logger.debug(f"[DEPRECATED] add -> UserCRUD.set_disabled")
        return await UserCRUD.set_disabled(
            db, username,
            disabled=True,
            disabled_at=disabled_at,
            enable_at=enable_at,
            original_groups=original_groups,
            reason=reason,
            punishment_step=punishment_step,
        )
    
    @staticmethod
    async def remove(db: AsyncSession, username: str) -> bool:
        """Remove user from disabled list. Delegates to UserCRUD."""
        db_disabled_logger.debug(f"[DEPRECATED] remove -> UserCRUD.set_disabled(False)")
        result = await UserCRUD.set_disabled(db, username, disabled=False)
        return result is not None
    
    @staticmethod
    async def get(db: AsyncSession, username: str) -> Optional[User]:
        """Get disabled user record. Delegates to UserCRUD."""
        db_disabled_logger.debug(f"[DEPRECATED] get -> UserCRUD.get_disabled_record")
        return await UserCRUD.get_disabled_record(db, username)
    
    @staticmethod
    async def is_disabled(db: AsyncSession, username: str) -> bool:
        """Check if user is disabled. Delegates to UserCRUD."""
        db_disabled_logger.debug(f"[DEPRECATED] is_disabled -> UserCRUD.is_disabled_by_limiter")
        return await UserCRUD.is_disabled_by_limiter(db, username)
    
    @staticmethod
    async def get_all(db: AsyncSession) -> List[User]:
        """Get all disabled users. Delegates to UserCRUD."""
        db_disabled_logger.debug(f"[DEPRECATED] get_all -> UserCRUD.get_all_disabled")
        return await UserCRUD.get_all_disabled(db)
    
    @staticmethod
    async def get_all_dict(db: AsyncSession) -> dict[str, float]:
        """Get all disabled users as dict. Delegates to UserCRUD."""
        db_disabled_logger.debug(f"[DEPRECATED] get_all_dict -> UserCRUD.get_all_disabled_dict")
        return await UserCRUD.get_all_disabled_dict(db)
    
    @staticmethod
    async def get_users_to_enable(db: AsyncSession, time_to_active: int) -> List[str]:
        """Get users that should be re-enabled. Delegates to UserCRUD."""
        db_disabled_logger.debug(f"[DEPRECATED] get_users_to_enable -> UserCRUD.get_users_to_enable")
        return await UserCRUD.get_users_to_enable(db, time_to_active)
    
    @staticmethod
    async def clear_all(db: AsyncSession) -> int:
        """
        Clear all disabled users. 
        NOTE: This sets is_disabled_by_limiter=False for all users.
        """
        db_disabled_logger.debug(f"[DEPRECATED] clear_all -> bulk set_disabled(False)")
        from sqlalchemy import update
        from db.models import User
        result = await db.execute(
            update(User).where(User.is_disabled_by_limiter == True).values(  # noqa: E712
                is_disabled_by_limiter=False,
                disabled_at=None,
                enable_at=None,
                original_groups=[],
                disable_reason=None,
            )
        )
        db_disabled_logger.info(f"✅ Cleared {result.rowcount} disabled users")
        return result.rowcount
