from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Sequence, Set


@dataclass(frozen=True)
class RuntimeEvaluationCase:
    key: str
    title: str
    required_operations: tuple[str, ...] = ()
    forbidden_operations: tuple[str, ...] = ()
    must_emit_final: bool = True
    must_emit_waiting_input: bool = False
    allow_error_events: bool = False


@dataclass(frozen=True)
class RuntimeEvaluationResult:
    case_key: str
    passed: bool
    score: float
    notes: tuple[str, ...] = ()
    seen_operations: tuple[str, ...] = ()
    seen_event_types: tuple[str, ...] = ()


def default_runtime_eval_cases() -> tuple[RuntimeEvaluationCase, ...]:
    return (
        RuntimeEvaluationCase(
            key="chat_basic_answer",
            title="Basic chat response without tool errors",
            required_operations=(),
            forbidden_operations=(),
            must_emit_final=True,
            must_emit_waiting_input=False,
            allow_error_events=False,
        ),
        RuntimeEvaluationCase(
            key="document_retrieval",
            title="Document retrieval path",
            required_operations=("collection.document.search",),
            forbidden_operations=(),
            must_emit_final=True,
            must_emit_waiting_input=False,
            allow_error_events=False,
        ),
        RuntimeEvaluationCase(
            key="table_or_sql_retrieval",
            title="Table or SQL retrieval path",
            required_operations=(),
            forbidden_operations=(),
            must_emit_final=True,
            must_emit_waiting_input=False,
            allow_error_events=False,
        ),
    )


def evaluate_runtime_case(
    case: RuntimeEvaluationCase,
    runtime_events: Sequence[Dict[str, Any]],
) -> RuntimeEvaluationResult:
    seen_event_types = _collect_event_types(runtime_events)
    seen_operations = _collect_operations(runtime_events)
    notes: List[str] = []
    checks_total = 0
    checks_passed = 0

    checks_total += 1
    if not case.must_emit_final or "final" in seen_event_types:
        checks_passed += 1
    else:
        notes.append("Final event is missing")

    checks_total += 1
    if case.must_emit_waiting_input == ("waiting_input" in seen_event_types):
        checks_passed += 1
    else:
        notes.append(
            "Waiting-input expectation mismatch "
            f"(expected={case.must_emit_waiting_input}, seen={'waiting_input' in seen_event_types})"
        )

    checks_total += 1
    has_error = "error" in seen_event_types
    if case.allow_error_events or not has_error:
        checks_passed += 1
    else:
        notes.append("Unexpected error event detected")

    for required in case.required_operations:
        checks_total += 1
        if required in seen_operations:
            checks_passed += 1
        else:
            notes.append(f"Required operation not found: {required}")

    for forbidden in case.forbidden_operations:
        checks_total += 1
        if forbidden in seen_operations:
            notes.append(f"Forbidden operation detected: {forbidden}")
        else:
            checks_passed += 1

    score = checks_passed / checks_total if checks_total else 0.0
    return RuntimeEvaluationResult(
        case_key=case.key,
        passed=checks_passed == checks_total,
        score=score,
        notes=tuple(notes),
        seen_operations=tuple(sorted(seen_operations)),
        seen_event_types=tuple(sorted(seen_event_types)),
    )


def evaluate_runtime_cases(
    cases: Iterable[RuntimeEvaluationCase],
    runtime_events: Sequence[Dict[str, Any]],
) -> tuple[RuntimeEvaluationResult, ...]:
    return tuple(evaluate_runtime_case(case, runtime_events) for case in cases)


def _collect_event_types(runtime_events: Sequence[Dict[str, Any]]) -> Set[str]:
    seen: Set[str] = set()
    for item in runtime_events:
        event_type = str(item.get("type") or "").strip().lower()
        if event_type:
            seen.add(event_type)
    return seen


def _collect_operations(runtime_events: Sequence[Dict[str, Any]]) -> Set[str]:
    seen: Set[str] = set()
    for item in runtime_events:
        data = item.get("data")
        if isinstance(data, dict):
            _extract_operation_from_mapping(data, seen)
        trace = item.get("trace")
        if isinstance(trace, dict):
            _extract_operation_from_mapping(trace, seen)
    return seen


def _extract_operation_from_mapping(payload: Dict[str, Any], seen: Set[str]) -> None:
    for key in ("operation", "operation_slug", "tool_slug", "canonical_op_slug"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            seen.add(value.strip())

    operations = payload.get("operations")
    if isinstance(operations, list):
        for value in operations:
            if isinstance(value, str) and value.strip():
                seen.add(value.strip())
            elif isinstance(value, dict):
                nested_slug = value.get("operation_slug") or value.get("canonical_op_slug")
                if isinstance(nested_slug, str) and nested_slug.strip():
                    seen.add(nested_slug.strip())
