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
    
    # Get the database file path
    db_path = DATABASE_URL.replace("sqlite+aiosqlite:///", "")
    if db_path.startswith("./"):
        db_path = db_path[2:]
    
    # Get alembic config
    alembic_cfg = Config("alembic.ini")
    
    try:
        if os.path.exists(db_path):
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Check if users table exists
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
            )
            has_users = cursor.fetchone() is not None
            
            # Check if users table has the new consolidated columns
            has_new_columns = False
            if has_users:
                cursor.execute("PRAGMA table_info(users)")
                columns = {row[1] for row in cursor.fetchall()}
                has_new_columns = "is_excepted" in columns
            
            conn.close()
            
            if has_users and not has_new_columns:
                # Database exists but missing new columns - add them directly
                db_logger.info("📌 Adding missing columns to users table...")
                _add_missing_columns(db_path)
                db_logger.info("✅ Columns added successfully")
                
                # Stamp at latest migration
                try:
                    command.stamp(alembic_cfg, "002_consolidate_users")
                except Exception:
                    pass  # Ignore stamp errors
            else:
                # Try normal upgrade
                try:
                    command.upgrade(alembic_cfg, "head")
                except Exception as e:
                    if "already exists" in str(e):
                        # Tables exist, try to stamp and continue
                        try:
                            command.stamp(alembic_cfg, "head")
                        except Exception:
                            pass
                    else:
                        db_logger.warning(f"Migration upgrade issue: {e}")
        else:
            # Fresh database - just run migrations
            db_logger.info("🔄 Creating new database with migrations...")
            command.upgrade(alembic_cfg, "head")
            
    except Exception as e:
        db_logger.warning(f"Migration handling: {e}")
        # Fallback: ensure columns exist
        if os.path.exists(db_path):
            _add_missing_columns(db_path)


def _add_missing_columns(db_path: str):
    """Add missing consolidated columns to users table."""
    import sqlite3
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get existing columns
    cursor.execute("PRAGMA table_info(users)")
    existing_columns = {row[1] for row in cursor.fetchall()}
    
    # Define columns to add
    columns_to_add = [
        ("is_excepted", "BOOLEAN DEFAULT 0"),
        ("exception_reason", "TEXT"),
        ("excepted_by", "VARCHAR(255)"),
        ("excepted_at", "DATETIME"),
        ("special_limit", "INTEGER"),
        ("special_limit_updated_at", "DATETIME"),
        ("is_disabled_by_limiter", "BOOLEAN DEFAULT 0"),
        ("disabled_at", "FLOAT"),
        ("enable_at", "FLOAT"),
        ("original_groups", "JSON"),
        ("disable_reason", "TEXT"),
        ("punishment_step", "INTEGER DEFAULT 0"),
    ]
    
    for col_name, col_type in columns_to_add:
        if col_name not in existing_columns:
            try:
                cursor.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}")
                db_logger.debug(f"  Added column: {col_name}")
            except sqlite3.OperationalError as e:
                if "duplicate column" not in str(e).lower():
                    db_logger.warning(f"  Could not add {col_name}: {e}")
    
    conn.commit()
    conn.close()


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
