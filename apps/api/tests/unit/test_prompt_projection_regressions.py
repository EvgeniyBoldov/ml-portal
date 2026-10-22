"""Regressions for data repeated at the model boundary."""
import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.system_llm_role import SystemLLMRoleType
from app.runtime.llm.structured import StructuredLLMCall
from app.runtime.planner.graph_planner import PlannerStep
from app.runtime.orchestrator import GraphOrchestrator
from app.runtime.synthesis_context import SynthesisContextBuilder
from app.services.runtime_limits_service import ModelCallLimits
from app.runtime.prompt_projections import task_result_for_prompt, preflight_context


@pytest.mark.asyncio
async def test_repeated_schema_repairs_replace_previous_correction_and_omit_error_input(monkeypatch):
    bad = {"proposal": {"terminal": "planner", "tasks": [{
        "task_id": "fetch", "executor": "inventory", "intent": "get inventory",
        "instructions": "RETAIN_OBSERVED_INPUT_" * 100,
    }]}}
    good = {"kind": "proposal", **bad}
    bad = {"kind": "invalid", **bad}
    requests = []

    async def chat(messages, **kwargs):
        requests.append(deepcopy(messages))
        return json.dumps(bad if len(requests) < 4 else good)

    call = StructuredLLMCall(session=AsyncMock(), llm_client=SimpleNamespace(chat=chat))
    call.role_service.get_role_config = AsyncMock(return_value={"role_type": "planner", "model": "local"})
    call.limits_service.resolve_model = AsyncMock(return_value=ModelCallLimits(request_timeout_s=5, max_retries=3))
    monkeypatch.setattr("app.runtime.llm.structured.asyncio.sleep", AsyncMock())
    result = await call.invoke(role=SystemLLMRoleType.PLANNER, payload={"goal": "inventory"}, schema=PlannerStep)
    assert result.value.kind == "proposal"
    assert [len(messages) for messages in requests] == [2, 4, 4, 4]
    assert requests[-1][-2]["content"] == json.dumps(bad)
    assert "RETAIN_OBSERVED_INPUT_" not in requests[-1][-1]["content"]
    assert "$.kind" in requests[-1][-1]["content"]
    assert len(requests[-1][-1]["content"]) < 1000


def test_task_data_and_answer_are_sent_once_to_planner_and_synthesizer():
    observed = {"devices": [{"name": "observed-device-812"}]}
    result = {"answer": "confirmed-answer-912", "description": "confirmed-answer-912",
              "structured_response": observed, "outputs": observed, "completion": "fulfilled"}
    plan = {"goal": "inventory", "tasks": {"fetch": {"task_id": "fetch", "status": "completed", "result": result}},
            "iterations": [{"id": "final", "synthesis_brief": {"user_question": "inventory"}}]}
    original = deepcopy(plan)
    for payload in (GraphOrchestrator._planner_ledger(plan), SynthesisContextBuilder().build(plan=plan, iteration_id="final")):
        rendered = json.dumps(payload)
        assert rendered.count("observed-device-812") == 1
        assert rendered.count("confirmed-answer-912") == 1
    assert plan == original


def test_projection_keeps_distinct_legacy_data_and_source_content():
    result = {"answer": "short", "description": "additional explanation",
              "structured_response": {"a": 1}, "outputs": {"b": 2}}
    assert task_result_for_prompt(result) == result


def test_scope_projection_keeps_authoritative_selection_and_conversation_focus():
    scope = {"keys": ["alpha"], "ceiling_keys": ["alpha", "beta"], "mode": "replace"}
    project = {"scope_context": scope, "effective_scope_keys": ["alpha"], "execution_context": {"scope_keys": ["alpha"]}}
    chat = {"focus": {"scope_keys": ["alpha"], "topic": "inventory", "entity_refs": ["device"]},
            "recent_anchor": {"assistant_outcome": "previous answer"}}
    p, c = preflight_context(project, chat)
    assert p == {"scope_context": scope}
    assert c["focus"] == {"topic": "inventory", "entity_refs": ["device"]}
    assert c["recent_anchor"] == chat["recent_anchor"]
    assert chat["focus"]["scope_keys"] == ["alpha"]


@pytest.mark.asyncio
async def test_failed_context_check_still_emits_complete_allocation_metrics():
    from app.adapters.impl.openai_compatible_llm import OpenAICompatibleLLM
    from app.adapters.interfaces.llm import LLMCallOptions, LLMProviderError
    from app.adapters.impl.llm_context import estimate_request_tokens
    create = AsyncMock()
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    probe = AsyncMock()
    request = {"model": "unknown", "messages": [{"role": "user", "content": "word " * 2000}]}
    with pytest.raises(LLMProviderError):
        await OpenAICompatibleLLM._create_completion(object.__new__(OpenAICompatibleLLM), client,
            request, 1024, 30, LLMCallOptions(on_context_allocation=probe))
    create.assert_not_awaited()
    allocation = probe.await_args.args[0]
    assert allocation["context_window"] == 1024
    assert allocation["estimated_input_tokens"] == estimate_request_tokens(request)
    assert allocation["max_output_tokens"] < allocation["minimum_output_tokens"]


def test_protocol_repair_preserves_successful_tool_history():
    from app.runtime.llm.repair import ProtocolRepair
    repair = ProtocolRepair()
    messages = [{"role": "user", "content": "task"}]
    repair.apply(messages, "bad first", "fix")
    repair.apply(messages, "bad latest", "fix latest")
    assert len(messages) == 3
    messages.extend([{"role": "assistant", "content": "read source"},
                     {"role": "tool", "content": "confirmed data"}])
    repair.apply(messages, "bad after retrieval", "fix again")
    assert messages[4]["content"] == "confirmed data"
    repair.apply(messages, "corrected later", "last feedback")
    assert messages[4]["content"] == "confirmed data" and len(messages) == 7


@pytest.mark.parametrize("native", [False, True])
def test_operation_contract_has_one_transport_and_no_extra_system_card(native):
    from app.agents.contracts import ResolvedOperation, ProviderExecutionTarget
    from app.agents.runtime.prompt_assembler import PromptAssembler
    from app.agents.runtime.policy import PolicyLimits
    operation = ResolvedOperation(operation_slug="test.read", operation="test.read", name="Read", scope="system",
        description="read observed records", source="local", data_instance_id="system", data_instance_slug="system",
        input_schema={"type": "object", "properties": {"source_ref": {"type": "string"}}},
        target=ProviderExecutionTarget(operation_slug="test.read", provider_type="local", handler_slug="test.read",
                                      data_instance_id="system", data_instance_slug="system"))
    request = SimpleNamespace(prompt="Agent policy", agent_version=None, resolved_data_instances=[])
    bundle = PromptAssembler().assemble(request, policy_limits=PolicyLimits(),
        resolved_operations=[operation], platform_config={"native_tool_calling": native})
    assert ("ОБЯЗАТЕЛЬНЫЕ ПРАВИЛА" in bundle.system_operations_prompt) is native
    assert bundle.system_prompt.count('"properties"') == (0 if native else 1)
    assert bool(bundle.operations_prompt) != native
