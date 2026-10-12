from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, create_autospec
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.agents.context import ToolContext
from app.agents.execution_preflight import ExecutionPreflight
from app.core.exceptions import ConflictError, ExternalServiceError, ForbiddenError
from app.models.agent import AgentType
from app.runtime.agent_executor import AgentExecutor
from app.runtime.orchestrator_contracts import TaskCompletionDeclaration, TaskExecutionError, TaskExecutionReceipt, TaskRequest
from app.schemas.agents import AgentCreate, AgentUpdate
from app.schemas.shadow_agents import ShadowAgentRequest, ShadowAgentResponse
from app.services import shadow_agent_service as module
from app.services.permission_service import EffectivePermissions
from app.services.runtime_event_logger import RuntimeEventLogger


@pytest.mark.parametrize("payload", [
    {"agent": "a"}, {"data": {}}, {"agent": "", "data": {}},
    {"agent": 1, "data": {}}, {"agent": "a", "data": []},
    {"agent": "a", "data": {}, "user_id": "forged"},
    {"agent": "a", "data": {"invalid": float("nan")}},
])
def test_request_rejects_invalid_envelopes(payload):
    with pytest.raises(ValidationError):
        ShadowAgentRequest.model_validate(payload)


def test_agent_type_defaults_and_validation():
    assert AgentCreate(slug="a", name="A").agent_type == AgentType.REGULAR
    assert AgentCreate(slug="a", name="A", agent_type="shadow").agent_type == AgentType.SHADOW
    assert AgentUpdate(agent_type="regular").agent_type == AgentType.REGULAR
    with pytest.raises(ValidationError):
        AgentCreate(slug="a", name="A", agent_type="other")


@pytest.fixture
def invocation(monkeypatch):
    agent = SimpleNamespace(slug="shadow-a", agent_type="shadow", logging_level="full")
    version = SimpleNamespace(id=uuid4(), version=3, status="published", requires_fresh_retrieval=False)
    agents = SimpleNamespace(get_agent_by_slug=AsyncMock(return_value=agent),
                             resolve_published_version=AsyncMock(return_value=version))
    permissions = SimpleNamespace(resolve_permissions=AsyncMock(
        return_value=EffectivePermissions(agent_permissions={agent.slug: True})))
    monkeypatch.setattr(module, "AgentService", lambda _: agents)
    monkeypatch.setattr(module, "PermissionService", lambda _: permissions)
    monkeypatch.setattr(module, "RuntimeConfigService", lambda _: SimpleNamespace(get_pipeline_config=AsyncMock(return_value={})))
    journal = create_autospec(RuntimeEventLogger, instance=True)
    journal.for_entity.return_value = journal
    monkeypatch.setattr(module.RuntimeEventJournalFactory, "create", Mock(return_value=journal))
    monkeypatch.setattr(module, "get_session_factory", lambda: None)
    service = module.ShadowAgentService(AsyncMock(), AsyncMock())
    service.executor.execute_attempt = AsyncMock(return_value=TaskExecutionReceipt(
        declaration=TaskCompletionDeclaration(completion="fulfilled", structured_response={"value": 42})))
    user_id, tenant_id = uuid4(), uuid4()
    return SimpleNamespace(service=service, agent=agent, version=version, permissions=permissions,
                           journal=journal, user_id=user_id, tenant_id=tenant_id,
                           kwargs=dict(user_id=user_id, tenant_id=tenant_id, scopes=["invoke"], request_id="test-request"))


async def invoke(fixture):
    return await fixture.service.invoke(ShadowAgentRequest(agent="shadow-a", data={"text": "x" * 9000}), **fixture.kwargs)


@pytest.mark.asyncio
async def test_invocation_preserves_identity_and_isolates_context(invocation):
    result = await invoke(invocation)
    assert result.model_dump() == {"agent": "shadow-a", "result": {"value": 42}}
    kwargs = invocation.service.executor.execute_attempt.call_args.kwargs
    assert kwargs["user_id"] == invocation.user_id
    assert kwargs["tenant_id"] == invocation.tenant_id
    assert kwargs["agent_version_id"] == invocation.version.id
    assert kwargs["messages"] == []
    assert kwargs["ctx"].chat_id is None
    assert kwargs["ctx"].extra["shadow_execution"] is True
    assert kwargs["ctx"].scopes == ["invoke"]
    assert kwargs["request"].inputs == {"text": "x" * 9000}
    assert kwargs["request"].memory_context == []
    invocation.permissions.resolve_permissions.assert_awaited_once_with(
        user_id=invocation.user_id, tenant_id=invocation.tenant_id)
    events = [call.args[0] for call in invocation.journal.emit.await_args_list]
    assert events[-1].data["status"] == "completed"
    assert events[-2].data["status"] == "completed"


@pytest.mark.asyncio
async def test_rbac_denial_prevents_execution(invocation):
    invocation.permissions.resolve_permissions.return_value = EffectivePermissions()
    with pytest.raises(ForbiddenError):
        await invoke(invocation)
    invocation.service.executor.execute_attempt.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [("agent_type", "regular"), ("status", "draft"), ("requires_fresh_retrieval", True)])
async def test_incompatible_agent_is_rejected(invocation, field, value):
    setattr(invocation.agent if field == "agent_type" else invocation.version, field, value)
    with pytest.raises(ConflictError):
        await invoke(invocation)
    invocation.service.executor.execute_attempt.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("result", [None, "prose", [], {"bad": float("inf")}])
