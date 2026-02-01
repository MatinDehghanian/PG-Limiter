"""
CRUD operations for Admin Patterns (prefix/postfix).
Used to match usernames to admins based on naming patterns.
"""

from typing import List, Optional
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import AdminPattern
from utils.logs import get_logger

admin_patterns_logger = get_logger("admin_patterns_crud")


class AdminPatternCRUD:
    """CRUD operations for admin patterns."""
    
    @staticmethod
    async def create(
        db: AsyncSession,
        admin_username: str,
        pattern_type: str,
        pattern: str,
        description: Optional[str] = None
    ) -> AdminPattern:
        """
        Create a new admin pattern.
        
        Args:
            db: Database session
            admin_username: The admin username who owns users matching this pattern
            pattern_type: "prefix" or "postfix"
            pattern: The pattern string
            description: Optional description
            
        Returns:
            The created AdminPattern
        """
        if pattern_type not in ("prefix", "postfix"):
            raise ValueError("pattern_type must be 'prefix' or 'postfix'")
        
        admin_patterns_logger.info(f"➕ Creating {pattern_type} pattern '{pattern}' for admin '{admin_username}'")
        
        admin_pattern = AdminPattern(
            admin_username=admin_username,
            pattern_type=pattern_type,
            pattern=pattern,
            description=description
        )
        db.add(admin_pattern)
        await db.flush()
        
        admin_patterns_logger.info(f"✅ Created pattern ID {admin_pattern.id}")
        return admin_pattern
    
    @staticmethod
    async def get_by_id(db: AsyncSession, pattern_id: int) -> Optional[AdminPattern]:
        """Get a pattern by ID."""
        result = await db.execute(select(AdminPattern).where(AdminPattern.id == pattern_id))
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_all(db: AsyncSession) -> List[AdminPattern]:
        """Get all patterns."""
        admin_patterns_logger.debug("📋 Getting all admin patterns")
        result = await db.execute(select(AdminPattern).order_by(AdminPattern.admin_username))
        patterns = list(result.scalars().all())
        admin_patterns_logger.debug(f"✅ Found {len(patterns)} patterns")
        return patterns
    
    @staticmethod
    async def get_by_admin(db: AsyncSession, admin_username: str) -> List[AdminPattern]:
        """Get all patterns for a specific admin."""
        admin_patterns_logger.debug(f"🔍 Getting patterns for admin '{admin_username}'")
        result = await db.execute(
            select(AdminPattern).where(AdminPattern.admin_username == admin_username)
        )
        patterns = list(result.scalars().all())
        admin_patterns_logger.debug(f"✅ Found {len(patterns)} patterns for admin '{admin_username}'")
        return patterns
    
    @staticmethod
    async def get_by_type(db: AsyncSession, pattern_type: str) -> List[AdminPattern]:
        """Get all patterns of a specific type (prefix or postfix)."""
        result = await db.execute(
            select(AdminPattern).where(AdminPattern.pattern_type == pattern_type)
        )
        return list(result.scalars().all())
    
    @staticmethod
    async def delete_by_id(db: AsyncSession, pattern_id: int) -> bool:
        """Delete a pattern by ID."""
        admin_patterns_logger.info(f"🗑️ Deleting pattern ID {pattern_id}")
        result = await db.execute(
            delete(AdminPattern).where(AdminPattern.id == pattern_id)
        )
        deleted = result.rowcount > 0
        if deleted:
            admin_patterns_logger.info(f"✅ Deleted pattern ID {pattern_id}")
        else:
            admin_patterns_logger.warning(f"⚠️ Pattern ID {pattern_id} not found")
        return deleted
    
    @staticmethod
    async def delete_by_admin(db: AsyncSession, admin_username: str) -> int:
        """Delete all patterns for an admin. Returns number of deleted patterns."""
        admin_patterns_logger.info(f"🗑️ Deleting all patterns for admin '{admin_username}'")
        result = await db.execute(
            delete(AdminPattern).where(AdminPattern.admin_username == admin_username)
        )
        admin_patterns_logger.info(f"✅ Deleted {result.rowcount} patterns for admin '{admin_username}'")
        return result.rowcount
    
    @staticmethod
    async def find_admin_by_username(db: AsyncSession, username: str) -> Optional[str]:
        """
        Find admin username by matching user's username against patterns.
        
        Args:
            db: Database session
            username: The username to match
            
        Returns:
            Admin username if a pattern matches, None otherwise
        """
        admin_patterns_logger.debug(f"🔍 Matching username '{username}' against patterns")
        
        # Get all patterns
        result = await db.execute(select(AdminPattern))
        patterns = list(result.scalars().all())
        
        # Check each pattern
        for pattern in patterns:
            if pattern.pattern_type == "prefix":
                if username.startswith(pattern.pattern):
                    admin_patterns_logger.debug(
                        f"✅ Username '{username}' matches prefix '{pattern.pattern}' -> admin '{pattern.admin_username}'"
                    )
                    return pattern.admin_username
            elif pattern.pattern_type == "postfix":
                if username.endswith(pattern.pattern):
                    admin_patterns_logger.debug(
                        f"✅ Username '{username}' matches postfix '{pattern.pattern}' -> admin '{pattern.admin_username}'"
                    )
                    return pattern.admin_username
        
        admin_patterns_logger.debug(f"❌ No pattern match for username '{username}'")
        return None
    
    @staticmethod
    async def find_matching_users(db: AsyncSession, pattern_id: int, all_usernames: List[str]) -> List[str]:
        """
        Find all usernames that match a specific pattern.
        
        Args:
            db: Database session
            pattern_id: The pattern ID to match against
            all_usernames: List of all usernames to check
            
        Returns:
            List of matching usernames
        """
        pattern = await AdminPatternCRUD.get_by_id(db, pattern_id)
        if not pattern:
            return []
        
        matching = []
        for username in all_usernames:
            if pattern.pattern_type == "prefix" and username.startswith(pattern.pattern):
                matching.append(username)
            elif pattern.pattern_type == "postfix" and username.endswith(pattern.pattern):
                matching.append(username)
        
        return matching
