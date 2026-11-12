"""Persistence, fencing and concurrency checks for runtime execution guards."""
from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.runtime_plan import RuntimePlan, RuntimePlanIteration, RuntimePlanTask, RuntimeTaskAttempt
from app.runtime.interaction import InteractionQuestion, InteractionRequester, RuntimeInteraction
from app.runtime.orchestrator_contracts import (
    TaskAttemptFailure, TaskCompletionDeclaration, TaskExecutionReceipt, TaskResult,
)
from app.runtime.plan_store import SqlPlanStore, StaleTaskClaimError
from app.services.runtime_execution_guard_service import RuntimeExecutionGuardError, RuntimeExecutionGuardService

pytestmark = pytest.mark.skipif(not os.getenv("RUNTIME_INTERACTION_TEST_URL"), reason="PostgreSQL test URL is required")


@pytest.mark.asyncio
async def test_superseded_sql_claim_cannot_finish_fail_heartbeat_or_read_task_request():
    url = os.environ["RUNTIME_INTERACTION_TEST_URL"]
    engine = create_async_engine(url)
    schema = "runtime_claim_fence_" + uuid4().hex
    async with engine.begin() as connection:
        await connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
    scoped = create_async_engine(url, connect_args={"server_settings": {"search_path": schema}})
    try:
        tables = [model.__table__ for model in (RuntimePlan, RuntimePlanIteration, RuntimePlanTask, RuntimeTaskAttempt)]
        async with scoped.begin() as connection:
            await connection.run_sync(lambda sync: Base.metadata.create_all(sync, tables=tables))
        sessions = async_sessionmaker(scoped, expire_on_commit=False)
        plan_id, root_run_id, iteration_id, task_row_id = uuid4(), uuid4(), uuid4(), uuid4()
        async with sessions() as session:
            session.add(RuntimePlan(id=plan_id, root_run_id=root_run_id, tenant_id=uuid4(), goal="claim test", status="active"))
            session.add(RuntimePlanIteration(id=iteration_id, plan_id=plan_id, sequence=1, terminal="planner"))
            session.add(RuntimePlanTask(id=task_row_id, plan_id=plan_id, iteration_id=iteration_id,
                task_id="work", planned_order=0, intent="work", instructions="work", executor="agent",
                status="running", inputs={}, expected_outputs=[], compiled_contract={}, scope_context={},
                freshness_policy="allow_memory", attempts=1))
            session.add(RuntimeTaskAttempt(task_row_id=task_row_id, attempt_number=1, status="running"))
            await session.commit()
        async with sessions() as session:
            task = await session.get(RuntimePlanTask, task_row_id)
            attempt = (await session.execute(select(RuntimeTaskAttempt).where(
                RuntimeTaskAttempt.task_row_id == task_row_id, RuntimeTaskAttempt.attempt_number == 1,
            ))).scalar_one()
            task.attempts, attempt.status = 2, "failed"
            session.add(RuntimeTaskAttempt(task_row_id=task_row_id, attempt_number=2, status="running"))
            await session.commit()

        async def assert_fenced(action):
            async with sessions() as session:
                with pytest.raises(StaleTaskClaimError):
                    await action(SqlPlanStore(session))

        await assert_fenced(lambda store: store.heartbeat_task(plan_id, "work", expected_attempt_number=1))
        await assert_fenced(lambda store: store.task_request(plan_id, "work", expected_attempt_number=1))
        await assert_fenced(lambda store: store.update_task_memory(plan_id, "work", [], expected_attempt_number=1))
        await assert_fenced(lambda store: store.link_attempt_execution(plan_id, "work", uuid4(), expected_attempt_number=1))
        await assert_fenced(lambda store: store.finish_failure(plan_id, "work",
            TaskAttemptFailure(code="late", message="late"), max_attempts=1, expected_attempt_number=1))
        await assert_fenced(lambda store: store.finish_attempt(plan_id, "work", expected_attempt_number=1,
            execution=TaskExecutionReceipt(declaration=TaskCompletionDeclaration(completion="fulfilled")),
            result=TaskResult(outcome="completed", description="late")))
        interaction = RuntimeInteraction.create(InteractionQuestion(question="late?"),
            InteractionRequester(stage="agent", entity_id=str(uuid4()), plan_id=str(plan_id),
                                 task_id="work", agent_slug="agent"))
        await assert_fenced(lambda store: store.pause_interaction(plan_id, interaction, expected_attempt_number=1))
        await assert_fenced(lambda store: store.pause_confirmation(plan_id, "work",
            {"operation_fingerprint": "late-fingerprint"}, expected_attempt_number=1))
        async with sessions() as session:
            task = await session.get(RuntimePlanTask, task_row_id)
            attempt = (await session.execute(select(RuntimeTaskAttempt).where(
                RuntimeTaskAttempt.task_row_id == task_row_id, RuntimeTaskAttempt.attempt_number == 2,
            ))).scalar_one()
            assert task.status == "running" and task.attempts == 2 and attempt.status == "running"

        # A session may have retained an attempt ORM object from before the
        # guard's short transaction. Refresh it under lock before merging the
        # terminal receipt so the guard state survives.
        merge_row_id = uuid4()
        async with sessions() as session:
            session.add(RuntimePlanTask(id=merge_row_id, plan_id=plan_id, iteration_id=iteration_id,
                task_id="merge", planned_order=1, intent="merge", instructions="merge", executor="agent",
                status="running", inputs={}, expected_outputs=[], compiled_contract={}, scope_context={},
                freshness_policy="allow_memory", attempts=1))
            session.add(RuntimeTaskAttempt(task_row_id=merge_row_id, attempt_number=1, status="running"))
            await session.commit()
        stale_session = sessions()
        try:
            stale_attempt = (await stale_session.execute(select(RuntimeTaskAttempt).where(
                RuntimeTaskAttempt.task_row_id == merge_row_id,
                RuntimeTaskAttempt.attempt_number == 1,
            ))).scalar_one()
            assert stale_attempt.execution_result is None
            async with sessions() as guard_session:
                guard_attempt = (await guard_session.execute(select(RuntimeTaskAttempt).where(
                    RuntimeTaskAttempt.task_row_id == merge_row_id,
                    RuntimeTaskAttempt.attempt_number == 1,
                ))).scalar_one()
                guard_attempt.execution_result = {"operation_guard": {"version": 1, "calls": {
                    "fingerprint": {"status": "completed", "outcome": "succeeded"},
                }}}
                await guard_session.commit()
            await SqlPlanStore(stale_session).finish_attempt(plan_id, "merge", expected_attempt_number=1,
                execution=TaskExecutionReceipt(declaration=TaskCompletionDeclaration(completion="fulfilled")),
                result=TaskResult(outcome="completed", description="done"))
        finally:
            await stale_session.close()
        async with sessions() as session:
            merged = (await session.execute(select(RuntimeTaskAttempt).where(
                RuntimeTaskAttempt.task_row_id == merge_row_id,
                RuntimeTaskAttempt.attempt_number == 1,
            ))).scalar_one()
            call = merged.execution_result["operation_guard"]["calls"]["fingerprint"]
            assert call["status"] == "completed" and call["outcome"] == "succeeded"
            assert "declaration" in merged.execution_result
    finally:
        await scoped.dispose()
        async with engine.begin() as connection:
            await connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
        await engine.dispose()


