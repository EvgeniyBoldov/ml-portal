from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.runtime.interaction import InteractionQuestion, InteractionRequester, RuntimeInteraction
from app.services.durable_runtime_execution import DurableExecutionSegment, _build_execution_input
from app.services.runtime_hitl_protocol_service import RuntimeHitlProtocolService


@pytest.mark.asyncio
async def test_timer_checkpoint_uses_same_pause_identity_and_does_not_publish_internal_context():
    segment = DurableExecutionSegment(AsyncMock(), SimpleNamespace())
    segment.service.complete_segment = AsyncMock()
    pause_id = uuid4()
    wake_at = datetime(2026, 11, 27, tzinfo=timezone.utc)
    context = {
        "pause_id": str(pause_id),
        "wake_at": wake_at.isoformat(),
        "checkpoint": {"tool_results": [{"secret": "hidden"}]},
        "user_update": "Продолжу завтра.",
    }
    await segment.finish("waiting_timer", context=context)

    kwargs = segment.service.complete_segment.await_args.kwargs
    assert kwargs["pause_id"] == pause_id
    assert kwargs["wake_at"] == wake_at
    assert kwargs["public_payload"] == {
        "pause_id": str(pause_id), "content": context["user_update"], "wake_at": context["wake_at"],
    }
    public_pause = RuntimeHitlProtocolService.public_pause({"reason": "waiting_timer", "context": context})
    assert public_pause["context"] == {"pause_id": str(pause_id), "wake_at": context["wake_at"]}


@pytest.mark.asyncio
async def test_resume_envelope_preserves_false_and_does_not_alter_goal():
    asker = InteractionRequester(stage="turn_preflight", entity_id=str(uuid4()))
    interaction = RuntimeInteraction.create(
        InteractionQuestion(question="Использовать проект по умолчанию?", response_type="boolean"),
        asker,
    )
    claim = SimpleNamespace(run_id=uuid4(), context={
        "context": {
            "interaction": interaction.model_dump(mode="json"),
            "original_goal": "Исходная цель",
            "runtime_budget_usage": {"active_wall_time_ms": 12},
        },
        "action": {"pause_id": interaction.id},
        "resume": {"signal_type": "answer", "pause_id": interaction.id, "payload": {"response": False}},
    })
    session = AsyncMock()
    session.get.return_value = None
    session.scalar.return_value = None
    session.execute.return_value = Mock(scalar_one_or_none=Mock(return_value=None))
    turn = SimpleNamespace(user_id=uuid4(), chat_id=uuid4())

    content, meta, tokens = await _build_execution_input(session, claim, turn, uuid4(), "Исходный запрос")

    assert content == "Нет"
    assert meta["durable_runtime"] is True
    checkpoint = meta["resume_checkpoint"]
    assert checkpoint["interaction_response"] is False
    assert checkpoint["original_goal"] == "Исходная цель"
    assert checkpoint["original_user_request"] == "Исходный запрос"
    assert checkpoint["budget_usage"] == {"active_wall_time_ms": 12}
    assert not tokens
