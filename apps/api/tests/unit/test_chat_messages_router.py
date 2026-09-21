from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api.deps import ChatContext
from app.api.v1.routers.chat import messages as chat_messages
from app.core.security import UserCtx
from app.schemas.chats import ChatMessageStreamRequest
from app.schemas.confirmations import ConfirmationIssueRequest
from app.schemas.runtime_continuation import RuntimeResumeAction, RuntimeResumeRequest


class _Result:
    def __init__(self, row):
        self._row = row

    def scalar_one_or_none(self):
        return self._row


def _request_with_headers(headers: dict[str, str]) -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/chat/placeholder/messages",
        "headers": [(k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in headers.items()],
    }

    async def _receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request(scope, _receive)


@pytest.mark.asyncio
async def test_issue_confirmation_token_returns_token_for_chat_owner(monkeypatch):
    chat_id = str(uuid4())
    user_id = str(uuid4())

    chat_ctx = ChatContext(chat_id=chat_id, tenant_id=str(uuid4()), user_id=user_id)
    current_user = UserCtx(id=user_id, tenant_ids=[chat_ctx.tenant_id])

    session = AsyncMock()
    session.execute.return_value = _Result(SimpleNamespace(owner_id=user_id))

    class _Service:
        def issue(self, *, user_id, chat_id, fingerprint):
            assert fingerprint == "fp-1234567890abcdef"
            return "token-xyz", datetime(2030, 1, 1, tzinfo=timezone.utc)

    monkeypatch.setattr(chat_messages, "get_confirmation_service", lambda: _Service())

    response = await chat_messages.issue_confirmation_token(
        chat_id=chat_id,
        body=ConfirmationIssueRequest(operation_fingerprint="fp-1234567890abcdef"),
        chat_ctx=chat_ctx,
        session=session,
        current_user=current_user,
    )

    assert response.token == "token-xyz"
    assert response.expires_at.year == 2030


@pytest.mark.asyncio
async def test_issue_confirmation_token_rejects_non_owner(monkeypatch):
    chat_id = str(uuid4())
    chat_ctx = ChatContext(chat_id=chat_id, tenant_id=str(uuid4()), user_id=str(uuid4()))
    current_user = UserCtx(id=str(uuid4()), tenant_ids=[chat_ctx.tenant_id])

    session = AsyncMock()
    session.execute.return_value = _Result(SimpleNamespace(owner_id=str(uuid4())))

    monkeypatch.setattr(chat_messages, "get_confirmation_service", lambda: None)

    with pytest.raises(HTTPException) as exc:
        await chat_messages.issue_confirmation_token(
            chat_id=chat_id,
            body=ConfirmationIssueRequest(operation_fingerprint="fp-1234567890abcdef"),
            chat_ctx=chat_ctx,
            session=session,
            current_user=current_user,
        )

    assert exc.value.status_code == 404
    assert "Chat not found" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_send_message_stream_passes_confirmation_tokens(monkeypatch):
    chat_id = str(uuid4())
    user_id = str(uuid4())
    tenant_id = str(uuid4())
    chat_ctx = ChatContext(chat_id=chat_id, tenant_id=tenant_id, user_id=user_id)

    captured: dict[str, object] = {}

    class _Service:
        def __init__(self, **kwargs):
            captured["init_kwargs"] = kwargs

        async def send_message_stream(self, **kwargs):
            captured["stream_kwargs"] = kwargs
            yield {"type": "noop"}

    monkeypatch.setattr(chat_messages, "ChatStreamService", _Service)
    monkeypatch.setattr(chat_messages, "map_service_event_to_sse", lambda _: "event: status\ndata: {}\n\n")

    request = _request_with_headers({"Idempotency-Key": "idem-123"})

    response = await chat_messages.send_message_stream(
        chat_id=chat_id,
        body=ChatMessageStreamRequest(
            content="hello",
            execution_mode="thinking",
            confirmation_tokens=["tok-1", "tok-2"],
            artifact_ids=[str(uuid4())],
            agent_slug="default",
        ),
        request=request,
        chat_ctx=chat_ctx,
        session=AsyncMock(),
        redis=AsyncMock(),
        llm=AsyncMock(),
        _rl=None,
    )

    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk)

    stream_kwargs = captured["stream_kwargs"]
    assert stream_kwargs["confirmation_tokens"] == ["tok-1", "tok-2"]
    assert str(stream_kwargs["execution_mode"].value) == "thinking"
    assert stream_kwargs["idempotency_key"] == "idem-123"
    assert any("event: done" in chunk for chunk in chunks)


