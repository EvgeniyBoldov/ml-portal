from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.agents.contracts import MissingRequirements, ProviderExecutionTarget, ResolvedOperation
from app.agents.execution_preflight import ExecutionMode, RoutingStatus
from app.models.system_llm_trace import SystemLLMTrace
from app.services.execution_trace_logger import ExecutionTraceLogger


@pytest.fixture
def run_store():
    store = AsyncMock()
    store.start_run = AsyncMock(return_value=uuid4())
    store.add_step = AsyncMock(return_value=uuid4())
    store.finish_run = AsyncMock()
    return store


@pytest.fixture
def routing_repo():
    repo = AsyncMock()
    repo.create = AsyncMock(return_value=Mock())
    return repo


@pytest.fixture
def trace_service():
    service = AsyncMock()
    service.create_trace_from_execution = AsyncMock(
        return_value=SimpleNamespace(id=uuid4(), duration_ms=1234)
    )
    return service


@pytest.fixture
def logger(run_store, routing_repo, trace_service):
    return ExecutionTraceLogger(
        run_store=run_store,
        routing_log_repo=routing_repo,
        system_trace_service=trace_service,
    )


def _sample_operation() -> ResolvedOperation:
    target = ProviderExecutionTarget(
        operation_slug="collection.table.get",
        provider_type="mcp",
        provider_instance_id=str(uuid4()),
        provider_instance_slug="mcp-prod",
        provider_url="https://example.invalid",
        data_instance_id=str(uuid4()),
        data_instance_slug="netbox-prod",
        handler_slug="get",
        mcp_tool_name="netbox.device.get",
        timeout_s=10,
        has_credentials=True,
        health_status="ready",
    )
    return ResolvedOperation(
        operation_slug="collection.table.get",
        operation="get",
        name="Get row",
        description="Get a single row",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        data_instance_id=str(uuid4()),
        data_instance_slug="netbox-prod",
        provider_instance_id=str(uuid4()),
        provider_instance_slug="mcp-prod",
        source="mcp",
        target=target,
    )


@pytest.mark.asyncio
async def test_level_normalization_aliases():
    assert ExecutionTraceLogger.normalize_level("short") == "brief"
    assert ExecutionTraceLogger.normalize_level("BRIEF") == "brief"
    assert ExecutionTraceLogger.normalize_level("full") == "full"
    assert ExecutionTraceLogger.normalize_level("unknown") == "brief"


@pytest.mark.asyncio
async def test_log_step_delegates_to_run_store(logger, run_store):
    run_id = uuid4()

    await logger.log_step(
        run_id,
        component="router",
        event="decision",
        data={"status": "success"},
        duration_ms=15,
    )

    run_store.add_step.assert_awaited_once()
    call_args = run_store.add_step.call_args.args
    assert call_args[0] == run_id
    assert call_args[1] == "router_decision"
    assert call_args[2] == {"status": "success"}


@pytest.mark.asyncio
async def test_start_run_redacts_context_snapshot(logger, run_store):
    await logger.start_run(
        tenant_id=str(uuid4()),
        agent_slug="assistant",
        logging_level="brief",
        context_snapshot={
            "db_dsn": "postgresql://user:secret@localhost:5432/app",
            "token": "abc123",
        },
    )

    run_store.start_run.assert_awaited_once()
    kwargs = run_store.start_run.call_args.kwargs
    snapshot = kwargs["context_snapshot"]
    assert snapshot["db_dsn"] == "***"
    assert snapshot["token"] == "***"


@pytest.mark.asyncio
async def test_log_routing_decision_persists_and_mirrors_run_step(logger, run_store, routing_repo):
    run_id = uuid4()
    missing = MissingRequirements(
        tools=["jira"],
        collections=["netbox"],
        credentials=["jira"],
    )
    operation = _sample_operation()
    target = operation.target

    result = await logger.log_routing_decision(
        run_id=run_id,
        user_id=uuid4(),
        tenant_id=uuid4(),
        request_text="create ticket",
        agent_slug="assistant",
        mode=ExecutionMode.FULL,
        missing=missing,
        available_operations=[operation],
        available_collections=["netbox-prod"],
        execution_targets={operation.operation_slug: target},
        routing_reasons=["loaded", "filtered"],
        status=RoutingStatus.SUCCESS,
        duration_ms=42,
    )

    assert result is not None
    run_store.add_step.assert_awaited()
    routing_repo.create.assert_awaited_once()
    created_log = routing_repo.create.call_args.args[0]
    assert created_log.run_id == run_id
    assert created_log.selected_agent_slug == "assistant"
    assert created_log.effective_operations == ["collection.table.get"]


@pytest.mark.asyncio
async def test_log_system_llm_trace_mirrors_summary(logger, run_store, trace_service):
    run_id = uuid4()
    trace = await logger.log_system_llm_trace(
        trace_type="triage",
        role_config={
            "id": str(uuid4()),
            "role_type": "triage",
            "model": "gpt-4.1",
            "temperature": 0.1,
            "max_tokens": 128,
            "prompt": "system prompt",
        },
        structured_input={"user_message": "hello"},
        messages=[{"role": "user", "content": "hello"}],
        llm_response='{"type":"final"}',
        parsed_response={"type": "final"},
        validation_status="success",
        start_time=0.0,
        model="gpt-4.1",
        temperature=0.1,
        max_tokens=128,
        run_id=run_id,
        agent_run_id=run_id,
        chat_id=uuid4(),
        tenant_id=uuid4(),
        user_id=uuid4(),
    )

    assert isinstance(trace, SystemLLMTrace) or hasattr(trace, "id")
    trace_service.create_trace_from_execution.assert_awaited_once()
    run_store.add_step.assert_awaited()
    call_args = run_store.add_step.call_args.args
    assert call_args[1] == "system_llm_trace"
