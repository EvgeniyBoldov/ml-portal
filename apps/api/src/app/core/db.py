#ПРОВЕРЕНО
from __future__ import annotations
import os
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, AsyncIterator
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import text

logger = logging.getLogger(__name__)

# Global state managed by lifespan
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _db_url() -> str:
    """Get database URL from environment variables"""
    # Use ASYNC_DB_URL if available, otherwise construct from DATABASE_URL
    async_url = os.getenv("ASYNC_DB_URL")
    if async_url:
        return async_url
    
    # Fallback to DATABASE_URL with asyncpg driver
    url = os.getenv("DATABASE_URL") or "postgresql+asyncpg://ml_portal:ml_portal_password@postgres:5432/ml_portal"
    if "+asyncpg" not in url:
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


@asynccontextmanager
async def lifespan(app):
    """FastAPI lifespan context manager for database initialization"""
    global _engine, _session_factory
    
    try:
        logger.info("Initializing database connection...")
        
        # Create async engine
        _engine = create_async_engine(
            _db_url(),
            echo=False,
            pool_pre_ping=True,
            pool_recycle=300,
            pool_size=10,
            max_overflow=20,
        )
        
        # Create session factory
        _session_factory = async_sessionmaker(
            _engine, 
            expire_on_commit=False,
            class_=AsyncSession
        )
        
        logger.info("Database connection initialized successfully")
        yield
        
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise
    finally:
        logger.info("Closing database connection...")
        if _engine:
            await _engine.dispose()
        logger.info("Database connection closed")


def get_engine() -> AsyncEngine:
    """Get the global async engine"""
    if _engine is None:
        raise RuntimeError("Database not initialized. Call lifespan() first.")
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get the global session factory"""
    if _session_factory is None:
        raise RuntimeError("Database not initialized. Call lifespan() first.")
    return _session_factory


async def get_db() -> AsyncIterator[AsyncSession]:
    """
    FastAPI dependency that yields an AsyncSession with explicit transaction boundaries.
    
    Usage:
        @app.get("/")
        async def endpoint(db: AsyncSession = Depends(get_db)):
            async with db.begin():
                # Your database operations here
                pass
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def health_check() -> bool:
    """Check database connectivity with real ping"""
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            return result.scalar() == 1
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return False
