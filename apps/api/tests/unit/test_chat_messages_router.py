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
            confirmation_tokens=["tok-1", "tok-2"],
            attachment_ids=[str(uuid4())],
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
    assert stream_kwargs["idempotency_key"] == "idem-123"
    assert any("event: done" in chunk for chunk in chunks)
