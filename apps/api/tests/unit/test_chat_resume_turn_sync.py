from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from app.api.v1.routers.chat import resume_run


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
        chat_service = AsyncMock()
        chat_service.send_message_stream = lambda **_: self._stream({"type": "final", "message_id": str(uuid4())})

        with (
            patch("app.services.chat_turn_service.ChatTurnService", return_value=turn_service),
            patch("app.api.v1.routers.chat.ChatStreamService", return_value=chat_service),
            patch("app.api.v1.routers.chat.get_redis", return_value=AsyncMock()),
            patch("app.api.v1.routers.chat.get_llm_client", return_value=AsyncMock()),
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
        mock_session.commit.assert_awaited()

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
