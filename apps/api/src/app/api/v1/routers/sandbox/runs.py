"""Sandbox runs — list, detail, execute and resume (SSE)."""
import asyncio
import json
import uuid
from typing import Any, AsyncGenerator, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, get_current_user_sse, require_admin
from app.agents import ToolContext
from app.agents.runtime.confirmation import get_confirmation_service
from app.agents.runtime_sandbox_resolver import RuntimeSandboxResolver
from app.core.db import get_session_factory
from app.runtime import PipelineRequest
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
    SandboxRunCreate,
    SandboxRunListItem,
    SandboxRunDetailResponse,
)
from app.schemas.runtime_continuation import RuntimeResumeAction, RuntimeResumeRequest
from app.schemas.runtime_events import RuntimeJournalEventResponse
from app.services.chat_attachment_service import ChatAttachmentService, ChatAttachmentNotFoundError
from app.services.chat_visibility import make_sandbox_upload_chat_name
from app.services.sandbox_service import SandboxService
from app.services.runtime_event_journal_service import RuntimeEventJournalService
from app.services.runtime_hitl_protocol_service import RuntimeHitlProtocolService
from app.services.runtime_resume_checkpoint_service import (
    RuntimeResumeCheckpointService,
    RuntimeResumeValidationError,
)
from app.services.chat_router_event_mapper import build_resume_content
from app.services.runtime_event_logger import RuntimeEventJournalFactory, RuntimeLogContext, RuntimeLoggingLevel
from app.services.runtime_tail_event_bus import RuntimeRunControlBus, RuntimeTailSubscriber
from app.services.sandbox.runtime_runner import SandboxRuntimeCommand, sandbox_runtime_runner
from app.core.config import get_settings

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


async def _observe_sandbox_runner(
    *,
    run_id: uuid.UUID,
    command: SandboxRuntimeCommand,
    llm_client: LLMClientProtocol,
    session_factory: Any,
    stream_db: AsyncSession,
) -> AsyncGenerator[str, None]:
    """Stream canonical tail/journal data without owning runtime execution."""
    subscriber = RuntimeTailSubscriber(stream_key=str(run_id))
    queue: asyncio.Queue[dict] = asyncio.Queue()
    emitted_event_ids: set[str] = set()
    listener_task: Optional[asyncio.Task] = None
    heartbeat_seconds = get_settings().SANDBOX_SSE_HEARTBEAT_SECONDS

    async def listen() -> None:
        async for message in subscriber.listen():
            await queue.put(message)

    def frame_for(message: dict) -> str | None:
        if message.get("type") == "delta":
            return _format_sse("delta", {"run_id": str(run_id), "content": str(message.get("content") or "")})
        if message.get("type") == "final":
            return _format_sse("final", {
                "run_id": str(run_id),
                "content": str(message.get("content") or ""),
                "sources": message.get("sources") or [],
                "attachments": message.get("attachments") or [],
            })
        if message.get("type") == "pause":
            return _format_sse("pause", {
                "run_id": str(run_id),
                "reason": message.get("reason"),
                "action": message.get("action"),
                "context": message.get("context"),
                "contract_version": message.get("contract_version"),
            })
        return _tail_sse_frame(message)

    try:
        await subscriber.subscribe()
        listener_task = asyncio.create_task(listen())
        # A resumed sandbox execution deliberately reuses the same run id. Do
        # not replay its previous journal segment into this SSE connection: a
        # historical waiting_input/confirmation_required event would otherwise
        # make the client reopen an already resolved pause after the new run
        # has produced its final answer.
        existing_rows = await RuntimeEventJournalService(stream_db).list_run_events(run_id)
        emitted_event_ids.update(str(row.id) for row in existing_rows)
        runner_task = await sandbox_runtime_runner.start(
            command=command,
            llm_client=llm_client,
            session_factory=session_factory,
        )
        yield _format_sse("run_started", {"run_id": str(run_id)})
        while not runner_task.done():
            try:
                message = await asyncio.wait_for(queue.get(), timeout=heartbeat_seconds)
            except asyncio.TimeoutError:
                yield ": ping\n\n"
                continue
            if message.get("event_id"):
                emitted_event_ids.add(str(message["event_id"]))
            frame = frame_for(message)
            if frame is not None:
                yield frame

        while not queue.empty():
            message = queue.get_nowait()
            if message.get("event_id"):
                emitted_event_ids.add(str(message["event_id"]))
            frame = frame_for(message)
            if frame is not None:
                yield frame

        rows = await RuntimeEventJournalService(stream_db).list_run_events(run_id)
        for row in rows:
            event_id = str(row.id)
            if event_id in emitted_event_ids:
                continue
            emitted_event_ids.add(event_id)
            yield _format_sse("journal", _journal_from_row(row))
        current_run = await SandboxService(stream_db).get_run(run_id)
        if current_run is not None and current_run.status == "failed":
            yield _format_sse("error", {"run_id": str(run_id), "error": "Sandbox execution failed"})
        elif current_run is not None and current_run.status == "cancelled":
            yield _format_sse("final", {"run_id": str(run_id), "status": "cancelled"})
    finally:
        if listener_task is not None:
            listener_task.cancel()
            await asyncio.gather(listener_task, return_exceptions=True)
        await subscriber.unsubscribe()
        yield _format_sse("done", {"run_id": str(run_id)})

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
            sandbox_overrides["memory_inline"] = True
            sandbox_overrides["sandbox_run_id"] = str(run_id)
            sandbox_overrides["sandbox_branch_id"] = str(branch_id)
            sandbox_overrides["sandbox_session_id"] = str(session_id)
            logger.info("[Sandbox] Runtime logging level forced to full")

            tool_ctx = ToolContext(
                tenant_id=t_uuid,
                user_id=u_uuid,
                chat_id=str(sandbox_chat_id),
                request_id=str(uuid.uuid4()),
                extra={},
            )
            runtime_deps = tool_ctx.get_runtime_deps()
            runtime_deps.session_factory = session_factory
            runtime_deps.sandbox_overrides = sandbox_overrides
            tool_ctx.set_runtime_deps(runtime_deps)

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
            async for frame in _observe_sandbox_runner(
                run_id=run_id,
                command=SandboxRuntimeCommand(
                    run_id=run_id,
                    user_id=u_uuid,
                    tenant_id=t_uuid,
                    pipeline_request=pipeline_request,
                    tool_context=tool_ctx,
                ),
                llm_client=llm_client,
                session_factory=session_factory,
                stream_db=stream_db,
            ):
                yield frame

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


