from __future__ import annotations

import pytest

from app.runtime.orchestrator_contracts import (
    IterationProposal, PlannedTask, SynthesisBrief, TaskAttemptFailure,
    TaskCompletionDeclaration, TaskExecutionReceipt, TerminalKind,
)
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
    claim = store.claim_task(plan["id"], "task")
    observed = {"status": "observed", "receipts": [{"success": True,
        "result_id": "result-1", "result_observation": {"revision": 2, "offset": 10}}],
        "sources": [], "artifacts": []}

    result = store.finish_failure(plan["id"], "task", TaskAttemptFailure(
        code="llm_failed", message="terminal generation failed", retryable=False,
        details={"runtime_observed_partial": observed},
    ), max_attempts=1, expected_attempt_number=claim["attempts"])

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


def test_planner_ledger_recovery_reference_survives_tight_budget_compaction() -> None:
    result_ref = {
        "status": "available", "result_id": "saved-result", "revision": 7,
        "reader": "result.read", "reader_arguments": {
            "result_id": "saved-result", "revision": 7, "path": "/structured_response",
            "offset": 0, "limit": 1,
        },
        "next_action": {"tool": "result.read", "arguments": {
            "result_id": "saved-result", "revision": 7, "path": "/structured_response",
            "offset": 0, "limit": 1,
        }},
    }
    tasks = {}
    for index in range(5):
        task_id = f"large-task-{index}"
        tasks[task_id] = {"iteration_id": "iteration", "planned_order": index,
            "intent": "inspect " * 80, "executor": "agent", "instructions": "inspect " * 80, "inputs": {},
            "response_spec": {}, "expected_outputs": [], "status": "completed", "depends_on": [],
            "attempts": 1, "result": {"completion": "fulfilled", "description": "done" * 5000,
                "outputs": {"large": "large" * 5000},
                "verified": {"task_result_ref": result_ref} if index == 0 else {}}}
    snapshot = {"status": "running", "iterations": [], "needs": [], "bindings": [], "resolutions": [],
                "tasks": tasks}
    planner_ledger = GraphOrchestrator._planner_ledger(snapshot)
    compacted = GraphOrchestrator._compact_ledger(planner_ledger, max_chars=3000)

    task = next(item for item in compacted["tasks"] if item["task_id"] == "large-task-0")
    assert task["result"]["task_result_ref"] == result_ref
    assert task["omission_manifest"]["result_ref"] == result_ref
    assert len(__import__("json").dumps(compacted, ensure_ascii=False)) <= 3000


def test_binding_projection_removes_only_provenance_selected_output() -> None:
    dependency = {"outputs": {"bound": False, "unrelated": False},
                  "structured_response": {"bound": False, "unrelated": False},
                  "sources": [{"source_id": "s"}], "limitation": None}

    _remove_bound_output(dependency, "bound")

    assert dependency["outputs"] == {"unrelated": False}
    assert dependency["structured_response"] == {"unrelated": False}
    assert dependency["sources"] == [{"source_id": "s"}]
    assert dependency["limitation"] is None


@pytest.mark.asyncio
async def test_claimed_task_attempt_identity_is_passed_in_trusted_context() -> None:
    from types import SimpleNamespace
    from uuid import uuid4
    from app.agents.context import ToolContext
    from app.runtime.events import RuntimeEvent

    class AsyncStore:
        def __init__(self):
            self.inner = InMemoryPlanStore()
            self.plan = self.inner.create(goal="goal", root_run_id=str(uuid4()), tenant_id="tenant")

        async def snapshot(self, plan_id): return self.inner.snapshot(str(plan_id))
        async def recover_stale_claims(self, plan_id, **kwargs): return self.inner.recover_stale_claims(str(plan_id), **kwargs)
        async def apply_iteration(self, plan_id, proposal, **kwargs): return self.inner.apply_iteration(str(plan_id), proposal, **kwargs)
        async def next_decision(self, plan_id): return self.inner.next_decision(str(plan_id))
        async def claim_task(self, plan_id, task_id): return self.inner.claim_task(str(plan_id), task_id)
        async def link_attempt_execution(self, plan_id, task_id, execution_id, **kwargs):
            return self.inner.link_attempt_execution(str(plan_id), task_id, execution_id, **kwargs)
        async def task_request(self, plan_id, task_id, **kwargs): return self.inner.task_request(str(plan_id), task_id, **kwargs)
        async def finish_attempt(self, plan_id, task_id, **kwargs): return self.inner.finish_attempt(str(plan_id), task_id, **kwargs)
        async def claim_checkpoint(self, plan_id, kind): return self.inner.claim_checkpoint(str(plan_id), kind)
        async def complete_synthesis(self, plan_id): return self.inner.complete_synthesis(str(plan_id))
        async def mark_failed(self, plan_id, code, message): return self.inner.mark_failed(str(plan_id), code, message)

    class Planner:
        async def plan(self, *, request, **kwargs):
            return IterationProposal(tasks=[PlannedTask(task_id="work", executor="reader",
                intent="inspect", instructions="inspect")], terminal=TerminalKind.SYNTHESIS,
                synthesis_brief=SynthesisBrief(user_question="goal", planned_work="inspect",
                    purpose="answer", answer_requirements="short"))

    class CapturingExecutor:
        received = None
        async def execute_attempt(self, *, request, ctx, **kwargs):
            self.received = dict(ctx.extra)
            return TaskExecutionReceipt(declaration=TaskCompletionDeclaration(completion="fulfilled", report="done"),
                                        verified={})

    class Synthesizer:
        async def stream(self, *, runtime_state, run_id, **kwargs):
            runtime_state.final_answer = "answer"
            yield RuntimeEvent.final("answer", run_id=str(run_id), sources=[], attachments=[])

    store, executor = AsyncStore(), CapturingExecutor()
    ctx = ToolContext(user_id=uuid4(), tenant_id=uuid4(), extra={"existing": "preserved"})
    state = SimpleNamespace(final_answer=None, deleted_artifact_ids=[], execution_limitations=[])
    events = [event async for event in GraphOrchestrator(store=store, planner=Planner(), executor=executor,
        synthesizer=Synthesizer()).run(plan_id=store.plan["id"], goal="goal", available_agents=[{"slug": "reader"}],
        planner_kwargs={"runtime_state": state, "ctx": ctx})]

    assert events[-1]["status"] == "completed"
    assert executor.received["existing"] == "preserved"
    assert executor.received["runtime_root_run_id"] == store.plan["root_run_id"]
    assert executor.received["runtime_plan_id"] == str(store.plan["id"])
    assert executor.received["runtime_task_id"] == "work"
    assert executor.received["runtime_task_attempt_number"] == 1
