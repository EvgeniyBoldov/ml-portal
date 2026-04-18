from __future__ import annotations

from types import SimpleNamespace

from app.agents.contracts import ActionType, RuntimeTriageDecision
from app.services.orchestration_contract import (
    PlannerStepType,
    intent_from_runtime_triage,
    planner_step_from_next_action,
    runtime_triage_from_intent,
)


def test_triage_intent_roundtrip():
    decision = RuntimeTriageDecision(
        type="orchestrate",
        confidence=0.8,
        goal="Resolve incident",
        inputs={"k": "v"},
        trace_id="t-1",
    )
    intent = intent_from_runtime_triage(decision)
    restored = runtime_triage_from_intent(intent)
    assert restored.type == "orchestrate"
    assert restored.goal == "Resolve incident"
    assert restored.inputs == {"k": "v"}
    assert restored.trace_id == "t-1"


def test_planner_step_from_next_action_agent_call():
    next_action = SimpleNamespace(
        type=ActionType.AGENT_CALL,
        agent=SimpleNamespace(agent_slug="kb-agent"),
        ask_user=None,
        meta=SimpleNamespace(phase_id="p1", phase_title="Collect", why="Need KB"),
    )
    decision = planner_step_from_next_action(next_action)
    assert decision.step_type == PlannerStepType.CALL_AGENT
    payload = decision.to_runtime_payload(2)
    assert payload["iteration"] == 2
    assert payload["action_type"] == "agent_call"
    assert payload["agent_slug"] == "kb-agent"
    assert decision.signature("fallback") == "agent_call:kb-agent:p1"
