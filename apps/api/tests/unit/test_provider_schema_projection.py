import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.adapters.impl.openai_compatible_llm import OpenAICompatibleLLM
from app.adapters.impl.llm_schema import project_provider_schema
from app.adapters.interfaces.llm import LLMErrorCode, LLMProviderError, ResolvedLLMConnection
from app.agents.contracts import ProviderExecutionTarget, ResolvedOperation
from app.agents.protocol import build_tools_payload
from app.agents.runtime.llm import LLMAdapter
from app.agents.runtime.model_context import outbound_request_snapshot
from app.agents.runtime.tools import OperationExecutionFacade
from app.models.system_llm_role import SystemLLMRoleType
from app.runtime.events import RuntimeEventType
from app.runtime.llm.structured import StructuredCallError, StructuredLLMCall
from app.runtime.orchestrator_contracts import TaskRequest, task_completion_json_schema
from app.runtime.planner.response_contract import PlannerStep
from app.runtime.turn_preflight import TurnPreflightDecision
from app.services.runtime_limits_service import ModelCallLimits


def client_with_completion(monkeypatch, create):
    connection = ResolvedLLMConnection(
        model_alias="local", provider_model_name="local", base_url="http://example.test/v1",
        connector="litellm_http", api_key=None, extra_config={},
    )
    llm = OpenAICompatibleLLM(connection_resolver=SimpleNamespace(resolve=AsyncMock(return_value=connection)))
    sdk = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(llm, "_get_or_create_client", lambda **kwargs: sdk)
    return llm


def completion(content: str):
    choice = SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=[]), finish_reason="stop")
    return SimpleNamespace(choices=[choice], usage=None, model="local")


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "schema", "route_key"), [
    (SystemLLMRoleType.TURN_PREFLIGHT, TurnPreflightDecision, "route"),
    (SystemLLMRoleType.PLANNER, PlannerStep, "kind"),
])
@pytest.mark.parametrize("query_length", [4000, 4001])
async def test_structured_role_projects_large_bounds_but_locally_validates_query(
    monkeypatch, role, schema, route_key, query_length,
):
    query = "x" * query_length

    async def grammar_server(**kwargs):
        response_format = kwargs["response_format"]
        assert response_format["type"] == "json_schema"
        definitions = response_format["json_schema"]["schema"]["$defs"]
        for name in ("FileDataSearchInput", "HippoMemorySearchInput"):
            field = definitions[name]["properties"]["query"]
            assert field == {"type": "string", "minLength": 1}
        if schema is TurnPreflightDecision:
            assert definitions["ArtifactDescription"]["properties"]["description"]["maxLength"] == 600
        return completion(json.dumps({
            route_key: "tool_call", "tool_call": {"tool": "memory.search", "arguments": {"query": query}},
        }))

    create = AsyncMock(side_effect=grammar_server)
    llm = client_with_completion(monkeypatch, create)
    call = StructuredLLMCall(session=AsyncMock(), llm_client=llm)
    call.role_service.get_role_config = AsyncMock(return_value={"role_type": role.value, "model": "local"})
    call.limits_service.resolve_model = AsyncMock(return_value=ModelCallLimits(request_timeout_s=5, max_retries=0))
    event_sink = AsyncMock()
    trace = {"event_sink": event_sink, "trace_parent_entity_id": "execution"}

    if query_length == 4000:
        result = await call.invoke(role=role, payload={}, schema=schema, **trace)
        assert result.value.tool_call.arguments.query == query
    else:
        with pytest.raises(StructuredCallError, match="4000"):
            await call.invoke(role=role, payload={}, schema=schema, **trace)
    assert create.await_count == 1
    request_event = next(call.args[0] for call in event_sink.await_args_list if call.args[0].type is RuntimeEventType.LLM_REQUEST)
    assert request_event.data["request_params"]["response_format"] == create.await_args.kwargs["response_format"]
    definitions = schema.model_json_schema()["$defs"]
    for name in ("FileDataSearchInput", "HippoMemorySearchInput"):
        assert definitions[name]["properties"]["query"]["maxLength"] == 4000


