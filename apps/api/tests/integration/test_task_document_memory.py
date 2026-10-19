"""Migration and owner-memory persistence in a disposable PostgreSQL database."""
import importlib
import os
from uuid import uuid4

import pytest
import pytest_asyncio
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.runtime_plan import (RuntimePlan, RuntimePlanIteration, RuntimePlanTask, RuntimeTaskDependency,
    RuntimeTaskNeed, RuntimeNeedBinding, RuntimeTaskResolution, RuntimeTaskAttempt, RuntimePause)
from app.runtime.memory.document_memory import accumulate_document_memory
from app.runtime.orchestrator_contracts import (IterationProposal, PlannedTask, SchedulerActionKind,
    TaskCompletionDeclaration, TaskExecutionReceipt, TaskResult, TaskResolution, TaskAttemptFailure)
from app.runtime.plan_store import SqlPlanStore


pytestmark = pytest.mark.skipif(not os.getenv("TASK_MEMORY_TEST_URL"), reason="Disposable PostgreSQL is required")


@pytest_asyncio.fixture
async def database():
    url = os.environ["TASK_MEMORY_TEST_URL"]
    engine = create_async_engine(url)
    schema = "task_memory_" + uuid4().hex
    async with engine.begin() as connection:
        await connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
    scoped = create_async_engine(url, connect_args={"server_settings": {"search_path": schema}})
    try:
        yield scoped
    finally:
        await scoped.dispose()
        async with engine.begin() as connection:
            await connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
        await engine.dispose()


@pytest.mark.asyncio
async def test_migration_preserves_existing_tasks(database):
    migration = importlib.import_module("app.migrations.versions.0193_task_document_memory")
    async with database.begin() as connection:
        await connection.exec_driver_sql("CREATE TABLE runtime_plan_tasks(id uuid PRIMARY KEY, instructions text)")
        await connection.execute(text("INSERT INTO runtime_plan_tasks VALUES(:id, 'preserve me')"), {"id": uuid4()})
        def upgrade(sync_connection):
            previous = migration.op
            migration.op = Operations(MigrationContext.configure(sync_connection))
            try:
                migration.upgrade()
            finally:
                migration.op = previous
        await connection.run_sync(upgrade)
        row = (await connection.execute(text("SELECT instructions, memory_context, continuation_of FROM runtime_plan_tasks"))).one()
        assert row.instructions == "preserve me" and row.memory_context == [] and row.continuation_of is None


@pytest.mark.asyncio
async def test_task_memory_survives_retry_and_explicit_needs_continuation(database):
    tables = [model.__table__ for model in (RuntimePlan, RuntimePlanIteration, RuntimePlanTask, RuntimeTaskDependency,
        RuntimeTaskNeed, RuntimeNeedBinding, RuntimeTaskResolution, RuntimeTaskAttempt, RuntimePause)]
    async with database.begin() as connection:
        await connection.run_sync(lambda sync: Base.metadata.create_all(sync, tables=tables))
    sessions = async_sessionmaker(database, expire_on_commit=False)
    passage = {"scope_slug": "company", "text": "Original complete rule", "source_references": [{"document_id": "doc"}]}
    memory = accumulate_document_memory([], {"groups": [{"scope_slug": "company", "status": "completed", "success": True,
        "items": [passage], "source_references": passage["source_references"]}]})
    async with sessions() as session:
        store = SqlPlanStore(session)
        plan = await store.create(goal="goal", root_run_id=uuid4(), tenant_id=uuid4(),
            scope_context={"selected": [{"key": "company"}], "ceiling_keys": ["company"]})
        plan_id = plan.id
        await store.update_memory_context(plan_id, memory)
        await store.apply_iteration(plan_id, IterationProposal(tasks=[PlannedTask(task_id="original", executor="research",
            intent="work", instructions="work")], terminal="planner"))
        await store.claim_task(plan_id, "original")
        assert (await store.task_request(plan_id, "original"))["memory_context"] == []
        await store.update_task_memory(plan_id, "original", memory)
        await store.finish_failure(plan_id, "original", TaskAttemptFailure(code="temporary", message="retry", retryable=True), max_attempts=3)
    # Reopen the store/session, as on retry or process restart.
    async with sessions() as session:
        store = SqlPlanStore(session)
        await store.claim_task(plan_id, "original")
        assert (await store.task_request(plan_id, "original"))["memory_context"] == memory
        execution = TaskExecutionReceipt(declaration=TaskCompletionDeclaration(completion="needs", report="need input",
            needs=[{"ref": "data", "key": "data", "description": "fetch input"}]))
        await store.finish_attempt(plan_id, "original", execution=execution, result=TaskResult(outcome="needs_dependency",
            description="need input", needs=execution.declaration.needs))
        await store.claim_checkpoint(plan_id, SchedulerActionKind.INVOKE_PLANNER)
        await store.apply_iteration(plan_id, IterationProposal(tasks=[
            PlannedTask(task_id="helper", executor="research", intent="fetch", instructions="fetch"),
            PlannedTask(task_id="continued", executor="research", continuation_of="original", intent="continue", instructions="continue")
        ], terminal="planner", resolutions=[TaskResolution(task_id="original", action="continue_with_tasks",
            replacement_task_ids=["helper", "continued"], reason="resolve need")]))
    async with sessions() as session:
        snapshot = await SqlPlanStore(session).snapshot(plan_id)
        assert snapshot["tasks"]["continued"]["memory_context"] == memory
        assert snapshot["tasks"]["helper"]["memory_context"] == []
        assert snapshot["tasks"]["continued"]["continuation_of"] == "original"
        assert snapshot["memory_context"] == memory
