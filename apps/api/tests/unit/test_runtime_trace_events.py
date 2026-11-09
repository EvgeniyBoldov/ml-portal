from uuid import uuid4

from app.agents.runtime.agent import _safe_tool_user_message
from app.agents.runtime.session import RunSession
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


def test_tool_result_keeps_known_completeness_and_count_metadata_without_inference() -> None:
    result = RuntimeEvent.tool_result(
        tool="records.search", call_id="call-2", success=True, data={"rows": []},
        result_id="result-1", result_delivery="stored",
        result_inline_complete=False, result_source_complete=True,
        result_row_count=0, result_source_total=0, truncated=True,
    )

    assert result.data["result_id"] == "result-1"
    assert result.data["result_delivery"] == "stored"
    assert result.data["result_inline_complete"] is False
    assert result.data["result_source_complete"] is True
    assert result.data["result_row_count"] == 0
    assert result.data["result_source_total"] == 0
    assert result.data["truncated"] is True

    unknown = RuntimeEvent.tool_result(
        tool="records.search", call_id="call-3", success=True, data={},
    )
    assert "result_inline_complete" not in unknown.data
    assert "result_source_complete" not in unknown.data


def test_tool_failure_user_text_is_catalog_backed_while_diagnostics_remain_separate() -> None:
    from app.runtime.operation_errors import RuntimeErrorCode

    mcp_failure = {
        "category": "auth",
        "user_message": "SQL password=secret from upstream",
        "message": "connection refused at private-host",
    }
    assert _safe_tool_user_message("opaque_code", mcp_failure) == (
        "The source rejected its authentication credentials."
    )
    assert _safe_tool_user_message(RuntimeErrorCode.OPERATION_TIMEOUT.value, None) == (
        "The operation took too long to complete."
    )
    assert _safe_tool_user_message("opaque_code", None) == (
        "The operation could not be completed."
    )


async def test_run_session_journal_mapper_preserves_result_metadata_and_unknown_outcome() -> None:
    session = RunSession(
        ctx=object(), agent_slug="test", logging_level="full", mode="sandbox",
    )
    session.run_id = uuid4()
    events = []
    async def capture(event):
        events.append(event)
    session._emit = capture

    await session.record_event("tool_result", {
        "tool": "records.search", "call_id": "call-1", "success": True,
        "data": {"row_count": 0}, "result_id": "result-1",
        "result_delivery": "stored", "result_inline_complete": False,
        "result_source_complete": True, "result_row_count": 0,
        "result_source_total": 0, "truncated": True,
        "mcp_failure": {"version": 1, "category": "auth", "message": "raw"},
        "safe_message": "raw diagnostic", "user_message": "Safe public text",
    })
    journal_event = events[0]
    assert journal_event.type is RuntimeEventType.TOOL_RESULT
    assert journal_event.data["result_id"] == "result-1"
    assert journal_event.data["result_inline_complete"] is False
    assert journal_event.data["result_source_complete"] is True
    assert journal_event.data["result_row_count"] == 0
    assert journal_event.data["result_source_total"] == 0
    assert journal_event.data["truncated"] is True
    assert journal_event.data["mcp_failure"]["message"] == "raw"
    assert journal_event.data["safe_message"] == "raw diagnostic"
    assert journal_event.data["user_message"] == "Safe public text"

    await session.record_event("tool_result", {"tool": "records.search", "call_id": "call-2", "data": {}})
    unknown_event = events[1]
    assert "success" not in unknown_event.data
    assert unknown_event.data["status"] == "unknown"
    assert "result_inline_complete" not in unknown_event.data


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


def test_access_snapshot_is_additive_and_keeps_safe_typed_inventory() -> None:
    items = [{"kind": "tool", "key": "memory.search", "label": "Поиск памяти", "status": "available"}]
    event = RuntimeEvent.access_snapshot(entity_type="preflight", entity_id="preflight-1", items=items,
        parent_entity_type="orchestrator", parent_entity_id="preflight-1",
        agent_description="Handles document lookup")

    assert event.type is RuntimeEventType.ACCESS_SNAPSHOT
    assert event.data == {"entity_type": "preflight", "entity_id": "preflight-1", "items": items,
        "parent_entity_type": "orchestrator", "parent_entity_id": "preflight-1",
        "agent_description": "Handles document lookup"}


