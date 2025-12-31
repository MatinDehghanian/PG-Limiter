"""
Database Connection and Session Management
Uses async SQLAlchemy with aiosqlite for SQLite.
"""

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from db.models import Base
from utils.logs import get_logger

db_logger = get_logger("database")

# Database URL - defaults to SQLite in data directory
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "sqlite+aiosqlite:///./data/pg_limiter.db"
)

# For SQLite, use StaticPool for better async support
if DATABASE_URL.startswith("sqlite"):
    db_logger.debug(f"📦 Using SQLite database: {DATABASE_URL}")
    engine = create_async_engine(
        DATABASE_URL,
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
else:
    db_logger.debug(f"📦 Using external database: {DATABASE_URL}")
    engine = create_async_engine(
        DATABASE_URL,
        echo=False,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )

# Session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def init_db():
    """
    Initialize the database - run migrations automatically.
    Should be called once at application startup.
    """
    # Ensure data directory exists
    db_path = DATABASE_URL.replace("sqlite+aiosqlite:///", "")
    if db_path.startswith("./"):
        db_path = db_path[2:]
    
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
        db_logger.info(f"📁 Created database directory: {db_dir}")
    
    db_logger.debug("🔄 Running database migrations...")
    
    # Run migrations automatically
    await run_migrations()
    
    db_logger.info(f"✅ Database initialized: {DATABASE_URL}")


async def run_migrations():
    """
    Run Alembic migrations automatically.
    Handles existing databases that were created before migrations were added.
    """
    import sqlite3
    from alembic.config import Config
    from alembic import command
    from alembic.script import ScriptDirectory
    
    # Get the database file path
    db_path = DATABASE_URL.replace("sqlite+aiosqlite:///", "")
    if db_path.startswith("./"):
        db_path = db_path[2:]
    
    # Get alembic config
    alembic_cfg = Config("alembic.ini")
    script = ScriptDirectory.from_config(alembic_cfg)
    
    # Check if this is an existing database without alembic_version
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Check if alembic_version table exists
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'"
            )
            has_alembic = cursor.fetchone() is not None
            
            # Check if users table exists (old database)
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
            )
            has_users = cursor.fetchone() is not None
            
            if has_users and not has_alembic:
                # Old database exists without migration tracking
                # Check if it has the new columns (is_excepted)
                cursor.execute("PRAGMA table_info(users)")
                columns = {row[1] for row in cursor.fetchall()}
                
                if "is_excepted" in columns:
                    # Database already has consolidated columns, stamp as current
                    db_logger.info("📌 Stamping existing database at 002_consolidate_users")
                    conn.close()
                    command.stamp(alembic_cfg, "002_consolidate_users")
                else:
                    # Old database without new columns, stamp at 001 then upgrade
                    db_logger.info("📌 Stamping existing database at 001_initial")
                    conn.close()
                    command.stamp(alembic_cfg, "001_initial")
                    db_logger.info("🔄 Upgrading database to latest version...")
                    command.upgrade(alembic_cfg, "head")
            else:
                conn.close()
                # Run normal upgrade (will create tables if needed or apply pending migrations)
                db_logger.info("🔄 Running database upgrade...")
                command.upgrade(alembic_cfg, "head")
                
        except Exception as e:
            db_logger.error(f"Migration check failed: {e}")
            # Fallback: try to run upgrade anyway
            try:
                command.upgrade(alembic_cfg, "head")
            except Exception as upgrade_error:
                db_logger.error(f"Migration upgrade failed: {upgrade_error}")
                raise
    else:
        # Fresh database - just run migrations
        db_logger.info("🔄 Creating new database with migrations...")
        command.upgrade(alembic_cfg, "head")


async def close_db():
    """Close database connections."""
    db_logger.debug("🔄 Closing database connections...")
    await engine.dispose()
    db_logger.info("✅ Database connections closed")


@asynccontextmanager
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Async context manager for database sessions.
    
    Usage:
        async with get_db() as db:
            result = await db.execute(select(User))
            users = result.scalars().all()
    """
    db_logger.debug("📂 Opening database session")
    session = AsyncSessionLocal()
    try:
        yield session
        await session.commit()
        db_logger.debug("✅ Database session committed")
    except Exception as e:
        await session.rollback()
        db_logger.error(f"❌ Database error (rolled back): {e}")
        raise
    finally:
        await session.close()
        db_logger.debug("📁 Database session closed")


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Async generator for FastAPI dependency injection.
    
    Usage:
        @app.get("/users")
        async def get_users(db: AsyncSession = Depends(get_db_session)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            raise
