"""Durable interaction checkpoints in an isolated PostgreSQL schema."""
import importlib
import os
from uuid import uuid4

import pytest
import pytest_asyncio
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.runtime_plan import (RuntimePlan, RuntimePlanIteration, RuntimePlanTask, RuntimeTaskDependency,
    RuntimeTaskNeed, RuntimeNeedBinding, RuntimeTaskResolution, RuntimeTaskAttempt, RuntimePause)
from app.runtime.interaction import InteractionQuestion, InteractionRequester, RuntimeInteraction
from app.runtime.orchestrator_contracts import IterationProposal, PlannedTask
from app.runtime.plan_store import SqlPlanStore, PlanValidationError

pytestmark = pytest.mark.skipif(not os.getenv("RUNTIME_INTERACTION_TEST_URL"), reason="PostgreSQL test URL is required")


@pytest_asyncio.fixture
async def database():
    url = os.environ["RUNTIME_INTERACTION_TEST_URL"]
    engine = create_async_engine(url)
    schema = "interaction_test_" + uuid4().hex
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
async def test_migration_preserves_old_tasks_and_downgrade_preserves_pauses(database):
    migration = importlib.import_module("app.migrations.versions.0194_runtime_interactions")
    async with database.begin() as connection:
        await connection.exec_driver_sql("CREATE TABLE runtime_plan_tasks(id uuid, status text, CONSTRAINT ck_runtime_task_status CHECK(status IN ('running', 'waiting_confirmation')))")
        await connection.exec_driver_sql("INSERT INTO runtime_plan_tasks VALUES(gen_random_uuid(), 'running')")
        def apply(sync, direction):
            previous = migration.op
            migration.op = Operations(MigrationContext.configure(sync))
            try:
                getattr(migration, direction)()
            finally:
                migration.op = previous
        await connection.run_sync(lambda sync: apply(sync, "upgrade"))
        await connection.exec_driver_sql("INSERT INTO runtime_plan_tasks VALUES(gen_random_uuid(), 'waiting_input')")
        await connection.run_sync(lambda sync: apply(sync, "downgrade"))
        assert (await connection.exec_driver_sql("SELECT status FROM runtime_plan_tasks ORDER BY status")).scalars().all() == ["running", "waiting_confirmation"]


@pytest.mark.asyncio
@pytest.mark.parametrize("response", ["Альфа", True, False])
async def test_task_interaction_and_answer_survive_new_sessions(database, response):
    tables = [model.__table__ for model in (RuntimePlan, RuntimePlanIteration, RuntimePlanTask, RuntimeTaskDependency,
        RuntimeTaskNeed, RuntimeNeedBinding, RuntimeTaskResolution, RuntimeTaskAttempt, RuntimePause)]
    async with database.begin() as connection:
        await connection.run_sync(lambda sync: Base.metadata.create_all(sync, tables=tables))
    sessions = async_sessionmaker(database, expire_on_commit=False)
    async with sessions() as session:
        store = SqlPlanStore(session)
        plan = await store.create(goal="goal", root_run_id=uuid4(), tenant_id=uuid4(),
            scope_context={"selected": [{"key": "company"}], "ceiling_keys": ["company"]})
        plan_id = plan.id
        await store.apply_iteration(plan_id, IterationProposal(tasks=[PlannedTask(
            task_id="work", executor="research", intent="work", instructions="original")], terminal="planner"))
        await store.claim_task(plan_id, "work")
        interaction = RuntimeInteraction.create(InteractionQuestion(question="Выбор?", response_type="text" if isinstance(response, str) else "boolean"),
            InteractionRequester(stage="agent", entity_id=str(uuid4()), plan_id=str(plan_id), task_id="work", agent_slug="research"),
            checkpoint={"messages": [{"role": "tool", "content": "completed result"}]})
        await store.pause_interaction(plan_id, interaction)
    async with sessions() as session:
        store = SqlPlanStore(session)
        assert (await store.snapshot(plan_id))["status"] == "waiting_input"
        await store.resume_interaction(plan_id, interaction.id, response)
    async with sessions() as session:
        store = SqlPlanStore(session)
        await store.claim_task(plan_id, "work")
        request = await store.task_request(plan_id, "work")
        assert request["resume_checkpoint"] == interaction.checkpoint
        assert request["interaction_history"][-1]["response"] == response
        assert request["instructions"] == "original"
        with pytest.raises(PlanValidationError):
            await store.resume_interaction(plan_id, interaction.id, response)


@pytest.mark.asyncio
async def test_cancelling_plan_resolves_persisted_interaction(database):
    tables = [model.__table__ for model in (RuntimePlan, RuntimePlanIteration, RuntimePlanTask, RuntimeTaskDependency,
        RuntimeTaskNeed, RuntimeNeedBinding, RuntimeTaskResolution, RuntimeTaskAttempt, RuntimePause)]
    async with database.begin() as connection:
        await connection.run_sync(lambda sync: Base.metadata.create_all(sync, tables=tables))
    sessions = async_sessionmaker(database, expire_on_commit=False)
    async with sessions() as session:
        store = SqlPlanStore(session)
        plan = await store.create(goal="goal", root_run_id=uuid4(), tenant_id=uuid4(),
            scope_context={"selected": [{"key": "company"}], "ceiling_keys": ["company"]})
        plan_id = plan.id
        await store.apply_iteration(plan_id, IterationProposal(tasks=[PlannedTask(
            task_id="work", executor="research", intent="work", instructions="original")], terminal="planner"))
        await store.claim_task(plan_id, "work")
        interaction = RuntimeInteraction.create(InteractionQuestion(question="Выбор?"),
            InteractionRequester(stage="agent", entity_id=str(uuid4()), plan_id=str(plan_id), task_id="work", agent_slug="research"))
        await store.pause_interaction(plan_id, interaction)
    async with sessions() as session:
        await SqlPlanStore(session).cancel_plan(plan_id, reason="user_cancelled")
    async with sessions() as session:
        snapshot = await SqlPlanStore(session).snapshot(plan_id)
        assert snapshot["status"] == "cancelled"
        assert snapshot["tasks"]["work"]["status"] == "cancelled"
        assert snapshot["pauses"][-1]["status"] == "cancelled"
        with pytest.raises(PlanValidationError):
            await SqlPlanStore(session).resume_interaction(plan_id, interaction.id, "Альфа")
