from __future__ import annotations
import os
import time
from app.core.logging import get_logger
from contextlib import asynccontextmanager
from typing import AsyncIterator
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import text
from app.core import startup
from app.core.config import get_settings
from app.core.di import cleanup_clients

logger = get_logger(__name__)

# Global state managed by lifespan
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None
_startup_ready: bool = False


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
    global _engine, _session_factory, _startup_ready

    try:
        _startup_ready = False
        _ensure_db_initialized()
        
        # Skip startup tasks in test mode (data already seeded via migrations)
        if os.getenv("SKIP_STARTUP_TASKS") != "true":
            await startup.run_all(_session_factory)
        
        _startup_ready = True

        yield
        
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise
    finally:
        _startup_ready = False
        logger.info("Closing database connection...")
        if _engine:
            await _engine.dispose()
        await cleanup_clients()
        logger.info("Database connection closed")


def _ensure_db_initialized() -> None:
    """Initialize engine/session factory lazily if needed."""
    global _engine, _session_factory
    if _engine is not None and _session_factory is not None:
        return

    logger.info("Initializing database connection...")
    _engine = create_async_engine(
        _db_url(),
        echo=False,
        pool_pre_ping=True,
        pool_recycle=300,
        pool_size=10,
        max_overflow=20,
    )
    _session_factory = async_sessionmaker(
        _engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    _install_slow_query_logging(_engine)
    logger.info("Database connection initialized successfully")


def _install_slow_query_logging(engine: AsyncEngine) -> None:
    settings = get_settings()
    if not settings.DB_SLOW_QUERY_LOG_ENABLED:
        return

    threshold_ms = int(max(settings.DB_SLOW_QUERY_THRESHOLD_MS, 0))
    text_max_len = int(max(settings.DB_SLOW_QUERY_TEXT_MAX_LEN, 80))

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany):  # type: ignore[no-untyped-def]
        conn.info.setdefault("query_start_time", []).append(time.perf_counter())

    @event.listens_for(engine.sync_engine, "after_cursor_execute")
    def _after_cursor_execute(conn, cursor, statement, parameters, context, executemany):  # type: ignore[no-untyped-def]
        started_stack = conn.info.get("query_start_time") or []
        if not started_stack:
            return
        started_at = started_stack.pop()
        elapsed_ms = (time.perf_counter() - started_at) * 1000.0
        if elapsed_ms < threshold_ms:
            return
        sql = " ".join(str(statement).split())
        if len(sql) > text_max_len:
            sql = f"{sql[:text_max_len]}..."
        logger.warning(
            "slow_query_detected",
            extra={
                "duration_ms": round(elapsed_ms, 2),
                "threshold_ms": threshold_ms,
                "statement": sql,
                "rowcount": getattr(cursor, "rowcount", None),
            },
        )


def get_engine() -> AsyncEngine:
    """Get the global async engine"""
    if _engine is None:
        _ensure_db_initialized()
    if _engine is None:
        raise RuntimeError("Database not initialized")
    return _engine


def is_startup_ready() -> bool:
    """True after startup tasks completed successfully and before shutdown."""
    return bool(_startup_ready)


def get_pool_stats() -> dict:
    """Best-effort SQLAlchemy pool stats for observability."""
    engine = get_engine()
    pool = getattr(engine.sync_engine, "pool", None)
    if pool is None:
        return {"pool_class": "unknown"}
    stats = {"pool_class": pool.__class__.__name__}
    for field_name in ("size", "checkedin", "checkedout", "overflow"):
        attr = getattr(pool, field_name, None)
        if callable(attr):
            try:
                stats[field_name] = int(attr())
            except Exception:
                pass
    return stats


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get the global session factory"""
    if _session_factory is None:
        _ensure_db_initialized()
    if _session_factory is None:
        raise RuntimeError("Database session factory is not initialized")
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
