from __future__ import annotations

from app.runtime.orchestrator_contracts import IterationProposal, TaskAttemptFailure
from app.runtime.orchestrator import GraphOrchestrator
from app.runtime.plan_store import InMemoryPlanStore
from app.runtime.plan_store import _remove_bound_output
from app.runtime.synthesis_context import SynthesisContextBuilder


def test_synthesis_keeps_distinct_chunk_provenance_and_marks_excerpt_coverage() -> None:
    builder = SynthesisContextBuilder()
    sources = builder._source_projection([
        {"source_id": "doc-1", "chunk_id": "a", "text": "a" * 700},
        {"source_id": "doc-1", "chunk_id": "b", "text": "b" * 700},
    ])

    assert len(builder._dedupe(sources, "evidence_id")) == 2
    assert sources[0]["excerpt_truncated"] is True
    assert sources[0]["excerpt_length"] == 700


def test_synthesis_preserves_exact_observed_result_reader_cursor() -> None:
    observation = {"result_id": "r", "revision": 3, "offset": 4, "limit": 2,
                   "fields": ["payload"], "read_complete": False, "next_offset": 6,
                   "source_complete": False, "path": "/records/0/body",
                   "text_offset": 12000, "text_limit": 6000, "next_text_offset": 18000,
                   "child_offset": 0, "child_limit": 20, "next_child_offset": 20}

    references = SynthesisContextBuilder._verified_result_references({"receipts": [{
        "success": True, "result_id": "r", "operation": "result.read",
        "result_observation": observation,
    }]})

    assert references[0]["observation"] == observation
    assert references[0]["revision"] == 3


def test_stale_result_revision_is_carried_as_explicit_synthesis_limitation() -> None:
    context = SynthesisContextBuilder().build(plan={
        "goal": "goal",
        "iterations": [{"id": "i", "sequence": 1, "terminal": "synthesis",
                        "synthesis_brief": {"purpose": "answer"}}],
        "tasks": {"t": {"iteration_id": "i", "status": "completed", "result": {
            "description": "Used the retained page", "completion": "fulfilled",
            "verified": {"status": "observed", "limitations": [{
                "code": "result_revision_conflict", "message": "Observed revision changed.",
            }]},
        }}},
    }, iteration_id="i")

    assert context["limitations"] == [{"task_id": "t", "code": "result_revision_conflict",
                                       "message": "Observed revision changed."}]


def test_failure_persists_observed_partial_receipts_without_marking_success() -> None:
    store = InMemoryPlanStore()
    plan = store.create(goal="goal", root_run_id="run", tenant_id="tenant")
    store.apply_iteration(plan["id"], IterationProposal.model_validate({
        "terminal": "planner", "tasks": [{
            "task_id": "task", "executor": "agent", "intent": "inspect",
            "instructions": "inspect",
        }],
    }))
    store.claim_task(plan["id"], "task")
    observed = {"status": "observed", "receipts": [{"success": True,
        "result_id": "result-1", "result_observation": {"revision": 2, "offset": 10}}],
        "sources": [], "artifacts": []}

    result = store.finish_failure(plan["id"], "task", TaskAttemptFailure(
        code="llm_failed", message="terminal generation failed", retryable=False,
        details={"runtime_observed_partial": observed},
    ), max_attempts=1)

    assert result["status"] == "failed"
    assert result["result"]["verified"] == observed
    assert result["result"]["reason_code"] == "llm_failed"


def test_compaction_exposes_task_recovery_manifest_and_all_dispositions() -> None:
    compacted = GraphOrchestrator._compact_ledger({"tasks": [{
        "task_id": "t", "status": "failed", "result": {"outputs": {"x": "x" * 20_000}},
    }]}, max_chars=10_000)

    task = compacted["tasks"][0]
    assert task["status"] == "failed"
    assert task["result"]["outputs"]["x"]["_omitted"] is True


def test_binding_projection_removes_only_provenance_selected_output() -> None:
    dependency = {"outputs": {"bound": False, "unrelated": False},
                  "structured_response": {"bound": False, "unrelated": False},
                  "sources": [{"source_id": "s"}], "limitation": None}

    _remove_bound_output(dependency, "bound")

    assert dependency["outputs"] == {"unrelated": False}
    assert dependency["structured_response"] == {"unrelated": False}
    assert dependency["sources"] == [{"source_id": "s"}]
    assert dependency["limitation"] is None
