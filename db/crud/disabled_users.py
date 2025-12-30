"""
Disabled User CRUD operations.
"""

import time
from typing import Optional, List

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import DisabledUser


class DisabledUserCRUD:
    """CRUD operations for DisabledUser table."""
    
    @staticmethod
    async def add(
        db: AsyncSession,
        username: str,
        disabled_at: Optional[float] = None,
        enable_at: Optional[float] = None,
        original_groups: Optional[List[int]] = None,
        reason: Optional[str] = None,
        punishment_step: int = 0,
    ) -> DisabledUser:
        """Add user to disabled list."""
        if disabled_at is None:
            disabled_at = time.time()
        
        result = await db.execute(select(DisabledUser).where(DisabledUser.username == username))
        disabled = result.scalar_one_or_none()
        
        if disabled:
            disabled.disabled_at = disabled_at
            disabled.enable_at = enable_at
            disabled.original_groups = original_groups or []
            disabled.reason = reason
            disabled.punishment_step = punishment_step
        else:
            disabled = DisabledUser(
                username=username,
                disabled_at=disabled_at,
                enable_at=enable_at,
                original_groups=original_groups or [],
                reason=reason,
                punishment_step=punishment_step,
            )
            db.add(disabled)
        
        await db.flush()
        return disabled
    
    @staticmethod
    async def remove(db: AsyncSession, username: str) -> bool:
        """Remove user from disabled list (when re-enabling)."""
        result = await db.execute(delete(DisabledUser).where(DisabledUser.username == username))
        return result.rowcount > 0
    
    @staticmethod
    async def get(db: AsyncSession, username: str) -> Optional[DisabledUser]:
        """Get disabled user record."""
        result = await db.execute(select(DisabledUser).where(DisabledUser.username == username))
        return result.scalar_one_or_none()
    
    @staticmethod
    async def is_disabled(db: AsyncSession, username: str) -> bool:
        """Check if user is disabled."""
        result = await db.execute(select(DisabledUser).where(DisabledUser.username == username))
        return result.scalar_one_or_none() is not None
    
    @staticmethod
    async def get_all(db: AsyncSession) -> List[DisabledUser]:
        """Get all disabled users."""
        result = await db.execute(select(DisabledUser))
        return result.scalars().all()
    
    @staticmethod
    async def get_all_dict(db: AsyncSession) -> dict[str, float]:
        """Get all disabled users as {username: disabled_timestamp} dict."""
        result = await db.execute(select(DisabledUser))
        disabled = result.scalars().all()
        return {d.username: d.disabled_at for d in disabled}
    
    @staticmethod
    async def get_users_to_enable(db: AsyncSession, time_to_active: int) -> List[str]:
        """
        Get users that should be re-enabled based on time_to_active.
        
        Args:
            time_to_active: Seconds after which to re-enable users
            
        Returns:
            List of usernames to re-enable
        """
        current_time = time.time()
        cutoff = current_time - time_to_active
        
        result = await db.execute(select(DisabledUser))
        disabled = result.scalars().all()
        
        to_enable = []
        for d in disabled:
            if d.enable_at is not None:
                if current_time >= d.enable_at:
                    to_enable.append(d.username)
            elif d.disabled_at <= cutoff:
                to_enable.append(d.username)
        
        return to_enable
    
    @staticmethod
    async def clear_all(db: AsyncSession) -> int:
        """Clear all disabled users. Returns count of cleared."""
        result = await db.execute(delete(DisabledUser))
        return result.rowcount
