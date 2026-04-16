"""
Session factory for Celery workers.

IMPORTANT: asyncio.run() creates a NEW event loop each time it's called.
AsyncEngine and its connection pool are bound to the event loop where they were created.
Therefore, we MUST create a fresh engine inside each asyncio.run() context.

This module provides a context manager that creates engine+session per task execution.
"""
from __future__ import annotations
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.core.config import get_settings


def _get_db_url() -> str:
    """Get database URL from settings or environment"""
    settings = get_settings()
    db_url = settings.ASYNC_DB_URL
    if not db_url:
        import os
        db_url = os.getenv("ASYNC_DB_URL")
        if not db_url:
            raise ValueError("ASYNC_DB_URL is not configured")
    return db_url


@asynccontextmanager
async def get_worker_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Create a fresh async session for Celery worker task.
    
    This creates a new engine bound to the CURRENT event loop (inside asyncio.run()),
    uses it for the session, and disposes it after the task completes.
    
    Usage in Celery task:
        async def _process():
            async with get_worker_session() as session:
                # use session here
                ...
        
        asyncio.run(_process())
    """
    db_url = _get_db_url()
    
    # Create engine bound to current event loop
    engine = create_async_engine(
        db_url,
        echo=False,
        pool_pre_ping=True,
        pool_recycle=300,
        pool_size=2,  # Small pool - one task at a time per worker
        max_overflow=3,
    )
    
    session_factory = async_sessionmaker(
        engine,
        expire_on_commit=False,
        class_=AsyncSession
    )
    
    try:
        async with session_factory() as session:
            yield session
    finally:
        await engine.dispose()
