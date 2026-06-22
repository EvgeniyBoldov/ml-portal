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
from app.agents.runtime_trace_logger import RuntimeTraceLogger
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
    SandboxRunStepResponse,
)
from app.services.chat_attachment_service import ChatAttachmentService
from app.services.sandbox_service import SandboxService
from app.services.sandbox_step_enrichment_service import SandboxStepEnrichmentService
from app.services.run_store import RunStore
from app.services.runtime_hitl_protocol_service import RuntimeHitlProtocolService
from app.services.chat_router_event_mapper import build_resume_content
from app.services.runtime_terminal_status import planner_terminal_from_event
from app.services.runtime_trace_builder import RuntimeTraceBuilder, TraceStep
from app.services.runtime_tail_event_bus import RuntimeTailSubscriber

from .helpers import check_session_owner, tenant_uuid, user_uuid

logger = get_logger(__name__)

router = APIRouter()
SANDBOX_UPLOAD_CHAT_PREFIX = "__sandbox_uploads__:"


def _is_pause_transport_step(evt_type: str, evt_data: dict) -> bool:
    reason = str(evt_data.get("reason") or "").strip().lower()
    if evt_type == "run_paused":
        return True
    if evt_type == "stop" and reason in {"waiting_input", "waiting_confirmation"}:
        return True
    return False




