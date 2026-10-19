from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.runtime.contracts import AttachmentContext
from app.runtime.turn_preflight import TurnPreflight, TurnPreflightDecision


@pytest.mark.asyncio
async def test_preflight_can_read_file_then_synthesize_without_plan(monkeypatch):
    from app.runtime import turn_preflight
    read = TurnPreflightDecision.model_validate({"route": "tool_call", "tool_call": {
        "tool": "file.read", "arguments": {"artifact_id": "file-1"}}})
    answer = TurnPreflightDecision.model_validate({"route": "synthesis", "synthesis_brief": {
        "answer_draft": "The document describes a process.", "synthesis_brief": {
            "user_question": "Summarize", "planned_work": "Read", "purpose": "Summarize",
            "answer_requirements": "Use document evidence"}}})
    receipt = {"tool": "file.read", "result": {"success": True, "artifact_id": "file-1",
        "content": "A process", "truncated": False}}
    tools = SimpleNamespace(descriptors=AsyncMock(return_value=[{"tool": "file.read"}]),
                            execute=AsyncMock(return_value=receipt))
    factory = lambda **kwargs: tools
    factory.MAX_CALLS = 3
    monkeypatch.setattr(turn_preflight, "RoleMemoryTools", factory)
    preflight = TurnPreflight(session=object(), llm_client=AsyncMock())
    preflight._llm.invoke = AsyncMock(side_effect=[SimpleNamespace(value=read), SimpleNamespace(value=answer)])
    result = await preflight.decide(user_request="Summarize", mechanical_lookup={}, attachments=[
        AttachmentContext(ref={"artifact_id": "file-1", "file_name": "process.txt"}, is_current=True)])
    assert result.route == "synthesis"
    assert result.memory_tool_results == [receipt]
    tools.execute.assert_awaited_once()
