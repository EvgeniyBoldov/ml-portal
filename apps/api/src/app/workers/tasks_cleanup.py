"""
Cleanup tasks for retention policies.

Handles automatic cleanup of old audit logs, agent runs, etc.
"""
from __future__ import annotations
from app.core.logging import get_logger
from datetime import datetime, timedelta, timezone

from celery import shared_task
from sqlalchemy import delete, select, func, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import os

from app.models.audit_log import AuditLog
from app.models.agent_run import AgentRun
from app.models.sandbox import SandboxSession
from app.models.tenant import Tenants
from app.models.user import Users
from app.models.collection import Collection
from app.models.agent import Agent
from app.models.rbac import RbacRule
from app.services.lifecycle_admin_service import LifecycleAdminService

logger = get_logger(__name__)

# Retention periods (days)
AUDIT_LOG_RETENTION_DAYS = 7
AGENT_RUN_RETENTION_DAYS = 7
DEFAULT_LIFECYCLE_RETENTION_DAYS = 14


def get_async_session():
    """Create async session for Celery tasks."""
    db_url = os.getenv("ASYNC_DB_URL") or os.getenv("DATABASE_URL", "").replace(
        "postgresql://", "postgresql+asyncpg://"
    )
    engine = create_async_engine(db_url, echo=False)
    return sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


LIFECYCLE_MODELS = (
    ("tenant", Tenants),
    ("user", Users),
    ("collection", Collection),
    ("agent", Agent),
    ("rbac_rule", RbacRule),
)


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


@shared_task(
    name="app.workers.tasks_cleanup.cleanup_expired_sandbox_sessions",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def cleanup_expired_sandbox_sessions(self):
    """
    Delete sandbox sessions past TTL (expires_at), including all cascade-linked records.
    """
    import asyncio

    async def _cleanup():
        AsyncSessionLocal = get_async_session()
        async with AsyncSessionLocal() as session:
            cutoff_date = datetime.now(timezone.utc)
            result = await session.execute(
                delete(SandboxSession).where(SandboxSession.expires_at < cutoff_date)
            )
            deleted_count = result.rowcount
            await session.commit()
            logger.info(
                "Deleted %s expired sandbox sessions (expires_at < %s)",
                deleted_count,
                cutoff_date.isoformat(),
            )
            return deleted_count

    try:
        return asyncio.run(_cleanup())
    except Exception as e:
        logger.error(f"Failed to cleanup expired sandbox sessions: {e}", exc_info=True)
        raise self.retry(exc=e)


@shared_task(
    name="app.workers.tasks_cleanup.cleanup_deprecated_entities",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def cleanup_deprecated_entities(self):
    """
    Hard-delete entities in deprecated lifecycle state past retention TTL.
    """
    import asyncio

    async def _cleanup():
        AsyncSessionLocal = get_async_session()
        deleted_by_kind: dict[str, int] = {}
        async with AsyncSessionLocal() as session:
            now_expr = func.now()
            for kind, model in LIFECYCLE_MODELS:
                if kind == "tenant":
                    status_filter = model.is_platform_default.is_(False)
                else:
                    status_filter = text("TRUE")

                expired_ids_query = (
                    select(model.id)
                    .where(model.lifecycle_status == "deprecated")
                    .where(model.deprecated_at.is_not(None))
                    .where(
                        now_expr
                        >= model.deprecated_at
                        + text(
                            "make_interval(days => COALESCE(retention_days, :default_retention))"
                        )
                    )
                    .where(status_filter)
                    .params(default_retention=DEFAULT_LIFECYCLE_RETENTION_DAYS)
                    .limit(500)
                )

                expired_ids = list((await session.execute(expired_ids_query)).scalars().all())
                deleted_count = 0
                for entity_id in expired_ids:
                    try:
                        await LifecycleAdminService(session).hard_delete(kind, entity_id)
                        await session.commit()
                        deleted_count += 1
                    except ValueError as exc:
                        if str(exc) == "not_found":
                            await session.rollback()
                            continue
                        await session.rollback()
                        logger.warning(
                            "Deprecated GC skipped %s:%s due to value error: %s",
                            kind,
                            entity_id,
                            str(exc),
                        )
                    except Exception:
                        await session.rollback()
                        logger.exception(
                            "Deprecated GC failed for %s:%s",
                            kind,
                            entity_id,
                        )

                deleted_by_kind[kind] = deleted_count

            logger.info("Deprecated entities cleanup completed: %s", deleted_by_kind)
            return deleted_by_kind

    try:
        return asyncio.run(_cleanup())
    except Exception as e:
        logger.error(f"Failed to cleanup deprecated entities: {e}", exc_info=True)
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

    try:
        results["sandbox_sessions"] = cleanup_expired_sandbox_sessions.delay().get(timeout=300)
    except Exception as e:
        results["sandbox_sessions"] = f"error: {e}"

    try:
        results["deprecated_entities"] = cleanup_deprecated_entities.delay().get(timeout=300)
    except Exception as e:
        results["deprecated_entities"] = f"error: {e}"
    
    logger.info(f"Cleanup completed: {results}")
    return results
