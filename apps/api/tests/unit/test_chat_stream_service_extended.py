"""Extended unit tests for ChatStreamService.

Covers turn idempotency lifecycle states, legacy Redis idempotency helpers,
send_message_stream transport branches (snapshot failure recovery, attachment
resolution, resumed turns, error mapping) and the _run_with_router pipeline
event translation.
"""
from __future__ import annotations

import asyncio
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents import ToolContext
from app.agents.contracts import MissingRequirements
from app.core.exceptions import AgentUnavailableError, ChatAttachmentNotFoundError
from app.core.idempotency import IdempotencyManager
from app.runtime import RuntimeEvent, RuntimeEventType
from app.services.chat_context_contracts import ChatContextSnapshot
from app.services.chat_stream_service import ChatStreamService
from app.services.chat_turn_service import CHAT_TURN_LEASE_SECONDS, ChatTurnIdempotencyError

CHAT_ID = "00000000-0000-0000-0000-000000000010"
USER_ID = "00000000-0000-0000-0000-000000000020"


def make_chat(**overrides: Any) -> SimpleNamespace:
    payload = {"id": CHAT_ID, "tenant_id": "00000000-0000-0000-0000-000000000001", "owner_id": USER_ID}
    payload.update(overrides)
    return SimpleNamespace(**payload)


def make_turn(
    status: str = "running",
    *,
    pause_status: str | None = None,
    heartbeat_at: datetime | None = None,
    started_at: datetime | None = None,
    user_message_id: str | None = "11111111-1111-1111-1111-111111111111",
    assistant_message_id: str | None = "22222222-2222-2222-2222-222222222222",
) -> SimpleNamespace:
    return SimpleNamespace(
        status=status,
        pause_status=pause_status,
        heartbeat_at=heartbeat_at,
        started_at=started_at,
        user_message_id=user_message_id,
        assistant_message_id=assistant_message_id,
        error_message=None,
        completed_at=None,
    )


def event_gen(events: list[dict[str, Any]], captured: dict[str, Any] | None = None):
    """Async generator fn that records its kwargs and yields events."""
    async def gen(*args: Any, **kwargs: Any):
        if captured is not None:
            captured["args"] = args
            captured["kwargs"] = kwargs
        for event in events:
            yield event
    return gen


def raising_gen(exc: BaseException):
    async def gen(*args: Any, **kwargs: Any):
        raise exc
        yield {}  # pragma: no cover
    return gen


def message_listener(messages: list[dict[str, Any]]):
    async def listen() -> Any:
        for message in messages:
            yield message
    return listen


@pytest.fixture
def chats_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.get_chat_by_id = AsyncMock(return_value=make_chat())
    return repo


@pytest.fixture
def messages_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.create_message = AsyncMock(return_value=SimpleNamespace(id="m-1", created_at=None))
    repo.get_recent_chat_messages = AsyncMock(return_value=[])
    return repo


@pytest.fixture
def service(mock_session, mock_redis, mock_llm_client, chats_repo, messages_repo) -> ChatStreamService:
    svc = ChatStreamService(
        session=mock_session,
        redis=mock_redis,
        llm_client=mock_llm_client,
        chats_repo=chats_repo,
        messages_repo=messages_repo,
    )
    svc.chat_turn_service.build_request_hash = MagicMock(return_value="hash-1")
    svc.chat_turn_service.has_payload_mismatch = AsyncMock(return_value=False)
    svc.chat_turn_service.get_latest_by_idempotency_key = AsyncMock(return_value=None)
    svc.chat_turn_service.get_by_id = AsyncMock(return_value=None)
    svc.chat_turn_service.fail_turn = AsyncMock()
    svc.context_service.load_chat_context = AsyncMock(return_value=[])
    svc.context_service.load_snapshot = AsyncMock(
        return_value=ChatContextSnapshot(chat_id=CHAT_ID, artifacts=[])
    )
    svc.attachment_service.artifact_metadata = AsyncMock(return_value=[])
    svc.attachment_service.build_runtime_artifact_contexts = AsyncMock(return_value=[])
    svc.attachment_service.bind_artifacts_to_message = AsyncMock()
    svc.idempotency.get_cached_result = AsyncMock(return_value=None)
    svc.idempotency.cache_result = AsyncMock()
    return svc


async def collect(gen: Any) -> list[dict[str, Any]]:
    return [event async for event in gen]


