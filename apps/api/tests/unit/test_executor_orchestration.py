"""
Unit tests for executor orchestration core modules:
- RunContextCompact (facts normalization, loop detection)
- Planner (guardrails, whitelist validation)
- PolicyEngine (max_iters, loop guard, confirmation gates)
- ToolRouter selection logic (tested via contracts only, no DB)
"""
import json
import pytest
from collections import deque

from app.agents.contracts import (
    ActionIntent,
    ActionMeta,
    ActionType,
    AgentAction,
    AskUserPayload,
    AvailableActions,
    FinalPayload,
    NextAction,
    Observation,
    ObservationError,
    ObservationStatus,
    PolicyDecisionType,
    StopReason,
    ToolAction,
    ToolActionPayload,
)
from app.agents.run_context_compact import (
    LOOP_THRESHOLD,
    MAX_FACTS,
    RunContextCompact,
    _action_signature,
    observation_to_fact,
    trim_observation_output,
)
from app.agents.planner import (
    _build_whitelist,
    _extract_json,
    _fallback_ask_user,
    validate_next_action,
)
from app.agents.policy_engine import PolicyEngine


# ─── Fixtures ────────────────────────────────────────────────────────────────

def _make_available_actions(
    tools: list[tuple[str, str]] | None = None,
) -> AvailableActions:
    tool_actions = []
    for slug, op in (tools or []):
        tool_actions.append(ToolAction(
            tool_slug=slug,
            op=op,
            description=f"{slug}.{op}",
            side_effects="none",
            risk_level="low",
            idempotent=True,
        ))
    return AvailableActions(
        agents=[AgentAction(agent_slug="test-agent")],
        tools=tool_actions,
    )


def _make_tool_call_action(slug: str, op: str, input_data: dict | None = None) -> NextAction:
    return NextAction(
        type=ActionType.TOOL_CALL,
        tool=ToolActionPayload(
            intent=ActionIntent(tool_slug=slug, op=op),
            input=input_data or {},
        ),
    )


def _make_final_action(answer: str = "done") -> NextAction:
    return NextAction(
        type=ActionType.FINAL,
        final=FinalPayload(answer=answer),
    )


