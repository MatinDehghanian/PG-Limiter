"""
CRUD operations for Limit Patterns (prefix/postfix with IP limits).
Used to set special IP limits for users based on username patterns.
"""

from typing import List, Optional
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import LimitPattern
from utils.logs import get_logger

limit_patterns_logger = get_logger("limit_patterns_crud")


class LimitPatternCRUD:
    """CRUD operations for limit patterns."""
    
    @staticmethod
    async def create(
        db: AsyncSession,
        pattern_type: str,
        pattern: str,
        ip_limit: int,
        description: Optional[str] = None
    ) -> LimitPattern:
        """
        Create a new limit pattern.
        
        Args:
            db: Database session
            pattern_type: "prefix" or "postfix"
            pattern: The pattern string
            ip_limit: The IP limit for matching users
            description: Optional description
            
        Returns:
            The created LimitPattern
        """
        if pattern_type not in ("prefix", "postfix"):
            raise ValueError("pattern_type must be 'prefix' or 'postfix'")
        
        limit_patterns_logger.info(f"➕ Creating {pattern_type} pattern '{pattern}' with limit {ip_limit}")
        
        limit_pattern = LimitPattern(
            pattern_type=pattern_type,
            pattern=pattern,
            ip_limit=ip_limit,
            description=description
        )
        db.add(limit_pattern)
        await db.flush()
        
        limit_patterns_logger.info(f"✅ Created limit pattern ID {limit_pattern.id}")
        return limit_pattern
    
    @staticmethod
    async def get_by_id(db: AsyncSession, pattern_id: int) -> Optional[LimitPattern]:
        """Get a pattern by ID."""
        result = await db.execute(select(LimitPattern).where(LimitPattern.id == pattern_id))
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_all(db: AsyncSession) -> List[LimitPattern]:
        """Get all limit patterns."""
        limit_patterns_logger.debug("📋 Getting all limit patterns")
        result = await db.execute(select(LimitPattern).order_by(LimitPattern.ip_limit))
        patterns = list(result.scalars().all())
        limit_patterns_logger.debug(f"✅ Found {len(patterns)} limit patterns")
        return patterns
    
    @staticmethod
    async def get_by_limit(db: AsyncSession, ip_limit: int) -> List[LimitPattern]:
        """Get all patterns with a specific limit."""
        result = await db.execute(
            select(LimitPattern).where(LimitPattern.ip_limit == ip_limit)
        )
        return list(result.scalars().all())
    
    @staticmethod
    async def get_by_type(db: AsyncSession, pattern_type: str) -> List[LimitPattern]:
        """Get all patterns of a specific type (prefix or postfix)."""
        result = await db.execute(
            select(LimitPattern).where(LimitPattern.pattern_type == pattern_type)
        )
        return list(result.scalars().all())
    
    @staticmethod
    async def delete_by_id(db: AsyncSession, pattern_id: int) -> bool:
        """Delete a pattern by ID."""
        limit_patterns_logger.info(f"🗑️ Deleting limit pattern ID {pattern_id}")
        result = await db.execute(
            delete(LimitPattern).where(LimitPattern.id == pattern_id)
        )
        deleted = result.rowcount > 0
        if deleted:
            limit_patterns_logger.info(f"✅ Deleted limit pattern ID {pattern_id}")
        else:
            limit_patterns_logger.warning(f"⚠️ Limit pattern ID {pattern_id} not found")
        return deleted
    
    @staticmethod
    async def find_limit_by_username(db: AsyncSession, username: str) -> Optional[int]:
        """
        Find IP limit by matching username against patterns.
        
        Args:
            db: Database session
            username: The username to match
            
        Returns:
            IP limit if a pattern matches, None otherwise
        """
        limit_patterns_logger.debug(f"🔍 Matching username '{username}' against limit patterns")
        
        # Get all patterns
        result = await db.execute(select(LimitPattern))
        patterns = list(result.scalars().all())
        
        # Check each pattern
        for pattern in patterns:
            if pattern.pattern_type == "prefix":
                if username.startswith(pattern.pattern):
                    limit_patterns_logger.debug(
                        f"✅ Username '{username}' matches prefix '{pattern.pattern}' -> limit {pattern.ip_limit}"
                    )
                    return pattern.ip_limit
            elif pattern.pattern_type == "postfix":
                if username.endswith(pattern.pattern):
                    limit_patterns_logger.debug(
                        f"✅ Username '{username}' matches postfix '{pattern.pattern}' -> limit {pattern.ip_limit}"
                    )
                    return pattern.ip_limit
        
        limit_patterns_logger.debug(f"❌ No limit pattern match for username '{username}'")
        return None
    
    @staticmethod
    async def update_limit(db: AsyncSession, pattern_id: int, new_limit: int) -> Optional[LimitPattern]:
        """Update the IP limit for a pattern."""
        result = await db.execute(select(LimitPattern).where(LimitPattern.id == pattern_id))
        pattern = result.scalar_one_or_none()
        if pattern:
            pattern.ip_limit = new_limit
            await db.flush()
            limit_patterns_logger.info(f"✅ Updated limit pattern ID {pattern_id} to limit {new_limit}")
        return pattern