async def _ensure_sandbox_upload_chat(
    db: AsyncSession,
    *,
    owner_id: uuid.UUID,
    session_id: uuid.UUID,
) -> uuid.UUID:
    name = f"{SANDBOX_UPLOAD_CHAT_PREFIX}{session_id}"
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
    runs_with_counts = await svc.list_runs_with_steps_count(session_id, branch_id)
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
            steps_count=steps_count,
        )
        for r, steps_count in runs_with_counts
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
    """Get run detail with steps."""
    svc = SandboxService(db)
    run = await svc.get_run_detail(run_id)
    if not run or run.session_id != session_id:
        raise HTTPException(status_code=404, detail="Run not found")

    branch = await db.scalar(select(SandboxBranch).where(SandboxBranch.id == run.branch_id))
    snapshot = await db.scalar(
        select(SandboxOverrideSnapshot).where(SandboxOverrideSnapshot.id == run.snapshot_id)
    )
    enricher = SandboxStepEnrichmentService(db)
    enriched_steps: list[SandboxRunStepResponse] = []
    for s in run.steps:
        enriched_payload = await enricher.enrich(
            s.step_data,
            branch_name=branch.name if branch else None,
            snapshot_hash=snapshot.snapshot_hash if snapshot else None,
        )
        enriched_steps.append(
            SandboxRunStepResponse(
                id=s.id,
                step_type=s.step_type,
                step_data=enriched_payload,
                order_num=s.order_num,
                created_at=s.created_at,
            )
        )

    trace = RuntimeTraceBuilder().build(
        TraceStep(
            id=str(s.id),
            raw_type=str(s.step_type),
            data=dict(enriched_steps[idx].step_data or {}),
            step_number=int(s.order_num) if s.order_num is not None else None,
            created_at=s.created_at,
            duration_ms=None,
        )
        for idx, s in enumerate(run.steps)
    )

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
        steps=enriched_steps,
        trace=trace,
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
    attachment_meta: list[dict] = []
    attachment_prompt_context = ""

    if data.attachment_ids:
        attachment_service = ChatAttachmentService(db)
        try:
            rows = await attachment_service.get_owned_attachments_any_chat(
                owner_id=str(u_uuid),
                attachment_ids=[str(item) for item in data.attachment_ids],
            )
        except ChatAttachmentNotFoundError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        attachment_meta = attachment_service.to_meta(rows)
        attachment_prompt_context = await attachment_service.build_prompt_context(attachments=rows)

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
                    runtime_trace = RuntimeTraceLogger(
                        session=stream_db,
                        session_factory=session_factory,
                        run_store=RunStore(session_factory=session_factory),
                    )
                    await runtime_trace.log_error(
                        run_id,
                        stage="sandbox_agent_resolve",
                        error=agent_err,
                        data={
                            "run_id": str(run_id),
                            "agent_slug": agent_slug,
                            "tenant_id": str(t_uuid),
                        },
                    )
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
            runtime_trace = RuntimeTraceLogger(
                session=stream_db,
                session_factory=session_factory,
                run_store=RunStore(session_factory=session_factory),
            )
            logger.info("[Sandbox] Runtime logging level forced to full")

            tool_ctx = runtime_trace.attach_context(ToolContext(
                tenant_id=t_uuid,
                user_id=u_uuid,
                chat_id=str(sandbox_chat_id),
                request_id=str(uuid.uuid4()),
                extra={"sandbox_confirmed_fingerprints": sandbox_confirmed_fingerprints},
            ))

            pipeline = RuntimePipeline(
                session=stream_db,
                llm_client=llm_client,
                run_store=RunStore(session_factory=session_factory),
            )

            messages = []
            if attachment_prompt_context:
                messages.append({"role": "system", "content": attachment_prompt_context})
            messages.append({"role": "user", "content": data.request_text})

            pipeline_request = PipelineRequest(
                request_text=data.request_text,
                chat_id=str(sandbox_chat_id),
                user_id=str(u_uuid),
                tenant_id=str(t_uuid),
                messages=messages,
                agent_slug=agent_slug,
                agent_version_id=str(agent_version_id) if agent_version_id else None,
                sandbox_overrides=sandbox_overrides,
                execution_mode=ExecutionMode(data.execution_mode or ExecutionMode.NORMAL.value),
            )
            step_num = await SandboxService(stream_db).get_next_run_step_order(run_id) - 1
            final_status = "completed"
            final_error: Optional[str] = None
            stream_enricher = SandboxStepEnrichmentService(stream_db)
            tail_pending: set[str] = set()
            tail_finished_early: set[str] = set()
            tail_subscriber = RuntimeTailSubscriber(stream_key=str(run_id))
            tail_queue: asyncio.Queue[dict] = asyncio.Queue()
            tail_listener_task: Optional[asyncio.Task] = None

            async def _persist_step(evt_type: str, evt_data: dict) -> None:
                nonlocal step_num
                if _is_pause_transport_step(evt_type, evt_data):
                    return
                step_num += 1
                try:
                    svc_inner = SandboxService(stream_db)
                    step_payload = {
                        **evt_data,
                        "snapshot_id": str(snapshot_id),
                        "branch_id": str(branch_id),
                    }
                    step_payload = stream_enricher.sanitize_step_payload(
                        step_type=evt_type,
                        step_data=step_payload,
                    )
                    step_payload = await stream_enricher.enrich(
                        step_payload,
                        branch_name=branch.name,
                        snapshot_hash=snapshot.snapshot_hash,
                    )
                    if attachment_meta:
                        step_payload["attachments"] = attachment_meta
                    await svc_inner.add_run_step(
                        run_id=run_id,
                        step_type=evt_type,
                        step_data=step_payload,
                        order_num=step_num,
                    )
                    await stream_db.commit()
                except Exception as step_err:
                    logger.warning(f"[Sandbox] Failed to persist step: {step_err}")

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

            try:
                await tail_subscriber.subscribe()

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
                    payload = {
                        "type": event.type.value,
                        "run_id": str(run_id),
                        **event.data,
                    }
                    if event.type == RuntimeEventType.STATUS and str(event.data.get("stage")) == "memory_write_dispatched":
                        tail_id = str(event.data.get("tail_id") or "").strip()
                        if tail_id:
                            if tail_id in tail_finished_early:
                                tail_finished_early.discard(tail_id)
                            else:
                                tail_pending.add(tail_id)
                    yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                    await _persist_step(event.type.value, event.data)
                    drained_tail = await _drain_tail_events()
                    for evt_type, evt_payload in drained_tail:
                        yield f"data: {json.dumps(evt_payload, ensure_ascii=False)}\n\n"
                        await _persist_step(evt_type, evt_payload)

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
                        await _persist_step(evt_type, evt_payload)
                    if tail_pending:
                        timeout_payload = {
                            "type": "status",
                            "run_id": str(run_id),
                            "stage": "tail_timeout",
                            "pending_tail_ids": sorted(tail_pending),
                        }
                        yield f"data: {json.dumps(timeout_payload, ensure_ascii=False)}\n\n"
                        await _persist_step("status", timeout_payload)

            except Exception as e:
                await runtime_trace.log_error(
                    run_id,
                    stage="sandbox_stream",
                    error=e,
                    data={"run_id": str(run_id)},
                )
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
            runtime_trace = RuntimeTraceLogger(
                session=stream_db,
                session_factory=session_factory,
                run_store=RunStore(session_factory=session_factory),
            )

            tool_ctx = runtime_trace.attach_context(ToolContext(
                tenant_id=t_uuid,
                user_id=u_uuid,
                chat_id=str(sandbox_chat_id),
                request_id=str(uuid.uuid4()),
                extra={"sandbox_confirmed_fingerprints": confirmed_fingerprints},
            ))

            pipeline = RuntimePipeline(
                session=stream_db,
                llm_client=llm_client,
                run_store=RunStore(session_factory=session_factory),
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

            step_num = await SandboxService(stream_db).get_next_run_step_order(run_id) - 1
            final_status = "completed"
            final_error: Optional[str] = None
            stream_enricher = SandboxStepEnrichmentService(stream_db)
            tail_pending: set[str] = set()
            tail_finished_early: set[str] = set()
            tail_subscriber = RuntimeTailSubscriber(stream_key=str(run_id))
            tail_queue: asyncio.Queue[dict] = asyncio.Queue()
            tail_listener_task: Optional[asyncio.Task] = None

            async def _persist_step(evt_type: str, evt_data: dict) -> None:
                nonlocal step_num
                if _is_pause_transport_step(evt_type, evt_data):
                    return
                step_num += 1
                try:
                    svc_inner = SandboxService(stream_db)
                    step_payload = {
                        **evt_data,
                        "branch_id": str(branch.id) if branch else "",
                    }
                    step_payload = stream_enricher.sanitize_step_payload(
                        step_type=evt_type,
                        step_data=step_payload,
                    )
                    step_payload = await stream_enricher.enrich(
                        step_payload,
                        branch_name=branch.name if branch else "",
                        snapshot_hash="",
                    )
                    await svc_inner.add_run_step(
                        run_id=run_id,
                        step_type=evt_type,
                        step_data=step_payload,
                        order_num=step_num,
                    )
                    await stream_db.commit()
                except Exception as step_err:
                    logger.warning(f"[Sandbox Resume] Failed to persist step: {step_err}")

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

            try:
                await tail_subscriber.subscribe()

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

                    payload = {
                        "type": event.type.value,
                        "run_id": str(run_id),
                        **event.data,
                    }
                    if event.type == RuntimeEventType.STATUS and str(event.data.get("stage")) == "memory_write_dispatched":
                        tail_id = str(event.data.get("tail_id") or "").strip()
                        if tail_id:
                            if tail_id in tail_finished_early:
                                tail_finished_early.discard(tail_id)
                            else:
                                tail_pending.add(tail_id)
                    yield f'data: {json.dumps(payload, ensure_ascii=False)}\n\n'
                    await _persist_step(event.type.value, event.data)
                    drained_tail = await _drain_tail_events()
                    for evt_type, evt_payload in drained_tail:
                        yield f'data: {json.dumps(evt_payload, ensure_ascii=False)}\n\n'
                        await _persist_step(evt_type, evt_payload)

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
                        await _persist_step(evt_type, evt_payload)
                    if tail_pending:
                        timeout_payload = {
                            "type": "status",
                            "run_id": str(run_id),
                            "stage": "tail_timeout",
                            "pending_tail_ids": sorted(tail_pending),
                        }
                        yield f'data: {json.dumps(timeout_payload, ensure_ascii=False)}\n\n'
                        await _persist_step("status", timeout_payload)

            except Exception as e:
                await runtime_trace.log_error(
                    run_id,
                    stage="sandbox_resume_stream",
                    error=e,
                    data={"run_id": str(run_id)},
                )
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