@router.post("/sessions/{session_id}/runs/{run_id}/resume")
async def resume_sandbox_run(
    session_id: uuid.UUID,
    run_id: uuid.UUID,
    data: RuntimeResumeRequest,
    db: AsyncSession = Depends(db_session),
    user: UserCtx = Depends(require_admin),
    llm_client: LLMClientProtocol = Depends(get_llm_client),
):
    """Resume a paused sandbox run (waiting_confirmation or waiting_input) via SSE stream.

    Continues the same run (no new trace), streaming incremental events.
    """
    svc = SandboxService(db)
    await check_session_owner(svc, session_id, user)

    run = await svc.get_run(run_id)
    if not run or run.session_id != session_id:
        raise HTTPException(status_code=404, detail="Run not found")
    try:
        user_input = RuntimeResumeCheckpointService.validate_action(
            pause_status=run.status,
            action=data.action,
            user_input=data.input,
        )
    except RuntimeResumeValidationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    action = data.action.value

    if data.action is RuntimeResumeAction.CANCEL:
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
        source_context_snapshot=RuntimeResumeCheckpointService.source_context_snapshot(
            goal=str(run.request_text or ""),
        ),
    )

    # The resume checkpoint is now copied in memory; clear the persisted pause
    # state and make the same sandbox run active again.
    await svc.resume_run(run_id)
    await db.commit()

    # Get branch info
    branch = await svc.get_branch(run.branch_id) if run.branch_id else None
    if not branch:
        raise HTTPException(status_code=400, detail="Run has no branch")

    # Confirmation data for HITL gate. Sandbox owns a hidden chat used for
    # attachments, so the operation executor follows the regular signed-token
    # path (rather than its chat_id=None sandbox preapproval path).
    confirmation_tokens: list[str] = []
    if isinstance(paused_action, dict):
        if data.action is RuntimeResumeAction.CONFIRM:
            fingerprint = RuntimeHitlProtocolService.extract_operation_fingerprint(
                paused_action,
                paused_context,
            )
            if fingerprint:
                try:
                    token, _ = get_confirmation_service().issue(
                        fingerprint=fingerprint,
                        user_id=u_uuid,
                        chat_id=sandbox_chat_id,
                    )
                    confirmation_tokens = [token]
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Failed to issue sandbox confirmation token on resume: %s", exc)

    async def event_stream() -> AsyncGenerator[str, None]:
        session_factory = get_session_factory()
        async with session_factory() as stream_db:
            runtime_sandbox_resolver = RuntimeSandboxResolver(session=stream_db)
            resolved_agent_state = None
            if resumed_agent_slug or resumed_agent_version_id:
                try:
                    resolved_agent_state = await runtime_sandbox_resolver.resolve_sandbox_agent(
                        agent_slug=resumed_agent_slug,
                        tenant_id=t_uuid,
                        agent_version_id=resumed_agent_version_id,
                    )
                except Exception as agent_err:  # noqa: BLE001
                    await RuntimeEventJournalFactory.create(
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
                    ).error(
                        agent_err,
                        payload={"stage": "sandbox_agent_resolve", "agent_slug": resumed_agent_slug},
                    )
                    await SandboxService(stream_db).finish_run(run_id, "failed", str(agent_err))
                    await stream_db.commit()
                    yield _format_sse(
                        "error",
                        {"run_id": str(run_id), "error": "Sandbox agent resolution failed"},
                    )
                    yield _format_sse("done", {"run_id": str(run_id)})
                    return

            tool_ctx = ToolContext(
                tenant_id=t_uuid,
                user_id=u_uuid,
                chat_id=str(sandbox_chat_id),
                request_id=str(uuid.uuid4()),
                extra={},
            )
            runtime_deps = tool_ctx.get_runtime_deps()
            runtime_deps.session_factory = session_factory
            resumed_overrides = runtime_sandbox_resolver.sandbox_runtime_overrides(
                effective_config,
                agent_version=(
                    resolved_agent_state.agent_version
                    if resolved_agent_state is not None
                    else None
                ),
            )
            resumed_overrides.update({
                "logging_level": "full",
                # A sandbox run persists its fact effects to the frozen branch
                # overlay in its own transaction. Keeping this inline makes
                # that write deterministic and visible before the run is
                # marked complete.
                "memory_inline": True,
                "sandbox_run_id": str(run_id),
                "sandbox_branch_id": str(branch.id),
                "sandbox_session_id": str(session_id),
            })
            runtime_deps.sandbox_overrides = resumed_overrides
            tool_ctx.set_runtime_deps(runtime_deps)

            # The original request is immutable for a sandbox run.  A pause
            # answer belongs only to the continuation message/checkpoint.
            request_text = str(run.request_text or "").strip()
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
                    "resumed_from_run_id": str(run_id),
                },
                confirmation_tokens=confirmation_tokens,
                await_background_tail=False,
            )
            async for frame in _observe_sandbox_runner(
                run_id=run_id,
                command=SandboxRuntimeCommand(
                    run_id=run_id,
                    user_id=u_uuid,
                    tenant_id=t_uuid,
                    pipeline_request=pipeline_request,
                    tool_context=tool_ctx,
                ),
                llm_client=llm_client,
                session_factory=session_factory,
                stream_db=stream_db,
            ):
                yield frame

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/sessions/{session_id}/runs/{run_id}/cancel")
async def cancel_sandbox_run(
    session_id: uuid.UUID,
    run_id: uuid.UUID,
    db: AsyncSession = Depends(db_session),
    user: UserCtx = Depends(require_admin),
) -> StreamingResponse:
    """Request cancellation through the runner that owns live execution."""
    svc = SandboxService(db)
    await check_session_owner(svc, session_id, user)

    run = await svc.get_run(run_id)
    if not run or run.session_id != session_id:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.status not in ("running", "cancelling"):
        raise HTTPException(status_code=400, detail="Run is not active")

    if run.status == "running":
        await svc.request_cancel(run_id)
        await db.commit()
        await sandbox_runtime_runner.cancel_local(run_id)
        try:
            await RuntimeRunControlBus().publish_cancel(str(run_id))
        except Exception:  # noqa: BLE001
            logger.warning("sandbox_cancel_control_publish_failed run_id=%s", run_id)
        status = "cancelling"
    elif run.status == "cancelling":
        status = "cancelling"
    async def _cancel_gen() -> AsyncGenerator[str, None]:
        yield _format_sse("final", {"run_id": str(run_id), "status": status})
        yield _format_sse("done", {"run_id": str(run_id)})

    return StreamingResponse(_cancel_gen(), media_type="text/event-stream")
