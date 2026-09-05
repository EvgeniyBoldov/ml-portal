from __future__ import annotations

import pytest

from app.runtime.orchestrator_contracts import PlanNodeKind, PlannedTask, TaskOutcome, TaskResult
from app.runtime.plan_store import InMemoryPlanStore
from app.runtime.synthesis_context import SynthesisContextBuilder, SynthesisContextError


def _plan() -> dict:
    return {
        "tasks": {
            "inspect": {
                "task_id": "inspect",
                "kind": "agent",
                "intent": "Inspect the document",
                "instructions": "Return the relevant findings",
                "status": "completed",
                "planned_order": 0,
                "result": {
                    "summary": "The document contains the requested policy.",
                    "outputs": {
                        "policy": {
                            "text": "Approved",
                            "artifacts": [{"artifact_id": "agent-claimed"}],
                        },
                    },
                    "verified": {
                        "artifacts": [{"artifact_id": "artifact-1", "file_name": "policy.txt"}],
                        "sources": [{"source_id": "doc-1", "source_name": "Policy"}],
                    },
                },
            },
            "replaced": {
                "task_id": "replaced",
                "kind": "agent",
                "intent": "Old approach",
                "instructions": "Ignore me",
                "status": "superseded",
                "planned_order": 1,
                "result": {"summary": "Stale report", "outputs": {}},
            },
            "checkpoint": {
                "task_id": "checkpoint",
                "kind": "planner",
                "intent": "Replan",
                "instructions": "Replan",
                "status": "completed",
                "planned_order": 2,
                "result": {"summary": "technical control data", "outputs": {}},
            },
            "synthesize": {
                "task_id": "synthesize",
                "kind": "synthesis",
                "intent": "Answer what the user actually asked",
                "instructions": "Give a direct answer and mention relevant caveats.",
                "status": "running",
                "planned_order": 3,
            },
        },
    }


def test_synthesis_context_contains_all_current_completed_agent_reports_only() -> None:
    context = SynthesisContextBuilder().build(plan=_plan(), synthesis_task_id="synthesize")

    assert context["synthesis_task"]["intent"] == "Answer what the user actually asked"
    assert [report["task_id"] for report in context["completed_task_reports"]] == ["inspect"]
    assert context["completed_task_reports"][0]["report"]["outputs"] == {
        "policy": {"text": "Approved"},
    }
    assert context["artifacts"] == [{
        "artifact_id": "artifact-1",
        "file_name": "policy.txt",
        "content_type": "",
        "size_bytes": None,
    }]
    assert context["sources"] == [{"source_id": "doc-1", "source_name": "Policy"}]


def test_synthesis_context_fails_instead_of_truncating_reports() -> None:
    plan = _plan()
    plan["tasks"]["inspect"]["result"]["outputs"] = {"report": {"text": "x" * 100}}

    with pytest.raises(SynthesisContextError, match="exceeds"):
        SynthesisContextBuilder(max_chars=50).build(plan=plan, synthesis_task_id="synthesize")


def test_replan_keeps_completed_task_as_superseded_for_trace_but_excludes_it_from_synthesis() -> None:
    store = InMemoryPlanStore()
    persisted = store.create(goal="answer", root_run_id="run", tenant_id="tenant")
    completed = PlannedTask(
        task_id="obsolete",
        executor="viewer",
        intent="Old research",
        instructions="Read old data",
    )
    synthesis = PlannedTask(
        task_id="synthesize",
        kind=PlanNodeKind.SYNTHESIS,
        intent="Answer the user",
        instructions="Use current reports only.",
    )
    from app.runtime.orchestrator_contracts import PlanPatch, PlannerDecisionKind

    store.apply_patch(
        persisted["id"],
        PlanPatch(expected_revision=0, decision=PlannerDecisionKind.CREATE_PLAN, tasks=[completed, synthesis]),
    )
    store.claim_ready(persisted["id"])
    store.apply_result(
        persisted["id"], "obsolete",
        TaskResult(outcome=TaskOutcome.COMPLETED, summary="obsolete finding"),
    )
    store.apply_patch(
        persisted["id"],
        PlanPatch(expected_revision=1, remove_task_ids=["obsolete"]),
    )

    plan = store.get(persisted["id"])
    assert plan["tasks"]["obsolete"]["status"] == "superseded"
    context = SynthesisContextBuilder().build(plan=plan, synthesis_task_id="synthesize")
    assert context["completed_task_reports"] == []
