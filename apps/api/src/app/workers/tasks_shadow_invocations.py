"""Execute durable shadow invocations and recover undispatched work."""
import asyncio
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import or_, select
from app.celery_app import app as celery_app
from app.core.config import get_settings
from app.core.di import cleanup_clients, get_llm_client, reset_llm_client
from app.core.logging import get_logger
from app.models.shadow_invocation import ShadowInvocation
from app.models.user import Users
from app.repositories.api_tokens_repo import ApiTokensRepository
from app.schemas.shadow_agents import ShadowAgentRequest
from app.services.shadow_agent_service import ShadowAgentService
from app.workers.session_factory import get_worker_session

logger = get_logger(__name__)
# A worker lost mid-run can be retried after the lease; claim_id fences late writers.
def _lease() -> timedelta:
    return timedelta(seconds=get_settings().SHADOW_INVOCATION_LEASE_SECONDS)


async def _execute(invocation_id: str) -> None:
    async with get_worker_session() as session:
        row = await session.scalar(select(ShadowInvocation).where(
            ShadowInvocation.id == UUID(invocation_id)).with_for_update(skip_locked=True))
        if row is None or row.status not in {"queued", "running"}:
            return
        if row.status == "running" and row.updated_at > datetime.now(timezone.utc) - _lease():
            return
        claim = uuid4()
        row.status, row.claim_id = "running", claim
        payload = ShadowAgentRequest(agent=row.agent, data=row.data)
        user_id, tenant_id, scopes, request_id = row.user_id, row.tenant_id, row.scopes, row.request_id
        await session.commit()
        try:
            user = await session.get(Users, user_id)
            tenant_ids = await ApiTokensRepository(session).active_tenant_ids(user_id)
            if user is None or not user.is_enabled or str(tenant_id) not in tenant_ids:
                raise PermissionError("User or tenant membership is no longer active")
            reset_llm_client()
            result = await ShadowAgentService(session, get_llm_client()).invoke(
                payload, user_id=user_id, tenant_id=tenant_id, scopes=scopes, request_id=request_id)
            status, output, error = "completed", result.result, None
        except Exception:
            logger.exception("shadow_invocation_failed", extra={"invocation_id": invocation_id})
            await session.rollback()
            status, output, error = "failed", None, "Shadow agent execution failed"
        finally:
            try:
                await cleanup_clients()
            except Exception:
                logger.exception("shadow_invocation_client_cleanup_failed", extra={"invocation_id": invocation_id})
        row = await session.scalar(select(ShadowInvocation).where(
            ShadowInvocation.id == UUID(invocation_id)).with_for_update().execution_options(populate_existing=True))
        if row is not None and row.status == "running" and row.claim_id == claim:
            row.status, row.result, row.error = status, output, error
            await session.commit()


@celery_app.task(name="app.workers.tasks_shadow_invocations.execute_shadow_invocation")
def execute_shadow_invocation(invocation_id: str) -> None:
    asyncio.run(_execute(invocation_id))


async def _pending() -> list[str]:
    async with get_worker_session() as session:
        rows = await session.scalars(select(ShadowInvocation.id).where(or_(
            ShadowInvocation.status == "queued",
            (ShadowInvocation.status == "running") & (ShadowInvocation.updated_at < datetime.now(timezone.utc) - _lease()),
        )).order_by(ShadowInvocation.created_at).limit(100))
        return [str(value) for value in rows]


@celery_app.task(name="app.workers.tasks_shadow_invocations.dispatch_shadow_invocations")
def dispatch_shadow_invocations() -> None:
    for invocation_id in asyncio.run(_pending()):
        execute_shadow_invocation.delay(invocation_id)
