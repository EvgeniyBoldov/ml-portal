from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.runtime.events import RuntimeEvent
from app.runtime.orchestrator import OrchestratorEvent
from app.runtime.stages.graph_planning_stage import GraphPlanningStage


@pytest.mark.asyncio
async def test_planner_iteration_logs_its_rbac_snapshot():
    run_id, orchestrator_id, iteration_id = uuid4(), str(uuid4()), str(uuid4())
    audit = {"candidates": ["viewer", "hidden"], "allowed": ["viewer"], "denied_by_rbac": ["hidden"]}

    async def run(**_kwargs):
        yield OrchestratorEvent(type="_runtime_event", runtime_event=RuntimeEvent.planner_iteration_start(
            iteration_id=iteration_id, orchestrator_id=orchestrator_id, iteration=1,
        ))

    plan = SimpleNamespace(id=uuid4(), status="active", goal="show collections")
    store = SimpleNamespace(get_by_run=AsyncMock(return_value=plan), snapshot=AsyncMock(return_value={"status": "completed"}))
    stage = GraphPlanningStage(orchestrator=SimpleNamespace(run=run), store=store, max_steps=1)
    state = SimpleNamespace(run_id=run_id, attachment_contexts=[], deleted_artifact_ids=set())
    request = SimpleNamespace(chat_id=None, sandbox_overrides={}, messages=[], model=None)
    ctx = SimpleNamespace(extra={})

    events = [item.event async for item in stage.run(
        runtime_state=state, request=request, ctx=ctx, user_id=uuid4(), tenant_id=uuid4(),
        available_agents=[], platform_config={}, planner_rbac_audit=audit,
        orchestrator_id=orchestrator_id,
    )]

    assert [event.type.value for event in events] == ["planner_iteration_start", "rbac_snapshot"]
    assert events[1].data == {
        "entity_type": "planner_iteration", "entity_id": iteration_id,
        "parent_entity_type": "orchestrator", "parent_entity_id": orchestrator_id,
        "rbac": audit,
    }
