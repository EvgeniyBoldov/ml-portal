"""Sandbox runs — list, detail, execute (SSE), confirm."""
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

from .helpers import check_session_owner, tenant_uuid, user_uuid

logger = get_logger(__name__)

router = APIRouter()
SANDBOX_UPLOAD_CHAT_PREFIX = "__sandbox_uploads__:"




async def _ensure_sandbox_upload_chat(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    owner_id: uuid.UUID,
    session_id: uuid.UUID,
) -> uuid.UUID:
    name = f"{SANDBOX_UPLOAD_CHAT_PREFIX}{session_id}"
    row = await db.scalar(
        select(Chats).where(
            and_(
                Chats.tenant_id == tenant_id,
                Chats.owner_id == owner_id,
                Chats.name == name,
            )
        )
    )
    if row:
        return row.id
    row = Chats(
        tenant_id=tenant_id,
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
    attachment_meta: list[dict] = []
    attachment_prompt_context = ""

    if data.attachment_ids:
        attachment_service = ChatAttachmentService(db)
        try:
            rows = await attachment_service.get_owned_attachments_any_chat(
                tenant_id=str(t_uuid),
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

            sandbox_overrides = runtime_sandbox_resolver.sandbox_runtime_overrides(
                effective_config,
                agent_version=resolved_agent_state.agent_version,
            )
            sandbox_overrides["logging_level"] = "full"
            runtime_trace = RuntimeTraceLogger(
                session=stream_db,
                session_factory=session_factory,
                run_store=RunStore(session_factory=session_factory),
                sandbox_overrides=sandbox_overrides,
            )
            logger.info("[Sandbox] Runtime logging level forced to full")

            tool_ctx = runtime_trace.attach_context(ToolContext(
                tenant_id=t_uuid,
                user_id=u_uuid,
                chat_id=None,
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
                chat_id=None,  # sandbox runs are not bound to a persistent chat
                user_id=str(u_uuid),
                tenant_id=str(t_uuid),
                messages=messages,
                agent_slug=agent_slug,
                agent_version_id=str(agent_version_id) if agent_version_id else None,
                sandbox_overrides=sandbox_overrides,
            )
            step_num = 0
            final_status = "completed"
            final_error: Optional[str] = None
            stream_enricher = SandboxStepEnrichmentService(stream_db)

            async def _persist_step(evt_type: str, evt_data: dict) -> None:
                nonlocal step_num
                step_num += 1
                try:
                    svc_inner = SandboxService(stream_db)
                    step_payload = {
                        **evt_data,
                        "snapshot_id": str(snapshot_id),
                        "branch_id": str(branch_id),
                    }
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

            try:
                async for event in pipeline.execute(pipeline_request, tool_ctx):
                    if event.type == RuntimeEventType.ERROR:
                        final_status = "failed"
                        final_error = str(event.data.get("error") or "runtime_error")
                    elif event.type == RuntimeEventType.STOP:
                        reason = str(event.data.get("reason") or "").strip()
                        final_status = reason or "stopped"
                        final_error = str(
                            event.data.get("message")
                            or event.data.get("question")
                            or ""
                        ) or None
                        paused_payload = RuntimeHitlProtocolService.build_paused_from_stop(dict(event.data or {}))
                        svc_pause = SandboxService(stream_db)
                        await svc_pause.pause_run(
                            run_id=run_id,
                            status=paused_payload["reason"],
                            paused_action=paused_payload["action"],
                            paused_context=paused_payload["context"],
                        )
                        await stream_db.commit()
                    elif event.type == RuntimeEventType.FINAL:
                        final_status = "completed"
                        final_error = None
                    payload = {
                        "type": event.type.value,
                        "run_id": str(run_id),
                        **event.data,
                    }
                    yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                    await _persist_step(event.type.value, event.data)

                if not str(final_status).startswith("waiting_"):
                    svc_final = SandboxService(stream_db)
                    await svc_final.finish_run(run_id, final_status, final_error)
                    await stream_db.commit()

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

    t_uuid = await tenant_uuid(db, user)
    u_uuid = user_uuid(user)
    chat_id = await _ensure_sandbox_upload_chat(
        db,
        tenant_id=t_uuid,
        owner_id=u_uuid,
        session_id=session_id,
    )
    attachment_service = ChatAttachmentService(db)
    try:
        uploaded = await attachment_service.upload_attachment(
            tenant_id=str(t_uuid),
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
