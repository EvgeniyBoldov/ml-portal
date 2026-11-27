"""Durable chat run dispatcher and fenced segment executor."""
from __future__ import annotations

import asyncio
import logging
import socket
from uuid import UUID, uuid4

from app.celery_app import app as celery_app
from app.core.config import get_settings
from app.core.db import dispose_db_engine
from app.core.di import cleanup_clients, get_llm_client, reset_llm_client
from app.core.redis import dispose_redis, get_redis
from app.services.durable_runtime_execution import execute_claimed_segment
from app.services.durable_runtime_service import DurableRuntimeService
from app.services.tool_result_store import dispose_tool_results_engine
from app.workers.session_factory import get_worker_session

logger = logging.getLogger(__name__)


def _lease_seconds() -> int:
    return int(getattr(get_settings(), "DURABLE_RUNTIME_LEASE_SECONDS", 900))


async def _heartbeat(segment_id: UUID, claim_id: UUID, stop: asyncio.Event) -> bool:
    """Keep only the current fenced claim alive; False means it was superseded."""
    interval = max(5, _lease_seconds() // 3)
    while True:
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
            return True
        except TimeoutError:
            try:
                async with get_worker_session() as session:
                    service = DurableRuntimeService(session)
                    claim = await service.get_claim(segment_id, claim_id)
                    if claim is None or not await service.heartbeat(claim, lease_seconds=_lease_seconds()):
                        await session.rollback()
                        return False
                    await session.commit()
            except asyncio.CancelledError:
                raise
            except Exception:
                # A transient DB error is not proof that the claim was lost.
                logger.exception("durable_runtime_heartbeat_failed", extra={"segment_id": str(segment_id)})


async def _execute(segment_id: UUID) -> None:
    async with get_worker_session() as session:
        claim = await DurableRuntimeService(session).claim_segment(
            segment_id,
            worker_id=f"{socket.gethostname()}:{uuid4()}",
            lease_seconds=_lease_seconds(),
        )
        if claim is None:
            # claim_segment may persist terminal failure after its retry cap.
            await session.commit()
            return
        claim_id = claim.claim_id
        await session.commit()

        stop = asyncio.Event()
        heartbeat = asyncio.create_task(_heartbeat(segment_id, claim_id, stop))
        work = asyncio.create_task(execute_claimed_segment(
            claim,
            session=session,
            llm_client=get_llm_client(),
            redis_client=get_redis(),
        ))
        try:
            done, _ = await asyncio.wait({heartbeat, work}, return_when=asyncio.FIRST_COMPLETED)
            if heartbeat in done and heartbeat.result() is False:
                work.cancel()
                await asyncio.gather(work, return_exceptions=True)
                return
            await work
        except asyncio.CancelledError:
            if not work.done():
                work.cancel()
                await asyncio.gather(work, return_exceptions=True)
            raise
        except Exception:
            # Leave the fenced segment recoverable by lease expiry. Execution
            # itself classifies and persists durable failures at safe boundaries.
            logger.exception("durable_runtime_segment_execution_failed", extra={"segment_id": str(segment_id)})
            await session.rollback()
        finally:
            stop.set()
            if not heartbeat.done():
                heartbeat.cancel()
            await asyncio.gather(heartbeat, return_exceptions=True)
            try:
                await cleanup_clients()
            except Exception:
                logger.exception("durable_runtime_client_cleanup_failed")


async def _run_isolated(segment_id: str) -> None:
    reset_llm_client()
    try:
        await _execute(UUID(segment_id))
    finally:
        await dispose_redis()
        await dispose_tool_results_engine()
        await dispose_db_engine()


@celery_app.task(name="app.workers.tasks_durable_runtime.execute_durable_runtime_segment")
def execute_durable_runtime_segment(segment_id: str) -> None:
    asyncio.run(_run_isolated(segment_id))


async def _dispatch_batch(limit: int = 25) -> int:
    sent = 0
    async with get_worker_session() as session:
        service = DurableRuntimeService(session)
        await service.accept_due_timers(limit=limit)
        ready_ids = await service.list_ready_segment_ids(limit=limit)
        await session.commit()
    for segment_id in ready_ids:
        execute_durable_runtime_segment.delay(str(segment_id))
        sent += 1
    return sent


@celery_app.task(name="app.workers.tasks_durable_runtime.dispatch_durable_runtime")
def dispatch_durable_runtime() -> int:
    async def run_and_dispose() -> int:
        try:
            return await _dispatch_batch()
        finally:
            await dispose_tool_results_engine()
            await dispose_db_engine()
    return asyncio.run(run_and_dispose())
