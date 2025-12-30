"""
Violation History CRUD operations.
"""

import time
from typing import Optional, List

from sqlalchemy import select, delete, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import ViolationHistory


class ViolationHistoryCRUD:
    """CRUD operations for ViolationHistory table."""
    
    @staticmethod
    async def add(
        db: AsyncSession,
        username: str,
        step_applied: int,
        disable_duration: int,
        ip_count: Optional[int] = None,
        ips: Optional[List[str]] = None,
    ) -> ViolationHistory:
        """Add a violation record."""
        violation = ViolationHistory(
            username=username,
            timestamp=time.time(),
            step_applied=step_applied,
            disable_duration=disable_duration,
            ip_count=ip_count,
            ips=ips,
        )
        db.add(violation)
        await db.flush()
        return violation
    
    @staticmethod
    async def get_user_violations(
        db: AsyncSession,
        username: str,
        window_hours: int = 72,
    ) -> List[ViolationHistory]:
        """Get violations for a user within the time window."""
        cutoff = time.time() - (window_hours * 3600)
        result = await db.execute(
            select(ViolationHistory)
            .where(
                and_(
                    ViolationHistory.username == username,
                    ViolationHistory.timestamp >= cutoff,
                )
            )
            .order_by(ViolationHistory.timestamp.desc())
        )
        return result.scalars().all()
    
    @staticmethod
    async def get_violation_count(
        db: AsyncSession,
        username: str,
        window_hours: int = 72,
    ) -> int:
        """Get count of violations for a user within the time window."""
        cutoff = time.time() - (window_hours * 3600)
        result = await db.execute(
            select(func.count(ViolationHistory.id))  # pylint: disable=not-callable
            .where(
                and_(
                    ViolationHistory.username == username,
                    ViolationHistory.timestamp >= cutoff,
                )
            )
        )
        return result.scalar() or 0
    
    @staticmethod
    async def clear_user(db: AsyncSession, username: str) -> int:
        """Clear all violations for a user."""
        result = await db.execute(delete(ViolationHistory).where(ViolationHistory.username == username))
        return result.rowcount
    
    @staticmethod
    async def clear_all(db: AsyncSession) -> int:
        """Clear all violation history."""
        result = await db.execute(delete(ViolationHistory))
        return result.rowcount
    
    @staticmethod
    async def cleanup_old(db: AsyncSession, days: int = 30) -> int:
        """Remove violations older than specified days."""
        cutoff = time.time() - (days * 24 * 3600)
        result = await db.execute(delete(ViolationHistory).where(ViolationHistory.timestamp < cutoff))
        return result.rowcount