class TestCheckTurnIdempotency:
    async def test_payload_mismatch_returns_conflict_without_turn_lookup(self, service):
        service.chat_turn_service.has_payload_mismatch = AsyncMock(return_value=True)

        result = await service.check_turn_idempotency(
            idempotency_key="idem", chat_id=CHAT_ID, user_id=USER_ID, content="hello",
        )

        assert result == {"state": "conflict"}
        service.chat_turn_service.get_latest_by_idempotency_key.assert_not_awaited()

    async def test_request_hash_includes_sorted_artifact_ids(self, service):
        service.chat_turn_service.build_request_hash = MagicMock(return_value="hash-art")

        await service.check_turn_idempotency(
            idempotency_key="idem", chat_id=CHAT_ID, user_id=USER_ID,
            content="hello", artifact_ids=["b-id", "a-id"],
        )

        service.chat_turn_service.build_request_hash.assert_called_once_with(
            "hello||artifacts:a-id,b-id"
        )

    async def test_no_turn_returns_none(self, service):
        assert await service.check_turn_idempotency(
            idempotency_key="idem", chat_id=CHAT_ID, user_id=USER_ID, content="hello",
        ) is None

    async def test_running_with_fresh_heartbeat_returns_processing(self, service):
        turn = make_turn("running", heartbeat_at=datetime.now(timezone.utc))
        service.chat_turn_service.get_latest_by_idempotency_key = AsyncMock(return_value=turn)

        result = await service.check_turn_idempotency(
            idempotency_key="idem", chat_id=CHAT_ID, user_id=USER_ID, content="hello",
        )

        assert result == {"state": "processing"}
        service.session.flush.assert_not_awaited()

    async def test_running_with_expired_lease_fails_turn(self, service):
        stale = datetime.now(timezone.utc) - timedelta(seconds=CHAT_TURN_LEASE_SECONDS + 30)
        turn = make_turn("running", heartbeat_at=stale)
        service.chat_turn_service.get_latest_by_idempotency_key = AsyncMock(return_value=turn)

        result = await service.check_turn_idempotency(
            idempotency_key="idem", chat_id=CHAT_ID, user_id=USER_ID, content="hello",
        )

        assert result == {
            "state": "terminal",
            "status": "failed",
            "error": "The previous request stopped before completing. Start a new request.",
        }
        assert turn.status == "failed"
        assert turn.error_message == "runtime_lease_expired"
        assert turn.completed_at is not None
        service.session.flush.assert_awaited_once()
        service.session.commit.assert_awaited_once()

    async def test_running_with_expired_started_at_fallback_fails_turn(self, service):
        stale = datetime.now(timezone.utc) - timedelta(seconds=CHAT_TURN_LEASE_SECONDS * 3)
        turn = make_turn("running", heartbeat_at=None, started_at=stale)
        service.chat_turn_service.get_latest_by_idempotency_key = AsyncMock(return_value=turn)

        result = await service.check_turn_idempotency(
            idempotency_key="idem", chat_id=CHAT_ID, user_id=USER_ID, content="hello",
        )

        assert result["state"] == "terminal"

    async def test_running_without_any_timestamps_returns_processing(self, service):
        turn = make_turn("running", heartbeat_at=None, started_at=None)
        service.chat_turn_service.get_latest_by_idempotency_key = AsyncMock(return_value=turn)

        result = await service.check_turn_idempotency(
            idempotency_key="idem", chat_id=CHAT_ID, user_id=USER_ID, content="hello",
        )

        assert result == {"state": "processing"}

    async def test_completed_with_both_messages_returns_completed(self, service):
        turn = make_turn("completed")
        service.chat_turn_service.get_latest_by_idempotency_key = AsyncMock(return_value=turn)

        result = await service.check_turn_idempotency(
            idempotency_key="idem", chat_id=CHAT_ID, user_id=USER_ID, content="hello",
        )

        assert result == {
            "state": "completed",
            "user_message_id": "11111111-1111-1111-1111-111111111111",
            "assistant_message_id": "22222222-2222-2222-2222-222222222222",
        }

    async def test_completed_without_assistant_message_returns_none(self, service):
        turn = make_turn("completed", assistant_message_id=None)
        service.chat_turn_service.get_latest_by_idempotency_key = AsyncMock(return_value=turn)

        assert await service.check_turn_idempotency(
            idempotency_key="idem", chat_id=CHAT_ID, user_id=USER_ID, content="hello",
        ) is None

    @pytest.mark.parametrize("status", ["failed", "cancelled"])
    async def test_terminal_statuses_return_terminal(self, service, status):
        turn = make_turn(status)
        service.chat_turn_service.get_latest_by_idempotency_key = AsyncMock(return_value=turn)

        result = await service.check_turn_idempotency(
            idempotency_key="idem", chat_id=CHAT_ID, user_id=USER_ID, content="hello",
        )

        assert result == {
            "state": "terminal",
            "status": status,
            "error": "The previous request did not complete",
        }

    @pytest.mark.parametrize(
        "status,pause_status",
        [("waiting_input", None), ("waiting_confirmation", None), ("paused", "waiting_confirmation")],
    )
    async def test_waiting_statuses_return_paused(self, service, status, pause_status):
        turn = make_turn(status, pause_status=pause_status)
        service.chat_turn_service.get_latest_by_idempotency_key = AsyncMock(return_value=turn)

        result = await service.check_turn_idempotency(
            idempotency_key="idem", chat_id=CHAT_ID, user_id=USER_ID, content="hello",
        )

        assert result == {"state": "paused"}

    @pytest.mark.parametrize("legacy", ["started", "resumed"])
    async def test_legacy_active_statuses_map_to_processing(self, service, legacy):
        turn = make_turn(legacy, heartbeat_at=datetime.now(timezone.utc))
        service.chat_turn_service.get_latest_by_idempotency_key = AsyncMock(return_value=turn)

        result = await service.check_turn_idempotency(
            idempotency_key="idem", chat_id=CHAT_ID, user_id=USER_ID, content="hello",
        )

        assert result == {"state": "processing"}