def test_preflight_access_projection_reports_effective_tools_and_safe_missing_reason() -> None:
    from types import SimpleNamespace
    from app.agents.execution_preflight import _build_access_items

    rows = _build_access_items(
        operations=[SimpleNamespace(operation_slug="memory.search", name="Поиск памяти", risk_level="safe",
            discovery_description="Ищет в подтверждённой памяти", scope="system", provider_instance_slug="memory")],
        missing=SimpleNamespace(tools=["file.read"]),
        configured_operations=[{"key": "crm.search", "label": "Поиск CRM", "source_key": "crm", "risk_level": "safe",
            "description": "Поиск записей", "source_label": "crm-mcp"}],
        denied_source_keys={"crm"},
    )

    assert rows == [
        {"kind": "tool", "key": "memory.search", "label": "Поиск памяти", "status": "available", "risk_level": "safe",
         "description": "Ищет в подтверждённой памяти", "source_label": "Система"},
        {"kind": "tool", "key": "crm.search", "label": "Поиск CRM", "status": "unavailable",
         "reason_code": "blocked_by_rbac", "reason": "Недоступен по правам доступа", "risk_level": "safe",
         "description": "Поиск записей", "source_label": "crm-mcp"},
        {"kind": "tool", "key": "file.read", "label": "file.read", "status": "unavailable",
         "reason_code": "tool_unavailable", "reason": "Инструмент недоступен"},
    ]


def test_agent_access_inventory_keeps_descriptions_and_source_labels() -> None:
    from types import SimpleNamespace
    from app.runtime.agent_executor import _agent_access_inventory

    operation = SimpleNamespace(operation_slug="crm.search", name="Search", scope="collection",
        discovery_description="Search CRM records", provider_instance_slug="crm-mcp", data_instance_slug="crm",
        risk_level="safe", collection_slug="crm")
    instance = SimpleNamespace(collection_slug="crm", slug="crm-instance", name="CRM",
        description="Customer records", data_description=None, usage_purpose=None)
    request = SimpleNamespace(
        rbac_audit={"collection_filter": {"candidates": ["crm"], "allowed": ["crm"],
            "candidate_source_details": {"crm": {"label": "CRM", "description": "Customer records"}}}},
        resolved_data_instances=[instance], resolved_operations=[operation], missing_requirements=None,
    )

    source, = _agent_access_inventory(request)
    assert source["description"] == "Customer records"
    assert source["children"] == [{"kind": "tool", "key": "crm.search", "label": "Search",
        "status": "available", "description": "Search CRM records", "source_label": "crm-mcp", "risk_level": "safe"}]


def test_agent_access_inventory_reads_nested_collection_audit_and_includes_system_tools() -> None:
    from types import SimpleNamespace
    from app.runtime.agent_executor import _agent_access_inventory

    sub_request = SimpleNamespace(
        rbac_audit={"collection_filter": {
            "candidates": ["netbox", "restricted"],
            "denied_by_rbac": ["restricted"],
            "candidate_source_details": {"restricted": {"label": "Private CRM", "description": "Customer records"}},
            "configured_operations": [
                {"key": "collection.netbox.search", "label": "Search devices", "source_key": "netbox", "scope": "collection", "risk_level": "safe", "description": "Find devices", "source_label": "netbox-api"},
                {"key": "crm.search", "label": "Search CRM", "source_key": "restricted", "scope": "collection", "risk_level": "safe", "description": "Find customers", "source_label": "crm-api"},
                {"key": "file.read", "label": "Read file", "source_key": "system", "scope": "system", "risk_level": "safe"},
            ],
        }},
        resolved_data_instances=[SimpleNamespace(collection_slug="netbox", name="Inventory", description="Inventory data")],
        resolved_operations=[
            SimpleNamespace(operation_slug="collection.netbox.search", name="Search devices", scope="collection", collection_slug="netbox", data_instance_slug="netbox", risk_level="safe", discovery_description="Find devices", provider_instance_slug="netbox-api"),
            SimpleNamespace(operation_slug="file.read", name="Read file", scope="system", collection_slug=None, data_instance_slug="system", risk_level="safe"),
        ],
        missing_requirements=SimpleNamespace(credentials=[]),
    )

    items = _agent_access_inventory(sub_request)
    sources = [item for item in items if item["kind"] == "source"]
    tools = [item for item in items if item["kind"] == "tool"]

    assert sources == [
        {"kind": "source", "key": "netbox", "label": "Inventory", "status": "available", "description": "Inventory data", "children": [
            {"kind": "tool", "key": "collection.netbox.search", "label": "Search devices", "status": "available",
             "description": "Find devices", "source_label": "netbox-api", "risk_level": "safe"},
        ]},
        {"kind": "source", "key": "restricted", "label": "Private CRM", "status": "unavailable", "reason_code": "blocked_by_rbac", "reason": "Недоступен по правам доступа", "description": "Customer records", "children": [
            {"kind": "tool", "key": "crm.search", "label": "Search CRM", "status": "unavailable", "reason_code": "blocked_by_rbac", "reason": "Недоступен по правам доступа", "description": "Find customers", "source_label": "crm-api", "risk_level": "safe"},
        ]},
    ]
    assert tools == [{"kind": "tool", "key": "file.read", "label": "Read file", "status": "available",
        "source_label": "Система", "risk_level": "safe"}]