async def test_invalid_results_fail_run(invocation, result):
    invocation.service.executor.execute_attempt.return_value = TaskExecutionReceipt(
        declaration=TaskCompletionDeclaration(completion="fulfilled", structured_response=result))
    with pytest.raises(ExternalServiceError):
        await invoke(invocation)
    events = [call.args[0] for call in invocation.journal.emit.await_args_list]
    assert events[-2].data["status"] == "failed"
    assert events[-1].data["status"] == "failed"


@pytest.mark.asyncio
async def test_runtime_failure_maps_to_upstream_error(invocation):
    invocation.service.executor.execute_attempt.side_effect = TaskExecutionError(
        code="agent_failed", message="failed", retryable=False)
    with pytest.raises(ExternalServiceError):
        await invoke(invocation)


@pytest.mark.asyncio
async def test_cancellation_finishes_run(invocation):
    invocation.service.executor.execute_attempt.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await invoke(invocation)
    assert invocation.journal.emit.await_args_list[-1].args[0].data["status"] == "cancelled"


@pytest.mark.asyncio
async def test_shadow_keeps_large_input_inline():
    task = TaskRequest(task_id="a", executor="shadow-a", intent="invoke", instructions="Do it", inputs={"text": "x" * 9000})
    ctx = ToolContext(user_id=uuid4(), tenant_id=uuid4(), extra={"shadow_execution": True, "runtime_root_run_id": str(uuid4())})
    assert await AgentExecutor._prepare_task_context(task, ctx, str(uuid4())) is task


@pytest.mark.asyncio
async def test_shadow_executor_disables_operation_discovery():
    executor = AgentExecutor(session=AsyncMock(), llm_client=AsyncMock())
    executor.preflight.prepare = AsyncMock(return_value=object())
    ctx = ToolContext(user_id=uuid4(), tenant_id=uuid4(), extra={"shadow_execution": True})
    await executor._prepare_sub_agent_request(
        ctx=ctx, agent_slug="shadow-a", user_id=ctx.user_id, tenant_id=ctx.tenant_id,
        request_text="invoke", platform_config={}, agent_version_id=None,
        lifecycle_agent_execution_id=None, timeout_s=10)
    assert executor.preflight.prepare.call_args.kwargs["enable_operations"] is False


@pytest.mark.asyncio
async def test_full_executor_runs_one_llm_call_and_returns_json(invocation, monkeypatch):
    """Exercise real executor + agent runtime, replacing only IO boundaries."""
    from app.agents.execution_preflight import ExecutionRequest
    from app.agents.runtime.policy import GenerationParams, PolicyLimits
    from app.services.runtime_event_logger import RuntimeEventLogger, RuntimeLogContext, RuntimeLoggingLevel

    observed = []

    async def emit(self, event, *, phase):
        observed.append(event)
        return event

    monkeypatch.setattr(RuntimeEventLogger, "emit", emit)
    journal = RuntimeEventLogger(context=RuntimeLogContext(
        run_id=uuid4(), level=RuntimeLoggingLevel.FULL, origin="shadow"))
    monkeypatch.setattr(module.RuntimeEventJournalFactory, "create", Mock(return_value=journal))
    invocation.service.session.scalar.return_value = "full"
    client = SimpleNamespace(chat=AsyncMock(return_value={"choices": [{"message": {"content":
        '{"completion":"fulfilled","structured_response":{"summary":"ok"},"needs":[]}'}}]}))
    executor = AgentExecutor(session=invocation.service.session, llm_client=client)
    invocation.service.executor = executor
    invocation.version.compiled_prompt = "Summarize the supplied text."
    executor.preflight.prepare = AsyncMock(return_value=ExecutionRequest(
        run_id=uuid4(), agent_slug=invocation.agent.slug, agent=invocation.agent,
        agent_version=invocation.version, user_id=invocation.user_id,
        tenant_id=invocation.tenant_id, prompt=invocation.version.compiled_prompt))
    executor._tool_runtime.config_resolver.resolve = AsyncMock(return_value=(
        PolicyLimits(), GenerationParams(model="test"), {}, SimpleNamespace(sources={})))

    result = await invoke(invocation)
    assert result.model_dump() == {"agent": "shadow-a", "result": {"summary": "ok"}}
    client.chat.assert_awaited_once()
    kwargs = client.chat.call_args.kwargs
    assert "tools" not in kwargs["params"]
    assert kwargs["params"]["response_format"]["type"] == "json_schema"
    assert "x" * 9000 in kwargs["messages"][-1]["content"]
    assert executor.preflight.prepare.call_args.kwargs["enable_operations"] is False
    endings = [event for event in observed if event.type.value == "agent_end"]
    assert len(endings) == 1
    assert endings[0].data["status"] == "completed"
    assert observed[-1].type.value == "run_end"


@pytest.mark.asyncio
async def test_explicit_shadow_selection_cannot_bypass_planner_catalog(monkeypatch):
    from app.core.exceptions import AgentUnavailableError
    from app.runtime import pipeline as module
    from app.runtime.platform_config import PlatformSnapshot

    service = SimpleNamespace(get_agent_by_slug=AsyncMock(return_value=SimpleNamespace(agent_type="shadow")))
    monkeypatch.setattr(module, "AgentService", lambda _: service)
    pipeline = module.RuntimePipeline(session=AsyncMock(), llm_client=AsyncMock())
    with pytest.raises(AgentUnavailableError, match="Shadow agents"):
        await pipeline._resolve_available_agents_for_planner(
            platform=PlatformSnapshot(), explicit_slug="shadow-a", user_id=uuid4(), tenant_id=uuid4())
