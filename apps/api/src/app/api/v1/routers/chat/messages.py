"""Messages: list, SSE stream, resume run."""
import asyncio
import json
import time
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
from app.core.db import get_session_factory
from app.core.http.clients import LLMClientProtocol
from app.core.logging import get_logger
from app.core.security import UserCtx
from app.models.chat import Chats
from app.models.chat_turn import ChatTurn
from app.repositories.chats_repo import AsyncChatMessagesRepository
from app.schemas.chat_events import (
    ActiveChatRunResponse,
    ChatSSEEventType,
    ErrorPayload,
    format_chat_sse,
    format_chat_sse_done,
)
from app.schemas.chats import ChatContextInspectionResponse, ChatContextResetResponse, ChatMessageStreamRequest, ChatMemoryScopesUpdate
from app.schemas.confirmations import ConfirmationIssueRequest, ConfirmationIssueResponse
from app.schemas.runtime_continuation import RuntimeResumeAction, RuntimeResumeRequest
from app.services.chat_router_event_mapper import build_resume_content, map_service_event_to_sse
from app.services.runtime_hitl_protocol_service import RuntimeHitlProtocolService
from app.services.chat_runtime_runner import (
    CHAT_RUN_OWNER_TTL_SECONDS,
    ChatRuntimeCommand,
    chat_event_stream_key,
    chat_run_owner_key,
    read_chat_stage_snapshot,
    chat_runtime_runner,
)
from app.services.runtime_tail_event_bus import RuntimeRunControlBus, RuntimeTailSubscriber
from app.core.chat_lifecycle import (
    ACTIVE_STATUSES,
    WAITING_STATUSES,
    normalize_chat_turn_status,
)
from app.services.chat_context_service import ChatContextService
from app.services.runtime_resume_checkpoint_service import RuntimeResumeCheckpointService
from app.services.runtime_resume_checkpoint_service import RuntimeResumeValidationError
from app.agents.runtime.confirmation import get_confirmation_service
from app.services.chat_status_snapshot import (
    build_chat_status_snapshot,
    latest_chat_turns_for_owner,
)

router = APIRouter()
logger = get_logger(__name__)
CHAT_STATUS_POLL_SECONDS = 2.0
CHAT_STATUS_KEEPALIVE_SECONDS = 15.0


@router.get("/{chat_id}/context", response_model=ChatContextInspectionResponse)
async def inspect_chat_context(
    chat_id: str,
    chat_ctx: ChatContext = Depends(resolve_chat_context),
    session: AsyncSession = Depends(db_session),
) -> ChatContextInspectionResponse:
    """Inspect the safe chat-local working context, never the runtime trace."""
    if str(chat_ctx.chat_id) != str(chat_id):
        raise HTTPException(status_code=404, detail="Chat not found")
    result = await ChatContextService(session, None, None).inspect_snapshot(
        chat_id=str(chat_ctx.chat_id), owner_id=str(chat_ctx.user_id), tenant_id=str(chat_ctx.tenant_id),
    )
    return ChatContextInspectionResponse.model_validate(result)


@router.put("/{chat_id}/memory-scopes", response_model=ChatContextInspectionResponse)
async def set_chat_memory_scopes(
    chat_id: str, body: ChatMemoryScopesUpdate,
    chat_ctx: ChatContext = Depends(resolve_chat_context), session: AsyncSession = Depends(db_session),
) -> ChatContextInspectionResponse:
    if str(chat_ctx.chat_id) != chat_id:
        raise HTTPException(status_code=404, detail="Chat not found")
    service = ChatContextService(session, None, None)
    try:
        await service.set_memory_scopes(chat_id=chat_id, owner_id=str(chat_ctx.user_id),
                                       keys=body.scope_keys, expected_revision=body.expected_revision)
    except ValueError as exc:
        raise HTTPException(status_code=409 if str(exc) == "stale_revision" else 422, detail=str(exc)) from exc
    await session.commit()
    return ChatContextInspectionResponse.model_validate(await service.inspect_snapshot(
        chat_id=chat_id, owner_id=str(chat_ctx.user_id), tenant_id=str(chat_ctx.tenant_id),
    ))


