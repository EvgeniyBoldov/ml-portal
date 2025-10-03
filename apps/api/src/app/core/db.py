
from __future__ import annotations
import os
from typing import AsyncGenerator, Optional
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None

def _db_url() -> str:
    # Prefer async driver; fall back to env DB_URL if it already contains +asyncpg
    url = os.getenv("DB_URL") or "postgresql+asyncpg://ml_portal:ml_portal_password@postgres:5432/ml_portal"
    if "+asyncpg" not in url:
        # Try to coerce psycopg/psql URLs into asyncpg
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url

def get_engine() -> AsyncEngine:
    global _engine, _session_factory
    if _engine is None:
        _engine = create_async_engine(
            _db_url(),
            echo=False,
            pool_pre_ping=True,
            pool_recycle=300,
        )
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine

def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        get_engine()
    assert _session_factory is not None
    return _session_factory

async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an AsyncSession."""
    factory = get_session_factory()
    async with factory() as session:
        yield session

def health_check() -> bool:
    """Check database connectivity (synchronous version for health endpoints)."""
    try:
        # For now, just check if we can create an engine
        engine = get_engine()
        return engine is not None
    except Exception:
        return False
