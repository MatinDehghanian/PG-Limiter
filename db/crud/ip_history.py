"""
IP History CRUD operations.
"""

from datetime import datetime, timedelta
from typing import Optional, List

from sqlalchemy import select, delete, and_
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import IPHistory


class IPHistoryCRUD:
    """CRUD operations for IPHistory table."""
    
    @staticmethod
    async def record_ip(
        db: AsyncSession,
        username: str,
        ip: str,
        node_name: Optional[str] = None,
        inbound_protocol: Optional[str] = None,
    ) -> IPHistory:
        """Record an IP for a user (update if exists, create if not)."""
        result = await db.execute(
            select(IPHistory).where(
                and_(IPHistory.username == username, IPHistory.ip == ip)
            )
        )
        history = result.scalar_one_or_none()
        
        if history:
            history.last_seen = datetime.utcnow()
            history.connection_count += 1
            if node_name:
                history.node_name = node_name
            if inbound_protocol:
                history.inbound_protocol = inbound_protocol
        else:
            history = IPHistory(
                username=username,
                ip=ip,
                node_name=node_name,
                inbound_protocol=inbound_protocol,
            )
            db.add(history)
        
        await db.flush()
        return history
    
    @staticmethod
    async def get_user_ips(db: AsyncSession, username: str, hours: int = 24) -> List[IPHistory]:
        """Get IPs for a user within the specified hours."""
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        result = await db.execute(
            select(IPHistory)
            .where(
                and_(
                    IPHistory.username == username,
                    IPHistory.last_seen >= cutoff,
                )
            )
            .order_by(IPHistory.last_seen.desc())
        )
        return result.scalars().all()
    
    @staticmethod
    async def cleanup_old(db: AsyncSession, days: int = 7) -> int:
        """Remove IP history older than specified days."""
        cutoff = datetime.utcnow() - timedelta(days=days)
        result = await db.execute(delete(IPHistory).where(IPHistory.last_seen < cutoff))
        return result.rowcount
