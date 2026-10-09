"""Opt-in persisted protocol checks in an isolated PostgreSQL schema."""
import os
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import get_settings
from app.runtime.orchestrator_contracts import (
    IterationProposal, SchedulerActionKind, TaskCompletionDeclaration, TaskExecutionReceipt, TaskRequest,
)
from app.runtime.plan_store import SqlPlanStore
from app.runtime.task_result_reducer import TaskAttemptResultReducer

pytestmark = pytest.mark.skipif(os.getenv("RUNTIME_PROTOCOL_PG") != "1", reason="requires opt-in PostgreSQL")


@pytest_asyncio.fixture
async def protocol_pg():
    schema = "runtime_protocol_test_" + uuid4().hex
    admin = create_async_engine(get_settings().ASYNC_DB_URL)
    engine = None
    tables = ["runtime_plans", "runtime_plan_iterations", "runtime_plan_tasks", "runtime_task_dependencies",
              "runtime_task_needs", "runtime_need_bindings", "runtime_task_resolutions", "runtime_task_attempts", "runtime_pauses"]
    try:
        async with admin.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
            for table in tables:
                await conn.execute(text(f'CREATE TABLE "{schema}"."{table}" (LIKE public."{table}" INCLUDING ALL)'))
        engine = create_async_engine(get_settings().ASYNC_DB_URL, connect_args={"server_settings": {"search_path": f'"{schema}",public'}})
        yield engine
    finally:
        if engine:
            await engine.dispose()
        async with admin.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await admin.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("registered", [False, True])
async def test_response_spec_and_schema_deviations_survive_sql_session(protocol_pg, registered):
    async with AsyncSession(protocol_pg, expire_on_commit=False) as session:
        store = SqlPlanStore(session)
        plan = await store.create(goal="goal", root_run_id=uuid4(), tenant_id=uuid4())
        plan_id = plan.id
        proposal = IterationProposal.model_validate({"terminal": "planner", "tasks": [{
            "task_id": "a", "executor": "agent", "intent": "read", "instructions": "read",
            "response_spec": {"mode": "structured", "schema": {"type": "string"}}}]})
        if registered:
            from app.runtime.orchestrator import GraphOrchestrator
            from app.runtime.orchestrator_contracts import TaskContractRef
            proposal.tasks[0].contract = TaskContractRef(mode="registered", contract_id="read")
            proposal = GraphOrchestrator._compile(proposal, [{"slug": "agent", "task_contracts": [{
                "contract_id": "read", "version": 1, "description": "Read",
                "input_schema": {"required": ["missing_input"]}}]}], {"tasks": [], "needs": []})
        await store.apply_iteration(plan_id, proposal)
        await store.claim_task(plan_id, "a")
        request = TaskRequest.model_validate(await store.task_request(plan_id, "a"))
        declaration = TaskCompletionDeclaration(completion="fulfilled", structured_response={"ip": None, "rows": []})
        result = TaskAttemptResultReducer().reduce(request=request, declaration=declaration, verified={})
        await store.finish_attempt(plan_id, "a", execution=TaskExecutionReceipt(declaration=declaration), result=result)
    async with AsyncSession(protocol_pg, expire_on_commit=False) as session:
        store = SqlPlanStore(session)
        snapshot = await store.snapshot(plan_id)
        task = snapshot["tasks"]["a"]
        assert task["status"] == "completed"
        assert task["contract"]["response_spec"]["mode"] == "structured"
        assert task["result"]["structured_response"] == {"ip": None, "rows": []}
        assert task["result"]["diagnostics"][0]["code"] == "schema_deviation"
        assert (await store.next_decision(plan_id)).kind == SchedulerActionKind.INVOKE_PLANNER
