from __future__ import annotations

from app.runtime.context_outcome import RuntimeOutcomeProjection
from app.services.chat_context_reducer import ChatContextReducer


def test_reducer_keeps_only_typed_verified_continuity_operations() -> None:
    projection = RuntimeOutcomeProjection(
        run_id="run-1", chat_id="chat-1", chat_turn_id="turn-1", terminal_state="waiting_input",
        effective_goal="Проверить отчёт", project_context={"explicit_project_keys": ["ML-Portal"]},
        term_bindings=[{"id": "term-1", "term": "RAG", "matched_aliases": ["rag"]}],
        clarification={"question": "Какой отчёт использовать?"},
        artifacts=[{"artifact_id": "artifact-1", "file_name": "report.xlsx"}],
    )

    operations = ChatContextReducer().reduce(projection=projection, expected_revision=4)

    assert {(item.kind, item.item_key) for item in operations} == {
        ("scope", "current_scope"),
        ("term_binding", "term-1"),
        ("goal", "active_goal"),
        ("open_loop", "turn:turn-1"),
        ("artifact_ref", "artifact-1"),
        ("recent_anchor", "recent_anchor"),
    }
    assert all(item.expected_revision == 4 for item in operations)


def test_completed_projection_closes_the_matching_open_loop() -> None:
    projection = RuntimeOutcomeProjection(
        run_id="run-1", chat_id="chat-1", chat_turn_id="turn-1", terminal_state="completed",
        effective_goal="Проверить отчёт",
    )

    operations = ChatContextReducer().reduce(projection=projection, expected_revision=0)

    assert any(item.action == "close" and item.kind == "open_loop" and item.item_key == "turn:turn-1" for item in operations)
    goal = next(item for item in operations if item.kind == "goal")
    assert goal.action == "update"
    assert goal.payload["status"] == "active"
    assert any(item.kind == "recent_anchor" for item in operations)


def test_task_outcome_is_stored_as_a_reference_not_raw_output() -> None:
    projection = RuntimeOutcomeProjection(
        run_id="run-1", chat_id="chat-1", chat_turn_id="turn-1", terminal_state="completed",
        task_result_refs=[{
            "plan_id": "plan-1", "task_entity_id": "task-1", "outcome": "completed",
            "safe_summary": "Отчёт подготовлен", "artifact_ids": ["artifact-1"], "source_run_id": "run-1",
        }],
    )

    operation = next(item for item in ChatContextReducer().reduce(projection=projection, expected_revision=2) if item.kind == "task_result_ref")

    assert operation.item_key == "plan-1:task-1"
    assert operation.payload["safe_summary"] == "Отчёт подготовлен"
    assert "outputs" not in operation.payload


def test_failed_turn_does_not_persist_a_technical_error_as_context() -> None:
    projection = RuntimeOutcomeProjection(
        run_id="run-1", chat_id="chat-1", chat_turn_id="turn-1", terminal_state="failed",
        effective_goal="Проверить отчёт", current_user_intent="Проверь отчёт",
        assistant_outcome={"summary": "provider timeout"},
    )

    operations = ChatContextReducer().reduce(projection=projection, expected_revision=2)

    assert not any(item.kind in {"goal", "recent_anchor"} for item in operations)
