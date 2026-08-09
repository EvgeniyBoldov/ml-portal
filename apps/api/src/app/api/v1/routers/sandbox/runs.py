"""Sandbox runs — list, detail, execute (SSE), confirm."""
import asyncio
import json
import uuid
from typing import Any, AsyncGenerator, AsyncIterator, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, get_current_user_sse, require_admin
from app.agents import ToolContext
from app.agents.runtime_sandbox_resolver import RuntimeSandboxResolver
from app.core.db import get_session_factory
from app.runtime import OrchestrationPhase, PipelineRequest, RuntimeEvent, RuntimeEventType, RuntimePipeline
from app.runtime.contracts import ExecutionMode
from app.core.di import get_llm_client
from app.core.http.clients import LLMClientProtocol
from app.core.logging import get_logger
from app.core.security import UserCtx
from app.models.chat import Chats
from app.models.sandbox import SandboxBranch, SandboxOverrideSnapshot
from app.models.agent import Agent
from app.models.agent_version import AgentVersion
from app.models.tool import Tool
from app.models.tool_release import ToolRelease
from app.models.collection import Collection
from app.models.tool_instance import ToolInstance
from app.schemas.chats import ChatAttachmentUploadResponse
from app.schemas.sandbox import (
    SandboxConfirmAction,
    SandboxRunCreate,
    SandboxRunListItem,
    SandboxRunDetailResponse,
)
from app.schemas.runtime_events import RuntimeJournalEventResponse
from app.services.chat_attachment_service import ChatAttachmentService, ChatAttachmentNotFoundError
from app.services.chat_visibility import make_sandbox_upload_chat_name
from app.services.sandbox_service import SandboxService
from app.services.runtime_event_journal_service import RuntimeEventJournalService
from app.services.runtime_hitl_protocol_service import RuntimeHitlProtocolService
from app.services.chat_router_event_mapper import build_resume_content
from app.services.runtime_terminal_status import planner_terminal_from_event
from app.services.runtime_event_logger import RuntimeEventJournalFactory, RuntimeLogContext, RuntimeLoggingLevel
from app.services.runtime_tail_event_bus import RuntimeTailSubscriber

from .helpers import check_session_owner, tenant_uuid, user_uuid

logger = get_logger(__name__)

router = APIRouter()

_JOURNAL_WIRE_FIELDS = {
    "type", "run_id", "event_id", "sequence", "occurred_at", "entity_type",
    "entity_id", "parent_entity_type", "parent_entity_id", "caused_by_event_id",
    "duration_ms",
}


def _format_sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"


def _journal_payload(*, event_id: object, run_id: object, sequence: object, event_type: object,
                     occurred_at: object, entity_type: object = None, entity_id: object = None,
                     parent_entity_type: object = None, parent_entity_id: object = None,
                     caused_by_event_id: object = None, duration_ms: object = None,
                     payload: object = None) -> dict:
    event = RuntimeJournalEventResponse.model_validate({
        "id": event_id, "run_id": run_id, "sequence": sequence, "event_type": event_type,
        "occurred_at": occurred_at, "entity_type": entity_type, "entity_id": entity_id,
        "parent_entity_type": parent_entity_type, "parent_entity_id": parent_entity_id,
        "caused_by_event_id": caused_by_event_id, "duration_ms": duration_ms,
        "payload": payload if isinstance(payload, dict) else {},
    })
    return event.model_dump(mode="json")


def _journal_from_row(row: object) -> dict:
    return _journal_payload(
        event_id=getattr(row, "id"), run_id=getattr(row, "run_id"), sequence=getattr(row, "sequence"),
        event_type=getattr(row, "event_type"), occurred_at=getattr(row, "occurred_at"),
        entity_type=getattr(row, "entity_type"), entity_id=getattr(row, "entity_id"),
        parent_entity_type=getattr(row, "parent_entity_type"), parent_entity_id=getattr(row, "parent_entity_id"),
        caused_by_event_id=getattr(row, "caused_by_event_id"), duration_ms=getattr(row, "duration_ms"),
        payload=getattr(row, "payload"),
    )


def _journal_from_tail(message: dict) -> dict | None:
    if not all(key in message for key in ("event_id", "run_id", "sequence", "type", "occurred_at")):
        return None
    return _journal_payload(
        event_id=message["event_id"], run_id=message["run_id"], sequence=message["sequence"],
        event_type=message["type"], occurred_at=message["occurred_at"],
        entity_type=message.get("entity_type"), entity_id=message.get("entity_id"),
        parent_entity_type=message.get("parent_entity_type"), parent_entity_id=message.get("parent_entity_id"),
        caused_by_event_id=message.get("caused_by_event_id"), duration_ms=message.get("duration_ms"),
        payload={key: value for key, value in message.items() if key not in _JOURNAL_WIRE_FIELDS},
    )


