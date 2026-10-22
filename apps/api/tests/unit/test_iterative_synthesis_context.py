from __future__ import annotations

import json

from app.runtime.synthesis_context import SynthesisContextBuilder


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
    assert {item["task_id"] for item in context["limitations"] if "task_id" in item} == set(task_ids)
    assert {item["message"] for item in context["limitations"] if "message" in item} >= (
        {"Task did not complete"}
        | {f"Runtime limitation {index}" for index in range(45)}
    )


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
