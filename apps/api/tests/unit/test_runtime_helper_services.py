from __future__ import annotations

from app.services.execution_outline_service import ExecutionOutlineService
from app.services.runtime_helper_summary_service import RuntimeHelperSummaryService


def test_runtime_helper_summary_service_builds_facts_and_questions() -> None:
    service = RuntimeHelperSummaryService()

    summary = service.build(
        request_text="Сравни регламенты",
        messages=[
            {"role": "user", "content": "Что изменилось?"},
            {"role": "assistant", "content": "Проверил регламент безопасности"},
        ],
    )

    assert summary.goal == "Сравни регламенты"
    assert summary.open_questions == ["Что изменилось?"]
    assert summary.facts == ["Проверил регламент безопасности"]


def test_execution_outline_service_adds_rag_and_compare_phases() -> None:
    service = ExecutionOutlineService()

    outline = service.build(
        request_text="Сравни регламенты в RAG",
        triage_result={"goal": "Сравнить регламенты"},
        available_agent_slugs=["rag-search", "analyst"],
    )

    phase_ids = [phase.phase_id for phase in outline.phases]
    assert outline.goal == "Сравнить регламенты"
    assert "collect_context" in phase_ids
    assert "retrieve_regulations" in phase_ids
    assert "compare_findings" in phase_ids
    assert phase_ids[-1] == "finalize"