@pytest.mark.asyncio
async def test_resume_run_reuses_paused_chat_turn(monkeypatch):
    chat_id = uuid4()
    user_id = uuid4()
    tenant_id = uuid4()
    run_id = uuid4()
    turn = SimpleNamespace(
        id=uuid4(),
        chat_id=chat_id,
        user_id=user_id,
        status="paused",
        pause_status="waiting_input",
        paused_action={"kind": "input"},
        paused_context={"question": "Какая тема?"},
        paused_at=datetime.now(timezone.utc),
    )
    captured: dict[str, object] = {}

    class _Service:
        def __init__(self, **kwargs):
            captured["init_kwargs"] = kwargs

        async def send_message_stream(self, **kwargs):
            captured["stream_kwargs"] = kwargs
            yield {"type": "final", "message_id": "assistant-1"}

    monkeypatch.setattr(chat_messages, "ChatStreamService", _Service)
    monkeypatch.setattr(chat_messages, "map_service_event_to_sse", lambda _: "event: final\ndata: {}\n\n")

    session = AsyncMock()
    session.execute.side_effect = [
        _Result(turn),
        _Result(SimpleNamespace(goal="Что мне почитать?")),
        _Result(turn),
    ]
    response = await chat_messages.resume_run(
        run_id=str(run_id),
        body=RuntimeResumeRequest(
            action=RuntimeResumeAction.INPUT,
            input="Сетевая инженерия",
        ),
        session=session,
        current_user=UserCtx(id=str(user_id), tenant_ids=[str(tenant_id)]),
        _rl=None,
    )

    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk)

    assert turn.status == "resumed"
    assert captured["stream_kwargs"]["resumed_turn_id"] == str(turn.id)
    assert captured["stream_kwargs"]["continuation_meta"]["resumed_from_run_id"] == str(run_id)
    checkpoint = captured["stream_kwargs"]["continuation_meta"]["resume_checkpoint"]
    assert checkpoint["original_goal"] == "Что мне почитать?"
    session.commit.assert_awaited_once()
    assert any("event: done" in chunk for chunk in chunks)


@pytest.mark.asyncio
async def test_resume_preflight_clarify_uses_goal_from_pause_context(monkeypatch):
    chat_id, user_id, tenant_id, run_id = uuid4(), uuid4(), uuid4(), uuid4()
    turn = SimpleNamespace(
        id=uuid4(), chat_id=chat_id, user_id=user_id, status="paused",
        pause_status="waiting_input", paused_action=None,
        paused_context={"question": "Какой проект?", "original_goal": "Обнови glossary"},
        paused_at=datetime.now(timezone.utc),
    )
    captured: dict[str, object] = {}

    class _Service:
        def __init__(self, **_kwargs):
            pass

        async def send_message_stream(self, **kwargs):
            captured.update(kwargs)
            yield {"type": "final", "message_id": "assistant-1"}

    monkeypatch.setattr(chat_messages, "ChatStreamService", _Service)
    monkeypatch.setattr(chat_messages, "map_service_event_to_sse", lambda _: "event: final\ndata: {}\n\n")
    session = AsyncMock()
    session.execute.side_effect = [_Result(turn), _Result(None), _Result(turn)]

    response = await chat_messages.resume_run(
        run_id=str(run_id),
        body=RuntimeResumeRequest(action=RuntimeResumeAction.INPUT, input="Проект Нема"),
        session=session,
        current_user=UserCtx(id=str(user_id), tenant_ids=[str(tenant_id)]),
        _rl=None,
    )
    async for _ in response.body_iterator:
        pass

    checkpoint = captured["continuation_meta"]["resume_checkpoint"]
    assert checkpoint["original_goal"] == "Обнови glossary"


