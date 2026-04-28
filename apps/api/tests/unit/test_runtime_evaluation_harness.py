from app.services.runtime_evaluation_harness import (
    RuntimeEvaluationCase,
    default_runtime_eval_cases,
    evaluate_runtime_case,
    evaluate_runtime_cases,
)


def test_runtime_eval_passes_document_retrieval_case():
    case = RuntimeEvaluationCase(
        key="doc_case",
        title="Document retrieval",
        required_operations=("collection.document.search",),
        must_emit_final=True,
        must_emit_waiting_input=False,
        allow_error_events=False,
    )
    events = [
        {"type": "status", "data": {"stage": "triage"}},
        {"type": "status", "data": {"operation_slug": "collection.document.search"}},
        {"type": "final", "data": {"message": "ok"}},
    ]

    result = evaluate_runtime_case(case, events)

    assert result.passed is True
    assert result.score == 1.0
    assert result.dimensions.tool_choice_score == 1.0
    assert "collection.document.search" in result.seen_operations


def test_runtime_eval_fails_when_forbidden_operation_seen():
    case = RuntimeEvaluationCase(
        key="forbidden_case",
        title="No direct SQL",
        forbidden_operations=("sql.execute_sql",),
        must_emit_final=True,
    )
    events = [
        {"type": "status", "data": {"operation": "sql.execute_sql"}},
        {"type": "final", "data": {"message": "done"}},
    ]

    result = evaluate_runtime_case(case, events)

    assert result.passed is False
    assert any("Forbidden operation detected" in note for note in result.notes)


def test_runtime_eval_waiting_input_expectation():
    case = RuntimeEvaluationCase(
        key="clarify_case",
        title="Clarify path",
        expected_terminal_event="waiting_input",
        must_emit_final=False,
        must_emit_waiting_input=True,
    )
    events = [
        {"type": "waiting_input", "data": {"question": "Specify vendor"}},
        {"type": "stop", "data": {"reason": "waiting_input"}},
    ]

    result = evaluate_runtime_case(case, events)
    assert result.passed is True


def test_default_cases_are_evaluable():
    events = [
        {"type": "status", "data": {"stage": "triage"}},
        {"type": "final", "data": {"message": "ok"}},
    ]
    results = evaluate_runtime_cases(default_runtime_eval_cases(), events)
    assert len(results) >= 7
