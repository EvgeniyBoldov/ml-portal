from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.chat_turn_service import ChatTurnService


@pytest.fixture
def service(mock_session) -> ChatTurnService:
    return ChatTurnService(mock_session)


class TestChatTurnService:
    @pytest.mark.asyncio
    async def test_start_turn_creates_started_record(self, service: ChatTurnService, mock_session):
        turn = await service.start_turn(
            tenant_id=uuid4(),
            chat_id=uuid4(),
            user_id=uuid4(),
            idempotency_key="idem-1",
        )

        assert turn.status == "started"
        assert turn.idempotency_key == "idem-1"
        mock_session.add.assert_called_once()
        mock_session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_complete_turn_sets_status_and_assistant_message(self, service: ChatTurnService):
        turn = SimpleNamespace(status="started", assistant_message_id=None, agent_run_id=None, completed_at=None)
        async def _get_by_id(_turn_id):
            return turn
        service.get_by_id = _get_by_id

        assistant_message_id = uuid4()
        agent_run_id = uuid4()
        result = await service.complete_turn(
            uuid4(),
            assistant_message_id=assistant_message_id,
            agent_run_id=agent_run_id,
        )

        assert result is turn
        assert turn.status == "completed"
        assert turn.assistant_message_id == assistant_message_id
        assert turn.agent_run_id == agent_run_id

    @pytest.mark.asyncio
    async def test_fail_turn_sets_error_message(self, service: ChatTurnService):
        turn = SimpleNamespace(status="started", error_message=None, agent_run_id=None, completed_at=None)
        async def _get_by_id(_turn_id):
            return turn
        service.get_by_id = _get_by_id

        result = await service.fail_turn(uuid4(), error_message="boom")

        assert result is turn
        assert turn.status == "failed"
        assert turn.error_message == "boom"
