"""Sandbox runs — list, detail, execute (SSE), confirm."""
import asyncio
import json
import uuid
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, get_current_user_sse, require_admin
from app.agents import ToolContext
from app.agents.runtime_sandbox_resolver import RuntimeSandboxResolver
from app.core.db import get_session_factory
from app.runtime import PipelineRequest, RuntimeEventType, RuntimePipeline
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
    RuntimeJournalEventResponse,
)
from app.services.chat_attachment_service import ChatAttachmentService, ChatAttachmentNotFoundError
from app.services.chat_visibility import make_sandbox_upload_chat_name
from app.services.sandbox_service import SandboxService
from app.services.runtime_event_journal_service import RuntimeEventJournalService
from app.services.runtime_hitl_protocol_service import RuntimeHitlProtocolService
from app.services.chat_router_event_mapper import build_resume_content
from app.services.runtime_terminal_status import planner_terminal_from_event
from app.services.runtime_event_logger import RuntimeEventLogger, RuntimeLogContext, RuntimeLoggingLevel
from app.services.runtime_tail_event_bus import RuntimeTailSubscriber

from .helpers import check_session_owner, tenant_uuid, user_uuid

logger = get_logger(__name__)

router = APIRouter()
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
        events=[RuntimeJournalEventResponse(
            id=event.id, run_id=event.run_id, sequence=event.sequence,
            event_type=event.event_type, occurred_at=event.occurred_at,
            entity_type=event.entity_type, entity_id=event.entity_id,
            parent_entity_type=event.parent_entity_type, parent_entity_id=event.parent_entity_id,
            caused_by_event_id=event.caused_by_event_id, duration_ms=event.duration_ms,
            payload=event.payload,
        ) for event in events],
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
    attachment_meta: list[dict] = []
    attachment_contexts = []

    if data.attachment_ids:
        try:
            rows = await attachment_service.get_owned_attachments_any_chat(
                owner_id=str(u_uuid),
                attachment_ids=[str(item) for item in data.attachment_ids],
            )
        except ChatAttachmentNotFoundError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        attachment_meta = attachment_service.dedupe_meta(
            await attachment_service.to_meta_with_references(rows)
        )
        attachment_contexts = await attachment_service.build_runtime_attachment_contexts_from_meta(
            attachments_meta=attachment_meta
        )

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
                    await RuntimeEventLogger(
                        context=RuntimeLogContext(run_id=run_id, level=RuntimeLoggingLevel.FULL,
                            origin="sandbox", tenant_id=t_uuid, user_id=u_uuid, stream=True),
                        session_factory=session_factory,
                    ).error(agent_err, payload={"stage": "sandbox_agent_resolve", "agent_slug": agent_slug})
                    try:
                        svc_err = SandboxService(stream_db)
                        await svc_err.finish_run(run_id, "failed", str(agent_err))
                        await stream_db.commit()
                    except Exception:
                        pass
                    yield f"data: {json.dumps({'type': 'error', 'error': str(agent_err), 'run_id': str(run_id)})}\n\n"
                    yield f"data: {json.dumps({'type': 'done', 'run_id': str(run_id)})}\n\n"
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
                chat_id=str(sandbox_chat_id),
                user_id=str(u_uuid),
                tenant_id=str(t_uuid),
                messages=messages,
                attachments=attachment_contexts,
                agent_slug=agent_slug,
                agent_version_id=str(agent_version_id) if agent_version_id else None,
                sandbox_overrides=sandbox_overrides,
                execution_mode=ExecutionMode(data.execution_mode or ExecutionMode.NORMAL.value),
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
                    payloads.append({
                        "type": row.event_type,
                        "run_id": str(row.run_id),
                        "event_id": event_id,
                        "sequence": row.sequence,
                        "occurred_at": row.occurred_at.isoformat(),
                        "entity_type": row.entity_type,
                        "entity_id": row.entity_id,
                        "parent_entity_type": row.parent_entity_type,
                        "parent_entity_id": row.parent_entity_id,
                        "caused_by_event_id": str(row.caused_by_event_id) if row.caused_by_event_id else None,
                        "duration_ms": row.duration_ms,
                        **(row.payload or {}),
                    })
                return payloads

            try:
                await tail_subscriber.subscribe()

                yield f'data: {json.dumps({"type": "stream_connected", "run_id": str(run_id)})}\n\n'

                # Confirm the HTTP/SSE connection immediately.  Runtime work
                # can spend several seconds inside an LLM/tool call before the
                # pipeline emits its first high-level event.
                async def _tail_listener() -> None:
                    async for message in tail_subscriber.listen():
                        await tail_queue.put(message)

                tail_listener_task = asyncio.create_task(_tail_listener())

                async for event in pipeline.execute(pipeline_request, tool_ctx):
                    terminal = planner_terminal_from_event(event)
                    if terminal is not None:
                        final_status = terminal[0].value
                        final_error = terminal[1]

                    if event.type == RuntimeEventType.STOP:
                        paused_payload = RuntimeHitlProtocolService.build_paused_from_stop(dict(event.data or {}))
                        svc_pause = SandboxService(stream_db)
                        await svc_pause.pause_run(
                            run_id=run_id,
                            status=paused_payload["reason"],
                            paused_action=paused_payload["action"],
                            paused_context=paused_payload["context"],
                        )
                        await stream_db.commit()
                        pause_event = {
                            "type": "run_paused",
                            "reason": paused_payload["reason"],
                            "action": paused_payload["action"],
                            "context": paused_payload["context"],
                            "contract_version": paused_payload["contract_version"],
                            "run_id": str(run_id),
                        }
                        yield f"data: {json.dumps(pause_event, ensure_ascii=False)}\n\n"
                    elif event.type == RuntimeEventType.FINAL:
                        final_status = "completed"
                        final_error = None
                    if event.type == RuntimeEventType.STATUS and str(event.data.get("stage")) == "memory_write_dispatched":
                        tail_id = str(event.data.get("tail_id") or "").strip()
                        if tail_id:
                            if tail_id in tail_finished_early:
                                tail_finished_early.discard(tail_id)
                            else:
                                tail_pending.add(tail_id)
                    # The runtime logger is the sole producer of sandbox
                    # events.  It persists first and then publishes to this
                    # run's tail channel; consuming that channel here keeps
                    # the live inspector identical to the event journal.
                    try:
                        message = await asyncio.wait_for(tail_queue.get(), timeout=1.0)
                    except asyncio.TimeoutError:
                        for fallback in await _journal_fallback():
                            yield f"data: {json.dumps(fallback, ensure_ascii=False, default=str)}\n\n"
                        continue
                    evt_type, evt_payload = await _handle_tail_event(message)
                    if evt_payload.get("event_id"):
                        emitted_event_ids.add(str(evt_payload["event_id"]))
                    yield f"data: {json.dumps(evt_payload, ensure_ascii=False)}\n\n"
                    drained_tail = await _drain_tail_events()
                    for evt_type, evt_payload in drained_tail:
                        if evt_payload.get("event_id"):
                            emitted_event_ids.add(str(evt_payload["event_id"]))
                        yield f"data: {json.dumps(evt_payload, ensure_ascii=False)}\n\n"

                if not str(final_status).startswith("waiting_"):
                    svc_final = SandboxService(stream_db)
                    await svc_final.finish_run(run_id, final_status, final_error)
                    await stream_db.commit()

                if tail_pending:
                    deadline = asyncio.get_event_loop().time() + 90.0
                    while tail_pending and asyncio.get_event_loop().time() < deadline:
                        timeout = min(1.0, max(0.0, deadline - asyncio.get_event_loop().time()))
                        try:
                            message = await asyncio.wait_for(tail_queue.get(), timeout=timeout)
                        except asyncio.TimeoutError:
                            continue
                        evt_type, evt_payload = await _handle_tail_event(message)
                        yield f"data: {json.dumps(evt_payload, ensure_ascii=False)}\n\n"
                    if tail_pending:
                        timeout_payload = {
                            "type": "status",
                            "run_id": str(run_id),
                            "stage": "tail_timeout",
                            "pending_tail_ids": sorted(tail_pending),
                        }
                        yield f"data: {json.dumps(timeout_payload, ensure_ascii=False)}\n\n"

                # Redis pub/sub is best effort.  Flush anything persisted while
                # the pipeline was running before closing the SSE response.
                for fallback in await _journal_fallback():
                    yield f"data: {json.dumps(fallback, ensure_ascii=False, default=str)}\n\n"

            except Exception as e:
                await RuntimeEventLogger(
                    context=RuntimeLogContext(run_id=run_id, level=RuntimeLoggingLevel.FULL,
                        origin="sandbox", tenant_id=t_uuid, user_id=u_uuid, stream=True),
                    session_factory=session_factory,
                ).error(e, payload={"stage": "sandbox_stream"})
                yield f"data: {json.dumps({'type': 'error', 'error': str(e), 'run_id': str(run_id)})}\n\n"
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
                yield f"data: {json.dumps({'type': 'done', 'run_id': str(run_id)})}\n\n"

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
            yield f'data: {{"type": "run_paused", "status": "cancelled", "run_id": "{run_id}"}}\n\n'
            yield f'data: {{"type": "done", "run_id": "{run_id}"}}\n\n'

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
    prior_events = await RuntimeEventJournalService(db).list_run_events(run_id)
    attachment_meta = _extract_attachment_meta_from_events(list(prior_events))
    attachment_contexts = await attachment_service.build_runtime_attachment_contexts_from_meta(
        attachments_meta=attachment_meta
    )

    # Extract agent_run_id for pipeline continuation (internal run ID from paused context)
    agent_run_id = paused_context.get("run_id") if paused_context else None

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

    # Update run to resumed state
    await svc.finish_run(run_id, "resumed", None)
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
            runtime_deps.sandbox_overrides = {"logging_level": "full", "sandbox_run_id": str(run_id)}
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
                chat_id=str(sandbox_chat_id),
                user_id=str(u_uuid),
                tenant_id=str(t_uuid),
                messages=[{"role": "user", "content": resume_content}],
                attachments=attachment_contexts,
                agent_slug=resumed_agent_slug,
                agent_version_id=str(resumed_agent_version_id) if resumed_agent_version_id else None,
                sandbox_overrides={
                    "logging_level": "full",
                    "sandbox_run_id": str(run_id),
                    "sandbox_branch_id": str(branch.id),
                    "sandbox_session_id": str(session_id),
                },
                continuation_meta={
                    "resume_checkpoint": checkpoint,
                    "resumed_from_run_id": agent_run_id,  # Continue same AgentRun, not new one
                },
                confirmation_tokens=confirmed_fingerprints,
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
                    payloads.append({
                        "type": row.event_type,
                        "run_id": str(row.run_id),
                        "event_id": event_id,
                        "sequence": row.sequence,
                        "occurred_at": row.occurred_at.isoformat(),
                        "entity_type": row.entity_type,
                        "entity_id": row.entity_id,
                        "parent_entity_type": row.parent_entity_type,
                        "parent_entity_id": row.parent_entity_id,
                        "caused_by_event_id": str(row.caused_by_event_id) if row.caused_by_event_id else None,
                        "duration_ms": row.duration_ms,
                        **(row.payload or {}),
                    })
                return payloads

            try:
                await tail_subscriber.subscribe()

                yield f'data: {json.dumps({"type": "stream_connected", "run_id": str(run_id)})}\n\n'

                async def _tail_listener() -> None:
                    async for message in tail_subscriber.listen():
                        await tail_queue.put(message)

                tail_listener_task = asyncio.create_task(_tail_listener())

                async for event in pipeline.execute(pipeline_request, tool_ctx):
                    terminal = planner_terminal_from_event(event)
                    if terminal is not None:
                        final_status = terminal[0].value
                        final_error = terminal[1]

                    if event.type == RuntimeEventType.STOP:
                        paused_payload = RuntimeHitlProtocolService.build_paused_from_stop(dict(event.data or {}))
                        svc_pause = SandboxService(stream_db)
                        await svc_pause.pause_run(
                            run_id=run_id,
                            status=paused_payload["reason"],
                            paused_action=paused_payload["action"],
                            paused_context=paused_payload["context"],
                        )
                        await stream_db.commit()
                        pause_event = {
                            "type": "run_paused",
                            "reason": paused_payload["reason"],
                            "action": paused_payload["action"],
                            "context": paused_payload["context"],
                            "contract_version": paused_payload["contract_version"],
                            "run_id": str(run_id),
                        }
                        yield f'data: {json.dumps(pause_event, ensure_ascii=False)}\n\n'
                    elif event.type == RuntimeEventType.FINAL:
                        final_status = "completed"
                        final_error = None

                    if event.type == RuntimeEventType.STATUS and str(event.data.get("stage")) == "memory_write_dispatched":
                        tail_id = str(event.data.get("tail_id") or "").strip()
                        if tail_id:
                            if tail_id in tail_finished_early:
                                tail_finished_early.discard(tail_id)
                            else:
                                tail_pending.add(tail_id)
                    try:
                        message = await asyncio.wait_for(tail_queue.get(), timeout=1.0)
                    except asyncio.TimeoutError:
                        for fallback in await _journal_fallback():
                            yield f"data: {json.dumps(fallback, ensure_ascii=False, default=str)}\n\n"
                        continue
                    evt_type, evt_payload = await _handle_tail_event(message)
                    if evt_payload.get("event_id"):
                        emitted_event_ids.add(str(evt_payload["event_id"]))
                    yield f'data: {json.dumps(evt_payload, ensure_ascii=False)}\n\n'
                    drained_tail = await _drain_tail_events()
                    for evt_type, evt_payload in drained_tail:
                        if evt_payload.get("event_id"):
                            emitted_event_ids.add(str(evt_payload["event_id"]))
                        yield f'data: {json.dumps(evt_payload, ensure_ascii=False)}\n\n'

                if not str(final_status).startswith("waiting_"):
                    svc_final = SandboxService(stream_db)
                    await svc_final.finish_run(run_id, final_status, final_error)
                    await stream_db.commit()

                if tail_pending:
                    deadline = asyncio.get_event_loop().time() + 90.0
                    while tail_pending and asyncio.get_event_loop().time() < deadline:
                        timeout = min(1.0, max(0.0, deadline - asyncio.get_event_loop().time()))
                        try:
                            message = await asyncio.wait_for(tail_queue.get(), timeout=timeout)
                        except asyncio.TimeoutError:
                            continue
                        evt_type, evt_payload = await _handle_tail_event(message)
                        yield f'data: {json.dumps(evt_payload, ensure_ascii=False)}\n\n'
                    if tail_pending:
                        timeout_payload = {
                            "type": "status",
                            "run_id": str(run_id),
                            "stage": "tail_timeout",
                            "pending_tail_ids": sorted(tail_pending),
                        }
                        yield f'data: {json.dumps(timeout_payload, ensure_ascii=False)}\n\n'

                for fallback in await _journal_fallback():
                    yield f"data: {json.dumps(fallback, ensure_ascii=False, default=str)}\n\n"

            except Exception as e:
                await RuntimeEventLogger(
                    context=RuntimeLogContext(run_id=run_id, level=RuntimeLoggingLevel.FULL,
                        origin="sandbox", tenant_id=t_uuid, user_id=u_uuid, stream=True),
                    session_factory=session_factory,
                ).error(e, payload={"stage": "sandbox_resume_stream"})
                yield f'data: {json.dumps({"type": "error", "error": str(e), "run_id": str(run_id)})}\n\n'
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

            yield f'data: {json.dumps({"type": "done", "run_id": str(run_id)})}\n\n'

    return StreamingResponse(event_stream(), media_type="text/event-stream")