@pytest.mark.asyncio
async def test_guard_is_durable_fenced_and_serializes_concurrent_admission():
    url = os.environ["RUNTIME_INTERACTION_TEST_URL"]
    engine = create_async_engine(url)
    schema = "execution_guard_" + uuid4().hex
    async with engine.begin() as connection:
        await connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
    scoped = create_async_engine(url, connect_args={"server_settings": {"search_path": schema}})
    try:
        tables = [model.__table__ for model in (RuntimePlan, RuntimePlanIteration, RuntimePlanTask, RuntimeTaskAttempt)]
        async with scoped.begin() as connection:
            await connection.run_sync(lambda sync: Base.metadata.create_all(sync, tables=tables))
        sessions = async_sessionmaker(scoped, expire_on_commit=False)
        plan_id, root_run_id, iteration_id, task_row_id = uuid4(), uuid4(), uuid4(), uuid4()
        async with sessions() as session:
            session.add(RuntimePlan(id=plan_id, root_run_id=root_run_id, tenant_id=uuid4(), goal="guard test", status="active"))
            session.add(RuntimePlanIteration(id=iteration_id, plan_id=plan_id, sequence=1, terminal="planner"))
            session.add(RuntimePlanTask(id=task_row_id, plan_id=plan_id, iteration_id=iteration_id,
                task_id="write", planned_order=0, intent="write", instructions="write once", executor="agent",
                status="running", inputs={}, expected_outputs=[], compiled_contract={}, scope_context={},
                freshness_policy="allow_memory", attempts=1))
            session.add(RuntimeTaskAttempt(task_row_id=task_row_id, attempt_number=1, status="running"))
            await session.commit()

        first = RuntimeExecutionGuardService(sessions, root_run_id=root_run_id,
            task_id="write", expected_attempt_number=1)
        args = {"id": "external-7", "value": "approved"}
        results = await asyncio.gather(
            first.admit(operation="remote.update", target="provider-a", arguments=args),
            first.admit(operation="remote.update", target="provider-a", arguments=args),
            return_exceptions=True,
        )
        admitted = [value for value in results if isinstance(value, str)]
        blocked = [value for value in results if isinstance(value, RuntimeExecutionGuardError)]
        assert len(admitted) == len(blocked) == 1
        assert blocked[0].code == "tool_outcome_unknown"

        after_admission_restart = RuntimeExecutionGuardService(sessions, root_run_id=root_run_id,
            task_id="write", expected_attempt_number=1)
        with pytest.raises(RuntimeExecutionGuardError) as in_flight_after_restart:
            await after_admission_restart.admit(operation="remote.update", target="provider-a", arguments=args)
        assert in_flight_after_restart.value.code == "tool_outcome_unknown"

        await first.complete(admitted[0], success=True)
        after_completion_restart = RuntimeExecutionGuardService(sessions, root_run_id=root_run_id,
            task_id="write", expected_attempt_number=1)
        with pytest.raises(RuntimeExecutionGuardError) as duplicate:
            await after_completion_restart.admit(operation="remote.update", target="provider-a", arguments=args)
        assert duplicate.value.code == "duplicate_execution_blocked"

        # A stale worker holding attempt 1 cannot write after the claim moves.
        async with sessions() as session:
            task = await session.get(RuntimePlanTask, task_row_id)
            old_attempt = (await session.execute(select(RuntimeTaskAttempt).where(
                RuntimeTaskAttempt.task_row_id == task_row_id,
                RuntimeTaskAttempt.attempt_number == 1,
            ))).scalar_one()
            task.attempts, old_attempt.status, task.status = 2, "failed", "running"
            session.add(RuntimeTaskAttempt(task_row_id=task_row_id, attempt_number=2, status="running"))
            await session.commit()
        with pytest.raises(RuntimeExecutionGuardError) as stale:
            await first.admit(operation="remote.create", target="provider-a", arguments={"name": "x"})
        assert stale.value.code == "execution_guard_stale"
        with pytest.raises(RuntimeExecutionGuardError) as stale_completion:
            await first.complete(admitted[0])
        assert stale_completion.value.code == "execution_guard_stale"

        current = RuntimeExecutionGuardService(sessions, root_run_id=root_run_id,
            task_id="write", expected_attempt_number=2)
        with pytest.raises(RuntimeExecutionGuardError) as inherited:
            await current.admit(operation="remote.update", target="provider-a", arguments=args)
        assert inherited.value.code == "duplicate_execution_blocked"

        continuation_row_id = uuid4()
        sibling_row_id = uuid4()
        async with sessions() as session:
            for row_id, task_id, predecessor in (
                (continuation_row_id, "continued", "write"),
                (sibling_row_id, "sibling", None),
            ):
                session.add(RuntimePlanTask(id=row_id, plan_id=plan_id, iteration_id=iteration_id,
                    task_id=task_id, planned_order=1, intent=task_id, instructions=task_id, executor="agent",
                    status="running", inputs={}, expected_outputs=[], compiled_contract={}, scope_context={},
                    freshness_policy="allow_memory", continuation_of=predecessor, attempts=1))
                session.add(RuntimeTaskAttempt(task_row_id=row_id, attempt_number=1, status="running"))
            await session.commit()
        continued = RuntimeExecutionGuardService(sessions, root_run_id=root_run_id,
            task_id="continued", expected_attempt_number=1)
        with pytest.raises(RuntimeExecutionGuardError) as inherited_continuation:
            await continued.admit(operation="remote.update", target="provider-a", arguments=args)
        assert inherited_continuation.value.code == "duplicate_execution_blocked"

        isolated_sibling = RuntimeExecutionGuardService(sessions, root_run_id=root_run_id,
            task_id="sibling", expected_attempt_number=1)
        sibling_admission = await isolated_sibling.admit(operation="remote.update", target="provider-a", arguments=args)
        await isolated_sibling.complete(sibling_admission, success=True)
        async with sessions() as session:
            sibling_attempt = (await session.execute(select(RuntimeTaskAttempt).where(
                RuntimeTaskAttempt.task_row_id == sibling_row_id,
                RuntimeTaskAttempt.attempt_number == 1,
            ))).scalar_one()
            sibling_attempt.execution_result = {"operation_guard": {"version": 99, "calls": {}}}
            await session.commit()
        with pytest.raises(RuntimeExecutionGuardError) as corrupt:
            await isolated_sibling.admit(operation="remote.create", target="provider-a", arguments={"name": "new"})
        assert corrupt.value.code == "execution_guard_invalid"
    finally:
        await scoped.dispose()
        async with engine.begin() as connection:
            await connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
        await engine.dispose()