@router.delete("/{chat_id}/context", response_model=ChatContextResetResponse)
async def reset_chat_context(
    chat_id: str,
    chat_ctx: ChatContext = Depends(resolve_chat_context),
    session: AsyncSession = Depends(db_session),
) -> ChatContextResetResponse:
    """Forget only chat-local working context; transcript and facts remain."""
    if str(chat_ctx.chat_id) != str(chat_id):
        raise HTTPException(status_code=404, detail="Chat not found")
    receipt = await ChatContextService(session, None, None).reset_context(chat_id=str(chat_ctx.chat_id))
    await session.commit()
    return ChatContextResetResponse(revision=receipt.revision, closed_items=receipt.applied_count)


@router.get("/{chat_id}/paused-run")
async def get_paused_run(
    chat_id: str,
    chat_ctx: ChatContext = Depends(resolve_chat_context),
    session: AsyncSession = Depends(db_session),
    current_user: UserCtx = Depends(get_current_user),
) -> dict[str, Any]:
    """Return the one resumable interaction for a chat as the public pause contract.

    A pause can outlive the SSE connection (for example after a page refresh).
    Do not expose the raw ChatTurn row: action/context are normalized through
    the same contract used by the streaming transport.
    """
    try:
        chat_uuid = uuid.UUID(chat_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid chat ID")

    if str(chat_ctx.chat_id) != str(chat_uuid):
        raise HTTPException(status_code=404, detail="Chat not found")

    result = await session.execute(
        select(ChatTurn)
        .where(
            ChatTurn.chat_id == chat_uuid,
            ChatTurn.user_id == uuid.UUID(str(current_user.id)),
            ChatTurn.status.in_(WAITING_STATUSES),
        )
        .order_by(ChatTurn.paused_at.desc(), ChatTurn.started_at.desc())
        .limit(1)
    )
    turn = result.scalar_one_or_none()
    if turn is None or turn.runtime_run_id is None:
        return {"pause": None}

    paused = RuntimeHitlProtocolService.build_paused_from_stop({
        "run_id": str(turn.runtime_run_id),
        "reason": str(turn.pause_status or normalize_chat_turn_status(turn.status)),
        "action": turn.paused_action if isinstance(turn.paused_action, dict) else {},
        "context": turn.paused_context if isinstance(turn.paused_context, dict) else {},
    })
    return {"pause": RuntimeHitlProtocolService.public_pause(paused)}


@router.get("/{chat_id}/active-run", response_model=ActiveChatRunResponse)
async def get_active_chat_run(
    chat_id: str,
    chat_ctx: ChatContext = Depends(resolve_chat_context),
    session: AsyncSession = Depends(db_session),
    current_user: UserCtx = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> ActiveChatRunResponse:
    """Return the current persisted run identity without deriving state from SSE."""
    if str(chat_ctx.chat_id) != str(chat_id):
        raise HTTPException(status_code=404, detail="Chat not found")
    result = await session.execute(
        select(ChatTurn)
        .where(
            ChatTurn.chat_id == uuid.UUID(str(chat_ctx.chat_id)),
            ChatTurn.user_id == uuid.UUID(str(current_user.id)),
            ChatTurn.status.in_(ACTIVE_STATUSES),
        )
        .order_by(ChatTurn.started_at.desc())
        .limit(1)
    )
    turn = result.scalar_one_or_none()
    if turn is None or turn.runtime_run_id is None:
        return ActiveChatRunResponse(run=None)
    activity = await read_chat_stage_snapshot(redis, str(turn.runtime_run_id))
    return ActiveChatRunResponse(run={
        "run_id": str(turn.runtime_run_id),
        "turn_id": str(turn.id),
        "status": normalize_chat_turn_status(turn.status, turn.pause_status),
        "user_message_id": str(turn.user_message_id) if turn.user_message_id else None,
        "stage": activity.get("stage") if activity else None,
        "activity": activity,
    })


@router.get("/status-events")
async def global_chat_status_events(
    request: Request,
    current_user: UserCtx = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> StreamingResponse:
    """Stream the latest persisted lifecycle state for each owned chat.

    This intentionally polls the database instead of relying on Redis Pub/Sub:
    every initial connection and reconnect begins with an authoritative snapshot,
    and no lifecycle change can be lost between a status write and publication.
    """
    owner_id = uuid.UUID(str(current_user.id))
    session_factory = get_session_factory()

    async def _gen() -> AsyncGenerator[str, None]:
        previous_snapshot: str | None = None
        last_keepalive = time.monotonic()
        try:
            while not await request.is_disconnected():
                try:
                    async with session_factory() as status_session:
                        turns = await latest_chat_turns_for_owner(status_session, owner_id=owner_id)

                    stages: dict[str, dict[str, Any]] = {}
                    for turn in turns:
                        if not turn.runtime_run_id or normalize_chat_turn_status(
                            turn.status, turn.pause_status,
                        ) not in ACTIVE_STATUSES + WAITING_STATUSES:
                            continue
                        try:
                            activity = await read_chat_stage_snapshot(redis, str(turn.runtime_run_id))
                        except Exception:
                            activity = None
                        if activity:
                            stages[str(turn.runtime_run_id)] = activity

                    snapshot = build_chat_status_snapshot(turns, stages_by_run_id=stages)
                    serialized = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))
                    if serialized != previous_snapshot:
                        yield f"event: snapshot\ndata: {serialized}\n\n"
                        previous_snapshot = serialized
                        last_keepalive = time.monotonic()
                    elif time.monotonic() - last_keepalive >= CHAT_STATUS_KEEPALIVE_SECONDS:
                        yield ": keepalive\n\n"
                        last_keepalive = time.monotonic()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("chat_status_snapshot_failed user_id=%s", owner_id)
                    if time.monotonic() - last_keepalive >= CHAT_STATUS_KEEPALIVE_SECONDS:
                        yield ": keepalive\n\n"
                        last_keepalive = time.monotonic()
                await asyncio.sleep(CHAT_STATUS_POLL_SECONDS)
        finally:
            logger.debug("chat_status_stream_closed user_id=%s", owner_id)

    return StreamingResponse(_gen(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })


@router.get("/{chat_id}/runs/{run_id}/events")
async def attach_chat_run_events(
    chat_id: str,
    run_id: str,
    chat_ctx: ChatContext = Depends(resolve_chat_context),
    session: AsyncSession = Depends(db_session),
    current_user: UserCtx = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> StreamingResponse:
    """Attach an SSE observer to an existing run; closing it does not cancel work."""
    try:
        run_uuid = uuid.UUID(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid run ID") from exc
    if str(chat_ctx.chat_id) != str(chat_id):
        raise HTTPException(status_code=404, detail="Chat not found")
    subscriber = RuntimeTailSubscriber(
        stream_key=chat_event_stream_key(str(run_uuid)), redis_client=redis,
    )
    await subscriber.subscribe()
    result = await session.execute(
        select(ChatTurn).where(
            ChatTurn.chat_id == uuid.UUID(str(chat_ctx.chat_id)),
            ChatTurn.user_id == uuid.UUID(str(current_user.id)),
            ChatTurn.runtime_run_id == run_uuid,
            ChatTurn.status.in_(ACTIVE_STATUSES),
        ).limit(1)
    )
    turn = result.scalar_one_or_none()
    if turn is None:
        await subscriber.unsubscribe()
        raise HTTPException(status_code=404, detail="Active run not found")
    activity = await read_chat_stage_snapshot(redis, str(run_uuid))
    state_frame = map_service_event_to_sse({
        "type": "state",
        "run_id": str(run_uuid),
        "status": normalize_chat_turn_status(turn.status, turn.pause_status),
        "stage": activity.get("stage") if activity else None,
        "activity": activity,
        "pause_reason": turn.pause_status,
        "user_message_id": str(turn.user_message_id) if turn.user_message_id else None,
    })
    await session.close()

    async def _gen() -> AsyncGenerator[str, None]:
        try:
            yield state_frame or ""
            async for event in subscriber.listen():
                if event.get("type") == "done":
                    break
                payload = event.get("event") if event.get("type") == "service_event" else None
                if isinstance(payload, dict):
                    sse_text = map_service_event_to_sse(payload)
                    if sse_text:
                        yield sse_text
            yield format_chat_sse_done()
        finally:
            await subscriber.unsubscribe()

    return StreamingResponse(_gen(), media_type="text/event-stream")


@router.post("/{chat_id}/runs/{run_id}/cancel")
async def cancel_active_chat_run(
    chat_id: str,
    run_id: str,
    chat_ctx: ChatContext = Depends(resolve_chat_context),
    session: AsyncSession = Depends(db_session),
    current_user: UserCtx = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> dict[str, Any]:
    """Send an explicit Stop command to the execution owner."""
    try:
        run_uuid = uuid.UUID(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid run ID") from exc
    if str(chat_ctx.chat_id) != str(chat_id):
        raise HTTPException(status_code=404, detail="Chat not found")
    result = await session.execute(
        select(ChatTurn).where(
            ChatTurn.chat_id == uuid.UUID(str(chat_ctx.chat_id)),
            ChatTurn.user_id == uuid.UUID(str(current_user.id)),
            ChatTurn.runtime_run_id == run_uuid,
            ChatTurn.status.in_(ACTIVE_STATUSES),
        ).limit(1)
    )
    if result.scalar_one_or_none() is None:
        # The run id is known to the client before runtime setup persists the
        # ChatTurn. Accept Stop during that short startup window only when the
        # server-side owner record matches this chat and user.
        owner_data = await redis.get(chat_run_owner_key(str(run_uuid)))
        try:
            owner = json.loads(owner_data) if owner_data else None
        except (TypeError, ValueError):
            owner = None
        if not isinstance(owner, dict) or owner.get("chat_id") != str(chat_ctx.chat_id) or owner.get("user_id") != str(current_user.id):
            raise HTTPException(status_code=404, detail="Active run not found")
    try:
        await RuntimeRunControlBus().publish_cancel(str(run_uuid), persist_marker=True)
    except Exception as exc:
        logger.warning("chat_run_cancel_publish_failed run_id=%s", run_uuid, exc_info=True)
        raise HTTPException(status_code=503, detail="Не удалось передать команду остановки") from exc
    return {"run_id": str(run_uuid), "accepted": True}


@router.get("/{chat_id}/messages")
async def list_messages(
    chat_id: str,
    limit: int = Query(50, ge=1, le=1000),
    cursor: Optional[str] = Query(None),
    before: Optional[str] = Query(None),
    tail: bool = Query(False),
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
        before_cursor=before,
        newest=tail,
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
    previous_cursor = None
    if len(items) == limit and items:
        if before or tail:
            previous_cursor = f"{items[0]['created_at']}|{items[0]['id']}"
        else:
            next_cursor = f"{items[-1]['created_at']}|{items[-1]['id']}"

    return {"items": items, "next_cursor": next_cursor, "previous_cursor": previous_cursor, "limit": limit}


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
    artifact_ids = [str(item) for item in body.artifact_ids or []]

    if not content:
        raise HTTPException(status_code=400, detail="Content is required")

    idempotency_key = request.headers.get("Idempotency-Key")
    if idempotency_key is not None and len(idempotency_key) > 255:
        raise HTTPException(status_code=400, detail="Idempotency-Key is too long")

    raw_run_id = request.headers.get("X-Run-ID")
    try:
        run_uuid = uuid.UUID(raw_run_id) if raw_run_id else uuid.uuid4()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid X-Run-ID") from exc
    command = ChatRuntimeCommand(
        run_id=run_uuid,
        chat_id=uuid.UUID(chat_ctx.chat_id),
        user_id=uuid.UUID(chat_ctx.user_id),
        tenant_id=uuid.UUID(chat_ctx.tenant_id),
        content=content,
        artifact_ids=artifact_ids,
        idempotency_key=idempotency_key,
    )
    # Register an ACL-bound owner before StreamingResponse starts iterating.
    # This makes Stop usable immediately after the client receives its run id.
    await redis.set(
        chat_run_owner_key(str(run_uuid)),
        json.dumps({"chat_id": str(chat_ctx.chat_id), "user_id": str(chat_ctx.user_id)}),
        ex=CHAT_RUN_OWNER_TTL_SECONDS,
    )

    async def _gen() -> AsyncGenerator[str, None]:
        subscriber = RuntimeTailSubscriber(
            stream_key=chat_event_stream_key(str(run_uuid)), redis_client=redis,
        )
        try:
            await subscriber.subscribe()
            await chat_runtime_runner.start(
                command=command,
                llm_client=llm,
                redis_client=redis,
                session_factory=get_session_factory(),
            )
            # Release the request dependency's DB connection while the SSE
            # observer remains open. Execution owns a separate session.
            await session.close()
            yield map_service_event_to_sse({
                "type": "run_started", "run_id": str(run_uuid), "status": "running",
            }) or ""
            async for event in subscriber.listen():
                if event.get("type") == "done":
                    break
                payload = event.get("event") if event.get("type") == "service_event" else None
                if not isinstance(payload, dict):
                    continue
                try:
                    sse_text = map_service_event_to_sse(payload)
                except Exception as exc:
                    logger.warning("Failed to map detached chat event to SSE: %s", exc)
                    sse_text = None
                if sse_text:
                    yield sse_text
            yield format_chat_sse_done()
        except Exception as e:
            logger.error(f"Error in chat stream: {e}", exc_info=True)
            yield format_chat_sse(ChatSSEEventType.ERROR, ErrorPayload(error="Не удалось обработать запрос. Попробуйте позже.", code="chat_stream_failed"))
            yield format_chat_sse_done()
        finally:
            await subscriber.unsubscribe()

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
    try:
        run_uuid = uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid run ID")

    turn_service = ChatTurnService(session)
    run_result = await session.execute(
        select(ChatTurn).where(
            ChatTurn.runtime_run_id == run_uuid,
            ChatTurn.status.in_(WAITING_STATUSES),
        ).with_for_update()
    )
    turn = run_result.scalar_one_or_none()
    if not turn:
        raise HTTPException(status_code=404, detail="Paused run not found")
    if str(turn.user_id) != str(current_user.id):
        raise HTTPException(status_code=404, detail="Paused run not found")
    if not turn.chat_id:
        raise HTTPException(status_code=404, detail="Paused run not found")
    chat_ctx = await resolve_chat_context(
        chat_id=str(turn.chat_id),
        session=session,
        current_user=current_user,
    )
    tenant_uuid_val = uuid.UUID(chat_ctx.tenant_id)
    paused_action = turn.paused_action
    paused_context = turn.paused_context

    expected_pause_id = (paused_action or {}).get("pause_id")
    if expected_pause_id and body.pause_id != expected_pause_id:
        raise HTTPException(status_code=409, detail="Уточнение устарело. Обновите состояние чата.")

    user_input = body.input
    try:
        from app.runtime.interaction import interaction_from_context
        interaction = interaction_from_context(paused_context)
        action, resolved_input, interaction_response = RuntimeResumeCheckpointService.resolve_request(body, paused_context)
        if interaction is not None:
            normalized_input = resolved_input
            body = body.model_copy(update={"action": action})
        else:
            normalized_input = RuntimeResumeCheckpointService.validate_action(
                pause_status=str(turn.pause_status or ""), action=body.action, user_input=user_input,
            )
    except RuntimeResumeValidationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if body.action is RuntimeResumeAction.CANCEL:
        await turn_service.cancel_turn(turn.id, error_message="Cancelled by user")
        if interaction is not None and interaction.requester.plan_id:
            from app.runtime.plan_store import SqlPlanStore
            await SqlPlanStore(session).cancel_plan(uuid.UUID(interaction.requester.plan_id), reason="user_cancelled")
        if turn.chat_id:
            await ChatContextService(session, None, None).cancel_turn_context(
                chat_id=str(turn.chat_id), chat_turn_id=str(turn.id),
            )
        await session.commit()
        async def _cancel_gen() -> AsyncGenerator[str, None]:
            yield map_service_event_to_sse({
                "type": "state", "run_id": str(run_uuid), "status": "cancelled",
                "user_message_id": str(turn.user_message_id) if turn.user_message_id else None,
            }) or ""
            yield map_service_event_to_sse({"type": "cancelled", "run_id": str(run_uuid)}) or ""
            yield format_chat_sse_done()
        return StreamingResponse(_cancel_gen(), media_type="text/event-stream")

    checkpoint_service = RuntimeResumeCheckpointService.from_session(session)
    original_goal = await checkpoint_service.resolve_original_goal(run_uuid)
    if original_goal is None and isinstance(paused_context, dict):
        # Root TurnPreflight can pause before a plan exists. Its runtime-owned
        # pause context carries the original goal precisely for this fallback.
        candidate = str(paused_context.get("original_goal") or "").strip()
        original_goal = candidate or None
    if original_goal is None:
        raise HTTPException(status_code=409, detail="Runtime continuation context not found")

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
    if interaction is not None:
        checkpoint["interaction_response"] = interaction_response

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
                raise HTTPException(status_code=503, detail="Не удалось подтвердить действие; повторите ответ.") from _ce


    # Keep one ChatTurn for the entire paused/resumed lifecycle.  Cancelling
    # this row before continuation made the next request look stale and also
    # created a duplicate ChatTurn for the same runtime run.
    claimed_turn = await turn_service.resume_turn(turn.id)
    if claimed_turn is None:
        raise HTTPException(status_code=409, detail="Paused run is no longer available")
    await session.commit()
    resume_content = build_resume_content(
        action=body.action.value,
        user_input=normalized_input,
        paused_action=paused_action if isinstance(paused_action, dict) else None,
        paused_context=paused_context if isinstance(paused_context, dict) else None,
    )

    resume_redis = get_redis()
    resume_llm = get_llm_client()
    command = ChatRuntimeCommand(
        run_id=run_uuid,
        chat_id=uuid.UUID(str(turn.chat_id)),
        user_id=uuid.UUID(str(current_user.id)),
        tenant_id=tenant_uuid_val,
        content=resume_content,
        artifact_ids=[],
        continuation_meta={
            "resume_checkpoint": checkpoint,
            "resumed_from_run_id": run_id,
        },
        resumed_turn_id=uuid.UUID(str(turn.id)),
        confirmation_tokens=confirmation_tokens,
        persist_user_message=interaction is not None or body.action is RuntimeResumeAction.INPUT,
    )
    resume_subscriber = RuntimeTailSubscriber(
        stream_key=chat_event_stream_key(str(run_uuid)), redis_client=resume_redis,
    )
    await resume_subscriber.subscribe()
    await chat_runtime_runner.start(
        command=command,
        llm_client=resume_llm,
        redis_client=resume_redis,
        session_factory=get_session_factory(),
    )
    await session.close()

    async def _resume_gen() -> AsyncGenerator[str, None]:
        try:
            yield map_service_event_to_sse({
                "type": "run_started", "run_id": str(run_uuid), "status": "running",
            }) or ""
            async for event in resume_subscriber.listen():
                if event.get("type") == "done":
                    break
                payload = event.get("event") if event.get("type") == "service_event" else None
                if not isinstance(payload, dict):
                    continue
                try:
                    sse_text = map_service_event_to_sse(payload)
                except Exception as exc:
                    logger.warning("Failed to map resume event to SSE: %s", exc)
                    sse_text = None
                if sse_text:
                    yield sse_text
            yield format_chat_sse_done()
        except Exception as e:
            logger.error(f"Error in resume stream: {e}", exc_info=True)
            yield format_chat_sse(ChatSSEEventType.ERROR, ErrorPayload(error="Не удалось обработать запрос. Попробуйте позже.", code="chat_stream_failed"))
            yield format_chat_sse_done()
        finally:
            await resume_subscriber.unsubscribe()

    return StreamingResponse(_resume_gen(), media_type="text/event-stream")
