from pathlib import Path

from app.services.runtime_evaluation_harness import (
    evaluate_runtime_case,
    load_eval_cases,
)


def _events_for_case(case_key: str):
    if case_key == "direct_answer_no_tool":
        return [
            {"type": "status", "data": {"stage": "planner"}},
            {"type": "final", "data": {"content": "ok"}},
        ]
    if case_key == "document_retrieval_case":
        return [
            {"type": "status", "data": {"operation_slug": "collection.document.search"}},
            {"type": "final", "data": {"content": "document grounded answer"}},
        ]
    if case_key == "clarify_missing_input":
        return [
            {"type": "waiting_input", "data": {"question": "need vendor"}},
            {"type": "stop", "data": {"reason": "waiting_input"}},
        ]
    raise AssertionError(f"Unhandled case: {case_key}")


def test_eval_cases_from_fixture_are_deterministic():
    fixture_path = Path(__file__).parent / "cases" / "runtime_eval_cases.json"
    cases = load_eval_cases([fixture_path])
    assert len(cases) == 3

    results = []
    for case in cases:
        result = evaluate_runtime_case(case, _events_for_case(case.key))
        results.append(result)
        assert result.passed is True
        assert result.score == 1.0

    assert {item.case_key for item in results} == {
        "direct_answer_no_tool",
        "document_retrieval_case",
        "clarify_missing_input",
    }
