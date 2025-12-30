"""
CRUD Operations for Database
Provides high-level async operations for all database models.
"""

from datetime import datetime, timedelta
from typing import Optional, List
import time

from sqlalchemy import select, delete, update, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    User,
    UserLimit,
    ExceptUser,
    DisabledUser,
    SubnetISP,
    ViolationHistory,
    Config,
    IPHistory,
)
from utils.logs import logger


# ═══════════════════════════════════════════════════════════════════════════
# USER OPERATIONS
# ═══════════════════════════════════════════════════════════════════════════

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
            # Update existing user
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
            # Create new user
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
        # For SQLite with JSON, we need to check if group_id is in the JSON array
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


# ═══════════════════════════════════════════════════════════════════════════
# USER LIMIT OPERATIONS
# ═══════════════════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════════════════
# EXCEPT USER OPERATIONS
# ═══════════════════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════════════════
# DISABLED USER OPERATIONS
# ═══════════════════════════════════════════════════════════════════════════

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
            # If custom enable_at is set, use that
            if d.enable_at is not None:
                if current_time >= d.enable_at:
                    to_enable.append(d.username)
            # Otherwise use global time_to_active
            elif d.disabled_at <= cutoff:
                # Only auto-enable if not a permanent disable (punishment_step check)
                # TODO: Check if this is an unlimited disable
                to_enable.append(d.username)
        
        return to_enable
    
    @staticmethod
    async def clear_all(db: AsyncSession) -> int:
        """Clear all disabled users. Returns count of cleared."""
        result = await db.execute(delete(DisabledUser))
        return result.rowcount


# ═══════════════════════════════════════════════════════════════════════════
# SUBNET ISP OPERATIONS
# ═══════════════════════════════════════════════════════════════════════════

class SubnetISPCRUD:
    """CRUD operations for SubnetISP cache."""
    
    @staticmethod
    def get_subnet_from_ip(ip: str) -> str:
        """Extract /24 subnet from IP address. e.g., 192.168.1.100 -> 192.168.1"""
        parts = ip.split(".")
        if len(parts) == 4:
            return ".".join(parts[:3])
        # For IPv6, use first 4 groups
        if ":" in ip:
            parts = ip.split(":")
            return ":".join(parts[:4])
        return ip
    
    @staticmethod
    async def get_by_ip(db: AsyncSession, ip: str) -> Optional[SubnetISP]:
        """Get ISP info for an IP (looks up by subnet)."""
        subnet = SubnetISPCRUD.get_subnet_from_ip(ip)
        result = await db.execute(select(SubnetISP).where(SubnetISP.subnet == subnet))
        isp = result.scalar_one_or_none()
        
        # Increment hit count if found
        if isp:
            isp.hit_count += 1
            await db.flush()
        
        return isp
    
    @staticmethod
    async def get_by_subnet(db: AsyncSession, subnet: str) -> Optional[SubnetISP]:
        """Get ISP info by subnet directly."""
        result = await db.execute(select(SubnetISP).where(SubnetISP.subnet == subnet))
        return result.scalar_one_or_none()
    
    @staticmethod
    async def cache_isp(
        db: AsyncSession,
        ip: str,
        isp: str,
        country: Optional[str] = None,
        city: Optional[str] = None,
        region: Optional[str] = None,
        asn: Optional[str] = None,
        as_name: Optional[str] = None,
    ) -> SubnetISP:
        """Cache ISP info for an IP's subnet."""
        subnet = SubnetISPCRUD.get_subnet_from_ip(ip)
        
        result = await db.execute(select(SubnetISP).where(SubnetISP.subnet == subnet))
        existing = result.scalar_one_or_none()
        
        if existing:
            existing.isp = isp
            existing.country = country
            existing.city = city
            existing.region = region
            existing.asn = asn
            existing.as_name = as_name
            existing.cached_at = datetime.utcnow()
            existing.hit_count += 1
            return existing
        
        subnet_isp = SubnetISP(
            subnet=subnet,
            isp=isp,
            country=country,
            city=city,
            region=region,
            asn=asn,
            as_name=as_name,
        )
        db.add(subnet_isp)
        await db.flush()
        return subnet_isp
    
    @staticmethod
    async def get_stats(db: AsyncSession) -> dict:
        """Get ISP cache statistics."""
        result = await db.execute(select(func.count(SubnetISP.id)))  # pylint: disable=not-callable
        count = result.scalar()
        
        result = await db.execute(select(func.sum(SubnetISP.hit_count)))
        total_hits = result.scalar() or 0
        
        return {
            "cached_subnets": count,
            "total_cache_hits": total_hits,
        }
    
    @staticmethod
    async def cleanup_old(db: AsyncSession, days: int = 30) -> int:
        """Remove cache entries older than specified days."""
        cutoff = datetime.utcnow() - timedelta(days=days)
        result = await db.execute(delete(SubnetISP).where(SubnetISP.cached_at < cutoff))
        return result.rowcount


# ═══════════════════════════════════════════════════════════════════════════
# VIOLATION HISTORY OPERATIONS
# ═══════════════════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════════════════
# CONFIG OPERATIONS
# ═══════════════════════════════════════════════════════════════════════════

class ConfigCRUD:
    """CRUD operations for Config table (key-value store)."""
    
    @staticmethod
    async def set(db: AsyncSession, key: str, value) -> Config:
        """Set a config value."""
        result = await db.execute(select(Config).where(Config.key == key))
        config = result.scalar_one_or_none()
        
        if config:
            config.value = value
            config.updated_at = datetime.utcnow()
        else:
            config = Config(key=key, value=value)
            db.add(config)
        
        await db.flush()
        return config
    
    @staticmethod
    async def get(db: AsyncSession, key: str, default=None):
        """Get a config value."""
        result = await db.execute(select(Config).where(Config.key == key))
        config = result.scalar_one_or_none()
        return config.value if config else default
    
    @staticmethod
    async def delete(db: AsyncSession, key: str) -> bool:
        """Delete a config key."""
        result = await db.execute(delete(Config).where(Config.key == key))
        return result.rowcount > 0
    
    @staticmethod
    async def get_all(db: AsyncSession) -> dict:
        """Get all config as a dictionary."""
        result = await db.execute(select(Config))
        configs = result.scalars().all()
        return {c.key: c.value for c in configs}


# ═══════════════════════════════════════════════════════════════════════════
# IP HISTORY OPERATIONS
# ═══════════════════════════════════════════════════════════════════════════

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
