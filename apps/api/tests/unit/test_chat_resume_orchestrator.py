from __future__ import annotations

import pytest

from app.services.chat_resume_orchestrator import ChatResumeOrchestrator


class _FakeService:
    def __init__(self, events):
        self._events = list(events)

    async def _stream(self, **kwargs):
        for event in self._events:
            yield event

    def send_message_stream(self, **kwargs):
        return self._stream(**kwargs)


@pytest.mark.asyncio
async def test_continue_chat_completed():
    service = _FakeService([{"type": "status"}, {"type": "final", "message_id": "m1"}])
    result = await ChatResumeOrchestrator(service).continue_chat(
        run_id="r1",
        chat_id="c1",
        user_id="u1",
        agent_slug="a1",
        resume_content="resume",
        checkpoint={"x": 1},
        paused_action={"kind": "input"},
        paused_context={"question": "q"},
        user_input="hello",
    )

    assert result["status"] == "resumed_completed"
    assert result["assistant_message_id"] == "m1"
    assert result["user_input"] == "hello"


@pytest.mark.asyncio
async def test_continue_chat_paused_again():
    service = _FakeService(
        [
            {
                "type": "run_paused",
                "reason": "waiting_input",
                "run_id": "r2",
                "action": {"type": "resume"},
                "context": {"question": "vlan?"},
            }
        ]
    )
    result = await ChatResumeOrchestrator(service).continue_chat(
        run_id="r1",
        chat_id="c1",
        user_id="u1",
        agent_slug="a1",
        resume_content="resume",
        checkpoint={"x": 1},
        paused_action=None,
        paused_context=None,
    )

    assert result["status"] == "resumed_paused_again"
    assert result["paused_again_reason"] == "waiting_input"
    assert result["paused_again_run_id"] == "r2"


@pytest.mark.asyncio
async def test_continue_chat_error():
    service = _FakeService([{"type": "error", "error": "boom"}])
    result = await ChatResumeOrchestrator(service).continue_chat(
        run_id="r1",
        chat_id="c1",
        user_id="u1",
        agent_slug="a1",
        resume_content="resume",
        checkpoint={"x": 1},
        paused_action=None,
        paused_context=None,
    )

    assert result["status"] == "resumed_with_error"
    assert result["error"] == "boom"
