from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from app.services.chat_turn_service import ChatTurnIdempotencyError, ChatTurnService


@pytest.mark.asyncio
async def test_duplicate_concurrent_turn_key_returns_processing_or_conflict():
    session = AsyncMock()
    session.add = MagicMock()
    session.flush.side_effect = IntegrityError("insert", {}, RuntimeError("unique violation"))
    existing = SimpleNamespace(request_hash="existing-hash")
    service = ChatTurnService(session)
    service.get_latest_by_idempotency_key = AsyncMock(return_value=existing)

    with pytest.raises(ChatTurnIdempotencyError) as error:
        await service.start_turn(
            chat_id="00000000-0000-0000-0000-000000000010",
            user_id="00000000-0000-0000-0000-000000000020",
            idempotency_key="same-key",
            request_hash="existing-hash",
        )

    assert error.value.conflict is False
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_duplicate_concurrent_turn_key_with_different_payload_is_conflict():
    session = AsyncMock()
    session.add = MagicMock()
    session.flush.side_effect = IntegrityError("insert", {}, RuntimeError("unique violation"))
    service = ChatTurnService(session)
    service.get_latest_by_idempotency_key = AsyncMock(
        return_value=SimpleNamespace(request_hash="existing-hash"),
    )

    with pytest.raises(ChatTurnIdempotencyError) as error:
        await service.start_turn(
            chat_id="00000000-0000-0000-0000-000000000010",
            user_id="00000000-0000-0000-0000-000000000020",
            idempotency_key="same-key",
            request_hash="different-hash",
        )

    assert error.value.conflict is True
