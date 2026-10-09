from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from jsonschema import Draft202012Validator

from app.models.system_llm_role import SystemLLMRole, SystemLLMRoleType
from app.runtime.llm.structured import StructuredLLMCall
from app.runtime.orchestrator_contracts import PlanRequest, PlannerContext
from app.runtime.planner.graph_planner import GraphPlanner, PlannerStep
from app.runtime.synthesizer import _compile_role_prompt as compile_synthesis_prompt
from app.services.orchestration_prompts import PLANNER_PROMPT_V3, SYNTHESIZER_PROMPT_V3
from app.services.system_role_prompt import compile_system_role_prompt


def test_role_sections_are_identical_in_database_and_both_callers():
    role = SystemLLMRole(role_type="planner", **PLANNER_PROMPT_V3)
    config = {"role_type": "planner", **PLANNER_PROMPT_V3}
    base = compile_system_role_prompt(config)
    assert role.compiled_prompt == base
    assert compile_synthesis_prompt(config, None) == base
    prompt = StructuredLLMCall._compile_role_prompt(config, None, schema=PlannerStep)
    assert prompt.startswith(base + "\n\n")
    assert prompt.count("# RULES\n") == 1
    assert prompt.count("# OUTPUT REQUIREMENTS\n") == 1
    assert prompt.count("# PLANNER TOOL LOOP\n") == 1


def test_planner_overrides_are_preserved_with_locked_generated_schema():
    config = {"role_type": "planner", **PLANNER_PROMPT_V3}
    overrides = {"rules": "CUSTOM RULES", "output_requirements": "CUSTOM OUTPUT", "examples": []}
    prompt = StructuredLLMCall._compile_role_prompt(config, overrides, schema=PlannerStep)
    assert "CUSTOM RULES" in prompt
    assert "CUSTOM OUTPUT" in prompt
    assert PLANNER_PROMPT_V3["rules"] not in prompt
    assert "# EXAMPLES" not in prompt
    encoded = prompt.split("по следующей схеме (без markdown и пояснений):\n", 1)[1]
    schema = json.loads(encoded)
    assert schema == StructuredLLMCall._compact_response_schema(PlannerStep.model_json_schema())
    assert "\n" not in encoded
    Draft202012Validator.check_schema(schema)


def test_override_none_inherits_and_empty_string_clears_section():
    config = {"identity": "Identity", "rules": "Rules", "prompt": "Legacy rules"}
    assert "Rules" in compile_system_role_prompt(config, {"rules": None})
    cleared = compile_system_role_prompt(config, {"identity": "", "rules": ""})
    assert "Rules" not in cleared and "Legacy rules" not in cleared


def test_structured_role_keeps_legacy_prompt_when_sections_are_absent():
    prompt = StructuredLLMCall._compile_role_prompt(
        {"role_type": "planner", "prompt": "LEGACY PLANNER"}, None, schema=PlannerStep,
    )
    assert prompt.startswith("LEGACY PLANNER\n\n")


def test_examples_render_as_valid_json_and_match_generated_and_runtime_contracts():
    rendered = compile_system_role_prompt(PLANNER_PROMPT_V3)
    schema = StructuredLLMCall._compact_response_schema(PlannerStep.model_json_schema())
    validator = Draft202012Validator(schema)
    encoded_outputs = [line.removeprefix("Output: ") for line in rendered.splitlines() if line.startswith("Output: ")]
    assert len(encoded_outputs) == len(PLANNER_PROMPT_V3["examples"])
    for encoded, example in zip(encoded_outputs, PLANNER_PROMPT_V3["examples"]):
        response = json.loads(encoded)
        assert response == example["output"]
        validator.validate(response)
        PlannerStep.model_validate(response)
    initial = PlannerStep.model_validate(PLANNER_PROMPT_V3["examples"][0]["output"]).proposal
    assert initial.tasks[0].executor in {agent["slug"] for agent in PLANNER_PROMPT_V3["examples"][0]["input"]["available_agents"]}
    assert initial.tasks[0].freshness_policy.value == "require_retrieval"
    assert not initial.bindings


@pytest.mark.asyncio
async def test_initial_inventory_handoff_sends_database_rules_and_only_one_protocol():
    planner = GraphPlanner(session=SimpleNamespace(), llm_client=AsyncMock())
    planner._llm.role_service.get_role_config = AsyncMock(return_value={"role_type": "planner", **PLANNER_PROMPT_V3})
    planner._llm.invoke = AsyncMock(return_value=SimpleNamespace(
        value=PlannerStep.model_validate(PLANNER_PROMPT_V3["examples"][0]["output"]),
    ))
    context = PlannerContext(**PLANNER_PROMPT_V3["examples"][0]["input"], trigger="initial")
    proposal = await planner.plan(request=PlanRequest(context=context), sandbox_overrides={
        "role_overrides": {"planner": {"output_requirements": "SANDBOX REQUIREMENTS"}},
    })
    assert proposal.tasks[0].executor == "inventory.netbox"
    call = planner._llm.invoke.call_args.kwargs
    assert call["role"] == SystemLLMRoleType.PLANNER
    assert PLANNER_PROMPT_V3["rules"] in call["system_prompt"]
    assert "SANDBOX REQUIREMENTS" in call["system_prompt"]
    assert call["system_prompt"].count("# PLANNER TOOL LOOP") == 1
    assert call["system_prompt"].count("# RUNTIME RESPONSE CONTRACT") == 1
    assert call["payload"]["execution_ledger"]["tasks"] == []


def test_synthesizer_defaults_and_configured_prompt_share_grounding_policy():
    from app.services.v3_role_defaults import SYNTHESIZER_V3

    for field, value in SYNTHESIZER_PROMPT_V3.items():
        assert SYNTHESIZER_V3[field] == value
    prompt = compile_synthesis_prompt(SYNTHESIZER_V3, {"rules": "CUSTOM GROUNDING"})
    assert "CUSTOM GROUNDING" in prompt
    assert SYNTHESIZER_PROMPT_V3["rules"] not in prompt