class TestLegacyIdempotencyHelpers:
    async def test_load_chat_context_delegates_with_limit(self, service):
        service.context_service.load_chat_context = AsyncMock(return_value=[{"role": "user", "content": "x"}])

        result = await service.load_chat_context(CHAT_ID, limit=7)

        assert result == [{"role": "user", "content": "x"}]
        service.context_service.load_chat_context.assert_awaited_once_with(CHAT_ID, limit=7)

    async def test_check_idempotency_returns_cached_when_hash_matches(self, service):
        service.idempotency.get_cached_result = AsyncMock(
            return_value={"request_hash": "hash-1", "user_message_id": "u1", "assistant_message_id": "a1"}
        )

        cached = await service.check_idempotency("idem", CHAT_ID, USER_ID, "hash-1")

        assert cached == {"request_hash": "hash-1", "user_message_id": "u1", "assistant_message_id": "a1"}
        service.idempotency.get_cached_result.assert_awaited_once_with(
            ChatStreamService._scoped_idempotency_key(
                idempotency_key="idem", chat_id=CHAT_ID, user_id=USER_ID,
            )
        )

    async def test_check_idempotency_conflict_on_hash_mismatch(self, service):
        service.idempotency.get_cached_result = AsyncMock(
            return_value={"request_hash": "other", "user_message_id": "u1", "assistant_message_id": "a1"}
        )

        assert await service.check_idempotency("idem", CHAT_ID, USER_ID, "hash-1") == {"state": "conflict"}

    async def test_store_idempotency_caches_scoped_payload(self, service):
        await service.store_idempotency(
            "idem", "u1", "a1", chat_id=CHAT_ID, user_id=USER_ID, request_hash="hash-1",
        )

        service.idempotency.cache_result.assert_awaited_once()
        args = service.idempotency.cache_result.await_args
        key = args.args[0]
        payload = args.args[1]
        assert key == ChatStreamService._scoped_idempotency_key(
            idempotency_key="idem", chat_id=CHAT_ID, user_id=USER_ID,
        )
        assert payload["user_message_id"] == "u1"
        assert payload["assistant_message_id"] == "a1"
        assert payload["chat_id"] == CHAT_ID
        assert payload["user_id"] == USER_ID
        assert payload["request_hash"] == "hash-1"
        assert "timestamp" in payload


