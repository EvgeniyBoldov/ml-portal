from __future__ import annotations

import json

import pytest

from app.runtime.synthesis_context import SynthesisContextBuilder


@pytest.mark.parametrize("receipt_source", ["task", "evidence"])
def test_synthesis_accepts_nullable_fields_in_serialized_result_observation(receipt_source):
    from app.agents.runtime.result_context import ResultObservation
    from app.runtime.synthesizer import Synthesizer

    observation = ResultObservation(
        result_id="dcbox-result", revision=1, source_complete=True, source_total=2, row_count=2,
    ).model_dump(mode="json")
    reports, run_context = [], {}
    if receipt_source == "task":
        references = SynthesisContextBuilder._verified_result_references({"receipts": [{
            "success": True, "result_id": "dcbox-result", "operation": "netbox_search_objects",
            "result_observation": observation,
        }]})
        reports = [{"verified_result_refs": references}]
    else:
        run_context = {"evidence": [{"tool": "result.read", "arguments": {}, "data": {
            "result_id": "dcbox-result", "revision": 1, "result_observation": observation,
        }}]}

    selected = Synthesizer._selected_result_references(reports, run_context)

    assert len(selected) == 1
    assert selected[0]["revision"] == 1
    assert selected[0]["fields"] is None
    assert selected[0]["observation"] == observation


def test_synthesis_keeps_distinct_field_projections_with_nullable_observation():
    from app.runtime.synthesizer import Synthesizer

    references = [{"result_id": "r", "revision": 1, "observation": {"fields": fields}}
                  for fields in (None, ["name"], ["address"])]
    selected = Synthesizer._selected_result_references([{"verified_result_refs": references}], {})

    assert len(selected) == 3
    assert {tuple(item["fields"] or []) for item in selected} == {(), ("name",), ("address",)}


def test_synthesis_receives_current_plan_focus_without_a_memory_search():
    scope = {"keys": ["company", "a"], "revision": 2}
    context = SynthesisContextBuilder().build(plan={
        "goal": "Найти задачи", "scope_context": scope,
        "iterations": [{"id": "final", "synthesis_brief": {"user_question": "Задачи", "purpose": "Ответить"}}],
        "memory_context": [{"type": "project_context", "scope_context": scope}],
    }, iteration_id="final")
    assert context["scope_context"] == scope
    assert context["execution_context"]["scope_keys"] == ["company", "a"]


def test_synthesis_keeps_rag_artifact_passport_and_exact_passage_provenance():
    passport = {
        "schema_version": 1, "artifact_id": "artifact-1",
        "origin": {"kind": "rag_document", "source_id": "document-1", "collection_id": "collection-1"},
        "file": {"name": "policy.pdf", "media_type": "application/pdf", "size_bytes": 500},
        "description": {"text": "Company policy", "source": "source_metadata"},
        "representation": None, "status": "ready", "attributes": {},
    }
    context = SynthesisContextBuilder().build(
        plan={
            "goal": "Summarize policy",
            "iterations": [{"id": "final", "sequence": 1, "terminal": "synthesis",
                "synthesis_brief": {"user_question": "Policy", "purpose": "Answer"}}],
            "tasks": {"read": {"iteration_id": "final", "planned_order": 0,
                "status": "completed", "intent": "Read source", "result": {
                    "description": "Read source", "outputs": {}, "sources": [{
                        "source_id": "document-1", "source_name": "policy.pdf",
                        "artifact_id": "artifact-1", "artifact": passport,
                        "chunk_id": "chunk-2", "page": 3, "score": 0.91,
                        "text": "Applicable policy passage",
                    }],
                }}},
        }, iteration_id="final")

    source = context["sources"][0]
    assert source["artifact"] == passport
    assert source["chunk_id"] == "chunk-2"
    assert source["page"] == 3
    assert source["excerpt"] == "Applicable policy passage"


def test_synthesis_compaction_keeps_all_task_statuses_and_bounds_final_context():
    task_ids = [f"task-{index:02d}" for index in range(45)]
    tasks = {
        task_id: {
            "iteration_id": "work", "planned_order": index, "status": "failed",
            "intent": "Check a source",
            "result": {"answer": "partial " + ("detail " * 500),
                       "outputs": {"payload": "x" * 5_000}},
        }
        for index, task_id in enumerate(task_ids)
    }
    plan = {
        "goal": "Check all sources",
        "iterations": [{"id": "final", "sequence": 2, "terminal": "synthesis",
                        "synthesis_brief": {"user_question": "Check all sources", "purpose": "Report results"}}],
        "tasks": tasks,
    }
    runtime_limitations = [{"message": f"Runtime limitation {index}"} for index in range(45)]

    max_chars = 40_000
    context = SynthesisContextBuilder(max_chars=max_chars).build(
        plan=plan,
        iteration_id="final",
        run_context={"evidence": [{"id": "selected", "data": {"content": "evidence " * 20_000}}]},
        runtime_limitations=runtime_limitations,
    )

    assert len(json.dumps(context, ensure_ascii=False)) <= max_chars
    assert {report["task_id"] for report in context["completed_task_reports"]} == set(task_ids)
    represented_task_ids = {
        item.get("task_id") for item in context["limitations"] if item.get("task_id")
    } | {
        item.get("reference") for item in context["withheld_materials"]
        if item.get("kind") == "limitation" and item.get("reference")
    }
    assert represented_task_ids == set(task_ids)
    assert any(item.get("kind") == "limitation" and item.get("message_sha256")
               for item in context["withheld_materials"])
    assert context["evidence_coverage"] == "partial"
    omitted_tasks = {item.get("task_id") for item in context["withheld_materials"]
                     if item.get("kind") == "task_result_field" and item.get("fields")}
    assert omitted_tasks
    for report in context["completed_task_reports"]:
        if report["task_id"] in omitted_tasks:
            assert "structured_response" not in report and "outputs" not in report
    assert not any("_truncated" in json.dumps(item) for item in context["completed_task_reports"])


