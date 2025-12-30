"""
Config CRUD operations (key-value store).
"""

from datetime import datetime

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Config


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
