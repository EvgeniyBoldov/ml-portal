"""
Cleanup tasks for retention policies.

Handles automatic cleanup of audit logs and canonical runtime events.
"""
from __future__ import annotations
from app.core.logging import get_logger
from datetime import datetime, timedelta, timezone

from celery import shared_task
from sqlalchemy import delete, select, func, text

from app.models.audit_log import AuditLog
from app.models.runtime_observability import RuntimeExecutionEvent, RuntimeEventSequence
from app.models.chat import Chats
from app.models.sandbox import SandboxSession
from app.models.tenant import Tenants
from app.models.user import Users
from app.models.collection import Collection
from app.models.agent import Agent
from app.models.rbac import RbacRule
from app.services.lifecycle_admin_service import LifecycleAdminService
from app.services.chat_attachment_service import ChatAttachmentService
from app.services.chat_artifact_reference_service import ChatArtifactReferenceService
from app.services.sandbox_service import SandboxService
from app.workers.session_factory import get_worker_session

logger = get_logger(__name__)

# Retention periods (days)
AUDIT_LOG_RETENTION_DAYS = 7
RUNTIME_EVENT_RETENTION_DAYS = 7
DEFAULT_LIFECYCLE_RETENTION_DAYS = 14
DETACHED_CHAT_ATTACHMENT_RETENTION_HOURS = 24
ORPHAN_CHAT_ATTACHMENT_GRACE_MINUTES = 15


LIFECYCLE_MODELS = (
    ("tenant", Tenants),
    ("user", Users),
    ("collection", Collection),
    ("agent", Agent),
    ("rbac_rule", RbacRule),
    ("chat", Chats),
    ("sandbox_session", SandboxSession),
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
        async with get_worker_session() as session:
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
    name="app.workers.tasks_cleanup.cleanup_old_runtime_events",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def cleanup_old_runtime_events(self):
    """
    Delete canonical runtime journal events older than retention period.
    
    Runs daily via Celery beat.
    """
    import asyncio
    
    async def _cleanup():
        async with get_worker_session() as session:
            cutoff_date = datetime.utcnow() - timedelta(days=RUNTIME_EVENT_RETENTION_DAYS)
            result = await session.execute(
                delete(RuntimeExecutionEvent).where(RuntimeExecutionEvent.occurred_at < cutoff_date)
            )
            deleted_count = result.rowcount
            await session.execute(
                delete(RuntimeEventSequence).where(~RuntimeEventSequence.run_id.in_(
                    select(RuntimeExecutionEvent.run_id).distinct()
                ))
            )
            await session.commit()
            
            logger.info(f"Deleted {deleted_count} runtime events older than {cutoff_date}")
            return deleted_count
    
    try:
        return asyncio.run(_cleanup())
    except Exception as e:
        logger.error(f"Failed to cleanup runtime events: {e}", exc_info=True)
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
        async with get_worker_session() as session:
            cutoff_date = datetime.now(timezone.utc)
            result = await session.execute(
                select(SandboxSession.id).where(SandboxSession.expires_at < cutoff_date)
            )
            session_ids = list(result.scalars().all())
            deleted_count = 0
            svc = SandboxService(session)
            for session_id in session_ids:
                if await svc.delete_session(session_id):
                    deleted_count += 1
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
    name="app.workers.tasks_cleanup.cleanup_expired_detached_chat_attachments",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def cleanup_expired_detached_chat_attachments(self):
    """
    Delete detached chat attachments (chat_id is null) older than retention period.
    """
    import asyncio

    async def _cleanup():
        async with get_worker_session() as session:
            older_than = datetime.now(timezone.utc) - timedelta(hours=DETACHED_CHAT_ATTACHMENT_RETENTION_HOURS)
            deleted_count = await ChatAttachmentService(session).cleanup_expired_detached_attachments(
                older_than=older_than,
            )
            await session.commit()
            logger.info(
                "Deleted %s detached chat attachments older than %s",
                deleted_count,
                older_than.isoformat(),
            )
            return deleted_count

    try:
        return asyncio.run(_cleanup())
    except Exception as e:
        logger.error(f"Failed to cleanup detached chat attachments: {e}", exc_info=True)
        raise self.retry(exc=e)


@shared_task(
    name="app.workers.tasks_cleanup.cleanup_orphaned_chat_attachments",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def cleanup_orphaned_chat_attachments(self):
    """Remove chat-bound attachments that have no owning artifact reference."""
    import asyncio

    async def _cleanup():
        async with get_worker_session() as session:
            older_than = datetime.now(timezone.utc) - timedelta(
                minutes=ORPHAN_CHAT_ATTACHMENT_GRACE_MINUTES
            )
            service = ChatArtifactReferenceService(session)
            deleted_count = await service.cleanup_orphaned_attachments(older_than=older_than)
            await session.commit()
            logger.info(
                "Deleted %s orphaned chat attachments older than %s",
                deleted_count,
                older_than.isoformat(),
            )
            return deleted_count

    try:
        return asyncio.run(_cleanup())
    except Exception as e:
        logger.error("Failed to cleanup orphaned chat attachments: %s", e, exc_info=True)
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
        deleted_by_kind: dict[str, int] = {}
        async with get_worker_session() as session:
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
                        (model.deprecated_root_id.is_(None))
                        | (model.deprecated_root_id == model.id)
                    )
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
                        entity = await session.get(model, entity_id)
                        if entity is None:
                            continue
                        await LifecycleAdminService(session).hard_delete(
                            kind,
                            entity_id,
                            cascade=bool(getattr(entity, "delete_cascade", False)),
                        )
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
        results["runtime_events"] = cleanup_old_runtime_events.delay().get(timeout=300)
    except Exception as e:
        results["runtime_events"] = f"error: {e}"

    try:
        results["sandbox_sessions"] = cleanup_expired_sandbox_sessions.delay().get(timeout=300)
    except Exception as e:
        results["sandbox_sessions"] = f"error: {e}"

    try:
        results["detached_chat_attachments"] = cleanup_expired_detached_chat_attachments.delay().get(timeout=300)
    except Exception as e:
        results["detached_chat_attachments"] = f"error: {e}"

    try:
        results["orphaned_chat_attachments"] = cleanup_orphaned_chat_attachments.delay().get(timeout=300)
    except Exception as e:
        results["orphaned_chat_attachments"] = f"error: {e}"

    try:
        results["deprecated_entities"] = cleanup_deprecated_entities.delay().get(timeout=300)
    except Exception as e:
        results["deprecated_entities"] = f"error: {e}"
    
    logger.info(f"Cleanup completed: {results}")
    return results
