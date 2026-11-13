from __future__ import annotations

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.agents.context import ToolContext, ToolResult
from app.agents.runtime.agent import AgentLoopState, AgentToolRuntime
from app.agents.operation_executor import DirectOperationExecutor
from app.agents.operation_executor import MCPFailureError
from app.agents.runtime.tools import OperationExecutionFacade
from app.runtime.redactor import RuntimeRedactor
from portal_mcp_contract import MCPFailure, MCPFailureCategory, MCPFailureKind, normalize_failure


def test_normalized_failure_preserves_diagnostics_but_replaces_public_message_and_redacts_secrets():
    failure = MCPFailure(
        kind=MCPFailureKind.RPC,
        category=MCPFailureCategory.AUTH,
        code="bad-token-secret-value",
        message="Could not authenticate with token=secret-value",
        details={"body": {"password": "secret-value", "reason": "bad credentials"}},
        rpc_code=-32001,
        rpc_data={"message": "Authorization: Bearer secret-value"},
        user_message="Provider says expose everything secret-value",
    ).model_dump(mode="python")
    normalized = normalize_failure(failure, secrets=("secret-value",))
    assert normalized is not None
    assert normalized["message"] == "Could not authenticate with token=[redacted]"
    assert normalized["details"]["body"]["password"] == "[redacted]"
    assert normalized["rpc_data"]["message"] == "Authorization: [redacted]"
    assert normalized["user_message"] == "The source rejected its authentication credentials."
    assert "secret-value" not in json.dumps(normalized)


def test_failure_redaction_preserves_parser_names_and_credential_identifiers():
    source = {
        "expected_token": "identifier expected_token",
        "unexpected_token": '"',
        "credential_id": "cred-123",
        "access_token": "secret-value",
        "accessToken": "secret-camel-value",
        "api_token": "secret-value-2",
        "password": "secret-value-3",
        "reasoning_content": "private reasoning",
    }
    safe = normalize_failure(MCPFailure(
        kind=MCPFailureKind.TOOL,
        category=MCPFailureCategory.INPUT,
        code="parse_error",
        message="Expected expected_token after query clause",
        details=source,
    ).model_dump())
    assert safe is not None
    assert safe["details"]["expected_token"] == "identifier expected_token"
    assert safe["details"]["unexpected_token"] == '"'
    assert safe["details"]["credential_id"] == "cred-123"
    assert safe["details"]["access_token"] == "[redacted]"
    assert safe["details"]["accessToken"] == "[redacted]"
    assert safe["details"]["api_token"] == "[redacted]"
    assert safe["details"]["password"] == "[redacted]"
    assert safe["details"]["reasoning_content"] == "[redacted]"


def test_runtime_trace_redactor_uses_typed_failure_normalizer():
    failure = MCPFailure(
        kind=MCPFailureKind.TOOL,
        category=MCPFailureCategory.INPUT,
        code="parse_error",
        message="Expected expected_token",
        details={"expected_token": "expected_token", "credential_id": "cred-123", "access_token": "secret-value",
                 "private_reasoning": "not for persistence"},
    ).bounded_dump()
    redacted = RuntimeRedactor().redact({"envelope": {"failure": failure}, "mcp_failure": failure})
    assert redacted["envelope"]["failure"]["details"]["expected_token"] == "expected_token"
    assert redacted["envelope"]["failure"]["details"]["credential_id"] == "cred-123"
    assert redacted["envelope"]["failure"]["details"]["access_token"] == "[redacted]"
    assert redacted["envelope"]["failure"]["details"]["private_reasoning"] == "[redacted]"
    assert redacted["mcp_failure"]["details"]["expected_token"] == "expected_token"


def test_mcp_tool_failure_reaches_model_context_as_structured_observation():
    title = "Какие задачи решает ML? (Часть 1. Классический ML)"
    payload = {
        "isError": True,
        "content": [{"type": "text", "text": f'Could not parse cql : siteSearch ~ ""{title}""'}],
        "structuredContent": {"reason": "query cannot be parsed"},
        "_meta": {"portal.failure": MCPFailure(
            kind=MCPFailureKind.TOOL,
            category=MCPFailureCategory.INPUT,
            code="tool_error",
            message=f'Could not parse cql : siteSearch ~ ""{title}""',
            details={"content": [{"text": f'Could not parse cql : siteSearch ~ ""{title}""'}]},
            user_message="do not trust upstream public text",
        ).bounded_dump()},
    }
    result = DirectOperationExecutor._tool_result_from_payload(payload)
    assert not result.success
    assert result.error == "The source rejected the search request."
    observation = json.loads(OperationExecutionFacade.format_result_for_context(result))
    assert observation["failure"]["category"] == "input"
    assert "Could not parse cql" in observation["failure"]["message"]
    assert title in observation["failure"]["details"]["content"][0]["text"]
    assert observation["failure"]["user_message"] == "The source rejected the search request."


def test_failure_context_budget_keeps_reason_and_marks_diagnostics_truncated():
    failure = MCPFailure(
        kind=MCPFailureKind.TOOL,
        category=MCPFailureCategory.INPUT,
        code="query_invalid",
        message="The query cannot be parsed.",
        details={"large": "x" * 5000},
    ).bounded_dump()
    rendered = OperationExecutionFacade.format_result_for_context(
        ToolResult.fail("safe", mcp_failure=failure), context_budget_tokens=256, context_model="test-model",
    )
    observation = json.loads(rendered)
    assert observation["failure"]["message"] == "The query cannot be parsed."
    assert observation["failure"]["details_truncated_for_context"] is True


