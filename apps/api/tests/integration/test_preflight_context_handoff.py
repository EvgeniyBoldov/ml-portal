"""Exercise real role assembly with deterministic provider responses, without network calls."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.agents.context import ToolContext
from app.runtime.input_builders import SynthesizerInputBuilder
from app.runtime.memory.role_tools import RoleMemoryTools
from app.runtime.orchestrator_contracts import PlanRequest, PlannerContext
from app.runtime.planner.graph_planner import GraphPlanner
from app.runtime.run_context import RunContext
from app.runtime.synthesis_context import SynthesisContextBuilder
from app.runtime.turn_preflight import TurnPreflight
from app.services.runtime_limits_service import ModelCallLimits


@pytest.mark.asyncio
async def test_preflight_compiles_dialogue_into_task_and_explicit_synthesis_material(monkeypatch):
    requests = {}
    dialogue = [
        {"message_id": "selected", "role": "assistant", "content": "SELECTED_TEXT", "truncated": False},
        {"message_id": "irrelevant", "role": "assistant", "content": "UNRELATED_OLD_RESULT"},
    ]
    brief = {"goal": "Compare selected text with current data", "direction": "Delegate a current check",
             "constraints": ["Verify the current state"], "expected_result": "A comparison",
             "resolved_references": [{"expression": "that text", "meaning": "SELECTED_TEXT", "source_message_ids": ["selected"]}],
             "message_refs": ["selected"], "uncertainties": ["Current state needs verification"]}
    synthesis_brief = {"user_question": brief["goal"], "planned_work": "Compare", "purpose": "Answer",
                       "answer_requirements": "Use the selected text as historical material", "message_refs": ["selected"]}

    async def chat(messages, *, model, **kwargs):
        requests[model] = json.loads(messages[1]["content"])
        assert kwargs["params"]["response_format"]["type"] == "json_schema"
        if model == "preflight":
            return json.dumps({"route": "planner", "task_brief": brief})
        return json.dumps({"kind": "proposal", "proposal": {"terminal": "synthesis", "synthesis_brief": synthesis_brief}})

    client = SimpleNamespace(chat=chat)
    monkeypatch.setattr(RoleMemoryTools, "descriptors", AsyncMock(return_value=[{
        "tool": "file.read", "description": "Read file", "input_schema": {"type": "object"},
    }]))
    preflight = TurnPreflight(session=AsyncMock(), llm_client=client)
    preflight._llm.role_service.get_role_config = AsyncMock(return_value={"role_type": "turn_preflight", "model": "preflight"})
    preflight._llm.limits_service.resolve_model = AsyncMock(return_value=ModelCallLimits(request_timeout_s=2, max_retries=0))
    decision = await preflight.decide(user_request="Compare that text with current data", mechanical_lookup={},
                                    recent_dialogue=dialogue,
                                    chat_context={"recent_anchor": {"assistant_outcome": "UNRELATED_OLD_RESULT"}},
                                    facts_context=[{"type": "chat_context", "old_answer": "UNRELATED_OLD_RESULT"}])
    assert len(requests["preflight"]["recent_dialogue"]) == 2
    assert requests["preflight"]["facts_context"] == []
    assert requests["preflight"]["available_tools"] == [{"tool": "file.read", "description": "Read file"}]

    run = RunContext(original_request="Compare that text with current data", goal=brief["goal"],
                     recent_dialogue=dialogue, chat_snapshot={"old": "UNRELATED_OLD_RESULT"},
                     task_brief=decision.task_brief.model_dump(mode="json"))
    planner = GraphPlanner(session=AsyncMock(), llm_client=client)
    planner._llm.role_service.get_role_config = AsyncMock(return_value={"role_type": "planner", "model": "planner"})
    planner._llm.limits_service.resolve_model = AsyncMock(return_value=ModelCallLimits(request_timeout_s=2, max_retries=0))
    ctx = ToolContext(user_id=uuid4(), tenant_id=uuid4(), extra={"runtime_turn_state": SimpleNamespace(run_context=run)})
    proposal = await planner.plan(request=PlanRequest(context=PlannerContext(
        goal=brief["goal"], trigger="initial", execution_ledger={}, task_brief=run.task_brief)), ctx=ctx)
    assert "UNRELATED_OLD_RESULT" not in json.dumps(requests["planner"])
    assert "recent_dialogue" not in requests["planner"]["run_context"]
    assert requests["planner"]["run_context"]["conversation_materials"][0]["message_id"] == "selected"
    assert requests["planner"]["task_brief"]["uncertainties"] == brief["uncertainties"]
    assert "goal" not in requests["planner"]["task_brief"]
    assert "constraints" not in requests["planner"]["run_context"]
    assert requests["planner"]["planner_tools"] == [{"tool": "file.read", "description": "Read file"}]

    context = SynthesisContextBuilder().build(plan={"goal": brief["goal"], "tasks": {}, "iterations": [
        {"id": "final", "synthesis_brief": proposal.synthesis_brief.model_dump(mode="json")}]}, iteration_id="final")
    context["run_context"] = run.projection(evidence_refs=proposal.synthesis_brief.evidence_refs,
                                           message_refs=proposal.synthesis_brief.message_refs)
    messages = SynthesizerInputBuilder().build(synthesis_context=context, system_prompt="Synthesize")
    assert "SELECTED_TEXT" in messages[1]["content"]
    assert "UNRELATED_OLD_RESULT" not in messages[1]["content"]
    assert json.loads(messages[1]["content"])["run_context"]["evidence"] == []
