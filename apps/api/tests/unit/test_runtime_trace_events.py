from app.runtime.events import RuntimeEvent, RuntimeEventType


def test_tool_request_and_result_share_a_canonical_entity() -> None:
    request = RuntimeEvent.tool_call(
        tool="file.read",
        call_id="call-1",
        arguments={"artifact_id": "artifact-1"},
        parent_entity_type="agent_execution",
        parent_entity_id="agent-1",
    )
    result = RuntimeEvent.tool_result(
        tool="file.read",
        call_id="call-1",
        success=True,
        data={"content": "ok"},
        parent_entity_type="agent_execution",
        parent_entity_id="agent-1",
    )

    assert request.type is RuntimeEventType.TOOL_CALL
    assert result.type is RuntimeEventType.TOOL_RESULT
    assert request.data["entity_type"] == result.data["entity_type"] == "tool_call"
    assert request.data["entity_id"] == result.data["entity_id"] == "call-1"
    assert request.data["parent_entity_id"] == result.data["parent_entity_id"] == "agent-1"


def test_agent_start_contains_executor_identity() -> None:
    event = RuntimeEvent.agent_start(
        agent_execution_id="planner-1",
        parent_entity_id="iteration-1",
        agent_slug="planner",
        executor_type="planner",
        task_title="Сформировать план",
    )

    assert event.data["executor_type"] == "planner"
    assert event.data["executor_name"] == "Планер"
    assert event.data["task_title"] == "Сформировать план"


def test_interaction_requests_are_children_of_executor_runs() -> None:
    clarify = RuntimeEvent.waiting_input(
        "Какой проект?",
        entity_id="planner-1:interaction",
        parent_entity_type="agent_execution",
        parent_entity_id="planner-1",
    )
    confirm = RuntimeEvent.confirmation_required(
        "Подтвердить запись",
        entity_id="agent-1:interaction",
        parent_entity_type="agent_execution",
        parent_entity_id="agent-1",
    )

    assert clarify.data["entity_type"] == confirm.data["entity_type"] == "interaction"
    assert clarify.data["interaction_kind"] == "clarify"
    assert confirm.data["interaction_kind"] == "confirm"
    assert clarify.data["parent_entity_id"] == "planner-1"
    assert confirm.data["parent_entity_id"] == "agent-1"


def test_step_is_a_stable_parent_for_executor_and_has_terminal_outcome() -> None:
    started = RuntimeEvent.step_start(
        step_id="step-1", iteration_id="iteration-1", kind="call_agent",
        title="Собрать данные", intent="Получить инвентарь", inputs={"site": "msk"},
    )
    ended = RuntimeEvent.step_end(
        step_id="step-1", iteration_id="iteration-1", status="completed",
        outcome="success", summary="Инвентарь получен", sufficient_for_phase=True,
    )

    assert started.type is RuntimeEventType.STEP_START
    assert ended.type is RuntimeEventType.STEP_END
    assert started.data["parent_entity_type"] == ended.data["parent_entity_type"] == "planner_iteration"
    assert started.data["entity_id"] == ended.data["entity_id"] == "step-1"
    assert ended.data["summary"] == "Инвентарь получен"


def test_task_and_checkpoint_graph_entities_have_stable_iteration_parents() -> None:
    task = RuntimeEvent.task_lifecycle(
        RuntimeEventType.TASK_PLANNED,
        plan_id="plan-1", iteration_id="iteration-1",
        task_id="collect", task_entity_id="task-entity-1",
        status="waiting",
    )
    checkpoint = RuntimeEvent.checkpoint_lifecycle(
        RuntimeEventType.CHECKPOINT_PLANNED,
        checkpoint_id="checkpoint-1", plan_id="plan-1",
        iteration_id="iteration-1", declared_next="synthesis",
        status="waiting",
    )

    assert task.data["entity_id"] == task.data["task_entity_id"] == "task-entity-1"
    assert task.data["task_id"] == "collect"
    assert task.data["parent_entity_id"] == "iteration-1"
    assert checkpoint.data["entity_id"] == checkpoint.data["checkpoint_id"] == "checkpoint-1"
    assert checkpoint.data["parent_entity_id"] == "iteration-1"


def test_final_answer_marker_is_the_run_result_owned_by_synthesis() -> None:
    event = RuntimeEvent.final_answer_marker(
        synthesis_id="synthesis-1", run_id="run-1", content="Готово",
        sources=[{"id": "source-1"}], attachments=[{"artifact_id": "artifact-1"}],
    )

    assert event.type is RuntimeEventType.FINAL_ANSWER_MARKER
    assert event.data == {
        "entity_type": "run", "entity_id": "run-1",
        "parent_entity_type": "synthesis_run", "parent_entity_id": "synthesis-1",
        "status": "completed", "producer": "synthesizer_llm", "content": "Готово",
        "sources": [{"id": "source-1"}], "attachments": [{"artifact_id": "artifact-1"}],
    }


def test_preflight_route_decision_keeps_proposed_and_effective_routes_distinct() -> None:
    event = RuntimeEvent.preflight_route_decision(
        preflight_id="preflight-1", run_id="run-1", proposed_route="synthesis",
        effective_route="planner", reason="runtime_reroute",
        detail="Текущий инвентарь нужно проверить через операционный источник.",
    )

    assert event.type is RuntimeEventType.PREFLIGHT_ROUTE_DECISION
    assert event.data == {
        "entity_type": "orchestrator", "entity_id": "preflight-1",
        "parent_entity_type": "run", "parent_entity_id": "run-1",
        "proposed_route": "synthesis", "effective_route": "planner",
        "reason": "runtime_reroute",
        "policy_recommendation_id": None,
        "policy_disposition": "not_applicable",
        "reason_code": None,
        "detail": "Текущий инвентарь нужно проверить через операционный источник.",
    }


def test_sandbox_override_snapshot_preserves_suppression_and_effective_operation() -> None:
    event = RuntimeEvent.sandbox_override_snapshot(
        agent_execution_id="agent-1",
        configured={"publication": {"tool-1": False}, "semantics": {}},
        effective_operations=[{"discovered_tool_id": "tool-2", "published_effective": True}],
        suppressed_publication={"tool-1": "disabled_by_sandbox_override"},
        parent_entity_type="task", parent_entity_id="task-1",
    )

    assert event.type is RuntimeEventType.SANDBOX_OVERRIDE_SNAPSHOT
    assert event.data["parent_entity_id"] == "task-1"
    assert event.data["configured"]["publication"] == {"tool-1": False}
    assert event.data["suppressed_publication"] == {"tool-1": "disabled_by_sandbox_override"}
    assert event.data["effective_operations"] == [{"discovered_tool_id": "tool-2", "published_effective": True}]