@pytest.mark.asyncio
async def test_facade_persists_before_provider_and_never_repeats_after_fresh_context():
    from types import SimpleNamespace
    from app.agents.context import RuntimeDependencies, ToolCall, ToolContext, ToolResult
    from app.agents.contracts import ProviderExecutionTarget, ResolvedOperation
    from app.agents.runtime.tools import OperationExecutionFacade

    url = os.environ["RUNTIME_INTERACTION_TEST_URL"]
    engine = create_async_engine(url)
    schema = "execution_guard_facade_" + uuid4().hex
    async with engine.begin() as connection:
        await connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
    scoped = create_async_engine(url, connect_args={"server_settings": {"search_path": schema}})
    try:
        tables = [model.__table__ for model in (RuntimePlan, RuntimePlanIteration, RuntimePlanTask, RuntimeTaskAttempt)]
        async with scoped.begin() as connection:
            await connection.run_sync(lambda sync: Base.metadata.create_all(sync, tables=tables))
        sessions = async_sessionmaker(scoped, expire_on_commit=False)
        plan_id, root_run_id, iteration_id, task_row_id = uuid4(), uuid4(), uuid4(), uuid4()
        async with sessions() as session:
            session.add(RuntimePlan(id=plan_id, root_run_id=root_run_id, tenant_id=uuid4(), goal="guard test", status="active"))
            session.add(RuntimePlanIteration(id=iteration_id, plan_id=plan_id, sequence=1, terminal="planner"))
            session.add(RuntimePlanTask(id=task_row_id, plan_id=plan_id, iteration_id=iteration_id,
                task_id="write", planned_order=0, intent="write", instructions="write once", executor="agent",
                status="running", inputs={}, expected_outputs=[], compiled_contract={}, scope_context={},
                freshness_policy="allow_memory", attempts=1))
            session.add(RuntimeTaskAttempt(task_row_id=task_row_id, attempt_number=1, status="running"))
            await session.commit()

        calls = 0

        class GuardedProvider:
            supports_runtime_execution_guard = True

            async def execute(self, call, ctx):
                nonlocal calls
                await ctx.extra["runtime_operation_dispatch_guard"]()
                calls += 1
                return ToolResult.ok({"updated": True}, delivery="direct")

        operation = ResolvedOperation(operation_slug="remote.update", operation="remote.update", name="Update",
            source="mcp", scope="system", data_instance_id="system", data_instance_slug="system",
            side_effects=True, idempotent=False, risk_level="write",
            target=ProviderExecutionTarget(operation_slug="remote.update", provider_type="mcp",
                handler_slug="remote.update", data_instance_id="system", data_instance_slug="system"))

        async def invoke(call_id: str):
            ctx = ToolContext(tenant_id=uuid4(), user_id=uuid4(), extra={
                "runtime_execution_guard_required": True,
                "runtime_execution_guard_service": RuntimeExecutionGuardService(sessions,
                    root_run_id=root_run_id, task_id="write", expected_attempt_number=1),
            })
            ctx.set_runtime_deps(RuntimeDependencies(operation_executor=GuardedProvider()))
            return await OperationExecutionFacade().execute(
                ToolCall(id=call_id, tool_name="remote.update", arguments={"id": "E-3"}), ctx, [operation],
            )

        first, _ = await invoke("first")
        assert first.success is True
        second, _ = await invoke("after-restart")
        assert second.success is False
        assert second.metadata["error_code"] == "duplicate_execution_blocked"
        assert calls == 1
    finally:
        await scoped.dispose()
        async with engine.begin() as connection:
            await connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
        await engine.dispose()
