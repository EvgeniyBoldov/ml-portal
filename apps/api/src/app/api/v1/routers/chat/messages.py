"""Messages: list, SSE stream, resume run."""
import uuid
from typing import Any, AsyncGenerator, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    ChatContext,
    db_session,
    get_current_user,
    get_llm_client,
    get_redis,
    rate_limit_dependency,
    resolve_chat_context,
)
from app.core.http.clients import LLMClientProtocol
from app.core.logging import get_logger
from app.core.security import UserCtx
from app.models.chat import Chats
from app.models.chat_turn import ChatTurn
from app.repositories.chats_repo import AsyncChatMessagesRepository
from app.repositories.factory import AsyncRepositoryFactory
from app.schemas.chat_events import ChatSSEEventType, ErrorPayload, format_chat_sse, format_chat_sse_done
from app.schemas.chats import ChatMessageStreamRequest
from app.schemas.confirmations import ConfirmationIssueRequest, ConfirmationIssueResponse
from app.schemas.runtime_continuation import RuntimeResumeAction, RuntimeResumeRequest
from app.services.chat_router_event_mapper import build_resume_content, map_service_event_to_sse
from app.services.runtime_hitl_protocol_service import RuntimeHitlProtocolService
from app.services.chat_stream_service import ChatStreamService
from app.services.runtime_resume_checkpoint_service import RuntimeResumeCheckpointService
from app.services.runtime_resume_checkpoint_service import RuntimeResumeValidationError
from app.agents.runtime.confirmation import get_confirmation_service
from app.runtime.contracts import ExecutionMode

router = APIRouter()
logger = get_logger(__name__)