def _make_ask_user_action(question: str = "what?") -> NextAction:
    return NextAction(
        type=ActionType.ASK_USER,
        ask_user=AskUserPayload(question=question),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# RunContextCompact
# ═══════════════════════════════════════════════════════════════════════════════

class TestRunContextCompact:

    def test_add_fact_dedup(self):
        ctx = RunContextCompact(goal="test")
        ctx.add_fact("fact1")
        ctx.add_fact("fact1")
        ctx.add_fact("fact2")
        assert list(ctx.facts) == ["fact1", "fact2"]

    def test_facts_bounded(self):
        ctx = RunContextCompact(goal="test")
        for i in range(MAX_FACTS + 10):
            ctx.add_fact(f"fact-{i}")
        assert len(ctx.facts) == MAX_FACTS

    def test_record_action_increments_iter(self):
        ctx = RunContextCompact(goal="test")
        action = _make_tool_call_action("rag", "search")
        ctx.record_action(action)
        ctx.record_action(action)
        assert ctx.iter_count == 2

    def test_is_looping_false_when_different_actions(self):
        ctx = RunContextCompact(goal="test")
        for i in range(LOOP_THRESHOLD):
            ctx.record_action(_make_tool_call_action("rag", f"op-{i}"))
        assert not ctx.is_looping()

    def test_is_looping_true_when_same_action_repeated(self):
        ctx = RunContextCompact(goal="test")
        action = _make_tool_call_action("rag", "search", {"query": "same"})
        for _ in range(LOOP_THRESHOLD):
            ctx.record_action(action)
        assert ctx.is_looping()

    def test_is_looping_false_when_not_enough_actions(self):
        ctx = RunContextCompact(goal="test")
        action = _make_tool_call_action("rag", "search")
        ctx.record_action(action)
        assert not ctx.is_looping()

    def test_update_from_observation_ok(self):
        ctx = RunContextCompact(goal="test")
        obs = Observation(
            status=ObservationStatus.OK,
            summary="Found 5 results",
            output={"count": 5},
        )
        ctx.update_from_observation(obs, "rag", "search")
        assert len(ctx.facts) == 1
        assert "[rag.search] OK: Found 5 results" in ctx.facts[0]
        assert ctx.last_observation is obs

    def test_update_from_observation_error(self):
        ctx = RunContextCompact(goal="test")
        obs = Observation(
            status=ObservationStatus.ERROR,
            summary="Failed",
            error=ObservationError(type="timeout", message="Timed out"),
        )
        ctx.update_from_observation(obs, "jira", "create")
        assert "[jira.create] ERROR: Timed out" in ctx.facts[0]

    def test_to_planner_input_structure(self):
        ctx = RunContextCompact(goal="find docs")
        ctx.add_fact("fact1")
        aa = _make_available_actions([("rag", "search")])
        result = ctx.to_planner_input(aa)
        assert result["goal"] == "find docs"
        assert result["facts"] == ["fact1"]
        assert result["iter"] == 0
        assert len(result["available_tools"]) == 1
        assert result["available_tools"][0]["tool_slug"] == "rag"


class TestObservationToFact:

    def test_ok(self):
        obs = Observation(status=ObservationStatus.OK, summary="Done")
        assert observation_to_fact(obs, "rag", "search") == "[rag.search] OK: Done"

    def test_error(self):
        obs = Observation(
            status=ObservationStatus.ERROR,
            summary="Fail",
            error=ObservationError(type="err", message="boom"),
        )
        assert observation_to_fact(obs, "jira", "create") == "[jira.create] ERROR: boom"

    def test_blocked(self):
        obs = Observation(status=ObservationStatus.BLOCKED, summary="No access")
        assert observation_to_fact(obs) == "[result] BLOCKED: No access"


class TestTrimObservationOutput:

    def test_small_output_unchanged(self):
        data = {"key": "value"}
        assert trim_observation_output(data) == data

    def test_large_output_truncated(self):
        data = {"big": "x" * 5000}
        result = trim_observation_output(data, max_bytes=100)
        assert "_truncated" in result or len(json.dumps(result)) <= 200


class TestActionSignature:

    def test_tool_call_signature(self):
        a = _make_tool_call_action("rag", "search", {"query": "test"})
        sig = _action_signature(a)
        assert sig.startswith("tool_call|rag|search|")

    def test_same_action_same_signature(self):
        a1 = _make_tool_call_action("rag", "search", {"query": "test"})
        a2 = _make_tool_call_action("rag", "search", {"query": "test"})
        assert _action_signature(a1) == _action_signature(a2)

    def test_different_input_different_signature(self):
        a1 = _make_tool_call_action("rag", "search", {"query": "test1"})
        a2 = _make_tool_call_action("rag", "search", {"query": "test2"})
        assert _action_signature(a1) != _action_signature(a2)

    def test_final_signature(self):
        a = _make_final_action("done")
        assert _action_signature(a) == "final"

    def test_ask_user_signature(self):
        a = _make_ask_user_action("what?")
        sig = _action_signature(a)
        assert sig.startswith("ask_user|")


# ═══════════════════════════════════════════════════════════════════════════════
# Planner guardrails
# ═══════════════════════════════════════════════════════════════════════════════

class TestExtractJson:

    def test_raw_json(self):
        assert _extract_json('{"type": "final"}') == '{"type": "final"}'

    def test_fenced_json(self):
        text = '```json\n{"type": "final"}\n```'
        assert _extract_json(text) == '{"type": "final"}'

    def test_no_json(self):
        assert _extract_json("no json here") is None

    def test_nested_json(self):
        text = 'Some text {"type": "tool_call", "tool": {"intent": {"tool_slug": "rag", "op": "search"}, "input": {}}} more text'
        result = _extract_json(text)
        assert result is not None
        parsed = json.loads(result)
        assert parsed["type"] == "tool_call"


class TestValidateNextAction:

    def test_valid_tool_call(self):
        aa = _make_available_actions([("rag", "search")])
        action = _make_tool_call_action("rag", "search")
        assert validate_next_action(action, aa) is None

    def test_invalid_tool_not_in_whitelist(self):
        aa = _make_available_actions([("rag", "search")])
        action = _make_tool_call_action("jira", "create")
        error = validate_next_action(action, aa)
        assert error is not None
        assert "not in available actions" in error

    def test_tool_call_missing_tool_field(self):
        aa = _make_available_actions([("rag", "search")])
        action = NextAction(type=ActionType.TOOL_CALL)
        error = validate_next_action(action, aa)
        assert error is not None
        assert "missing" in error

    def test_ask_user_valid(self):
        aa = _make_available_actions()
        action = _make_ask_user_action("what?")
        assert validate_next_action(action, aa) is None

    def test_ask_user_missing_field(self):
        aa = _make_available_actions()
        action = NextAction(type=ActionType.ASK_USER)
        error = validate_next_action(action, aa)
        assert error is not None

    def test_final_valid(self):
        aa = _make_available_actions()
        action = _make_final_action("done")
        assert validate_next_action(action, aa) is None

    def test_final_missing_field(self):
        aa = _make_available_actions()
        action = NextAction(type=ActionType.FINAL)
        error = validate_next_action(action, aa)
        assert error is not None


class TestBuildWhitelist:

    def test_whitelist_from_available_actions(self):
        aa = _make_available_actions([("rag", "search"), ("jira", "create")])
        wl = _build_whitelist(aa)
        assert ("rag", "search") in wl
        assert ("jira", "create") in wl
        assert ("netbox", "query") not in wl


class TestFallbackAskUser:

    def test_returns_ask_user(self):
        action = _fallback_ask_user()
        assert action.type == ActionType.ASK_USER
        assert action.ask_user is not None
        assert len(action.ask_user.question) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# PolicyEngine
# ═══════════════════════════════════════════════════════════════════════════════

class TestPolicyEngine:

    def test_allow_normal_tool_call(self):
        engine = PolicyEngine(max_iters=20)
        aa = _make_available_actions([("rag", "search")])
        ctx = RunContextCompact(goal="test")
        action = _make_tool_call_action("rag", "search")
        decision = engine.evaluate(action, ctx, aa)
        assert decision.decision == PolicyDecisionType.ALLOW

    def test_block_on_max_iters(self):
        engine = PolicyEngine(max_iters=5)
        aa = _make_available_actions([("rag", "search")])
        ctx = RunContextCompact(goal="test")
        ctx.iter_count = 5
        action = _make_tool_call_action("rag", "search")
        decision = engine.evaluate(action, ctx, aa)
        assert decision.decision == PolicyDecisionType.BLOCK

    def test_require_input_on_loop(self):
        engine = PolicyEngine(max_iters=20)
        aa = _make_available_actions([("rag", "search")])
        ctx = RunContextCompact(goal="test")
        action = _make_tool_call_action("rag", "search", {"query": "same"})
        for _ in range(LOOP_THRESHOLD):
            ctx.record_action(action)
        decision = engine.evaluate(action, ctx, aa)
        assert decision.decision == PolicyDecisionType.REQUIRE_INPUT

    def test_block_tool_not_in_whitelist(self):
        engine = PolicyEngine(max_iters=20)
        aa = _make_available_actions([("rag", "search")])
        ctx = RunContextCompact(goal="test")
        action = _make_tool_call_action("jira", "create")
        decision = engine.evaluate(action, ctx, aa)
        assert decision.decision == PolicyDecisionType.BLOCK

    def test_allow_ask_user(self):
        engine = PolicyEngine(max_iters=20)
        aa = _make_available_actions()
        ctx = RunContextCompact(goal="test")
        action = _make_ask_user_action("what?")
        decision = engine.evaluate(action, ctx, aa)
        assert decision.decision == PolicyDecisionType.ALLOW

    def test_allow_final(self):
        engine = PolicyEngine(max_iters=20)
        aa = _make_available_actions()
        ctx = RunContextCompact(goal="test")
        action = _make_final_action("done")
        decision = engine.evaluate(action, ctx, aa)
        assert decision.decision == PolicyDecisionType.ALLOW

    def test_require_confirmation_for_destructive(self):
        engine = PolicyEngine(
            max_iters=20,
            require_confirmation_for_destructive=True,
        )
        tools = [ToolAction(
            tool_slug="netbox",
            op="delete",
            side_effects="destructive",
            risk_level="high",
            idempotent=False,
        )]
        aa = AvailableActions(agents=[], tools=tools)
        ctx = RunContextCompact(goal="test")
        action = _make_tool_call_action("netbox", "delete")
        decision = engine.evaluate(action, ctx, aa)
        assert decision.decision == PolicyDecisionType.REQUIRE_CONFIRMATION

    def test_allow_destructive_when_not_required(self):
        engine = PolicyEngine(
            max_iters=20,
            require_confirmation_for_destructive=False,
        )
        tools = [ToolAction(
            tool_slug="netbox",
            op="delete",
            side_effects="destructive",
            risk_level="high",
            idempotent=False,
        )]
        aa = AvailableActions(agents=[], tools=tools)
        ctx = RunContextCompact(goal="test")
        action = _make_tool_call_action("netbox", "delete")
        decision = engine.evaluate(action, ctx, aa)
        assert decision.decision == PolicyDecisionType.ALLOW

    def test_require_confirmation_for_write(self):
        engine = PolicyEngine(
            max_iters=20,
            require_confirmation_for_write=True,
        )
        tools = [ToolAction(
            tool_slug="jira",
            op="create",
            side_effects="write",
            risk_level="medium",
        )]
        aa = AvailableActions(agents=[], tools=tools)
        ctx = RunContextCompact(goal="test")
        action = _make_tool_call_action("jira", "create")
        decision = engine.evaluate(action, ctx, aa)
        assert decision.decision == PolicyDecisionType.REQUIRE_CONFIRMATION


# ═══════════════════════════════════════════════════════════════════════════════
# StopReason enum
# ═══════════════════════════════════════════════════════════════════════════════

class TestStopReason:

    def test_values(self):
        assert StopReason.DONE.value == "done"
        assert StopReason.WAITING_INPUT.value == "waiting_input"
        assert StopReason.WAITING_CONFIRMATION.value == "waiting_confirmation"
        assert StopReason.LOOP_DETECTED.value == "loop_detected"
        assert StopReason.MAX_ITERS.value == "max_iters"
        assert StopReason.FAILED.value == "failed"
