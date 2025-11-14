"""
Shared session factory for Celery workers (one engine per process)
"""
from __future__ import annotations
from typing import Optional
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncEngine, AsyncSession
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Global engine and session factory (initialized once per worker process)
_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker] = None


def _initialize_session_factory() -> None:
    """Initialize session factory - called on worker process start"""
    global _engine, _session_factory
    
    if _session_factory is not None and _engine is not None:
        return  # Already initialized
    
    settings = get_settings()
    logger.info("Initializing worker session factory (one per process)")
    
    # Get ASYNC_DB_URL from settings
    db_url = settings.ASYNC_DB_URL
    if not db_url:
        # Try to get from environment variable directly
        import os
        db_url = os.getenv("ASYNC_DB_URL")
        if not db_url:
            raise ValueError("ASYNC_DB_URL is not configured")
    
    _engine = create_async_engine(
        db_url,
        echo=False,
        pool_pre_ping=True,
        pool_recycle=300,
        pool_size=5,  # Smaller pool for workers
        max_overflow=10,
    )
    
    _session_factory = async_sessionmaker(
        _engine,
        expire_on_commit=False,
        class_=AsyncSession
    )
    
    logger.info(f"Worker session factory initialized with DB URL: {db_url.split('@')[-1] if '@' in db_url else '***'}")


def get_worker_session_factory() -> async_sessionmaker:
    """
    Get or create shared session factory for Celery worker.
    
    This creates a single engine per worker process, avoiding
    connection pool exhaustion from creating engines in each task.
    
    Note: In Celery with ForkPoolWorker, global variables may not persist
    across forks, so we always check if session_factory is None and reinitialize.
    """
    global _engine, _session_factory
    
    # Always check if None (important for fork workers)
    if _session_factory is None or _engine is None:
        logger.warning(f"Session factory is None before initialization. _session_factory={_session_factory}, _engine={_engine}")
        try:
            _initialize_session_factory()
            logger.info("Session factory reinitialized successfully")
        except Exception as e:
            logger.error(f"Failed to reinitialize session factory: {e}", exc_info=True)
            raise
    
    # Double check after initialization
    if _session_factory is None:
        logger.error("Session factory is still None after initialization attempt")
        raise RuntimeError("Failed to initialize worker session factory")
    
    logger.debug(f"Returning session factory: type={type(_session_factory)}")
    return _session_factory


async def dispose_worker_engine():
    """
    Dispose worker engine (call on worker shutdown).
    
    Typically called from worker signal handlers or cleanup hooks.
    """
    global _engine, _session_factory
    
    if _engine:
        logger.info("Disposing worker engine")
        await _engine.dispose()
        _engine = None
        _session_factory = None

