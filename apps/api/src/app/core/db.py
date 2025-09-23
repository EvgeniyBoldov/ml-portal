from __future__ import annotations
from contextlib import asynccontextmanager, contextmanager
from typing import AsyncGenerator, Generator, Optional
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool
from .config import settings
from .logging import get_logger

logger = get_logger(__name__)

# Sync engine and session
engine = create_engine(
    settings.DB_URL,
    pool_pre_ping=True,
    future=True,
    pool_size=10,
    max_overflow=20,
    pool_recycle=3600,
    echo=False
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    future=True
)

# Async engine and session
async_engine = create_async_engine(
    settings.DB_URL.replace("postgresql://", "postgresql+asyncpg://"),
    pool_pre_ping=True,
    future=True,
    pool_size=10,
    max_overflow=20,
    pool_recycle=3600,
    echo=False
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    autoflush=False,
    autocommit=False,
    future=True,
    class_=AsyncSession
)

# Connection event listeners
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Set SQLite pragmas for better performance"""
    if "sqlite" in str(dbapi_connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

class DatabaseManager:
    """Database connection manager with both sync and async support"""
    
    def __init__(self):
        self._engine = engine
        self._async_engine = async_engine
        self._session_factory = SessionLocal
        self._async_session_factory = AsyncSessionLocal
    
    def get_session(self) -> Generator[Session, None, None]:
        """Get sync database session (FastAPI dependency)"""
        db = self._session_factory()
        try:
            yield db
            db.commit()
        except Exception as e:
            logger.error(f"Database session error: {e}")
            db.rollback()
            raise
        finally:
            db.close()
    
    async def get_async_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get async database session (FastAPI dependency)"""
        async with self._async_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception as e:
                logger.error(f"Async database session error: {e}")
                await session.rollback()
                raise
    
    @contextmanager
    def session_scope(self) -> Generator[Session, None, None]:
        """Provide a transactional scope around a series of operations (sync)"""
        db = self._session_factory()
        try:
            yield db
            db.commit()
        except Exception as e:
            logger.error(f"Database session scope error: {e}")
            db.rollback()
            raise
        finally:
            db.close()
    
    @asynccontextmanager
    async def async_session_scope(self) -> AsyncGenerator[AsyncSession, None]:
        """Provide a transactional scope around a series of operations (async)"""
        async with self._async_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception as e:
                logger.error(f"Async database session scope error: {e}")
                await session.rollback()
                raise
    
    def close_all(self) -> None:
        """Close all database connections"""
        try:
            self._engine.dispose()
            logger.info("Sync database engine disposed")
        except Exception as e:
            logger.error(f"Error disposing sync engine: {e}")
    
    async def close_async_all(self) -> None:
        """Close all async database connections"""
        try:
            await self._async_engine.dispose()
            logger.info("Async database engine disposed")
        except Exception as e:
            logger.error(f"Error disposing async engine: {e}")
    
    def health_check(self) -> bool:
        """Check database connection health"""
        try:
            with self._session_factory() as session:
                session.execute(text("SELECT 1"))
                return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False
    
    async def async_health_check(self) -> bool:
        """Check async database connection health"""
        try:
            async with self._async_session_factory() as session:
                await session.execute(text("SELECT 1"))
                return True
        except Exception as e:
            logger.error(f"Async database health check failed: {e}")
            return False

# Global database manager instance
db_manager = DatabaseManager()

# Convenience functions for backward compatibility
def get_session() -> Generator[Session, None, None]:
    """Get sync database session (FastAPI dependency)"""
    return db_manager.get_session()

async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Get async database session (FastAPI dependency)"""
    async for session in db_manager.get_async_session():
        yield session

@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Provide a transactional scope around a series of operations (sync)"""
    return db_manager.session_scope()

@asynccontextmanager
async def async_session_scope() -> AsyncGenerator[AsyncSession, None]:
    """Provide a transactional scope around a series of operations (async)"""
    return db_manager.async_session_scope()
