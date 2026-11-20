"""
Transaction utilities for Celery workers

Provides consistent transaction management across all workers.
Workers should NEVER call session.commit() directly - use these helpers instead.
"""
from __future__ import annotations
from typing import TypeVar
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.logging import get_logger

logger = get_logger(__name__)

T = TypeVar('T')


@asynccontextmanager
async def worker_transaction(session: AsyncSession, task_name: str):
    """
    Context manager for worker transactions.
    
    Usage:
        async with worker_transaction(session, "extract_document"):
            # Do work
            # session.flush() is OK for intermediate operations
            # NO session.commit() needed - handled automatically
    
    Commits on success, rolls back on error.
    """
    try:
        logger.debug(f"[{task_name}] Transaction started")
        yield session
        await session.commit()
        logger.debug(f"[{task_name}] Transaction committed")
    except Exception as e:
        logger.error(f"[{task_name}] Transaction failed: {e}", exc_info=True)
        await session.rollback()
        raise
    finally:
        await session.close()


async def checkpoint_commit(session: AsyncSession, task_name: str, checkpoint: str):
    """
    Commit a checkpoint in long-running tasks.
    
    Use sparingly - only when you need to persist intermediate state
    that should survive even if later steps fail.
    
    Args:
        session: Database session
        task_name: Name of the task
        checkpoint: Description of checkpoint
    """
    await session.commit()
    logger.info(f"[{task_name}] Checkpoint committed: {checkpoint}")