class TestSendMessageStream:
    async def test_terminal_turn_state_yields_previous_attempt_failed(self, service):
        service.check_turn_idempotency = AsyncMock(return_value={
            "state": "terminal", "status": "failed", "error": "boom-reason",
        })

        events = await collect(service.send_message_stream(
            chat_id=CHAT_ID, user_id=USER_ID, content="hi", idempotency_key="idem",
        ))

        assert events == [{
            "type": "error",
            "error": "boom-reason",
            "code": "idempotency_previous_attempt_failed",
        }]

    async def test_paused_turn_state_yields_paused_error(self, service):
        service.check_turn_idempotency = AsyncMock(return_value={"state": "paused"})

        events = await collect(service.send_message_stream(
            chat_id=CHAT_ID, user_id=USER_ID, content="hi", idempotency_key="idem",
        ))

        assert events == [{
            "type": "error",
            "error": "This request is paused; continue it through the resume action",
            "code": "idempotency_paused",
        }]

    async def test_legacy_cache_hit_yields_cached_event(self, service):
        service.check_turn_idempotency = AsyncMock(return_value=None)
        service.check_idempotency = AsyncMock(return_value={
            "user_message_id": "u1", "assistant_message_id": "a1",
        })

        events = await collect(service.send_message_stream(
            chat_id=CHAT_ID, user_id=USER_ID, content="hi", idempotency_key="idem",
        ))

        assert events == [{"type": "cached", "user_message_id": "u1", "assistant_message_id": "a1"}]

    async def test_legacy_cache_conflict_yields_conflict_error(self, service):
        service.check_turn_idempotency = AsyncMock(return_value=None)
        service.check_idempotency = AsyncMock(return_value={"state": "conflict"})

        events = await collect(service.send_message_stream(
            chat_id=CHAT_ID, user_id=USER_ID, content="hi", idempotency_key="idem",
        ))

        assert events[-1]["code"] == "idempotency_conflict"

    async def test_missing_chat_yields_chat_not_found(self, service, chats_repo):
        chats_repo.get_chat_by_id = AsyncMock(return_value=None)

        events = await collect(service.send_message_stream(
            chat_id=CHAT_ID, user_id=USER_ID, content="hi",
        ))

        assert events == [{"type": "error", "error": "Chat not found", "code": "chat_not_found"}]

    async def test_snapshot_failure_rolls_back_and_uses_empty_snapshot(self, service, chats_repo, mock_session):
        service.context_service.load_snapshot = AsyncMock(side_effect=RuntimeError("snapshot boom"))
        chats_repo.get_chat_by_id = AsyncMock(side_effect=[make_chat(), make_chat()])
        captured: dict[str, Any] = {}
        service.turn_orchestrator.execute_turn = event_gen([{"type": "status"}], captured)
        metric = MagicMock()
        with patch("app.core.prometheus_metrics.chat_context_snapshot_load_total", metric):
            events = await collect(service.send_message_stream(
                chat_id=CHAT_ID, user_id=USER_ID, content="hi",
            ))

        assert events == [{"type": "status"}]
        mock_session.rollback.assert_awaited_once()
        assert chats_repo.get_chat_by_id.await_count == 2
        metric.labels.assert_called_once_with(status="failed")
        metric.labels.return_value.inc.assert_called_once_with()
        snapshot = captured["kwargs"]["preloaded_context_snapshot"]
        assert isinstance(snapshot, ChatContextSnapshot)
        assert snapshot.chat_id == CHAT_ID
        assert snapshot.artifacts == []

    async def test_snapshot_failure_when_chat_disappears_yields_not_found(self, service, chats_repo):
        service.context_service.load_snapshot = AsyncMock(side_effect=RuntimeError("snapshot boom"))
        chats_repo.get_chat_by_id = AsyncMock(side_effect=[make_chat(), None])
        with patch("app.core.prometheus_metrics.chat_context_snapshot_load_total", MagicMock()):
            events = await collect(service.send_message_stream(
                chat_id=CHAT_ID, user_id=USER_ID, content="hi",
            ))

        assert events == [{"type": "error", "error": "Chat not found", "code": "chat_not_found"}]

    async def test_non_snapshot_payload_is_replaced_by_empty_snapshot(self, service):
        service.context_service.load_snapshot = AsyncMock(return_value=SimpleNamespace(unexpected=True))
        captured: dict[str, Any] = {}
        service.turn_orchestrator.execute_turn = event_gen([{"type": "ok"}], captured)

        events = await collect(service.send_message_stream(
            chat_id=CHAT_ID, user_id=USER_ID, content="hi",
        ))

        assert events == [{"type": "ok"}]
        snapshot = captured["kwargs"]["preloaded_context_snapshot"]
        assert isinstance(snapshot, ChatContextSnapshot)
        assert snapshot.artifacts == []

    async def test_missing_attachment_yields_attachment_not_found(self, service):
        service.attachment_service.artifact_metadata = AsyncMock(
            side_effect=ChatAttachmentNotFoundError("att-1")
        )

        events = await collect(service.send_message_stream(
            chat_id=CHAT_ID, user_id=USER_ID, content="hi", artifact_ids=["att-1"],
        ))

        assert events == [{
            "type": "error",
            "error": "Attachment not found or access denied",
            "code": "attachment_not_found",
        }]

    async def test_delegates_to_turn_orchestrator_with_transport_kwargs(self, service):
        captured: dict[str, Any] = {}
        service.turn_orchestrator.execute_turn = event_gen([{"type": "delta", "content": "x"}], captured)
        context = [{"role": "user", "content": "hi"}]
        service.context_service.load_chat_context = AsyncMock(return_value=context)

        events = await collect(service.send_message_stream(
            chat_id=CHAT_ID,
            user_id=USER_ID,
            content="hi",
            tenant_id="00000000-0000-0000-0000-000000000001",
            artifact_ids=["att-1"],
            confirmation_tokens=["tok-1"],
            idempotency_key="idem",
            continuation_meta={"k": "v"},
            resumed_turn_id="turn-7",
            persist_user_message=False,
            runtime_run_id="run-7",
            cancellation_reason="custom reason",
        ))

        assert events == [{"type": "delta", "content": "x"}]
        kwargs = captured["kwargs"]
        assert kwargs["chat_id"] == CHAT_ID
        assert kwargs["user_id"] == USER_ID
        assert kwargs["tenant_id"] == "00000000-0000-0000-0000-000000000001"
        assert kwargs["content"] == "hi"
        assert kwargs["artifact_ids"] == ["att-1"]
        assert kwargs["confirmation_tokens"] == ["tok-1"]
        assert kwargs["idempotency_key"] == "idem"
        assert kwargs["continuation_meta"] == {"k": "v"}
        assert kwargs["resumed_turn_id"] == "turn-7"
        assert kwargs["persist_user_message"] is False
        assert kwargs["requested_runtime_run_id"] == "run-7"
        assert kwargs["cancellation_reason"] == "custom reason"
        assert kwargs["run_with_router"] == service._run_with_router
        assert kwargs["store_idempotency"] == service.store_idempotency
        assert kwargs["bind_attachments"] == service.attachment_service.bind_artifacts_to_message
        assert kwargs["preloaded_context"] == context

    async def test_resumed_turn_restores_current_artifacts_from_original_message(self, service, mock_session):
        service.chat_turn_service.get_by_id = AsyncMock(
            return_value=SimpleNamespace(user_message_id="msg-1")
        )
        mock_session.get = AsyncMock(return_value=SimpleNamespace(
            meta={"attachments": [{"artifact_id": "att-orig"}, {"no_id": True}]}
        ))
        service.attachment_service.artifact_metadata = AsyncMock(return_value=[{"artifact_id": "att-orig"}])
        captured: dict[str, Any] = {}
        service.turn_orchestrator.execute_turn = event_gen([{"type": "ok"}], captured)

        await collect(service.send_message_stream(
            chat_id=CHAT_ID, user_id=USER_ID, content="hi", resumed_turn_id="turn-7",
        ))

        service.attachment_service.build_runtime_artifact_contexts.assert_awaited_once_with(
            artifact_ids=["att-orig"],
            current_artifact_ids=["att-orig"],
            chat_id=CHAT_ID,
            owner_id=USER_ID,
        )
        assert captured["kwargs"]["attachment_contexts"] == []

    async def test_unavailable_history_attachments_are_skipped_silently(self, service):
        service.context_service.load_chat_context = AsyncMock(return_value=[
            {"role": "user", "content": "old", "meta": {"attachments": [
                {"artifact_id": "gone-1"}, {"artifact_id": "kept-2"},
            ]}},
        ])

        async def metadata(chat_id: str, owner_id: str, artifact_ids: list[str]) -> list[dict[str, Any]]:
            if artifact_ids == ["cur-0"]:
                return [{"artifact_id": "cur-0"}]
            if artifact_ids == ["gone-1"]:
                raise ChatAttachmentNotFoundError("gone-1")
            return [{"artifact_id": artifact_ids[0]}]

        service.attachment_service.artifact_metadata = AsyncMock(side_effect=metadata)
        captured: dict[str, Any] = {}
        service.turn_orchestrator.execute_turn = event_gen([{"type": "ok"}], captured)

        events = await collect(service.send_message_stream(
            chat_id=CHAT_ID, user_id=USER_ID, content="hi", artifact_ids=["cur-0"],
        ))

        assert events == [{"type": "ok"}]
        service.attachment_service.build_runtime_artifact_contexts.assert_awaited_once_with(
            artifact_ids=["kept-2", "cur-0"],
            current_artifact_ids=["cur-0"],
            chat_id=CHAT_ID,
            owner_id=USER_ID,
        )

    async def test_duplicate_attachment_ids_are_deduplicated(self, service):
        service.context_service.load_chat_context = AsyncMock(return_value=[
            {"role": "user", "content": "old", "meta": {"attachments": [{"artifact_id": "dup-1"}]}},
        ])

        async def metadata(chat_id: str, owner_id: str, artifact_ids: list[str]) -> list[dict[str, Any]]:
            return [{"artifact_id": artifact_ids[0]}]

        service.attachment_service.artifact_metadata = AsyncMock(side_effect=metadata)
        captured: dict[str, Any] = {}
        service.turn_orchestrator.execute_turn = event_gen([{"type": "ok"}], captured)

        await collect(service.send_message_stream(
            chat_id=CHAT_ID, user_id=USER_ID, content="hi", artifact_ids=["dup-1"],
        ))

        service.attachment_service.build_runtime_artifact_contexts.assert_awaited_once_with(
            artifact_ids=["dup-1"],
            current_artifact_ids=["dup-1"],
            chat_id=CHAT_ID,
            owner_id=USER_ID,
        )

    async def test_turn_idempotency_error_conflict(self, service):
        service.turn_orchestrator.execute_turn = raising_gen(ChatTurnIdempotencyError(conflict=True))

        events = await collect(service.send_message_stream(
            chat_id=CHAT_ID, user_id=USER_ID, content="hi", idempotency_key="idem",
        ))

        assert events[-1]["code"] == "idempotency_conflict"

    async def test_turn_idempotency_error_processing(self, service):
        service.turn_orchestrator.execute_turn = raising_gen(ChatTurnIdempotencyError(conflict=False))

        events = await collect(service.send_message_stream(
            chat_id=CHAT_ID, user_id=USER_ID, content="hi", idempotency_key="idem",
        ))

        assert events[-1]["code"] == "idempotency_processing"

    async def test_generic_error_without_resumed_turn_keeps_session(self, service, mock_session):
        service.turn_orchestrator.execute_turn = raising_gen(RuntimeError("boom"))

        events = await collect(service.send_message_stream(
            chat_id=CHAT_ID, user_id=USER_ID, content="hi",
        ))

        assert events == [{
            "type": "error",
            "error": "Failed to process chat request",
            "code": "chat_stream_failed",
        }]
        mock_session.rollback.assert_not_awaited()
        service.chat_turn_service.fail_turn.assert_not_awaited()

    async def test_generic_error_with_resumed_turn_fails_turn(self, service, mock_session):
        service.turn_orchestrator.execute_turn = raising_gen(RuntimeError("boom"))

        events = await collect(service.send_message_stream(
            chat_id=CHAT_ID, user_id=USER_ID, content="hi", resumed_turn_id="turn-9",
        ))

        assert events[-1]["code"] == "chat_stream_failed"
        mock_session.rollback.assert_awaited_once()
        service.chat_turn_service.fail_turn.assert_awaited_once_with(
            "turn-9", error_message="chat_stream_failed"
        )
        mock_session.commit.assert_awaited_once()