@router.get("/{chat_id}/messages")
async def list_messages(
    chat_id: str,
    limit: int = Query(50, ge=1, le=1000),
    cursor: Optional[str] = Query(None),
    chat_ctx: ChatContext = Depends(resolve_chat_context),
    session: AsyncSession = Depends(db_session),
):
    """List messages for a chat with keyset pagination (cursor = ISO timestamp)"""
    try:
        chat_uuid = uuid.UUID(chat_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid chat ID")

    messages_repo = AsyncChatMessagesRepository(
        session=session,
        tenant_id=None,
        user_id=uuid.UUID(chat_ctx.user_id),
    )
    messages = await messages_repo.get_chat_messages(
        chat_id=str(chat_uuid),
        limit=limit,
        cursor=cursor,
    )

    items = []
    for message in messages:
        content_text = message.content
        if isinstance(content_text, dict) and "text" in content_text:
            content_text = content_text["text"]
        elif isinstance(content_text, dict):
            content_text = str(content_text)

        created_at_str = None
        if message.created_at:
            ts = message.created_at.isoformat()
            if ts.endswith("+00:00"):
                ts = ts[:-6]
            elif ts.endswith("Z"):
                ts = ts[:-1]
            created_at_str = ts + "Z"

        items.append({
            "id": str(message.id),
            "chat_id": str(message.chat_id),
            "role": message.role,
            "content": content_text,
            "created_at": created_at_str,
            "meta": message.meta if message.meta else None,
        })

    next_cursor = None
    if len(items) == limit and items:
        next_cursor = items[-1]["created_at"]

    return {"items": items, "next_cursor": next_cursor, "limit": limit}


@router.post("/{chat_id}/messages")
async def send_message_stream(
    chat_id: str,
    body: ChatMessageStreamRequest,
    request: Request,
    chat_ctx: ChatContext = Depends(resolve_chat_context),
    session: AsyncSession = Depends(db_session),
    redis: Redis = Depends(get_redis),
    llm: LLMClientProtocol = Depends(get_llm_client),
    _rl: None = Depends(rate_limit_dependency(key_prefix="chat_messages", rpm=30, rph=600)),
) -> StreamingResponse:
    """Send a message to a chat with SSE streaming."""
    content = body.content
    model = body.model
    agent_slug = body.agent_slug
    artifact_ids = body.artifact_ids or []
    confirmation_tokens = body.confirmation_tokens or []
    execution_mode = ExecutionMode(body.execution_mode or ExecutionMode.NORMAL.value)

    if not content:
        raise HTTPException(status_code=400, detail="Content is required")

    idempotency_key = request.headers.get("Idempotency-Key")

    repo_factory = AsyncRepositoryFactory(
        session, uuid.UUID(chat_ctx.tenant_id), chat_ctx.user_id,
    )
    service = ChatStreamService(
        session=session,
        redis=redis,
        llm_client=llm,
        chats_repo=repo_factory.get_chats_repository(),
        messages_repo=repo_factory.get_chat_messages_repository(),
    )

    async def _gen() -> AsyncGenerator[str, None]:
        try:
            async for event in service.send_message_stream(
                chat_id=chat_ctx.chat_id,
                user_id=chat_ctx.user_id,
                tenant_id=chat_ctx.tenant_id,
                content=content,
                artifact_ids=artifact_ids,
                confirmation_tokens=confirmation_tokens,
                execution_mode=execution_mode,
                idempotency_key=idempotency_key,
                model=model,
                agent_slug=agent_slug,
            ):
                try:
                    sse_text = map_service_event_to_sse(event)
                except Exception as exc:
                    logger.warning("Failed to map chat event to SSE: %s", exc)
                    sse_text = None
                if sse_text:
                    yield sse_text
            yield format_chat_sse_done()
        except Exception as e:
            logger.error(f"Error in chat stream: {e}", exc_info=True)
            yield format_chat_sse(ChatSSEEventType.ERROR, ErrorPayload(error=str(e)))
            yield format_chat_sse_done()

    return StreamingResponse(_gen(), media_type="text/event-stream")


@router.post(
    "/{chat_id}/confirm",
    response_model=ConfirmationIssueResponse,
)
async def issue_confirmation_token(
    chat_id: str,
    body: ConfirmationIssueRequest,
    chat_ctx: ChatContext = Depends(resolve_chat_context),
    session: AsyncSession = Depends(db_session),
    current_user: UserCtx = Depends(get_current_user),
):
    if str(chat_ctx.chat_id) != str(chat_id):
        raise HTTPException(status_code=404, detail="Chat not found")
    chat_row = (
        await session.execute(select(Chats).where(Chats.id == uuid.UUID(str(chat_ctx.chat_id))))
    ).scalar_one_or_none()
    if not chat_row or str(chat_row.owner_id) != str(current_user.id):
        raise HTTPException(status_code=404, detail="Chat not found")
    service = get_confirmation_service()
    token, expires_at = service.issue(
        user_id=uuid.UUID(str(chat_ctx.user_id)),
        chat_id=uuid.UUID(str(chat_ctx.chat_id)),
        fingerprint=body.operation_fingerprint,
    )
    return ConfirmationIssueResponse(token=token, expires_at=expires_at)


@router.post("/runs/{run_id}/resume")
async def resume_run(
    run_id: str,
    body: RuntimeResumeRequest,
    session: AsyncSession = Depends(db_session),
    current_user: UserCtx = Depends(get_current_user),
    _rl: None = Depends(rate_limit_dependency(key_prefix="chat_resume", rpm=20, rph=300)),
) -> StreamingResponse:
    """Resume a paused run (waiting_confirmation or waiting_input) with SSE streaming."""
    from app.services.chat_turn_service import ChatTurnService
    from app.repositories.chats_repo import AsyncChatsRepository, AsyncChatMessagesRepository

    try:
        run_uuid = uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid run ID")

    turn_service = ChatTurnService(session)
    run_result = await session.execute(
        select(ChatTurn).where(
            ChatTurn.runtime_run_id == run_uuid,
            ChatTurn.status == "paused",
        )
    )
    turn = run_result.scalar_one_or_none()
    if not turn:
        raise HTTPException(status_code=404, detail="Paused run not found")
    if str(turn.user_id) != str(current_user.id):
        raise HTTPException(status_code=404, detail="Paused run not found")
    tenant_ids = current_user.tenant_ids or []
    if not tenant_ids:
        raise HTTPException(status_code=403, detail="No tenant scope available")
    tenant_uuid_val = uuid.UUID(str(tenant_ids[0]))
    paused_action = turn.paused_action
    paused_context = turn.paused_context

    user_input = body.input
    try:
        normalized_input = RuntimeResumeCheckpointService.validate_action(
            pause_status=str(turn.pause_status or ""),
            action=body.action,
            user_input=user_input,
        )
    except RuntimeResumeValidationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if body.action is RuntimeResumeAction.CANCEL:
        await turn_service.cancel_turn(turn.id, error_message="Cancelled by user")
        await session.commit()
        async def _cancel_gen() -> AsyncGenerator[str, None]:
            yield format_chat_sse_done()
        return StreamingResponse(_cancel_gen(), media_type="text/event-stream")

    checkpoint_service = RuntimeResumeCheckpointService.from_session(session)
    original_goal = await checkpoint_service.resolve_original_goal(run_uuid)
    if original_goal is None:
        raise HTTPException(status_code=409, detail="Runtime continuation plan not found")

    checkpoint = checkpoint_service.build(
        run_id=run_uuid,
        agent_slug="",
        tenant_id=tenant_uuid_val,
        user_id=turn.user_id,
        chat_id=turn.chat_id,
        paused_action=paused_action if isinstance(paused_action, dict) else None,
        paused_context=paused_context if isinstance(paused_context, dict) else None,
        resume_action=body.action.value,
        user_input=normalized_input or None,
        source_context_snapshot=RuntimeResumeCheckpointService.source_context_snapshot(
            goal=original_goal,
        ),
    )

    # Keep one ChatTurn for the entire paused/resumed lifecycle.  Cancelling
    # this row before continuation made the next request look stale and also
    # created a duplicate ChatTurn for the same runtime run.
    await turn_service.resume_turn(turn.id)
    await session.commit()

    if not turn.chat_id:
        # No chat_id - can't stream, return error SSE
        async def _no_chat_gen() -> AsyncGenerator[str, None]:
            yield format_chat_sse(ChatSSEEventType.ERROR, ErrorPayload(error="Run has no chat_id", code="missing_chat"))
            yield format_chat_sse_done()
        return StreamingResponse(_no_chat_gen(), media_type="text/event-stream")

    resume_content = build_resume_content(
        action=body.action.value,
        user_input=normalized_input,
        paused_action=paused_action if isinstance(paused_action, dict) else None,
        paused_context=paused_context if isinstance(paused_context, dict) else None,
    )

    # P0-4: For confirm action, issue a confirmation token so the resumed pipeline
    # can pass the HITL gate without looping back to another confirmation_required.
    confirmation_tokens: list[str] = []
    if body.action is RuntimeResumeAction.CONFIRM and isinstance(paused_action, dict):
        fingerprint = RuntimeHitlProtocolService.extract_operation_fingerprint(
            paused_action if isinstance(paused_action, dict) else None,
            paused_context if isinstance(paused_context, dict) else None,
        )
        if fingerprint and turn.chat_id:
            try:
                conf_svc = get_confirmation_service()
                token, _ = conf_svc.issue(
                    fingerprint=fingerprint,
                    user_id=uuid.UUID(str(current_user.id)),
                    chat_id=uuid.UUID(str(turn.chat_id)),
                )
                confirmation_tokens = [token]
            except Exception as _ce:
                logger.warning("Failed to issue confirmation token on resume: %s", _ce)

    user_uuid_val = uuid.UUID(str(current_user.id))
    chats_repo = AsyncChatsRepository(session, tenant_uuid_val, user_uuid_val)
    messages_repo = AsyncChatMessagesRepository(session, tenant_uuid_val, user_uuid_val)
    service = ChatStreamService(
        session=session,
        redis=get_redis(),
        llm_client=get_llm_client(),
        chats_repo=chats_repo,
        messages_repo=messages_repo,
    )

    async def _resume_gen() -> AsyncGenerator[str, None]:
        try:
            async for event in service.send_message_stream(
                chat_id=str(turn.chat_id),
                user_id=str(current_user.id),
                tenant_id=str(tenant_uuid_val),
                content=resume_content,
                artifact_ids=[],
                idempotency_key=None,
                model=None,
                agent_slug=None,
                continuation_meta={
                    "resume_checkpoint": checkpoint,
                    "resumed_from_run_id": run_id,
                },
                resumed_turn_id=str(turn.id),
                confirmation_tokens=confirmation_tokens,
                persist_user_message=False,
            ):
                try:
                    sse_text = map_service_event_to_sse(event)
                except Exception as exc:
                    logger.warning("Failed to map resume event to SSE: %s", exc)
                    sse_text = None
                if sse_text:
                    yield sse_text
            yield format_chat_sse_done()
        except Exception as e:
            logger.error(f"Error in resume stream: {e}", exc_info=True)
            yield format_chat_sse(ChatSSEEventType.ERROR, ErrorPayload(error=str(e)))
            yield format_chat_sse_done()

    return StreamingResponse(_resume_gen(), media_type="text/event-stream")