@pytest.mark.asyncio
async def test_native_tool_wire_projection_preserves_identifiers_and_literals(monkeypatch):
    schema = {
        "type": "object",
        "properties": {
            "maxLength": {"anyOf": [{"type": "string", "maxLength": 2000}, {"type": "null"}]},
            "literal": {"const": {"maxLength": 2000}},
            "bounded": {"type": "string", "maxLength": 1999},
            "exclusive": {"oneOf": [{"type": "string", "maxLength": 4000}, {"type": "null"}]},
            "nested": {"type": "array", "items": {"type": "string", "maxLength": 4000}},
        },
        "required": ["maxLength"],
    }
    operation = ResolvedOperation(
        operation_slug="example", operation="example", name="Example", scope="system",
        description="Example operation", source="local", data_instance_id="system", data_instance_slug="system",
        input_schema=schema,
        target=ProviderExecutionTarget(operation_slug="example", provider_type="local", handler_slug="example",
                                       data_instance_id="system", data_instance_slug="system"),
    )
    original = deepcopy(schema)
    create = AsyncMock(return_value=completion("ok"))
    llm = client_with_completion(monkeypatch, create)
    messages = [{"role": "user", "content": '{"maxLength":4000}'}]
    tools = build_tools_payload([operation], project_for_provider=OperationExecutionFacade.has_full_argument_validation())
    snapshot = outbound_request_snapshot(model="local", messages=messages, tools=tools, tool_choice="auto")

    await LLMAdapter(llm).call_raw(snapshot["messages"], model="local", tools=snapshot["tools"])

    request = create.await_args.kwargs
    wire = request["tools"][0]["function"]["parameters"]
    assert wire["properties"]["maxLength"] == {"anyOf": [{"type": "string"}, {"type": "null"}]}
    assert wire["properties"]["nested"]["items"] == {"type": "string"}
    for field in ("literal", "bounded", "exclusive"):
        assert wire["properties"][field] == schema["properties"][field]
    assert wire["required"] == ["maxLength"]
    assert request["messages"] == messages
    assert request["tools"] == snapshot["tools"]
    assert operation.input_schema == original
    assert OperationExecutionFacade._validate_args(operation, {"maxLength": "x" * 2000}) is None
    assert OperationExecutionFacade._validate_args(operation, {"maxLength": "x" * 2001}) is not None

    monkeypatch.setattr("app.agents.runtime.tools._JSONSCHEMA_AVAILABLE", False)
    with_builtin_validation = build_tools_payload(
        [operation], project_for_provider=OperationExecutionFacade.has_full_argument_validation(),
    )
    assert with_builtin_validation[0]["function"]["parameters"] == original


def test_native_completion_keeps_question_bound_in_validation_schema():
    task = TaskRequest(task_id="report", executor="agent", intent="report", instructions="Return a report")
    canonical = task_completion_json_schema(task)
    wire = task_completion_json_schema(task, provider_compatible=True)
    assert canonical["$defs"]["InteractionQuestion"]["properties"]["question"]["maxLength"] == 4000
    assert "maxLength" not in wire["$defs"]["InteractionQuestion"]["properties"]["question"]


@pytest.mark.parametrize("keyword", ["not", "if", "oneOf", "contains"])
def test_projection_retains_definitions_under_sensitive_references(keyword):
    reference = {"$ref": "#/$defs/Bounded"}
    schema = {
        "$defs": {"Bounded": {"type": "string", "maxLength": 4000}},
        keyword: [reference] if keyword == "oneOf" else reference,
    }
    assert project_provider_schema(schema) == schema
    assert schema["$defs"]["Bounded"]["maxLength"] == 4000


@pytest.mark.asyncio
async def test_structured_json_mode_fallback_keeps_canonical_length_bounds(monkeypatch):
    rejection = LLMProviderError(
        code=LLMErrorCode.STRUCTURED_OUTPUT_UNSUPPORTED, safe_message="Unsupported", retryable=False,
    )
    create = AsyncMock(side_effect=[rejection, completion(json.dumps({
        "route": "tool_call", "tool_call": {"tool": "memory.search", "arguments": {"query": "search"}},
    }))])
    llm = client_with_completion(monkeypatch, create)
    call = StructuredLLMCall(session=AsyncMock(), llm_client=llm)
    call.role_service.get_role_config = AsyncMock(return_value={"role_type": "turn_preflight", "model": "local"})
    call.limits_service.resolve_model = AsyncMock(return_value=ModelCallLimits(request_timeout_s=5, max_retries=1))
    monkeypatch.setattr("app.runtime.llm.structured.asyncio.sleep", AsyncMock())

    await call.invoke(role=SystemLLMRoleType.TURN_PREFLIGHT, payload={}, schema=TurnPreflightDecision)

    assert create.await_count == 2
    fallback = create.await_args.kwargs
    assert fallback["response_format"] == {"type": "json_object"}
    assert '"maxLength":4000' in fallback["messages"][0]["content"]