@pytest.mark.asyncio
async def test_failure_diagnostic_survives_runtime_event_and_run_journal():
    failure = MCPFailure(
        kind=MCPFailureKind.TOOL,
        category=MCPFailureCategory.INPUT,
        code="query_invalid",
        message="Could not parse cql : siteSearch ~ \"\"title\"\"",
        details={"upstream": "CQL parser rejected the query"},
        user_message="The source rejected the search request.",
    ).bounded_dump()
    failed_result = ToolResult.fail(failure["user_message"], mcp_failure=failure, user_message=failure["user_message"])

    class Tools:
        async def execute(self, *args, **kwargs):
            return failed_result, []

        @staticmethod
        def _find_operation(*args, **kwargs):
            return None, None

        @staticmethod
        def format_result_for_context(result, **kwargs):
            return OperationExecutionFacade.format_result_for_context(result, **kwargs)

    class RunSession:
        run_id = "run-1"

        def __init__(self):
            self.events = []

        async def record_event(self, event_type, payload):
            self.events.append((event_type, payload))

    runtime = object.__new__(AgentToolRuntime)
    runtime.tools = Tools()
    journal = RunSession()
    context = ToolContext(tenant_id=uuid4(), user_id=uuid4())
    emitted = [event async for event in runtime._execute_single_operation_call(
        operation_call=SimpleNamespace(tool_name="confluence_search", id="call-1", arguments={"query": "title"}),
        agent_slug="confluence_agent", agent_execution_id="agent-run-1", llm_call_id="llm-1",
        ctx=context, available_operations=[], policy=SimpleNamespace(max_tool_calls_total=5, tool_timeout_ms=1000),
        run_session=journal, all_operation_outputs=[], all_sources=[], loop_state=AgentLoopState(),
        operation_results_for_context=[], operation_calls_total_ref=[0], result_context_budget_tokens=None,
        result_context_model=None, remaining_wall_time_ms=10000,
    )]
    result_event = next(event for event in emitted if event.type.value == "tool_result")
    assert result_event.data["result"]["failure"]["message"] == failure["message"]
    journal_result = next(payload for kind, payload in journal.events if kind == "tool_result")
    assert journal_result["mcp_failure"]["details"]["upstream"] == "CQL parser rejected the query"
    assert journal_result["error"] == "The source rejected the search request."
    assert journal_result["user_message"] == "The source rejected the search request."


@pytest.mark.asyncio
@pytest.mark.parametrize("status,category", [(401, "auth"), (503, "availability")])
async def test_initialize_http_failure_keeps_stage_status_and_bounded_body(status, category):
    executor = object.__new__(DirectOperationExecutor)
    executor._get_client = lambda *_args: _async_value(object())

    async def post(**_kwargs):
        return SimpleNamespace(status_code=status, content=b'{"message":"source unavailable"}', headers={}), 1

    executor._post_with_retry = post
    with pytest.raises(MCPFailureError) as raised:
        await executor._mcp_initialize_fresh("https://mcp.example", 5, request_id="request-1")
    failure = raised.value.mcp_failure
    assert failure["stage"] == "initialize"
    assert failure["http_status"] == status
    assert failure["category"] == category
    assert failure["details"]["message"] == "source unavailable"


@pytest.mark.asyncio
async def test_initialize_jsonrpc_failure_preserves_code_data_and_stage():
    executor = object.__new__(DirectOperationExecutor)
    executor._get_client = lambda *_args: _async_value(object())
    response = SimpleNamespace(
        status_code=200,
        content=b'{"jsonrpc":"2.0","id":1,"error":{"code":-32011,"message":"broker rejected credential","data":{"reason":"credential expired"}}}',
        text='{"jsonrpc":"2.0","id":1,"error":{"code":-32011,"message":"broker rejected credential","data":{"reason":"credential expired"}}}',
        headers={},
    )

    async def post(**_kwargs):
        return response, 1

    executor._post_with_retry = post
    with pytest.raises(MCPFailureError) as raised:
        await executor._mcp_initialize_fresh("https://mcp.example", 5, request_id="request-2")
    failure = raised.value.mcp_failure
    assert failure["stage"] == "initialize"
    assert failure["rpc_code"] == -32011
    assert failure["rpc_data"]["reason"] == "credential expired"
    assert failure["message"] == "broker rejected credential"


async def _async_value(value):
    return value


@pytest.mark.parametrize("value", [{"issues": []}, [], False, 0, ""])
def test_non_null_mcp_structured_values_take_precedence(value):
    result = DirectOperationExecutor._tool_result_from_payload({
        "structuredContent": value, "content": [{"type": "text", "text": '{"other": true}'}],
    })
    assert result.success and result.data == value


def test_null_mcp_structured_content_falls_back_to_json_text():
    result = DirectOperationExecutor._tool_result_from_payload({
        "structuredContent": None,
        "content": [{"type": "text", "text": '{"issues": [], "total": 0}'}],
    })
    assert result.success and result.data == {"issues": [], "total": 0}


def test_null_mcp_value_without_json_text_remains_null():
    result = DirectOperationExecutor._tool_result_from_payload({"structuredContent": None, "content": []})
    assert result.success and result.data is None