def _tail_sse_frame(message: dict) -> str | None:
    if message.get("type") == "runtime_progress":
        return _format_sse("progress", {
            "run_id": str(message.get("run_id") or ""),
            "phase": str(message.get("phase") or ""),
            "kind": str(message.get("kind") or ""),
            "description": str(message.get("description") or ""),
            "status": message.get("status"),
        })
    journal = _journal_from_tail(message)
    return _format_sse("journal", journal) if journal is not None else None


async def _merge_pipeline_and_tail(
    pipeline_events: AsyncIterator[Any],
    tail_queue: asyncio.Queue[dict],
) -> AsyncGenerator[tuple[str, Any], None]:
    """Yield journal events while the pipeline is awaiting an LLM, tool, or worker."""
    iterator = pipeline_events.__aiter__()
    pipeline_task: asyncio.Task[Any] | None = asyncio.create_task(anext(iterator))
    tail_task: asyncio.Task[dict] | None = asyncio.create_task(tail_queue.get())
    try:
        while pipeline_task is not None:
            pending = {pipeline_task}
            if tail_task is not None:
                pending.add(tail_task)
            done, _ = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            if tail_task is not None and tail_task in done:
                yield "tail", tail_task.result()
                tail_task = asyncio.create_task(tail_queue.get())
            if pipeline_task in done:
                try:
                    event = pipeline_task.result()
                except StopAsyncIteration:
                    pipeline_task = None
                    continue
                yield "pipeline", event
                pipeline_task = asyncio.create_task(anext(iterator))
    finally:
        for task in (pipeline_task, tail_task):
            if task is not None and not task.done():
                task.cancel()
        await asyncio.gather(*(task for task in (pipeline_task, tail_task) if task is not None), return_exceptions=True)

def _extract_attachment_meta_from_events(events: list) -> list[dict]:
    for event in reversed(events):
        payload = getattr(event, "payload", None)
        if not isinstance(payload, dict):
            continue
        attachments = payload.get("attachments")
        if isinstance(attachments, list):
            return [item for item in attachments if isinstance(item, dict)]
    return []




async def _ensure_sandbox_upload_chat(
    db: AsyncSession,
    *,
    owner_id: uuid.UUID,
    session_id: uuid.UUID,
) -> uuid.UUID:
    name = make_sandbox_upload_chat_name(session_id)
    row = await db.scalar(
        select(Chats).where(
            and_(
                Chats.owner_id == owner_id,
                Chats.name == name,
            )
        )
    )
    if row:
        return row.id
    row = Chats(
        owner_id=owner_id,
        name=name,
        tags=["sandbox", "system", f"sandbox_session:{session_id}"],
    )
    db.add(row)
    await db.flush()
    return row.id


@router.get(
    "/sessions/{session_id}/runs",
    response_model=list[SandboxRunListItem],
)
async def list_runs(
    session_id: uuid.UUID,
    branch_id: Optional[uuid.UUID] = Query(default=None),
    db: AsyncSession = Depends(db_session),
    user: UserCtx = Depends(require_admin),
):
    """List all runs for a session."""
    svc = SandboxService(db)
    runs_with_counts = await svc.list_runs_with_event_count(session_id, branch_id)
    return [
        SandboxRunListItem(
            id=r.id,
            branch_id=r.branch_id,
            snapshot_id=r.snapshot_id,
            parent_run_id=r.parent_run_id,
            request_text=r.request_text,
            status=r.status,
            started_at=r.started_at,
            finished_at=r.finished_at,
            steps_count=events_count,
        )
        for r, events_count in runs_with_counts
    ]


@router.get(
    "/sessions/{session_id}/runs/{run_id}",
    response_model=SandboxRunDetailResponse,
)
async def get_run_detail(
    session_id: uuid.UUID,
    run_id: uuid.UUID,
    db: AsyncSession = Depends(db_session),
    user: UserCtx = Depends(require_admin),
):
    """Get run detail with the canonical runtime journal."""
    svc = SandboxService(db)
    run = await svc.get_run_detail(run_id)
    if not run or run.session_id != session_id:
        raise HTTPException(status_code=404, detail="Run not found")

    events = await RuntimeEventJournalService(db).list_run_events(run.id)

    return SandboxRunDetailResponse(
        id=run.id,
        branch_id=run.branch_id,
        snapshot_id=run.snapshot_id,
        parent_run_id=run.parent_run_id,
        request_text=run.request_text,
        status=run.status,
        effective_config=run.effective_config,
        error=run.error,
        started_at=run.started_at,
        finished_at=run.finished_at,
        events=[RuntimeJournalEventResponse.model_validate(_journal_from_row(event)) for event in events],
    )


