"""Messages: list, SSE stream, resume run."""
import uuid
from datetime import datetime, timezone
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
from app.models.agent_run import AgentRun
from app.repositories.factory import AsyncRepositoryFactory, get_async_repository_factory
from app.schemas.chat_events import ChatSSEEventType, ErrorPayload, format_chat_sse, format_chat_sse_done
from app.schemas.chats import ChatMessageStreamRequest
from app.services.chat_router_event_mapper import build_resume_content, map_service_event_to_sse
from app.services.chat_stream_service import ChatStreamService
from app.services.runtime_resume_checkpoint_service import RuntimeResumeCheckpointService

router = APIRouter()
logger = get_logger(__name__)


def _compat_symbol(name: str, fallback: Any) -> Any:
    """Compatibility shim for legacy test patch points on package module."""
    try:
        from app.api.v1.routers import chat as chat_pkg  # type: ignore

        return getattr(chat_pkg, name, fallback)
    except Exception:
        return fallback


@router.get("/{chat_id}/messages")
async def list_messages(
    chat_id: str,
    limit: int = Query(50, ge=1, le=1000),
    cursor: Optional[str] = Query(None),
    current_user: UserCtx = Depends(get_current_user),
    repo_factory: AsyncRepositoryFactory = Depends(get_async_repository_factory),
):
    """List messages for a chat with keyset pagination (cursor = ISO timestamp)"""
    try:
        chat_uuid = uuid.UUID(chat_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid chat ID")

    messages_repo = repo_factory.get_chat_messages_repository()
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
    attachment_ids = body.attachment_ids or []

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
                content=content,
                attachment_ids=attachment_ids,
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


@router.post("/runs/{run_id}/resume")
async def resume_run(
    run_id: str,
    body: Dict[str, Any],
    session: AsyncSession = Depends(db_session),
    current_user: UserCtx = Depends(get_current_user),
    _rl: None = Depends(rate_limit_dependency(key_prefix="chat_resume", rpm=20, rph=300)),
):
    """Resume a paused run (waiting_confirmation or waiting_input)."""
    from app.services.chat_turn_service import ChatTurnService
    from app.repositories.chats_repo import AsyncChatsRepository, AsyncChatMessagesRepository

    try:
        run_uuid = uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid run ID")

    action = body.get("action", "")
    if action not in ("confirm", "cancel", "input"):
        raise HTTPException(status_code=400, detail="action must be 'confirm', 'cancel', or 'input'")

    turn_service = ChatTurnService(session)
    run_result = await session.execute(
        select(AgentRun).where(
            AgentRun.id == run_uuid,
            AgentRun.status.in_(["waiting_confirmation", "waiting_input"]),
        )
    )
    run = run_result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Paused run not found")
    if run.user_id and str(run.user_id) != str(current_user.id):
        raise HTTPException(status_code=404, detail="Paused run not found")
    if current_user.tenant_ids and str(run.tenant_id) not in set(current_user.tenant_ids):
        raise HTTPException(status_code=404, detail="Paused run not found")

    turn = await turn_service.get_by_agent_run_id(run_uuid)
    paused_action = run.paused_action
    paused_context = run.paused_context

    if action == "cancel":
        run.status = "cancelled"
        run.error = "Cancelled by user"
        run.finished_at = datetime.now(timezone.utc)
        run.paused_action = None
        run.paused_context = None
        if turn:
            await turn_service.cancel_turn(turn.id, error_message="Cancelled by user", agent_run_id=run_uuid)
        await session.commit()
        return {"run_id": run_id, "status": "cancelled"}

    user_input = ""
    if action == "input":
        user_input = str(body.get("input", "")).strip()
        if not user_input:
            raise HTTPException(status_code=400, detail="input field is required for action='input'")

    checkpoint = RuntimeResumeCheckpointService().build(
        run_id=run_uuid,
        agent_slug=run.agent_slug,
        tenant_id=run.tenant_id,
        user_id=run.user_id or current_user.id,
        chat_id=run.chat_id,
        paused_action=paused_action if isinstance(paused_action, dict) else None,
        paused_context=paused_context if isinstance(paused_context, dict) else None,
        resume_action=action,
        user_input=user_input or None,
    )

    run.status = "resumed"
    run.error = None
    run.finished_at = datetime.now(timezone.utc)
    snapshot = dict(getattr(run, "context_snapshot", None) or {})
    snapshot["resume_checkpoint"] = checkpoint
    run.context_snapshot = snapshot
    run.paused_action = None
    run.paused_context = None
    if turn:
        await turn_service.cancel_turn(
            turn.id,
            error_message="Turn resumed via continuation flow",
            agent_run_id=run_uuid,
        )
    await session.commit()

    if not run.chat_id:
        payload: Dict[str, Any] = {
            "run_id": run_id,
            "status": "resumed_without_continuation",
            "paused_action": paused_action,
            "paused_context": paused_context,
            "resume_checkpoint": checkpoint,
            "warning": "Run has no chat_id, continuation skipped",
        }
        if action == "input":
            payload["user_input"] = user_input
        return payload

    resume_content = build_resume_content(
        action=action,
        user_input=user_input,
        paused_action=paused_action if isinstance(paused_action, dict) else None,
        paused_context=paused_context if isinstance(paused_context, dict) else None,
    )

    tenant_uuid_val = uuid.UUID(str(run.tenant_id))
    user_uuid_val = uuid.UUID(str(current_user.id))
    chats_repo = AsyncChatsRepository(session, tenant_uuid_val, user_uuid_val)
    messages_repo = AsyncChatMessagesRepository(session, tenant_uuid_val, user_uuid_val)
    chat_stream_service_cls = _compat_symbol("ChatStreamService", ChatStreamService)
    redis_factory = _compat_symbol("get_redis", get_redis)
    llm_factory = _compat_symbol("get_llm_client", get_llm_client)

    service = chat_stream_service_cls(
        session=session,
        redis=redis_factory(),
        llm_client=llm_factory(),
        chats_repo=chats_repo,
        messages_repo=messages_repo,
    )

    continuation_status = "completed"
    continuation_error: Optional[str] = None
    assistant_message_id: Optional[str] = None
    paused_again_reason: Optional[str] = None
    paused_again_run_id: Optional[str] = None

    async for event in service.send_message_stream(
        chat_id=str(run.chat_id),
        user_id=str(current_user.id),
        content=resume_content,
        attachment_ids=[],
        idempotency_key=None,
        model=None,
        agent_slug=run.agent_slug,
        continuation_meta={
            "resume_checkpoint": checkpoint,
            "resumed_from_run_id": str(run_uuid),
        },
    ):
        et = event.get("type")
        if et == "error":
            continuation_status = "error"
            continuation_error = str(event.get("error") or "Unknown continuation error")
        elif et == "final":
            assistant_message_id = str(event.get("message_id")) if event.get("message_id") else None
        elif et == "run_paused":
            continuation_status = "paused"
            paused_again_reason = str(event.get("reason") or "")
            paused_again_run_id = str(event.get("run_id") or "")

    if continuation_status == "error":
        payload = {
            "run_id": run_id,
            "status": "resumed_with_error",
            "paused_action": paused_action,
            "paused_context": paused_context,
            "resume_checkpoint": checkpoint,
            "error": continuation_error,
        }
        if action == "input":
            payload["user_input"] = user_input
        return payload

    if continuation_status == "paused":
        payload = {
            "run_id": run_id,
            "status": "resumed_paused_again",
            "paused_action": paused_action,
            "paused_context": paused_context,
            "resume_checkpoint": checkpoint,
            "paused_again_reason": paused_again_reason,
            "paused_again_run_id": paused_again_run_id,
        }
        if action == "input":
            payload["user_input"] = user_input
        return payload

    payload = {
        "run_id": run_id,
        "status": "resumed_completed",
        "paused_action": paused_action,
        "paused_context": paused_context,
        "resume_checkpoint": checkpoint,
    }
    if action == "input":
        payload["user_input"] = user_input
    if assistant_message_id:
        payload["assistant_message_id"] = assistant_message_id
    return payload