def test_synthesis_limit_keeps_original_request_constraints_and_answer_requirements():
    context = SynthesisContextBuilder(max_chars=3_000).build(
        plan={
            "goal": "Summarize project",
            "scope_context": {"keys": ["project"]},
            "iterations": [{"id": "final", "sequence": 1, "terminal": "synthesis",
                "synthesis_brief": {"user_question": "Summary", "purpose": "Answer",
                    "answer_requirements": "Include constraints and exact limits"}}],
            "tasks": {"large": {"iteration_id": "final", "planned_order": 0,
                "status": "completed", "intent": "Read selected result",
                "expected_outputs": [{"key": "items", "required": True}],
                "result": {"description": "done", "structured_response": {"items": "x" * 20_000},
                    "outputs": {"items": "x" * 20_000}, "verified": {"status": "observed",
                        "receipts": [{"success": True, "operation": "collection.search",
                                      "result_id": "result-1", "source_complete": False}]}}}},
        }, iteration_id="final",
        run_context={"original_request": "Summarize current project",
                     "constraints": ["only approved repositories", "exclude archived projects"],
                     "answer_requirements": "Keep project attribution exact",
                     "evidence": [{"id": "evidence-1", "tool": "memory.search", "data": {"text": "y" * 20_000}}],
                     "selected_material_refs": ["evidence-1"], "available_material_refs": ["evidence-1"],
                     "evidence_coverage": "selected", "evidence_catalog": [{"id": "evidence-1", "tool": "memory.search"}]},
    )
    assert context["run_context"]["original_request"] == "Summarize current project"
    assert context["run_context"]["constraints"] == ["only approved repositories", "exclude archived projects"]
    assert context["synthesis_brief"]["answer_requirements"] == "Include constraints and exact limits"
    assert context["completed_task_reports"][0]["verified_result_refs"][0]["result_id"] == "result-1"
    assert context["withheld_materials"] and context["limitations"][-1]["code"] == "synthesis_context_budget_exceeded"
    assert "structured_response" not in context["completed_task_reports"][0]
    assert context["run_context"]["evidence_catalog"] == [{"id": "evidence-1", "tool": "memory.search"}]


def test_missing_selected_material_refs_are_explicit_without_claiming_sufficiency():
    context = SynthesisContextBuilder().build(
        plan={"goal": "Answer", "iterations": [{"id": "final", "synthesis_brief": {"purpose": "Answer"}}]},
        iteration_id="final",
        run_context={"original_request": "Answer", "evidence": [], "evidence_catalog": [],
                     "selected_material_refs": ["missing-message"], "available_material_refs": [],
                     "unavailable_material_refs": ["missing-message"], "evidence_coverage": "invalid_refs"},
    )
    limitation = next(item for item in context["limitations"] if item.get("code") == "selected_material_incomplete")
    assert limitation["unavailable_material_refs"] == ["missing-message"]
    assert context["run_context"]["evidence_coverage"] == "invalid_refs"


def test_synthesis_result_selection_uses_only_explicit_verified_receipts_and_selected_result_tools():
    from app.runtime.synthesizer import Synthesizer

    refs = Synthesizer._selected_result_references(
        [{"verified_result_refs": [{"result_id": "verified-1", "operation": "result.read"}],
          "outputs": {"arbitrary": {"result_id": "unverified-2"}}}],
        {"evidence": [
            {"id": "selected", "tool": "result.describe", "data": {"result_id": "selected-3", "revision": 2}},
            {"id": "non-result", "tool": "memory.search", "data": {"result_id": "ignored-4"}},
        ]},
    )
    assert refs == [
        {"result_id": "selected-3", "operation": "result.describe", "revision": 2},
        {"result_id": "verified-1", "operation": "result.read"},
    ]


