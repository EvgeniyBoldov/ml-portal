"""
Cleanup tasks for retention policies.

Handles automatic cleanup of old audit logs, agent runs, etc.
"""
from __future__ import annotations
import logging
from datetime import datetime, timedelta

from celery import shared_task
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import os

from app.models.audit_log import AuditLog
from app.models.agent_run import AgentRun

logger = logging.getLogger(__name__)

# Retention periods (days)
AUDIT_LOG_RETENTION_DAYS = 7
AGENT_RUN_RETENTION_DAYS = 7


def get_async_session():
    """Create async session for Celery tasks."""
    db_url = os.getenv("ASYNC_DB_URL") or os.getenv("DATABASE_URL", "").replace(
        "postgresql://", "postgresql+asyncpg://"
    )
    engine = create_async_engine(db_url, echo=False)
    return sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@shared_task(
    name="app.workers.tasks_cleanup.cleanup_old_audit_logs",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def cleanup_old_audit_logs(self):
    """
    Delete audit logs older than retention period.
    
    Runs daily via Celery beat.
    """
    import asyncio
    
    async def _cleanup():
        AsyncSessionLocal = get_async_session()
        async with AsyncSessionLocal() as session:
            cutoff_date = datetime.utcnow() - timedelta(days=AUDIT_LOG_RETENTION_DAYS)
            
            result = await session.execute(
                delete(AuditLog).where(AuditLog.created_at < cutoff_date)
            )
            deleted_count = result.rowcount
            await session.commit()
            
            logger.info(f"Deleted {deleted_count} audit logs older than {cutoff_date}")
            return deleted_count
    
    try:
        return asyncio.run(_cleanup())
    except Exception as e:
        logger.error(f"Failed to cleanup audit logs: {e}", exc_info=True)
        raise self.retry(exc=e)


@shared_task(
    name="app.workers.tasks_cleanup.cleanup_old_agent_runs",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def cleanup_old_agent_runs(self):
    """
    Delete agent runs older than retention period.
    
    Runs daily via Celery beat.
    """
    import asyncio
    
    async def _cleanup():
        AsyncSessionLocal = get_async_session()
        async with AsyncSessionLocal() as session:
            cutoff_date = datetime.utcnow() - timedelta(days=AGENT_RUN_RETENTION_DAYS)
            
            # AgentRunStep will be cascade deleted
            result = await session.execute(
                delete(AgentRun).where(AgentRun.started_at < cutoff_date)
            )
            deleted_count = result.rowcount
            await session.commit()
            
            logger.info(f"Deleted {deleted_count} agent runs older than {cutoff_date}")
            return deleted_count
    
    try:
        return asyncio.run(_cleanup())
    except Exception as e:
        logger.error(f"Failed to cleanup agent runs: {e}", exc_info=True)
        raise self.retry(exc=e)


@shared_task(name="app.workers.tasks_cleanup.run_all_cleanup")
def run_all_cleanup():
    """
    Run all cleanup tasks.
    
    Can be triggered manually or scheduled via Celery beat.
    """
    results = {}
    
    try:
        results["audit_logs"] = cleanup_old_audit_logs.delay().get(timeout=300)
    except Exception as e:
        results["audit_logs"] = f"error: {e}"
    
    try:
        results["agent_runs"] = cleanup_old_agent_runs.delay().get(timeout=300)
    except Exception as e:
        results["agent_runs"] = f"error: {e}"
    
    logger.info(f"Cleanup completed: {results}")
    return results
