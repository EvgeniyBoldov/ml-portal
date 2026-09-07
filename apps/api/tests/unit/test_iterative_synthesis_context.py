from __future__ import annotations

from app.runtime.synthesis_context import SynthesisContextBuilder


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
    assert context["completed_task_reports"] == [{"task_id": "partial", "intent": "Read files", "description": "Девять файлов доступны", "outputs": {"nine": {"text": "nine"}}}]
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