def test_synthesis_uses_accepted_partial_output_and_keeps_unresolved_limitation() -> None:
    context = SynthesisContextBuilder().build(
        plan={
            "goal": "Собрать все файлы",
            "iterations": [{"id": "final", "sequence": 2, "terminal": "synthesis", "synthesis_brief": {"user_question": "Что найдено?", "planned_work": "Прочитать файлы", "purpose": "Дать сводку", "answer_requirements": "Кратко"}}],
            "resolutions": [{"task_id": "partial", "action": "accept_partial", "output_keys": ["nine"], "reason": "Девять файлов доступны"}, {"task_id": "missing", "action": "report_unresolved", "reason": "Один файл недоступен"}],
            "tasks": {
                "partial": {"status": "unfulfillable", "intent": "Read files", "result": {"description": "9 of 10", "outputs": {"nine": {"text": "nine"}, "ten": {"text": "ten"}}, "limitation": {"code": "file_missing", "message": "Tenth file missing"}}},
                "missing": {"status": "failed", "intent": "Read tenth", "result": {"description": "No access", "outputs": {}, "limitation": {"code": "access_denied", "message": "Access denied"}}},
            },
        },
        iteration_id="final",
    )
    reports = context["completed_task_reports"]
    assert {report["task_id"] for report in reports} == {"partial", "missing"}
    partial = next(report for report in reports if report["task_id"] == "partial")
    assert partial["answer"] == "9 of 10"
    assert partial["status"] == "unfulfillable"
    assert partial["structured_response"] == {"nine": {"text": "nine"}, "ten": {"text": "ten"}}
    assert "outputs" not in partial and "description" not in partial

    assert context["limitations"] == [{"task_id": "missing", "status": "failed", "reason_code": "access_denied", "message": "Access denied"}]


def test_synthesis_does_not_deliver_an_artifact_deleted_later_in_the_run() -> None:
    context = SynthesisContextBuilder().build(
        plan={
            "goal": "Сформировать файл",
            "iterations": [{
                "id": "final", "sequence": 1, "terminal": "synthesis",
                "synthesis_brief": {"user_question": "Сформировать файл", "planned_work": "Создать", "purpose": "Отдать", "answer_requirements": "Ссылка"},
            }],
            "resolutions": [],
            "tasks": {"write": {
                "iteration_id": "final", "planned_order": 0, "status": "completed", "intent": "write",
                "result": {"description": "done", "outputs": {}, "verified": {"artifacts": [{"artifact_id": "deleted", "file_name": "old.txt"}]}},
            }},
        },
        iteration_id="final",
        deleted_artifact_ids=["deleted"],
    )

    assert context["artifacts"] == []


def test_completed_task_generated_artifact_is_carried_to_synthesis() -> None:
    context = SynthesisContextBuilder().build(
        plan={
            "goal": "Сформировать файл",
            "iterations": [{
                "id": "final", "sequence": 1, "terminal": "synthesis",
                "synthesis_brief": {"user_question": "Сформировать файл", "planned_work": "Создать", "purpose": "Отдать", "answer_requirements": "Файл"},
            }],
            "resolutions": [],
            "tasks": {"write": {
                "iteration_id": "final", "planned_order": 0, "status": "completed", "intent": "generate_report",
                "result": {
                    "description": "done", "outputs": {"summary": "done"},
                    "verified": {"artifacts": [{"artifact_id": "artifact-1", "artifact_ref": "artifact-1", "file_name": "filled.xlsx"}]},
                    "artifact_selections": [],
                },
            }},
        },
        iteration_id="final",
    )

    assert context["artifacts"] == [{"artifact_id": "artifact-1", "file_name": "filled.xlsx", "content_type": "", "size_bytes": None}]


def test_accepted_partial_artifact_is_carried_to_synthesis() -> None:
    context = SynthesisContextBuilder().build(
        plan={
            "goal": "Сформировать файл",
            "iterations": [{
                "id": "final", "sequence": 2, "terminal": "synthesis",
                "synthesis_brief": {"user_question": "Сформировать файл", "planned_work": "Создать", "purpose": "Отдать", "answer_requirements": "Файл"},
            }],
            "resolutions": [{
                "task_id": "write", "action": "accept_partial",
                "output_keys": ["file"], "reason": "Файл был создан до сбоя.",
            }],
            "tasks": {"write": {
                "iteration_id": "previous", "planned_order": 0,
                "status": "unfulfillable", "intent": "generate_report",
                "result": {
                    "description": "Metadata update failed",
                    "outputs": {},
                    "artifact_selections": [{"artifact_ref": "artifact-1", "output_key": "file", "description": "Generated report"}],
                    "verified": {"artifacts": [{"artifact_id": "artifact-1", "artifact_ref": "artifact-1", "file_name": "report.xlsx"}]},
                    "limitation": {"code": "metadata_failed", "message": "Metadata update failed"},
                },
            }},
        },
        iteration_id="final",
    )

    assert context["artifacts"] == [{"artifact_id": "artifact-1", "file_name": "report.xlsx", "content_type": "", "size_bytes": None}]
    assert context["limitations"] == []
