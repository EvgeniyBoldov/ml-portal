"""Regressions at the model response / runtime contract boundary."""
import json
from copy import deepcopy

import pytest
from jsonschema import Draft202012Validator
from pydantic import BaseModel

from app.runtime.llm.structured import StructuredLLMCall, StructuredCallError
from app.runtime.planner.graph_planner import PlannerStep
from app.runtime.orchestrator_contracts import TaskRequest, TaskCompletionDeclaration, task_completion_json_schema
from app.runtime.partial_answer import limitation_message

TASK = {'task_id': 't', 'executor': 'inventory.netbox', 'intent': 'Read', 'instructions': 'Read',
        'inputs': {'values': ['', ' ', None, {}, [], {'nested': ['', 0, False]}]}}
PROPOSAL = {'terminal': 'planner', 'tasks': [TASK]}


def test_structured_parser_preserves_arbitrary_task_data():
    result = StructuredLLMCall._parse_and_validate(json.dumps({'kind': 'proposal', 'proposal': PROPOSAL}), PlannerStep)
    assert result.proposal.tasks[0].inputs == TASK['inputs']


def test_structured_parser_does_not_convert_objects_into_references():
    class References(BaseModel):
        refs: list[str]
    with pytest.raises(StructuredCallError):
        StructuredLLMCall._parse_and_validate('{"refs":[{"name":"invented-ref"}]}', References)


@pytest.mark.parametrize('wrapper', ['missing_kind', 'misplaced_kind', 'outer_wrapper', 'bare'])
def test_planner_adapter_recovers_only_unambiguous_envelopes(wrapper):
    canonical = {'kind': 'proposal', 'proposal': deepcopy(PROPOSAL)}
    raw = {'missing_kind': {'proposal': PROPOSAL},
           'misplaced_kind': {'proposal': {'kind': 'proposal', **PROPOSAL}},
           'outer_wrapper': {'proposal': canonical}, 'bare': PROPOSAL}[wrapper]
    original = deepcopy(raw)
    result = StructuredLLMCall._parse_and_validate(json.dumps(raw), PlannerStep)
    assert result.proposal.tasks[0].inputs == TASK['inputs']
    assert raw == original


@pytest.mark.parametrize('raw', [
    {'kind': 'interaction', 'proposal': PROPOSAL},
    {'proposal': PROPOSAL, 'interaction': {'question': 'Which?'}},
    {'proposal': {'kind': 'interaction', **PROPOSAL}},
    {'proposal': {'proposal': {'kind': 'proposal', 'proposal': PROPOSAL}}},
    {'proposal': PROPOSAL, 'unexpected': None},
])
def test_planner_adapter_rejects_ambiguous_or_conflicting_envelopes(raw):
    with pytest.raises(StructuredCallError):
        StructuredLLMCall._parse_and_validate(json.dumps(raw), PlannerStep)


def test_planner_wire_brief_needs_no_copy_of_immutable_goal():
    raw = {'kind': 'proposal', 'proposal': {'terminal': 'synthesis', 'synthesis_brief': {
        'purpose': 'Answer', 'planned_work': 'Done', 'answer_requirements': 'Use results'}}}
    Draft202012Validator(PlannerStep.model_json_schema()).validate(raw)
    result = PlannerStep.model_validate(raw).to_runtime_proposal(goal='Read inventory')
    assert result.synthesis_brief.user_question == 'Read inventory'
    raw['proposal']['synthesis_brief']['user_question'] = 'A different question'
    legacy = PlannerStep.model_validate(raw).to_runtime_proposal(goal='Read inventory')
    assert legacy.synthesis_brief.user_question == 'A different question'


def test_planner_wire_schema_omits_runtime_owned_fields():
    schema = PlannerStep.model_json_schema()
    task_ref = next(v for v in schema['$defs'].values() if 'executor' in v.get('properties', {}))
    assert 'scope_context' not in task_ref['properties']
    assert 'protocol_version' not in task_ref['properties']
    contract_ref = next(v for v in schema['$defs'].values() if 'contract_id' in v.get('properties', {}))
    assert 'contract_hash' not in contract_ref['properties']
    assert 'input_schema' not in contract_ref['properties']