@pytest.mark.asyncio
async def test_resume_cancel_terminates_confirmation_without_reentering_runtime(monkeypatch):
    user_id, tenant_id, run_id = uuid4(), uuid4(), uuid4()
    turn = SimpleNamespace(
        id=uuid4(), chat_id=uuid4(), user_id=user_id, status="paused",
        pause_status="waiting_confirmation", paused_action={}, paused_context={}, paused_at=datetime.now(timezone.utc),
    )
    session = AsyncMock()
    session.execute.side_effect = [_Result(turn), _Result(turn)]

    class _UnexpectedService:
        def __init__(self, **_kwargs):
            raise AssertionError("Cancelled confirmation must not start ChatStreamService")

    monkeypatch.setattr(chat_messages, "ChatStreamService", _UnexpectedService)
    class _ContextService:
        def __init__(self, *_args, **_kwargs):
            pass

        async def cancel_turn_context(self, **_kwargs):
            return None

    # The router owns cancellation orchestration; context reconciliation is
    # covered independently and must not consume this router fixture's SQL
    # result queue.
    monkeypatch.setattr(chat_messages, "ChatContextService", _ContextService)
    response = await chat_messages.resume_run(
        run_id=str(run_id),
        body=RuntimeResumeRequest(action=RuntimeResumeAction.CANCEL),
        session=session,
        current_user=UserCtx(id=str(user_id), tenant_ids=[str(tenant_id)]),
        _rl=None,
    )

    chunks = [chunk async for chunk in response.body_iterator]
    assert turn.status == "cancelled"
    assert any("event: done" in chunk for chunk in chunks)


@pytest.mark.asyncio
async def test_get_paused_run_returns_public_contract_for_preflight_clarification():
    chat_id, user_id, run_id = uuid4(), uuid4(), uuid4()
    turn = SimpleNamespace(
        runtime_run_id=run_id,
        pause_status="waiting_input",
        paused_action={"kind": "input"},
        paused_context={"question": "Для какого проекта?", "original_goal": "Обнови регламент"},
    )
    session = AsyncMock()
    session.execute.return_value = _Result(turn)

    response = await chat_messages.get_paused_run(
        chat_id=str(chat_id),
        chat_ctx=ChatContext(chat_id=str(chat_id), tenant_id=str(uuid4()), user_id=str(user_id)),
        session=session,
        current_user=UserCtx(id=str(user_id), tenant_ids=[str(uuid4())]),
    )

    assert response["pause"]["run_id"] == str(run_id)
    assert response["pause"]["reason"] == "waiting_input"
    assert response["pause"]["action"]["kind"] == "input"
    assert response["pause"]["context"]["question"] == "Для какого проекта?"


@pytest.mark.asyncio
async def test_get_paused_run_returns_confirmation_question_from_action():
    chat_id, user_id, run_id = uuid4(), uuid4(), uuid4()
    turn = SimpleNamespace(
        runtime_run_id=run_id,
        pause_status="waiting_confirmation",
        paused_action={
            "kind": "confirm",
            "question": "Подтвердить публикацию изменений?",
            "operation_fingerprint": "fingerprint-1",
        },
        paused_context={},
    )
    session = AsyncMock()
    session.execute.return_value = _Result(turn)

    response = await chat_messages.get_paused_run(
        chat_id=str(chat_id),
        chat_ctx=ChatContext(chat_id=str(chat_id), tenant_id=str(uuid4()), user_id=str(user_id)),
        session=session,
        current_user=UserCtx(id=str(user_id), tenant_ids=[str(uuid4())]),
    )

    assert response["pause"]["reason"] == "waiting_confirmation"
    assert response["pause"]["action"]["question"] == "Подтвердить публикацию изменений?"