class TestRunWithRouter:
    @staticmethod
    def make_ctx(extra: dict[str, Any] | None = None) -> ToolContext:
        return ToolContext(
            tenant_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            chat_id=uuid.uuid4(),
            extra=extra or {},
        )

    @contextmanager
    def router_patches(
        self,
        pipeline_execute,
        tail_messages: list[dict[str, Any]] | None = None,
        subscribe_error: Exception | None = None,
        unsubscribe_error: Exception | None = None,
    ):
        pipeline_instance = MagicMock()
        pipeline_instance.execute = pipeline_execute
        pipeline_cls = MagicMock(return_value=pipeline_instance)

        subscriber = MagicMock()
        subscriber.subscribe = AsyncMock(
            side_effect=subscribe_error) if subscribe_error else AsyncMock()
        subscriber.unsubscribe = AsyncMock(
            side_effect=unsubscribe_error) if unsubscribe_error else AsyncMock()
        subscriber.listen = message_listener(tail_messages or [])
        subscriber_cls = MagicMock(return_value=subscriber)

        session_factory = object()
        with (
            patch("app.services.chat_stream_service.RuntimePipeline", pipeline_cls),
            patch("app.services.chat_stream_service.RuntimeTailSubscriber", subscriber_cls),
            patch(
                "app.services.chat_stream_service.get_session_factory",
                MagicMock(return_value=session_factory),
            ),
        ):
            yield {
                "pipeline_cls": pipeline_cls,
                "subscriber_cls": subscriber_cls,
                "subscriber": subscriber,
                "session_factory": session_factory,
            }

    async def run(self, service, ctx: ToolContext, **overrides: Any) -> list[dict[str, Any]]:
        params: dict[str, Any] = dict(
            user_id=USER_ID,
            tenant_id="00000000-0000-0000-0000-000000000001",
            llm_messages=[{"role": "user", "content": "hi"}],
            tool_ctx=ctx,
            content="hi",
        )
        params.update(overrides)
        return await collect(service._run_with_router(**params))

    async def test_final_event_maps_to_final_content(self, service):
        ctx = self.make_ctx()
        events_out = [RuntimeEvent(RuntimeEventType.FINAL, {
            "content": "done",
            "sources": [{"id": "s1"}],
            "attachments": [{"id": "a1"}],
            "stop_reason": "stop",
            "run_id": "run-1",
        })]
        with self.router_patches(event_gen(events_out)):
            events = await self.run(service, ctx, runtime_run_id="run-1")

        assert events == [{
            "type": "final_content",
            "run_id": "run-1",
            "content": "done",
            "sources": [{"id": "s1"}],
            "attachments": [{"id": "a1"}],
            "stop_reason": "stop",
        }]

    async def test_final_event_falls_back_to_router_run_id(self, service):
        ctx = self.make_ctx()
        with self.router_patches(event_gen([RuntimeEvent(RuntimeEventType.FINAL, {"content": "x"})])):
            events = await self.run(service, ctx, runtime_run_id="run-2")

        assert events[0]["run_id"] == "run-2"

    async def test_stop_waiting_input_maps_to_run_paused(self, service):
        ctx = self.make_ctx()
        with self.router_patches(event_gen([RuntimeEvent(RuntimeEventType.STOP, {
            "reason": "waiting_input", "run_id": "run-3", "question": "q?",
        })])):
            events = await self.run(service, ctx, runtime_run_id="run-3")

        assert len(events) == 1
        paused = events[0]
        assert paused["type"] == "run_paused"
        assert paused["reason"] == "waiting_input"
        assert paused["run_id"] == "run-3"
        assert paused["contract_version"] == 1
        assert paused["action"]["question"] == "q?"

    async def test_stop_waiting_confirmation_maps_to_run_paused(self, service):
        ctx = self.make_ctx()
        with self.router_patches(event_gen([RuntimeEvent(RuntimeEventType.STOP, {
            "reason": "waiting_confirmation", "run_id": "run-4",
        })])):
            events = await self.run(service, ctx, runtime_run_id="run-4")

        assert events[0]["reason"] == "waiting_confirmation"

    async def test_terminal_stop_reason_is_dropped(self, service):
        ctx = self.make_ctx()
        with self.router_patches(event_gen([
            RuntimeEvent(RuntimeEventType.STOP, {"reason": "failed", "run_id": "run-5"}),
        ])):
            events = await self.run(service, ctx, runtime_run_id="run-5")

        assert events == []

    async def test_delta_event_maps_to_delta(self, service):
        ctx = self.make_ctx()
        with self.router_patches(event_gen([RuntimeEvent(RuntimeEventType.DELTA, {"content": "abc"})])):
            events = await self.run(service, ctx)

        assert events == [{"type": "delta", "content": "abc"}]

    async def test_progress_tagged_event_is_dropped(self, service):
        ctx = self.make_ctx()
        with self.router_patches(event_gen([
            RuntimeEvent(RuntimeEventType.DELTA, {"content": "abc", "_progress": {"stage": "planning"}}),
        ])):
            events = await self.run(service, ctx)

        assert events == []

    async def test_unmapped_event_type_is_dropped(self, service):
        ctx = self.make_ctx()
        with self.router_patches(event_gen([
            RuntimeEvent(RuntimeEventType.RUN_START, {"entity_id": "run-6"}),
        ])):
            events = await self.run(service, ctx)

        assert events == []

    async def test_tail_progress_is_forwarded_as_stage(self, service):
        ctx = self.make_ctx()
        tail = [{
            "type": "runtime_progress", "run_id": "run-7",
            "chat_stage": "planning", "action": "act", "description": "Работаю",
            "outcome": "ok",
        }]
        with self.router_patches(
            event_gen([RuntimeEvent(RuntimeEventType.FINAL, {"content": "done"})]),
            tail_messages=tail,
        ) as patches:
            events = await self.run(service, ctx, runtime_run_id="run-7")

        patches["subscriber_cls"].assert_called_once_with(stream_key="run-7")
        stages = [event for event in events if event["type"] == "stage"]
        assert len(stages) == 1
        assert stages[0]["activity"] == {
            "run_id": "run-7",
            "stage": "planning",
            "action": "act",
            "description": "Работаю",
            "outcome": "ok",
        }
        assert events[-1]["type"] == "final_content"

    async def test_tail_messages_for_other_runs_are_ignored(self, service):
        ctx = self.make_ctx()
        tail = [
            {"type": "runtime_progress", "run_id": "other", "chat_stage": "planning"},
            {"type": "not_progress", "run_id": "run-8"},
        ]
        with self.router_patches(
            event_gen([RuntimeEvent(RuntimeEventType.FINAL, {"content": "done"})]),
            tail_messages=tail,
        ):
            events = await self.run(service, ctx, runtime_run_id="run-8")

        assert [event["type"] for event in events] == ["final_content"]

    async def test_tail_stage_fields_fall_back_to_defaults(self, service):
        ctx = self.make_ctx()
        tail = [{"type": "runtime_progress", "run_id": "run-9"}]
        with self.router_patches(
            event_gen([RuntimeEvent(RuntimeEventType.FINAL, {"content": "done"})]),
            tail_messages=tail,
        ):
            events = await self.run(service, ctx, runtime_run_id="run-9")

        stages = [event for event in events if event["type"] == "stage"]
        assert stages[0]["activity"]["stage"] == "preparing"
        assert stages[0]["activity"]["action"] == "runtime_activity"
        assert stages[0]["activity"]["description"] == "Выполняю запрос"
        assert stages[0]["activity"]["outcome"] is None

    async def test_tail_metric_failure_is_swallowed(self, service):
        ctx = self.make_ctx()
        tail = [{"type": "runtime_progress", "run_id": "run-13"}]
        broken_metric = MagicMock()
        broken_metric.inc.side_effect = RuntimeError("metric boom")
        with self.router_patches(
            event_gen([RuntimeEvent(RuntimeEventType.FINAL, {"content": "done"})]),
            tail_messages=tail,
        ):
            with patch(
                "app.core.prometheus_metrics.chat_runtime_progress_forwarded_total",
                broken_metric,
            ):
                events = await self.run(service, ctx, runtime_run_id="run-13")

        stages = [event for event in events if event["type"] == "stage"]
        assert len(stages) == 1
        broken_metric.inc.assert_called_once_with()
        assert events[-1]["type"] == "final_content"

    async def test_subscription_failure_still_streams_pipeline_events(self, service):
        ctx = self.make_ctx()
        with self.router_patches(
            event_gen([RuntimeEvent(RuntimeEventType.FINAL, {"content": "done"})]),
            subscribe_error=RuntimeError("no bus"),
        ) as patches:
            events = await self.run(service, ctx, runtime_run_id="run-10")

        assert [event["type"] for event in events] == ["final_content"]
        patches["subscriber"].unsubscribe.assert_awaited_once()

    async def test_unsubscribe_failure_is_swallowed(self, service):
        ctx = self.make_ctx()
        with self.router_patches(
            event_gen([RuntimeEvent(RuntimeEventType.FINAL, {"content": "done"})]),
            unsubscribe_error=RuntimeError("boom"),
        ):
            events = await self.run(service, ctx, runtime_run_id="run-11")

        assert [event["type"] for event in events] == ["final_content"]

    async def test_pipeline_request_is_built_from_transport_params(self, service):
        ctx = self.make_ctx(extra={
            "continuation_meta": {"page": 2},
            "confirmation_tokens": ["tok-1"],
        })
        captured: dict[str, Any] = {}
        with self.router_patches(event_gen([RuntimeEvent(RuntimeEventType.FINAL, {"content": "d"})], captured)):
            snapshot = ChatContextSnapshot(chat_id=str(ctx.chat_id), artifacts=[])
            await self.run(
                service, ctx,
                content={"text": "dict content"},
                runtime_run_id="run-12",
                chat_turn_id="turn-12",
                expected_context_revision=4,
                chat_context_snapshot=snapshot,
                chat_user_message_id="um-12",
                attachment_contexts=[{
                    "ref": {"artifact_id": "att-1", "file_name": "a.txt"},
                    "is_current": True,
                    "snippet": "txt",
                }],
            )

        request = captured["args"][0]
        assert request.request_text == "dict content"
        assert request.runtime_run_id == "run-12"
        assert request.chat_id == str(ctx.chat_id)
        assert request.chat_turn_id == "turn-12"
        assert request.expected_context_revision == 4
        assert request.chat_context_snapshot is snapshot
        assert request.chat_user_message_id == "um-12"
        assert request.user_id == USER_ID
        assert request.tenant_id == "00000000-0000-0000-0000-000000000001"
        assert request.messages == [{"role": "user", "content": "hi"}]
        assert len(request.attachments) == 1
        assert request.attachments[0].ref.artifact_id == "att-1"
        assert request.attachments[0].ref.file_name == "a.txt"
        assert request.attachments[0].is_current is True
        assert request.attachments[0].snippet == "txt"
        assert request.continuation_meta == {"page": 2}
        assert request.confirmation_tokens == ["tok-1"]
        assert request.await_background_tail is False

    async def test_runtime_deps_session_factory_is_injected(self, service):
        ctx = self.make_ctx()
        with self.router_patches(event_gen([RuntimeEvent(RuntimeEventType.FINAL, {"content": "d"})])) as patches:
            await self.run(service, ctx)

        deps = ctx.extra["runtime_deps"]
        assert deps.session_factory is patches["session_factory"]

    async def test_agent_unavailable_rbac_denied_maps_status_and_error(self, service):
        ctx = self.make_ctx()
        missing = MissingRequirements(
            tools=["tool-x"], collections=["coll-y"], credentials=["cred-z"],
        )
        error = AgentUnavailableError(
            "denied", missing,
            reason_code="rbac_agent_invoke_denied",
            details={"agent_slug": "agent-x"},
        )
        with self.router_patches(raising_gen(error)):
            events = await self.run(service, ctx)

        assert events[0] == {
            "type": "status",
            "stage": "rbac_agent_invoke_denied",
            "agent_slug": "agent-x",
        }
        assert events[1]["type"] == "error"
        assert events[1]["error"] == "Access denied to invoke selected agent"
        assert events[1]["code"] == "rbac_agent_invoke_denied"
        assert events[1]["missing_tools"] == ["tool-x"]
        assert events[1]["missing_collections"] == ["coll-y"]
        assert events[1]["missing_credentials"] == ["cred-z"]

    async def test_agent_unavailable_with_reason_code_maps_error(self, service):
        ctx = self.make_ctx()
        error = AgentUnavailableError("m", reason_code="tool_unavailable")
        with self.router_patches(raising_gen(error)):
            events = await self.run(service, ctx)

        assert len(events) == 1
        assert events[0]["error"] == "Agent unavailable: tool_unavailable"
        assert events[0]["code"] == "tool_unavailable"
        assert events[0]["missing_tools"] == []

    async def test_agent_unavailable_without_reason_maps_generic_message(self, service):
        ctx = self.make_ctx()
        error = AgentUnavailableError("m")
        with self.router_patches(raising_gen(error)):
            events = await self.run(service, ctx)

        assert events[0]["error"] == "Agent unavailable"
        assert events[0]["code"] is None

    async def test_generic_router_error_rolls_back_and_yields_routing_failed(self, service, mock_session):
        ctx = self.make_ctx()
        with self.router_patches(raising_gen(RuntimeError("router boom"))):
            events = await self.run(service, ctx)

        assert events == [{"type": "error", "error": "Routing failed", "code": "routing_failed"}]
        mock_session.rollback.assert_awaited_once()
