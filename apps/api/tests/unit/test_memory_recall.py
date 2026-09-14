"""Tests for the structured Recall boundary and its planner guard."""
from __future__ import annotations

from types import SimpleNamespace

from app.runtime.agent_executor import _render_memory_recall
from app.runtime.memory.preparer import PreparedMemoryContext, _term_matches_query
from app.runtime.memory.recall import MemoryRecallService, _item_is_applicable, _query_project_ids
from app.runtime.orchestrator import (
    _has_successful_rag_evidence, _has_successful_runtime_observation, _recall_requires_rag,
)


def _prepared(*, reasons: list[str], intent: str = "informational") -> PreparedMemoryContext:
    return PreparedMemoryContext(
        items=[
            {"type": "fact", "scope": "user", "subject": "user.role", "value": "network engineer"},
            {"type": "project_knowledge", "kind": "procedure", "subject": "switch.vlan_change",
             "value": "{\"steps\":[\"backup\"]}", "source_references": [{"section_id": "section-1", "label": "VLAN change"}]},
        ],
        selected_fact_count=1, selected_project_count=1, selected_project_fact_count=1,
        selected_glossary_count=1, ambiguities=[], resolved_terms=["Сфера"],
        resolved_projects=["network"], needs_source_check=bool(reasons),
        source_check_reasons=reasons, intent=intent,
    )


def test_recall_separates_procedure_and_evidence() -> None:
    recall = MemoryRecallService._structure(_prepared(reasons=[]))
    item = recall.as_item()

    assert item["applicable_procedures"][0]["subject"] == "switch.vlan_change"
    assert item["source_references"] == [{"section_id": "section-1", "label": "VLAN change"}]
    assert item["rag_required"] is False


def test_recall_keeps_company_rules_and_requires_tool_for_action() -> None:
    prepared = _prepared(reasons=[], intent="action")
    prepared = PreparedMemoryContext(
        **{**prepared.__dict__, "items": [
            {"type": "company_knowledge", "kind": "rule", "subject": "change.approval", "value": "approval required", "source_references": []},
        ]}
    )
    recall = MemoryRecallService._structure(prepared)

    assert recall.applicable_rules[0]["subject"] == "change.approval"
    assert recall.tool_required is True


def test_applicability_requires_matching_project_and_tenant() -> None:
    item = SimpleNamespace(
        applicability={"project_ids": ["project-1"], "tenant_ids": ["tenant-1"]},
        visibility={"tenant_ids": ["tenant-1"]},
    )

    assert _item_is_applicable(item, ["project-1"], "tenant-1") is True
    assert _item_is_applicable(item, ["project-2"], "tenant-1") is False
    assert _item_is_applicable(item, ["project-1"], "tenant-2") is False


def test_applicability_fails_closed_for_unknown_restriction() -> None:
    item = SimpleNamespace(
        applicability={"environment_ids": ["prod"]}, visibility={"mode": "source"},
    )
    assert _item_is_applicable(item, [], "tenant-1") is False


def test_query_project_ids_uses_exact_company_aliases() -> None:
    assert _query_project_ids("Как поменять VLAN в Сфере?", [
        {"id": "project-1", "key": "network", "name": "Network", "aliases": ["Сфера"]},
    ]) == ["project-1"]


def test_recall_marks_verification_and_agent_rendering() -> None:
    recall = MemoryRecallService._structure(_prepared(reasons=["semantic_memory_stale"]))
    lines = _render_memory_recall(recall.as_item())

    assert recall.rag_required is True
    assert any("RAG verification required" in line for line in lines)
    assert any("Memory evidence" in line for line in lines)


def test_recall_exposes_entity_ambiguity_as_clarification_not_rag() -> None:
    recall = MemoryRecallService._structure(
        _prepared(reasons=[]),
        resolved_entities=[{"type": "service", "canonical_name": "Сфера"}],
        entity_ambiguities=["ambiguous_entity_project:Сфера"],
    )
    lines = _render_memory_recall(recall.as_item())

    assert recall.clarification_required is True
    assert recall.rag_required is False
    assert any("Resolved entity" in line and "Сфера" in line for line in lines)
    assert any("Clarification required" in line for line in lines)


def test_agent_renderer_keeps_structured_procedure_atomic() -> None:
    recall = MemoryRecallService._structure(PreparedMemoryContext(
        items=[{"type": "project_knowledge", "kind": "procedure", "subject": "switch.vlan_change",
                "content": {
                    "goal": "Change VLAN", "applicability_conditions": [], "required_approvals": [],
                    "prechecks": ["Backup"],
                    "steps": [{"order": 1, "instruction": "Apply", "expected_result": "Applied", "confirmation_required": True}],
                    "verification": ["Ping"], "rollback": {"mode": "steps", "steps": ["Restore"], "reason": None},
                    "exceptions": [],
                }, "source_references": []}],
        selected_fact_count=0, selected_project_count=0, selected_project_fact_count=1,
        selected_glossary_count=0, ambiguities=[], resolved_terms=[], resolved_projects=[],
        needs_source_check=False, source_check_reasons=[],
    ))

    lines = _render_memory_recall(recall.as_item())

    assert any("Step 1: Apply. Expected: Applied" in line for line in lines)
    assert any("Rollback: Restore" in line for line in lines)


def test_short_abbreviation_is_kept_by_deterministic_selector_guard() -> None:
    assert _term_matches_query("dc", "как изменить dc") is True


def test_rag_guard_requires_successful_document_search() -> None:
    context = [{"type": "memory_recall", "rag_required": True}]
    state = SimpleNamespace(tool_ledger=SimpleNamespace(entries=[
        SimpleNamespace(operation="collection.document.search", status="failed"),
        SimpleNamespace(operation="collection.document.search", status="succeeded"),
    ]))

    assert _recall_requires_rag(context) is True
    assert _has_successful_rag_evidence(state) is True
    assert _has_successful_rag_evidence(SimpleNamespace(tool_ledger=SimpleNamespace(entries=[]))) is False


def test_rag_guard_accepts_instance_operation_only_for_recalled_source() -> None:
    state = SimpleNamespace(tool_ledger=SimpleNamespace(entries=[
        SimpleNamespace(
            operation="instance.docs.collection.document.search", status="succeeded",
            result_data={"hits": [{"document_id": "doc-1", "text": "evidence"}]},
        ),
    ]))
    context = [{"type": "memory_recall", "source_references": [{"document_id": "doc-1"}]}]
    wrong_context = [{"type": "memory_recall", "source_references": [{"document_id": "doc-2"}]}]

    assert _has_successful_rag_evidence(state, context) is True
    assert _has_successful_rag_evidence(state, wrong_context) is False


def test_runtime_observation_does_not_accept_rag_search_as_current_state() -> None:
    rag_only = SimpleNamespace(tool_ledger=SimpleNamespace(entries=[
        SimpleNamespace(operation="collection.document.search", status="succeeded"),
    ]))
    observed = SimpleNamespace(tool_ledger=SimpleNamespace(entries=[
        SimpleNamespace(operation="network.switch.get_status", status="succeeded"),
    ]))
    assert _has_successful_runtime_observation(rag_only) is False
    assert _has_successful_runtime_observation(observed) is True
