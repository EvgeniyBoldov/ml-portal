from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from app.api.v1.routers.chat import resume_run
from app.services.chat_turn_orchestrator import ChatTurnOrchestrator


class TestChatResumeTurnSync:
    @staticmethod
    def _mock_execute_with_run(mock_session, run_obj):
        mock_session.execute = AsyncMock(
            return_value=SimpleNamespace(scalar_one_or_none=lambda: run_obj)
        )

    @staticmethod
    def _stream(*events):
        async def _gen():
            for event in events:
                yield event
        return _gen()

    @pytest.mark.asyncio
    async def test_resume_confirm_resumes_turn_and_run(self, mock_session):
        run_id = str(uuid4())
        user_id = str(uuid4())
        tenant_id = str(uuid4())
        current_user = SimpleNamespace(id=user_id, tenant_ids=[tenant_id])
        paused_run = SimpleNamespace(
            id=uuid4(),
            user_id=user_id,
            tenant_id=tenant_id,
            status="waiting_confirmation",
            paused_action={"kind": "confirm", "operation_fingerprint": "fp-1"},
            paused_context={"x": 1},
            error=None,
            finished_at=None,
            chat_id=uuid4(),
            agent_slug="agent-x",
            context_snapshot={},
        )
        turn = SimpleNamespace(id=uuid4())
        self._mock_execute_with_run(mock_session, paused_run)

        turn_service = AsyncMock()
        turn_service.get_by_agent_run_id = AsyncMock(return_value=turn)
        turn_service.cancel_turn = AsyncMock()
        captured_kwargs = {}

        def _send_message_stream(**kwargs):
            captured_kwargs.update(kwargs)
            return self._stream({"type": "final", "message_id": str(uuid4())})

        chat_service = SimpleNamespace(send_message_stream=_send_message_stream)
        confirmation_service = SimpleNamespace(issue=AsyncMock())
        confirmation_service.issue = lambda **_: ("tok-confirm", None)

        with (
            patch("app.services.chat_turn_service.ChatTurnService", return_value=turn_service),
            patch("app.api.v1.routers.chat.ChatStreamService", return_value=chat_service),
            patch("app.api.v1.routers.chat.get_redis", return_value=AsyncMock()),
            patch("app.api.v1.routers.chat.get_llm_client", return_value=AsyncMock()),
            patch("app.api.v1.routers.chat.messages.get_confirmation_service", return_value=confirmation_service),
        ):
            result = await resume_run(run_id=run_id, body={"action": "confirm"}, session=mock_session, current_user=current_user)

        assert result["status"] == "resumed_completed"
        assert paused_run.status == "resumed"
        assert paused_run.paused_action is None
        assert paused_run.paused_context is None
        assert "resume_checkpoint" in paused_run.context_snapshot
        turn_service.cancel_turn.assert_awaited_once_with(
            turn.id,
            error_message="Turn resumed via continuation flow",
            agent_run_id=UUID(run_id),
        )
        assert captured_kwargs.get("confirmation_tokens") == ["tok-confirm"]
        mock_session.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_resume_confirm_issues_token_when_fingerprint_only_in_paused_context(self, mock_session):
        run_id = str(uuid4())
        user_id = str(uuid4())
        tenant_id = str(uuid4())
        current_user = SimpleNamespace(id=user_id, tenant_ids=[tenant_id])
        paused_run = SimpleNamespace(
            id=uuid4(),
            user_id=user_id,
            tenant_id=tenant_id,
            status="waiting_confirmation",
            paused_action={"kind": "confirm"},
            paused_context={"operation_fingerprint": "fp-from-context"},
            error=None,
            finished_at=None,
            chat_id=uuid4(),
            agent_slug="agent-x",
            context_snapshot={},
        )
        turn = SimpleNamespace(id=uuid4())
        self._mock_execute_with_run(mock_session, paused_run)

        turn_service = AsyncMock()
        turn_service.get_by_agent_run_id = AsyncMock(return_value=turn)
        turn_service.cancel_turn = AsyncMock()
        captured_kwargs = {}

        def _send_message_stream(**kwargs):
            captured_kwargs.update(kwargs)
            return self._stream({"type": "final", "message_id": str(uuid4())})

        chat_service = SimpleNamespace(send_message_stream=_send_message_stream)
        confirmation_service = SimpleNamespace(issue=lambda **_: ("tok-confirm-ctx", None))

        with (
            patch("app.services.chat_turn_service.ChatTurnService", return_value=turn_service),
            patch("app.api.v1.routers.chat.ChatStreamService", return_value=chat_service),
            patch("app.api.v1.routers.chat.get_redis", return_value=AsyncMock()),
            patch("app.api.v1.routers.chat.get_llm_client", return_value=AsyncMock()),
            patch("app.api.v1.routers.chat.messages.get_confirmation_service", return_value=confirmation_service),
        ):
            result = await resume_run(run_id=run_id, body={"action": "confirm"}, session=mock_session, current_user=current_user)

        assert result["status"] == "resumed_completed"
        assert captured_kwargs.get("confirmation_tokens") == ["tok-confirm-ctx"]

    @pytest.mark.asyncio
    async def test_resume_cancel_fails_turn_and_finishes_run(self, mock_session):
        run_id = str(uuid4())
        user_id = str(uuid4())
        tenant_id = str(uuid4())
        current_user = SimpleNamespace(id=user_id, tenant_ids=[tenant_id])
        paused_run = SimpleNamespace(
            id=uuid4(),
            user_id=user_id,
            tenant_id=tenant_id,
            status="waiting_confirmation",
            paused_action={"kind": "confirm"},
            paused_context={"x": 1},
            error=None,
            finished_at=None,
            chat_id=uuid4(),
            agent_slug="agent-x",
            context_snapshot={},
        )
        turn = SimpleNamespace(id=uuid4())
        self._mock_execute_with_run(mock_session, paused_run)

        turn_service = AsyncMock()
        turn_service.get_by_agent_run_id = AsyncMock(return_value=turn)
        turn_service.cancel_turn = AsyncMock()

        with patch("app.services.chat_turn_service.ChatTurnService", return_value=turn_service):
            result = await resume_run(run_id=run_id, body={"action": "cancel"}, session=mock_session, current_user=current_user)

        assert result["status"] == "cancelled"
        assert paused_run.status == "cancelled"
        assert paused_run.error == "Cancelled by user"
        assert paused_run.paused_action is None
        assert paused_run.paused_context is None
        turn_service.cancel_turn.assert_awaited_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_resume_input_resumes_turn_and_returns_input(self, mock_session):
        run_id = str(uuid4())
        user_id = str(uuid4())
        tenant_id = str(uuid4())
        current_user = SimpleNamespace(id=user_id, tenant_ids=[tenant_id])
        paused_run = SimpleNamespace(
            id=uuid4(),
            user_id=user_id,
            tenant_id=tenant_id,
            status="waiting_input",
            paused_action={"kind": "input"},
            paused_context={"x": 1},
            error=None,
            finished_at=None,
            chat_id=uuid4(),
            agent_slug="agent-x",
            context_snapshot={},
        )
        turn = SimpleNamespace(id=uuid4())
        self._mock_execute_with_run(mock_session, paused_run)

        turn_service = AsyncMock()
        turn_service.get_by_agent_run_id = AsyncMock(return_value=turn)
        turn_service.cancel_turn = AsyncMock()
        chat_service = AsyncMock()
        chat_service.send_message_stream = lambda **_: self._stream(
            {"type": "status", "stage": "agent_running"},
            {"type": "final", "message_id": str(uuid4())},
        )

        with (
            patch("app.services.chat_turn_service.ChatTurnService", return_value=turn_service),
            patch("app.api.v1.routers.chat.ChatStreamService", return_value=chat_service),
            patch("app.api.v1.routers.chat.get_redis", return_value=AsyncMock()),
            patch("app.api.v1.routers.chat.get_llm_client", return_value=AsyncMock()),
        ):
            result = await resume_run(run_id=run_id, body={"action": "input", "input": "hello"}, session=mock_session, current_user=current_user)

        assert result["status"] == "resumed_completed"
        assert result["user_input"] == "hello"
        assert paused_run.status == "resumed"
        assert "resume_checkpoint" in paused_run.context_snapshot
        turn_service.cancel_turn.assert_awaited_once_with(
            turn.id,
            error_message="Turn resumed via continuation flow",
            agent_run_id=UUID(run_id),
        )
        mock_session.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_resume_returns_paused_again_payload(self, mock_session):
        run_id = str(uuid4())
        user_id = str(uuid4())
        tenant_id = str(uuid4())
        paused_again_run_id = str(uuid4())
        current_user = SimpleNamespace(id=user_id, tenant_ids=[tenant_id])
        paused_run = SimpleNamespace(
            id=uuid4(),
            user_id=user_id,
            tenant_id=tenant_id,
            status="waiting_input",
            paused_action={"kind": "input"},
            paused_context={"x": 1},
            error=None,
            finished_at=None,
            chat_id=uuid4(),
            agent_slug="agent-x",
            context_snapshot={},
        )
        turn = SimpleNamespace(id=uuid4())
        self._mock_execute_with_run(mock_session, paused_run)

        turn_service = AsyncMock()
        turn_service.get_by_agent_run_id = AsyncMock(return_value=turn)
        turn_service.cancel_turn = AsyncMock()
        chat_service = AsyncMock()
        chat_service.send_message_stream = lambda **_: self._stream(
            {
                "type": "run_paused",
                "reason": "waiting_input",
                "run_id": paused_again_run_id,
                "action": {"type": "resume", "question": "Уточните VLAN"},
                "context": {"question": "Уточните VLAN", "reason": "waiting_input"},
            },
        )

        with (
            patch("app.services.chat_turn_service.ChatTurnService", return_value=turn_service),
            patch("app.api.v1.routers.chat.ChatStreamService", return_value=chat_service),
            patch("app.api.v1.routers.chat.get_redis", return_value=AsyncMock()),
            patch("app.api.v1.routers.chat.get_llm_client", return_value=AsyncMock()),
        ):
            result = await resume_run(
                run_id=run_id,
                body={"action": "input", "input": "hello"},
                session=mock_session,
                current_user=current_user,
            )

        assert result["status"] == "resumed_paused_again"
        assert result["paused_again_run_id"] == paused_again_run_id
        assert result["paused_again_reason"] == "waiting_input"
        assert isinstance(result["paused_again_action"], dict)
        assert isinstance(result["paused_again_context"], dict)

    @pytest.mark.asyncio
    async def test_resume_denies_other_user_run(self, mock_session):
        run_id = str(uuid4())
        current_user = SimpleNamespace(id=str(uuid4()), tenant_ids=[str(uuid4())])
        paused_run = SimpleNamespace(
            id=uuid4(),
            user_id=str(uuid4()),
            tenant_id=current_user.tenant_ids[0],
            status="waiting_input",
            paused_action={"kind": "input"},
            paused_context={"x": 1},
            error=None,
            finished_at=None,
            chat_id=uuid4(),
            agent_slug="agent-x",
            context_snapshot={},
        )
        self._mock_execute_with_run(mock_session, paused_run)

        with patch("app.services.chat_turn_service.ChatTurnService", return_value=AsyncMock()):
            with pytest.raises(HTTPException) as err:
                await resume_run(run_id=run_id, body={"action": "confirm"}, session=mock_session, current_user=current_user)

        assert err.value.status_code == 404
        mock_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_resume_denies_other_tenant_run(self, mock_session):
        run_id = str(uuid4())
        current_user = SimpleNamespace(id=str(uuid4()), tenant_ids=[str(uuid4())])
        paused_run = SimpleNamespace(
            id=uuid4(),
            user_id=current_user.id,
            tenant_id=str(uuid4()),
            status="waiting_input",
            paused_action={"kind": "input"},
            paused_context={"x": 1},
            error=None,
            finished_at=None,
            chat_id=uuid4(),
            agent_slug="agent-x",
            context_snapshot={},
        )
        self._mock_execute_with_run(mock_session, paused_run)

        with patch("app.services.chat_turn_service.ChatTurnService", return_value=AsyncMock()):
            with pytest.raises(HTTPException) as err:
                await resume_run(run_id=run_id, body={"action": "confirm"}, session=mock_session, current_user=current_user)

        assert err.value.status_code == 404
        mock_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_waiting_input_to_resume_input_end_to_end(self, mock_session):
        run_id = str(uuid4())
        user_id = str(uuid4())
        tenant_id = str(uuid4())
        question = "Уточните VLAN"

        # Phase 1: turn execution pauses with waiting_input.
        turn_service_phase1 = AsyncMock()
        turn_service_phase1.start_turn = AsyncMock(return_value=SimpleNamespace(id=uuid4()))
        turn_service_phase1.attach_user_message = AsyncMock()
        turn_service_phase1.pause_turn = AsyncMock()
        turn_service_phase1.build_request_hash = lambda payload: "h1"
        context_service = AsyncMock()
        context_service.load_chat_context = AsyncMock(return_value=[])
        persistence_service = AsyncMock()
        persistence_service.create_user_message = AsyncMock(
            return_value=SimpleNamespace(message_id="user-msg-1", created_at="2026-01-01T12:00:00Z")
        )
        title_service = AsyncMock()
        title_service.generate_chat_title = AsyncMock(return_value=None)
        orchestrator = ChatTurnOrchestrator(
            context_service=context_service,
            persistence_service=persistence_service,
            title_service=title_service,
            turn_service=turn_service_phase1,
        )
        chat = SimpleNamespace(tenant_id=tenant_id, name="Chat")
        paused_action = {"type": "resume", "question": question}
        paused_context = {"reason": "waiting_input", "question": question}

        async def fake_run_with_router(**kwargs):
            yield {
                "type": "run_paused",
                "reason": "waiting_input",
                "run_id": run_id,
                "action": paused_action,
                "context": paused_context,
            }

        phase1_events = [
            event
            async for event in orchestrator.execute_turn(
                chat=chat,
                chat_id=str(uuid4()),
                user_id=user_id,
                content="Найди проблемный vlan",
                attachment_ids=[],
                attachment_meta=[],
                attachment_prompt_context="",
                idempotency_key=None,
                model=None,
                agent_slug=None,
                continuation_meta=None,
                run_with_router=fake_run_with_router,
                store_idempotency=AsyncMock(),
                bind_attachments=AsyncMock(),
                process_generated_files=AsyncMock(return_value={"content": "", "attachments": []}),
            )
        ]
        stop_event = next(event for event in phase1_events if event["type"] == "stop")
        assert stop_event["reason"] == "waiting_input"
        assert stop_event["run_id"] == run_id
        assert stop_event["question"] == question
        turn_service_phase1.pause_turn.assert_awaited_once()

        # Phase 2: resume same paused run via resume endpoint and finish.
        current_user = SimpleNamespace(id=user_id, tenant_ids=[tenant_id])
        paused_run = SimpleNamespace(
            id=UUID(run_id),
            user_id=user_id,
            tenant_id=tenant_id,
            status="waiting_input",
            paused_action=paused_action,
            paused_context=paused_context,
            error=None,
            finished_at=None,
            chat_id=uuid4(),
            agent_slug="planner",
            context_snapshot={},
        )
        turn = SimpleNamespace(id=uuid4())
        self._mock_execute_with_run(mock_session, paused_run)

        turn_service_phase2 = AsyncMock()
        turn_service_phase2.get_by_agent_run_id = AsyncMock(return_value=turn)
        turn_service_phase2.cancel_turn = AsyncMock()

        sent_payloads = []

        def _send_message_stream(**kwargs):
            sent_payloads.append(kwargs)
            return self._stream(
                {"type": "status", "stage": "agent_running"},
                {"type": "final", "message_id": str(uuid4())},
            )

        chat_service = SimpleNamespace(send_message_stream=_send_message_stream)

        with (
            patch("app.services.chat_turn_service.ChatTurnService", return_value=turn_service_phase2),
            patch("app.api.v1.routers.chat.ChatStreamService", return_value=chat_service),
            patch("app.api.v1.routers.chat.get_redis", return_value=AsyncMock()),
            patch("app.api.v1.routers.chat.get_llm_client", return_value=AsyncMock()),
        ):
            result = await resume_run(
                run_id=run_id,
                body={"action": "input", "input": "VLAN 100"},
                session=mock_session,
                current_user=current_user,
            )

        assert result["status"] == "resumed_completed"
        assert result["user_input"] == "VLAN 100"
        assert paused_run.status == "resumed"
        assert paused_run.paused_action is None
        assert paused_run.paused_context is None
        assert sent_payloads
        assert "VLAN 100" in str(sent_payloads[0].get("content", ""))