@router.post("/sessions/{session_id}/run")
async def run_sandbox(
    session_id: uuid.UUID,
    data: SandboxRunCreate,
    db: AsyncSession = Depends(db_session),
    user: UserCtx = Depends(require_admin),
    llm_client: LLMClientProtocol = Depends(get_llm_client),
):
    """Execute agent in sandbox session via RuntimePipeline. Returns SSE stream."""
    svc = SandboxService(db)
    await check_session_owner(svc, session_id, user)

    session_obj = await svc.get_session(session_id)
    if not session_obj or session_obj.status != "active":
        raise HTTPException(status_code=400, detail="Session is not active")

    # Cleanup zombie runs
    stale_count = await svc.fail_stale_runs(session_id)
    if stale_count:
        logger.info(f"[Sandbox] Cleaned up {stale_count} stale runs for session {session_id}")
        await db.commit()

    # Resolve branch
    branch_id = data.branch_id
    if branch_id is None:
        default_branch = await svc.ensure_default_branch(session_id, user_uuid(user))
        branch_id = default_branch.id

    branch = await svc.get_branch(branch_id)
    if not branch or branch.session_id != session_id:
        raise HTTPException(status_code=404, detail="Branch not found")

    sandbox_confirmed_fingerprints = list(data.confirmed_fingerprints or [])
    if data.parent_run_id and not sandbox_confirmed_fingerprints:
        parent_run = await svc.get_run(data.parent_run_id)
        if parent_run and parent_run.session_id == session_id:
            sandbox_confirmed_fingerprints = RuntimeHitlProtocolService.extract_confirmed_fingerprints(
                parent_run.paused_action if isinstance(parent_run.paused_action, dict) else None,
                parent_run.paused_context if isinstance(parent_run.paused_context, dict) else None,
            )

    # Create snapshot + run record through one sandbox service contract
    run_prep = await svc.prepare_run(
        session_id=session_id,
        branch_id=branch_id,
        user_id=user_uuid(user),
        request_text=data.request_text,
        input_artifact_ids=[str(item) for item in (data.artifact_ids or [])],
        parent_run_id=data.parent_run_id,
    )
    await db.commit()
    await db.refresh(run_prep.run)

    snapshot = run_prep.snapshot
    effective_config = run_prep.effective_config
    sandbox_run = run_prep.run
    run_id = sandbox_run.id
    u_uuid = user_uuid(user)
    t_uuid = await tenant_uuid(db, user)
    sandbox_chat_id = await _ensure_sandbox_upload_chat(
        db,
        owner_id=u_uuid,
        session_id=session_id,
    )
    # The SSE generator uses a separate database session.  Commit the hidden
    # sandbox chat before it can register generated artifacts against its FK.
    await db.commit()
    attachment_service = ChatAttachmentService(db)
    attachment_contexts = []

    if data.artifact_ids:
        try:
            attachment_contexts = await attachment_service.build_runtime_artifact_contexts(
                artifact_ids=[str(item) for item in data.artifact_ids],
                chat_id=str(sandbox_chat_id),
                owner_id=str(u_uuid),
            )
        except ChatAttachmentNotFoundError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    # Resolve overrides
    sandbox_resolver = RuntimeSandboxResolver()
    overrides_summary = sandbox_resolver.describe_sandbox_overrides(effective_config)
    if overrides_summary.get("total"):
        logger.info(
            "[Sandbox] Active overrides: %s",
            json.dumps(overrides_summary, ensure_ascii=False, default=str)[:500],
        )

    # Agent slug override from tenant settings
    agent_slug: Optional[str] = sandbox_resolver.sandbox_agent_slug(effective_config)
    agent_version_id = sandbox_resolver.sandbox_agent_version_id(effective_config)

    snapshot_id = snapshot.id

    async def event_stream() -> AsyncGenerator[str, None]:
        session_factory = get_session_factory()
        async with session_factory() as stream_db:
            runtime_sandbox_resolver = RuntimeSandboxResolver(session=stream_db)
            resolved_agent_state = None
            if agent_slug or agent_version_id:
                try:
                    resolved_agent_state = await runtime_sandbox_resolver.resolve_sandbox_agent(
                        agent_slug=agent_slug,
                        tenant_id=t_uuid,
                        agent_version_id=agent_version_id,
                    )
                except Exception as agent_err:
                    await RuntimeEventJournalFactory.create(
                        context=RuntimeLogContext(run_id=run_id, level=RuntimeLoggingLevel.FULL,
                            origin="sandbox", tenant_id=t_uuid, user_id=u_uuid,
                            stream_logs=True, stream_progress=True),
                        session_factory=session_factory,
                    ).error(agent_err, payload={"stage": "sandbox_agent_resolve", "agent_slug": agent_slug})
                    try:
                        svc_err = SandboxService(stream_db)
                        await svc_err.finish_run(run_id, "failed", str(agent_err))
                        await stream_db.commit()
                    except Exception:
                        pass
                    yield _format_sse("error", {"run_id": str(run_id), "error": "Sandbox agent resolution failed"})
                    yield _format_sse("done", {"run_id": str(run_id)})
                    return

            if resolved_agent_state is not None:
                sandbox_overrides = runtime_sandbox_resolver.sandbox_runtime_overrides(
                    effective_config,
                    agent_version=resolved_agent_state.agent_version,
                )
            else:
                sandbox_overrides = runtime_sandbox_resolver.sandbox_runtime_overrides(
                    effective_config,
                    agent_version=None,
                )
            sandbox_overrides["logging_level"] = "full"
            # In sandbox we keep memory finalize inline so fact/summary helper
            # events are visible in the same run trace.
            sandbox_overrides["memory_inline"] = bool(sandbox_overrides.get("memory_inline", False))
            sandbox_overrides["sandbox_run_id"] = str(run_id)
            sandbox_overrides["sandbox_branch_id"] = str(branch_id)
            sandbox_overrides["sandbox_session_id"] = str(session_id)
            logger.info("[Sandbox] Runtime logging level forced to full")

            tool_ctx = ToolContext(
                tenant_id=t_uuid,
                user_id=u_uuid,
                chat_id=str(sandbox_chat_id),
                request_id=str(uuid.uuid4()),
                extra={"sandbox_confirmed_fingerprints": sandbox_confirmed_fingerprints},
            )
            runtime_deps = tool_ctx.get_runtime_deps()
            runtime_deps.session_factory = session_factory
            runtime_deps.sandbox_overrides = sandbox_overrides
            tool_ctx.set_runtime_deps(runtime_deps)

            pipeline = RuntimePipeline(
                session=stream_db,
                llm_client=llm_client,
            )

            messages = [{"role": "user", "content": data.request_text}]

            pipeline_request = PipelineRequest(
                request_text=data.request_text,
                runtime_run_id=str(run_id),
                chat_id=str(sandbox_chat_id),
                user_id=str(u_uuid),
                tenant_id=str(t_uuid),
                messages=messages,
                attachments=attachment_contexts,
                agent_slug=agent_slug,
                agent_version_id=str(agent_version_id) if agent_version_id else None,
                sandbox_overrides=sandbox_overrides,
                execution_mode=ExecutionMode(data.execution_mode or ExecutionMode.NORMAL.value),
                await_background_tail=False,
            )
            final_status = "completed"
            final_error: Optional[str] = None
            tail_pending: set[str] = set()
            tail_finished_early: set[str] = set()
            emitted_event_ids: set[str] = set()
            tail_subscriber = RuntimeTailSubscriber(stream_key=str(run_id))
            tail_queue: asyncio.Queue[dict] = asyncio.Queue()
            tail_listener_task: Optional[asyncio.Task] = None

            async def _handle_tail_event(message: dict) -> tuple[str, dict]:
                evt_type = str(message.get("type") or "status")
                yield_payload = dict(message)
                if evt_type == "status" and str(yield_payload.get("stage")) == "tail_finished":
                    tail_id = str(yield_payload.get("tail_id") or "").strip()
                    if tail_id and tail_id in tail_pending:
                        tail_pending.discard(tail_id)
                    elif tail_id:
                        tail_finished_early.add(tail_id)
                return evt_type, yield_payload

            async def _drain_tail_events(max_items: int = 100) -> list[tuple[str, dict]]:
                drained = 0
                out: list[tuple[str, dict]] = []
                while drained < max_items:
                    try:
                        message = tail_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                    out.append(await _handle_tail_event(message))
                    drained += 1
                return out

            async def _journal_fallback() -> list[dict]:
                rows = await RuntimeEventJournalService(stream_db).list_run_events(run_id)
                payloads: list[dict] = []
                for row in rows:
                    event_id = str(row.id)
                    if event_id in emitted_event_ids:
                        continue
                    emitted_event_ids.add(event_id)
                    payloads.append(_journal_from_row(row))
                return payloads

            try:
                await tail_subscriber.subscribe()

                yield _format_sse("run_started", {"run_id": str(run_id)})

                # Confirm the HTTP/SSE connection immediately.  Runtime work
                # can spend several seconds inside an LLM/tool call before the
                # pipeline emits its first high-level event.
                async def _tail_listener() -> None:
                    async for message in tail_subscriber.listen():
                        await tail_queue.put(message)

                tail_listener_task = asyncio.create_task(_tail_listener())

                async for source, item in _merge_pipeline_and_tail(pipeline.execute(pipeline_request, tool_ctx), tail_queue):
                    if source == "tail":
                        _evt_type, evt_payload = await _handle_tail_event(item)
                        if evt_payload.get("event_id"):
                            emitted_event_ids.add(str(evt_payload["event_id"]))
                        frame = _tail_sse_frame(evt_payload)
                        if frame is not None:
                            yield frame
                        continue
                    event = item
                    if event.type == RuntimeEventType.STOP:
                        paused_payload = RuntimeHitlProtocolService.build_paused_from_stop(dict(event.data or {}))
                        final_status = str(paused_payload["reason"])
                        final_error = None
                        svc_pause = SandboxService(stream_db)
                        await svc_pause.pause_run(
                            run_id=run_id,
                            status=paused_payload["reason"],
                            paused_action=paused_payload["action"],
                            paused_context=paused_payload["context"],
                        )
                        await stream_db.commit()
                        pause_event = {
                            "reason": paused_payload["reason"],
                            "action": paused_payload["action"],
                            "context": paused_payload["context"],
                            "contract_version": paused_payload["contract_version"],
                            "run_id": str(run_id),
                        }
                        yield _format_sse("pause", pause_event)
                    elif event.type == RuntimeEventType.DELTA:
                        content = event.data.get("content")
                        if isinstance(content, str) and content:
                            yield _format_sse("delta", {"run_id": str(run_id), "content": content})
                    elif event.type == RuntimeEventType.FINAL:
                        if not str(final_status).startswith("waiting_"):
                            final_status = "completed"
                            final_error = None
                            yield _format_sse("final", {
                                "run_id": str(run_id),
                                "content": str(event.data.get("content") or ""),
                                "sources": event.data.get("sources") or [],
                                "attachments": event.data.get("attachments") or [],
                            })
                    else:
                        terminal = planner_terminal_from_event(event)
                        if terminal is not None:
                            final_status = terminal[0].value
                            final_error = terminal[1]
                    if event.type == RuntimeEventType.STATUS and str(event.data.get("stage")) == "memory_write_dispatched":
                        tail_id = str(event.data.get("tail_id") or "").strip()
                        if tail_id:
                            if tail_id in tail_finished_early:
                                tail_finished_early.discard(tail_id)
                            else:
                                tail_pending.add(tail_id)

                if not str(final_status).startswith("waiting_"):
                    svc_final = SandboxService(stream_db)
                    await svc_final.finish_run(run_id, final_status, final_error)
                    await stream_db.commit()

                # Redis pub/sub is best effort.  Flush anything persisted while
                # the pipeline was running before closing the SSE response.
                for fallback in await _journal_fallback():
                    yield _format_sse("journal", fallback)

            except asyncio.CancelledError:
                # The SSE client may disappear because the user pressed Stop,
                # navigated away, or refreshed the page.  CancelledError does
                # not inherit from Exception, so it must close the sandbox
                # lifecycle explicitly before propagating cancellation.
                try:
                    current_run = await SandboxService(stream_db).get_run(run_id)
                    was_running = current_run is not None and current_run.status == "running"
                    if was_running:
                        await SandboxService(stream_db).finish_run(
                            run_id,
                            "cancelled",
                            "Sandbox stream cancelled",
                        )
                        await stream_db.commit()
                    if was_running:
                        cancel_logger = RuntimeEventJournalFactory.create(
                            context=RuntimeLogContext(
                                run_id=run_id,
                                level=RuntimeLoggingLevel.FULL,
                                origin="sandbox",
                                tenant_id=t_uuid,
                                user_id=u_uuid,
                                stream_logs=True,
                                stream_progress=True,
                            ),
                            session_factory=session_factory,
                        )
                        await cancel_logger.emit(
                            RuntimeEvent.run_end(run_id=str(run_id), status="cancelled"),
                            phase=OrchestrationPhase.PIPELINE,
                        )
                except Exception:
                    logger.exception("Failed to persist cancelled sandbox run run_id=%s", run_id)
                raise
            except Exception as e:
                await RuntimeEventJournalFactory.create(
                    context=RuntimeLogContext(run_id=run_id, level=RuntimeLoggingLevel.FULL,
                        origin="sandbox", tenant_id=t_uuid, user_id=u_uuid,
                        stream_logs=True, stream_progress=True),
                    session_factory=session_factory,
                ).error(e, payload={"stage": "sandbox_stream"})
                yield _format_sse("error", {"run_id": str(run_id), "error": "Sandbox execution failed"})
                try:
                    svc_err = SandboxService(stream_db)
                    await svc_err.finish_run(run_id, "failed", str(e))
                    await stream_db.commit()
                except Exception:
                    pass
            finally:
                if tail_listener_task is not None:
                    tail_listener_task.cancel()
                    try:
                        await tail_listener_task
                    except BaseException:
                        pass
                await tail_subscriber.unsubscribe()
                yield _format_sse("done", {"run_id": str(run_id)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/sessions/{session_id}/uploads", response_model=ChatAttachmentUploadResponse)
async def upload_sandbox_attachment(
    session_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(db_session),
    user: UserCtx = Depends(require_admin),
):
    if not file:
        raise HTTPException(status_code=400, detail="File is required")
    svc = SandboxService(db)
    await check_session_owner(svc, session_id, user)
    session_obj = await svc.get_session(session_id)
    if not session_obj or session_obj.status != "active":
        raise HTTPException(status_code=400, detail="Session is not active")

    u_uuid = user_uuid(user)
    chat_id = await _ensure_sandbox_upload_chat(
        db,
        owner_id=u_uuid,
        session_id=session_id,
    )
    attachment_service = ChatAttachmentService(db)
    try:
        uploaded = await attachment_service.upload_attachment(
            chat_id=str(chat_id),
            owner_id=str(u_uuid),
            file=file,
        )
        await db.commit()
        return ChatAttachmentUploadResponse(**uploaded)
    except UploadValidationError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        await db.rollback()
        raise


@router.post("/sessions/{session_id}/runs/{run_id}/confirm")
async def confirm_run_action(
    session_id: uuid.UUID,
    run_id: uuid.UUID,
    data: SandboxConfirmAction,
    db: AsyncSession = Depends(db_session),
    user: UserCtx = Depends(require_admin),
):
    """Confirm or reject a pending write action for a paused run. Owner only."""
    svc = SandboxService(db)
    await check_session_owner(svc, session_id, user)

    run = await svc.get_run(run_id)
    if not run or run.session_id != session_id:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.status != "waiting_confirmation":
        raise HTTPException(status_code=400, detail="Run is not waiting for confirmation")

    if data.confirmed:
        confirmed_fingerprints = RuntimeHitlProtocolService.extract_confirmed_fingerprints(
            run.paused_action if isinstance(run.paused_action, dict) else None,
            run.paused_context if isinstance(run.paused_context, dict) else None,
        )
        await svc.finish_run(run_id, "confirmed", None)
        await db.commit()
        return {
            "status": "confirmed",
            "run_id": str(run_id),
            "resume": {
                "parent_run_id": str(run_id),
                "confirmed_fingerprints": confirmed_fingerprints,
            },
        }
    else:
        await svc.finish_run(run_id, "completed", "Write action rejected by user")
        await db.commit()
        return {"status": "rejected", "run_id": str(run_id)}


@router.post("/sessions/{session_id}/runs/{run_id}/resume")
async def resume_sandbox_run(
    session_id: uuid.UUID,
    run_id: uuid.UUID,
    data: SandboxConfirmAction,
    db: AsyncSession = Depends(db_session),
    user: UserCtx = Depends(require_admin),
    llm_client: LLMClientProtocol = Depends(get_llm_client),
):
    """Resume a paused sandbox run (waiting_confirmation or waiting_input) via SSE stream.

    Continues the same run (no new trace), streaming incremental events.
    """
    from app.services.runtime_resume_checkpoint_service import RuntimeResumeCheckpointService

    svc = SandboxService(db)
    await check_session_owner(svc, session_id, user)

    run = await svc.get_run(run_id)
    if not run or run.session_id != session_id:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.status not in ("waiting_confirmation", "waiting_input"):
        raise HTTPException(status_code=400, detail="Run is not waiting for resume")

    user_input = str(data.user_input or "").strip()
    if run.status == "waiting_input":
        action = "input"
        if not user_input:
            raise HTTPException(status_code=400, detail="user_input is required for waiting_input resume")
    else:
        action = "confirm" if data.confirmed else "cancel"

    if action == "cancel":
        await svc.finish_run(run_id, "cancelled", "Cancelled by user")
        await db.commit()

        async def _cancel_gen() -> AsyncGenerator[str, None]:
            yield _format_sse("final", {"run_id": str(run_id), "status": "cancelled"})
            yield _format_sse("done", {"run_id": str(run_id)})

        return StreamingResponse(_cancel_gen(), media_type="text/event-stream")

    # Build checkpoint from paused state
    paused_action = run.paused_action if isinstance(run.paused_action, dict) else None
    paused_context = run.paused_context if isinstance(run.paused_context, dict) else None
    effective_config = run.effective_config if isinstance(run.effective_config, dict) else {}
    sandbox_resolver = RuntimeSandboxResolver()
    resumed_agent_slug = sandbox_resolver.sandbox_agent_slug(effective_config)
    resumed_agent_version_id = sandbox_resolver.sandbox_agent_version_id(effective_config)
    u_uuid = user_uuid(user)
    t_uuid = await tenant_uuid(db, user)
    sandbox_chat_id = await _ensure_sandbox_upload_chat(
        db,
        owner_id=u_uuid,
        session_id=session_id,
    )
    await db.commit()
    attachment_service = ChatAttachmentService(db)
    attachment_contexts = await attachment_service.build_runtime_artifact_contexts(
        artifact_ids=list(run.input_artifact_ids or []),
        chat_id=str(sandbox_chat_id),
        owner_id=str(u_uuid),
    )

    # Preserve the runtime execution identity for continuation lineage.
    agent_execution_id = paused_context.get("run_id") if paused_context else None

    checkpoint = RuntimeResumeCheckpointService().build(
        run_id=run_id,
        agent_slug=resumed_agent_slug,
        tenant_id=str(await tenant_uuid(db, user)),
        user_id=str(user_uuid(user)),
        chat_id=str(sandbox_chat_id),
        paused_action=paused_action,
        paused_context=paused_context,
        resume_action=action,
        user_input=user_input or None,
        source_context_snapshot=None,
    )

    # The resume checkpoint is now copied in memory; clear the persisted pause
    # state and make the same sandbox run active again.
    await svc.resume_run(run_id)
    await db.commit()

    # Get branch info
    branch = await svc.get_branch(run.branch_id) if run.branch_id else None
    if not branch:
        raise HTTPException(status_code=400, detail="Run has no branch")

    # Confirmation tokens for HITL gate
    confirmed_fingerprints: list[str] = []
    if isinstance(paused_action, dict):
        confirmed_fingerprints = RuntimeHitlProtocolService.extract_confirmed_fingerprints(paused_action, paused_context)

    async def event_stream() -> AsyncGenerator[str, None]:
        session_factory = get_session_factory()
        async with session_factory() as stream_db:
            tool_ctx = ToolContext(
                tenant_id=t_uuid,
                user_id=u_uuid,
                chat_id=str(sandbox_chat_id),
                request_id=str(uuid.uuid4()),
                extra={"sandbox_confirmed_fingerprints": confirmed_fingerprints},
            )
            runtime_deps = tool_ctx.get_runtime_deps()
            runtime_deps.session_factory = session_factory
            resumed_overrides = RuntimeSandboxResolver.sandbox_runtime_overrides(
                effective_config,
                agent_version=None,
            )
            resumed_overrides.update({
                "logging_level": "full",
                "sandbox_run_id": str(run_id),
                "sandbox_branch_id": str(branch.id),
                "sandbox_session_id": str(session_id),
            })
            runtime_deps.sandbox_overrides = resumed_overrides
            tool_ctx.set_runtime_deps(runtime_deps)

            pipeline = RuntimePipeline(
                session=stream_db,
                llm_client=llm_client,
            )

            # Build request from paused state context
            original_goal = ""
            if paused_context and isinstance(paused_context.get("inputs"), dict):
                original_goal = paused_context["inputs"].get("goal", "")
            if not original_goal and paused_context and isinstance(paused_context.get("orchestrator"), dict):
                original_goal = paused_context["orchestrator"].get("goal", "")

            request_text = original_goal or str(run.request_text or "").strip() or "Continue"
            resume_content = build_resume_content(
                action=action,
                user_input=user_input,
                paused_action=paused_action if isinstance(paused_action, dict) else None,
                paused_context=paused_context if isinstance(paused_context, dict) else None,
            )

            pipeline_request = PipelineRequest(
                request_text=request_text,
                runtime_run_id=str(run_id),
                chat_id=str(sandbox_chat_id),
                user_id=str(u_uuid),
                tenant_id=str(t_uuid),
                messages=[{"role": "user", "content": resume_content}],
                attachments=attachment_contexts,
                agent_slug=resumed_agent_slug,
                agent_version_id=str(resumed_agent_version_id) if resumed_agent_version_id else None,
                sandbox_overrides=resumed_overrides,
                continuation_meta={
                    "resume_checkpoint": checkpoint,
                    "resumed_from_run_id": agent_execution_id,
                },
                confirmation_tokens=confirmed_fingerprints,
                await_background_tail=False,
            )

            final_status = "completed"
            final_error: Optional[str] = None
            tail_pending: set[str] = set()
            tail_finished_early: set[str] = set()
            emitted_event_ids: set[str] = set()
            tail_subscriber = RuntimeTailSubscriber(stream_key=str(run_id))
            tail_queue: asyncio.Queue[dict] = asyncio.Queue()
            tail_listener_task: Optional[asyncio.Task] = None

            async def _handle_tail_event(message: dict) -> tuple[str, dict]:
                evt_type = str(message.get("type") or "status")
                yield_payload = dict(message)
                if evt_type == "status" and str(yield_payload.get("stage")) == "tail_finished":
                    tail_id = str(yield_payload.get("tail_id") or "").strip()
                    if tail_id and tail_id in tail_pending:
                        tail_pending.discard(tail_id)
                    elif tail_id:
                        tail_finished_early.add(tail_id)
                return evt_type, yield_payload

            async def _drain_tail_events(max_items: int = 100) -> list[tuple[str, dict]]:
                drained = 0
                out: list[tuple[str, dict]] = []
                while drained < max_items:
                    try:
                        message = tail_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                    out.append(await _handle_tail_event(message))
                    drained += 1
                return out

            async def _journal_fallback() -> list[dict]:
                rows = await RuntimeEventJournalService(stream_db).list_run_events(run_id)
                payloads: list[dict] = []
                for row in rows:
                    event_id = str(row.id)
                    if event_id in emitted_event_ids:
                        continue
                    emitted_event_ids.add(event_id)
                    payloads.append(_journal_from_row(row))
                return payloads

            try:
                await tail_subscriber.subscribe()

                yield _format_sse("run_started", {"run_id": str(run_id)})

                async def _tail_listener() -> None:
                    async for message in tail_subscriber.listen():
                        await tail_queue.put(message)

                tail_listener_task = asyncio.create_task(_tail_listener())

                async for source, item in _merge_pipeline_and_tail(pipeline.execute(pipeline_request, tool_ctx), tail_queue):
                    if source == "tail":
                        _evt_type, evt_payload = await _handle_tail_event(item)
                        if evt_payload.get("event_id"):
                            emitted_event_ids.add(str(evt_payload["event_id"]))
                        frame = _tail_sse_frame(evt_payload)
                        if frame is not None:
                            yield frame
                        continue
                    event = item
                    if event.type == RuntimeEventType.STOP:
                        paused_payload = RuntimeHitlProtocolService.build_paused_from_stop(dict(event.data or {}))
                        final_status = str(paused_payload["reason"])
                        final_error = None
                        svc_pause = SandboxService(stream_db)
                        await svc_pause.pause_run(
                            run_id=run_id,
                            status=paused_payload["reason"],
                            paused_action=paused_payload["action"],
                            paused_context=paused_payload["context"],
                        )
                        await stream_db.commit()
                        pause_event = {
                            "reason": paused_payload["reason"],
                            "action": paused_payload["action"],
                            "context": paused_payload["context"],
                            "contract_version": paused_payload["contract_version"],
                            "run_id": str(run_id),
                        }
                        yield _format_sse("pause", pause_event)
                    elif event.type == RuntimeEventType.DELTA:
                        content = event.data.get("content")
                        if isinstance(content, str) and content:
                            yield _format_sse("delta", {"run_id": str(run_id), "content": content})
                    elif event.type == RuntimeEventType.FINAL:
                        if not str(final_status).startswith("waiting_"):
                            final_status = "completed"
                            final_error = None
                            yield _format_sse("final", {
                                "run_id": str(run_id),
                                "content": str(event.data.get("content") or ""),
                                "sources": event.data.get("sources") or [],
                                "attachments": event.data.get("attachments") or [],
                            })
                    else:
                        terminal = planner_terminal_from_event(event)
                        if terminal is not None:
                            final_status = terminal[0].value
                            final_error = terminal[1]

                    if event.type == RuntimeEventType.STATUS and str(event.data.get("stage")) == "memory_write_dispatched":
                        tail_id = str(event.data.get("tail_id") or "").strip()
                        if tail_id:
                            if tail_id in tail_finished_early:
                                tail_finished_early.discard(tail_id)
                            else:
                                tail_pending.add(tail_id)

                if not str(final_status).startswith("waiting_"):
                    svc_final = SandboxService(stream_db)
                    await svc_final.finish_run(run_id, final_status, final_error)
                    await stream_db.commit()

                for fallback in await _journal_fallback():
                    yield _format_sse("journal", fallback)

            except Exception as e:
                await RuntimeEventJournalFactory.create(
                    context=RuntimeLogContext(run_id=run_id, level=RuntimeLoggingLevel.FULL,
                        origin="sandbox", tenant_id=t_uuid, user_id=u_uuid,
                        stream_logs=True, stream_progress=True),
                    session_factory=session_factory,
                ).error(e, payload={"stage": "sandbox_resume_stream"})
                yield _format_sse("error", {"run_id": str(run_id), "error": "Sandbox execution failed"})
                try:
                    svc_err = SandboxService(stream_db)
                    await svc_err.finish_run(run_id, "failed", str(e))
                    await stream_db.commit()
                except Exception:
                    pass
            finally:
                if tail_listener_task and not tail_listener_task.done():
                    tail_listener_task.cancel()
                    try:
                        await tail_listener_task
                    except asyncio.CancelledError:
                        pass
                await tail_subscriber.unsubscribe()

            yield _format_sse("done", {"run_id": str(run_id)})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/sessions/{session_id}/runs/{run_id}/cancel")
async def cancel_sandbox_run(
    session_id: uuid.UUID,
    run_id: uuid.UUID,
    db: AsyncSession = Depends(db_session),
    user: UserCtx = Depends(require_admin),
) -> StreamingResponse:
    """Cancel a sandbox run paused for clarification or confirmation."""
    svc = SandboxService(db)
    await check_session_owner(svc, session_id, user)

    run = await svc.get_run(run_id)
    if not run or run.session_id != session_id:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.status not in ("running", "waiting_confirmation", "waiting_input"):
        raise HTTPException(status_code=400, detail="Run is not active")

    await svc.finish_run(run_id, "cancelled", "Cancelled by user")
    await db.commit()

    async def _cancel_gen() -> AsyncGenerator[str, None]:
        yield _format_sse("final", {"run_id": str(run_id), "status": "cancelled"})
        yield _format_sse("done", {"run_id": str(run_id)})

    return StreamingResponse(_cancel_gen(), media_type="text/event-stream")
