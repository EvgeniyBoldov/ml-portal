"""Execute durable shadow invocations and recover undispatched work."""
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select, update
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


def _heartbeat_period() -> float:
    return _lease().total_seconds() / 3


async def _refresh_claim(invocation_id: UUID, claim_id: UUID) -> bool:
    """Refresh a live claim through its own short-lived database session."""
    async with get_worker_session() as session:
        result = await session.execute(update(ShadowInvocation).where(
            ShadowInvocation.id == invocation_id,
            ShadowInvocation.claim_id == claim_id,
            ShadowInvocation.status == "running",
        ).values(updated_at=func.now()))
        await session.commit()
        return bool(result.rowcount == 1)


async def _heartbeat(invocation_id: UUID, claim_id: UUID, stop: asyncio.Event) -> bool:
    """Return False when the current claim is no longer the row owner."""
    while True:
        try:
            await asyncio.wait_for(stop.wait(), timeout=_heartbeat_period())
            return True
        except TimeoutError:
            try:
                if not await _refresh_claim(invocation_id, claim_id):
                    return False
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("shadow_invocation_heartbeat_failed",
                                 extra={"invocation_id": str(invocation_id), "claim_id": str(claim_id)})
                # A transient heartbeat DB error is not evidence that the
                # claim was superseded. Retry on the next lease-derived tick;
                # terminal writes remain fenced by the claim ID.


async def _invoke_under_lease(invocation_id: UUID, claim_id: UUID,
                              invoke: Callable[[], Awaitable[Any]]) -> Any:
    """Cancel stale work when a fenced heartbeat proves the claim was lost."""
    stop = asyncio.Event()
    heartbeat_task = asyncio.create_task(_heartbeat(invocation_id, claim_id, stop))
    invocation_task = asyncio.create_task(invoke())
    try:
        done, _ = await asyncio.wait({heartbeat_task, invocation_task}, return_when=asyncio.FIRST_COMPLETED)
        if heartbeat_task in done and not heartbeat_task.result():
            invocation_task.cancel()
            await asyncio.gather(invocation_task, return_exceptions=True)
            raise RuntimeError("Shadow invocation claim was superseded")
        return await invocation_task
    except BaseException:
        if not invocation_task.done():
            invocation_task.cancel()
            await asyncio.gather(invocation_task, return_exceptions=True)
        raise
    finally:
        stop.set()
        if not heartbeat_task.done():
            await asyncio.gather(heartbeat_task, return_exceptions=True)


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
            async def invoke():
                return await ShadowAgentService(session, get_llm_client()).invoke(
                    payload, user_id=user_id, tenant_id=tenant_id, scopes=scopes, request_id=request_id)
            result = await _invoke_under_lease(UUID(invocation_id), claim, invoke)
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
