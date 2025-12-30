"""
Subnet ISP Cache CRUD operations.
"""

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import SubnetISP


class SubnetISPCRUD:
    """CRUD operations for SubnetISP cache."""
    
    @staticmethod
    def get_subnet_from_ip(ip: str) -> str:
        """Extract /24 subnet from IP address. e.g., 192.168.1.100 -> 192.168.1"""
        parts = ip.split(".")
        if len(parts) == 4:
            return ".".join(parts[:3])
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