@pytest.mark.parametrize('payload,valid', [
    ({'completion': 'needs'}, False),
    ({'completion': 'fulfilled', 'needs': [{'ref': 'n', 'key': 'x', 'description': 'Missing'}]}, False),
    ({'completion': 'interaction'}, False),
    ({'completion': 'fulfilled', 'interaction': {'question': 'Which?', 'response_type': 'text'}}, False),
    ({'completion': 'interaction', 'interaction': {'question': 'Which?', 'response_type': 'text'}}, True),
    ({'completion': 'needs', 'needs': [{'ref': 'n', 'key': 'x', 'description': 'Missing'}]}, True),
    ({'completion': 'fulfilled', 'structured_response': {'values': ['', None]}}, True),
])
def test_agent_schema_and_validator_agree_on_completion_branches(payload, valid):
    task = TaskRequest(task_id='t', executor='a', intent='Read', instructions='Read')
    for provider in (False, True):
        schema = task_completion_json_schema(task, provider_compatible=provider)
        assert Draft202012Validator(schema).is_valid(payload) is valid
    if valid:
        TaskCompletionDeclaration.model_validate(payload)
    else:
        with pytest.raises(ValueError):
            TaskCompletionDeclaration.model_validate(payload)


def test_schema_extra_forbidden_is_never_reported_as_access_denial():
    assert 'прав доступа' not in limitation_message('schema validation failed: extra_forbidden')
    assert 'прав доступа' in limitation_message('operation forbidden: 403')


def test_synthesizer_advertises_the_actual_delivery_contract():
    from app.services.system_llm_role_contracts import build_response_contract
    from app.runtime.synthesis_files import FileSynthesisOutput
    assert build_response_contract('synthesizer')['format'] == 'plain_text'
    contract = build_response_contract('synthesizer', delivery='files')
    assert contract['schema'] == FileSynthesisOutput.model_json_schema()
    assert contract['examples_v2'] is None


@pytest.mark.asyncio
async def test_normalized_planner_response_is_traced_without_repeating_data(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from uuid import uuid4
    from app.models.system_llm_role import SystemLLMRoleType
    from app.services.runtime_limits_service import ModelCallLimits
    raw = json.dumps({'proposal': PROPOSAL})
    client = SimpleNamespace(chat=AsyncMock(return_value=raw))
    call = StructuredLLMCall(session=AsyncMock(), llm_client=client)
    call.role_service.get_role_config = AsyncMock(return_value={'role_type': 'planner', 'model': 'local'})
    call.limits_service.resolve_model = AsyncMock(return_value=ModelCallLimits(request_timeout_s=5, max_retries=0))
    events = []
    async def sink(event):
        events.append(event)
    result = await call.invoke(role=SystemLLMRoleType.PLANNER, payload={'goal': 'Read'}, schema=PlannerStep,
                              event_sink=sink, trace_parent_entity_id=str(uuid4()))
    assert client.chat.await_count == 1
    assert result.raw_response == raw
    normalization = next(e.data for e in events if e.data.get('stage') == 'llm_response_normalized')
    assert normalization['normalizations'] == [{'path': '$', 'operation': 'infer_proposal_kind'}]
    assert 'values' not in json.dumps(normalization)
    assert result.value.to_runtime_proposal(goal='Read').tasks[0].inputs == TASK['inputs']


def test_failure_policy_metadata_does_not_promise_fixed_retries_or_text_filters():
    from app.services.system_llm_role_contracts import build_response_contract
    assert build_response_contract('planner')['failure_policy']['on_invalid'] == 'retry_with_runtime_limits_then_fail'
    assert build_response_contract('fact_extractor')['failure_policy']['on_invalid'] == 'retry_with_runtime_limits_then_configured_fallback'
    assert build_response_contract('synthesizer')['failure_policy']['on_invalid'] == 'report_stream_failure'
