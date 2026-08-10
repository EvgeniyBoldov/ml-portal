"""Deterministic orchestration loop for the canonical plan graph."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator, Dict, Optional, Protocol

from app.runtime.orchestrator_contracts import (
    AgentTaskResult,
    PlanRequest,
    TaskExecutionError,
    TaskAttemptFailure,
    TaskOutcome,
    TaskRequest,
    TaskSuccessAction,
)
from app.runtime.plan_store import SqlPlanStore
from uuid import UUID, uuid4
from app.models.runtime_observability import RuntimePlannerInvocation
from app.runtime.events import RuntimeEvent, RuntimeEventType
from app.core.logging import get_logger
from app.runtime.entity_ids import (
    agent_execution_id as make_agent_execution_id,
    attempt_id as make_attempt_id,
    checkpoint_id as make_checkpoint_id,
    planner_iteration_id as make_iteration_id,
    planner_orchestrator_id,
    step_id as make_step_id,
)

logger = get_logger(__name__)


class Planner(Protocol):
    async def plan(self, *, request: PlanRequest, **kwargs: Any): ...


class TaskExecutor(Protocol):
    async def execute_task(self, *, request: TaskRequest) -> AgentTaskResult: ...


class OrchestratorEvent(dict):
    """Small event DTO used by the engine; runtime event adapters can wrap it."""

    def to_runtime_event(self) -> RuntimeEvent:
        event_name = str(self.get("type") or "")
        try:
            event_type = RuntimeEventType(event_name)
        except ValueError:
            return RuntimeEvent.status("orchestrator", **dict(self))
        payload = dict(self)
        payload.pop("type", None)
        if event_type is RuntimeEventType.PLANNER_ITERATION_START:
            return RuntimeEvent.planner_iteration_start(
                iteration_id=str(payload.pop("entity_id")),
                orchestrator_id=str(payload.pop("parent_entity_id")),
                iteration=int(payload.pop("iteration", 0)),
                iteration_type=str(payload.pop("iteration_type", payload.pop("mode", "decision"))),
                **payload,
            )
        if event_type is RuntimeEventType.PLANNER_ITERATION_END:
            return RuntimeEvent.planner_iteration_end(
                iteration_id=str(payload.pop("entity_id")),
                orchestrator_id=str(payload.pop("parent_entity_id")),
                iteration=int(payload.pop("iteration", 0)),
                status=str(payload.pop("status", "completed")),
                iteration_type=str(payload.pop("iteration_type", payload.pop("mode", "decision"))),
                **payload,
            )
        if event_type is RuntimeEventType.AGENT_START:
            return RuntimeEvent.agent_start(
                agent_execution_id=str(payload.pop("agent_execution_id", payload.pop("entity_id"))),
                parent_entity_type=str(payload.pop("parent_entity_type")),
                parent_entity_id=str(payload.pop("parent_entity_id")),
                agent_slug=str(payload.pop("agent_slug")),
                executor_type=str(payload.pop("executor_type", "agent")),
                executor_name=payload.pop("executor_name", None),
                task_title=payload.pop("task_title", None),
                **payload,
            )
        if event_type is RuntimeEventType.AGENT_END:
            return RuntimeEvent.agent_end(
                agent_execution_id=str(payload.pop("agent_execution_id", payload.pop("entity_id"))),
                parent_entity_type=str(payload.pop("parent_entity_type")),
                parent_entity_id=str(payload.pop("parent_entity_id")),
                agent_slug=str(payload.pop("agent_slug")),
                status=str(payload.pop("status", "completed")),
                **payload,
            )
        return RuntimeEvent(event_type, payload)


class GraphOrchestrator:
    """Persisted graph scheduler; all task lifecycle changes go through SQL."""

    def __init__(self, *, store: SqlPlanStore, planner: Planner, executor: TaskExecutor,
                 max_attempts: int = 3, retry_delay_seconds: int = 60,
                 event_sink: Optional[Any] = None,
                 budget_service: Optional[Any] = None,
                 logging_level: str = "brief") -> None:
        self.store, self.planner, self.executor = store, planner, executor
        self.max_attempts = max(1, max_attempts)
        self.retry_delay_seconds = max(1, retry_delay_seconds)
        self.event_sink = event_sink
        self.budget_service = budget_service
        self.logging_level = logging_level

    @staticmethod
    def _has_declared_resolvers(
        plan: Dict[str, Any], pending_needs: list[Dict[str, Any]]
    ) -> bool:
        """Return whether every pending runtime need has a graph producer.

        ``needs`` are discovered by executors, never declared by the planner.
        A replan is therefore useful only when it adds (or connects) a task
        that explicitly promises the missing output.  Without this check a
        planner can re-emit an unchanged graph until the revision budget is
        exhausted.
        """
        tasks = plan.get("tasks", {})
        if not isinstance(tasks, dict):
            return False
        for need in pending_needs:
            task = tasks.get(need.get("task_id"))
            if not isinstance(task, dict):
                return False
            key = need.get("key")
            if not isinstance(key, str) or not key:
                return False
            for producer_id in task.get("depends_on", []):
                producer = tasks.get(producer_id)
                if not isinstance(producer, dict):
                    continue
                outputs = producer.get("expected_outputs", [])
                if any(
                    isinstance(output, dict) and output.get("key") == key
                    for output in outputs
                ):
                    break
            else:
                return False
        return True

    async def run(self, *, plan_id: UUID, goal: str, available_agents: list[dict[str, Any]],
                  available_artifacts: Optional[list[dict[str, Any]]] = None,
                  max_steps: int = 80, planner_kwargs: Optional[Dict[str, Any]] = None) -> AsyncIterator[OrchestratorEvent]:
        plan = await self.store.snapshot(plan_id)
        root_run_id = UUID(str(plan["root_run_id"]))
        iteration_number = 1
        orchestrator_id = planner_orchestrator_id(str(root_run_id))

        async def observe(event_type: str, *, entity_type: str, entity_id: str, parent_type: Optional[str] = None, parent_id: Optional[str] = None, payload: Optional[Dict[str, Any]] = None, trigger: Optional[str] = None) -> None:
            # These lifecycle events are yielded below and therefore persisted
            # by RuntimeEventLogger.  All other observations use the same
            # root journal through ``event_sink``.
            if event_type in {"plan_created", "task_started", "task_completed", "task_unfulfillable"}:
                return
            if self.event_sink is None:
                return
            await self.event_sink(RuntimeEvent(
                RuntimeEventType(event_type),
                {
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "parent_entity_type": parent_type,
                    "parent_entity_id": parent_id,
                    "trigger": trigger,
                    **(payload or {}),
                },
            ))
        planner_kwargs = planner_kwargs or {}
        force_replan = bool(planner_kwargs.get("force_replan"))
        resume_user_response = str(planner_kwargs.get("resume_user_response") or "").strip() or None
        limits = dict(planner_kwargs.get("runtime_limits") or {})
        planner_rbac_audit = dict(planner_kwargs.get("planner_rbac_audit") or {})
        llm_kwargs = {
            key: planner_kwargs[key]
            for key in ("chat_id", "tenant_id", "user_id", "agent_execution_id", "sandbox_overrides")
            if key in planner_kwargs
        }
        # A planner iteration represents one planner decision and the task
        # steps executed against that decision.  It is deliberately not a
        # synonym for one claimed task.
        active_iteration_id: Optional[str] = None
        active_iteration_type = "execution"
        active_step_number = 1
        iteration_open = False

        def close_active_iteration(*, status: str, outcome: Optional[str] = None) -> Optional[OrchestratorEvent]:
            nonlocal iteration_open
            if not iteration_open or active_iteration_id is None:
                return None
            iteration_open = False
            payload: Dict[str, Any] = {
                "type": "planner_iteration_end",
                "entity_id": active_iteration_id,
                "planner_iteration_id": active_iteration_id,
                "parent_entity_type": "orchestrator",
                "parent_entity_id": orchestrator_id,
                "iteration": iteration_number,
                "iteration_number": iteration_number,
                "iteration_type": active_iteration_type,
                "status": status,
            }
            if outcome:
                payload["outcome"] = outcome
            return OrchestratorEvent(**payload)

        async def revise(*, reason: str, last_failure: Optional[Dict[str, Any]] = None) -> Optional[str]:
            nonlocal iteration_number, active_iteration_id, active_iteration_type, active_step_number, iteration_open
            current = await self.store.snapshot(plan_id)
            iteration_number += 1
            iteration_entity_id = make_iteration_id(str(root_run_id), iteration_number)
            active_iteration_id = iteration_entity_id
            active_iteration_type = "replan"
            active_step_number = 2
            iteration_open = True
            planner_step_id = make_step_id(iteration_entity_id, 1, "replan")
            planner_executor_id = make_agent_execution_id(iteration_entity_id, "planner", iteration_number)
            invocation_id = uuid4()
            checkpoint_id = make_checkpoint_id(str(root_run_id), "planner", str(invocation_id))
            await observe("orchestrator_checkpoint_started", entity_type="orchestrator_checkpoint", entity_id=checkpoint_id,
                          parent_type="orchestrator", parent_id=orchestrator_id,
                          payload={"kind": "planner", "mode": "replan", "reason": reason, "revision": current["revision"]}, trigger=reason)
            self.store.session.add(RuntimePlannerInvocation(
                id=invocation_id, run_id=root_run_id, orchestrator_id=orchestrator_id,
                plan_id=plan_id, trigger=reason, status="running", revision_before=current["revision"],
                context_snapshot={"goal": goal, "last_failure": last_failure},
            ))
            await self.store.session.flush()
            await observe("planner_invocation_started", entity_type="planner_invocation", entity_id=str(invocation_id), parent_type="orchestrator", parent_id=orchestrator_id, payload={"trigger": reason, "revision": current["revision"]}, trigger=reason)
            await observe("planner_iteration_start", entity_type="planner_iteration", entity_id=iteration_entity_id, parent_type="orchestrator", parent_id=orchestrator_id, payload={"iteration": iteration_number, "iteration_number": iteration_number, "iteration_type": "replan", "mode": "replan"}, trigger=reason)
            await observe("step_start", entity_type="step", entity_id=planner_step_id, parent_type="planner_iteration", parent_id=iteration_entity_id, payload={"step_number": 1, "kind": "plan", "title": "Перепланировать", "objective": reason}, trigger=reason)
            await observe("agent_start", entity_type="agent_execution", entity_id=planner_executor_id, parent_type="step", parent_id=planner_step_id, payload={"agent_execution_id": planner_executor_id, "agent_slug": "planner", "executor_type": "planner", "executor_name": "Планер", "task_title": reason}, trigger=reason)
            await observe("rbac_snapshot", entity_type="agent_execution", entity_id=planner_executor_id, parent_type="step", parent_id=planner_step_id, payload={"rbac": planner_rbac_audit}, trigger=reason)
            try:
                patch = await self.planner.plan(request=PlanRequest(
                    goal=goal,
                    available_agents=available_agents,
                    plan=current,
                    completed_outputs=self._completed_outputs(current),
                    available_artifacts=self._available_artifacts(current, available_artifacts),
                    needs=[
                        {"task_id": task_id, **need}
                        for task_id, task in current.get("tasks", {}).items()
                        for need in task.get("needs", [])
                        if isinstance(need, dict)
                    ],
                    last_failure=last_failure,
                    user_response=resume_user_response if reason == "user_input" else None,
                    memory_context=list(planner_kwargs.get("planner_memory_context") or []),
                    trigger=reason,
                    run_id=root_run_id,
                    plan_id=plan_id,
                    trace_parent_id=checkpoint_id,
                ), **{**llm_kwargs, "agent_execution_id": UUID(planner_executor_id), "event_sink": self.event_sink})
                await observe("planner_decision", entity_type="planner_iteration", entity_id=iteration_entity_id,
                              parent_type="orchestrator", parent_id=orchestrator_id,
                              payload={"mode": "replan", "decision": patch.decision.value,
                                       "revision_before": current["revision"], "task_count": len(patch.tasks),
                                       "remove_task_count": len(patch.remove_task_ids)}, trigger=reason)
                decision = await self.budget_service.consume(run_id=root_run_id, owner_type="run", owner_id=str(root_run_id), metric="plan_revisions", limit=limits.get("plan_revisions"), reason=reason) if self.budget_service else None
                if decision is not None and not decision.allowed:
                    raise RuntimeError("plan revision budget exceeded")
                updated = await self.store.apply_patch(plan_id, patch, reason=reason, planner_invocation_id=str(invocation_id))
            except Exception as exc:
                failure = {"code": type(exc).__name__, "message": str(exc), "trigger": reason}
                invocation = await self.store.session.get(RuntimePlannerInvocation, invocation_id, with_for_update=True)
                if invocation is not None:
                    invocation.status = "failed"
                    invocation.error = str(exc)
                    invocation.finished_at = datetime.now(timezone.utc)
                await self.store.mark_failed(plan_id, failure)
                await observe("planner_invocation_finished", entity_type="planner_invocation", entity_id=str(invocation_id), parent_type="orchestrator", parent_id=orchestrator_id,
                              payload={"status": "failed", "revision_before": current["revision"], "error_code": type(exc).__name__}, trigger=reason)
                terminal_error = {"error": str(exc), "error_code": "plan_patch_invalid", "recoverable": False}
                if getattr(exc, "llm_call_id", None):
                    terminal_error["llm_call_id"] = str(exc.llm_call_id)
                await observe("error", entity_type="error", entity_id=str(uuid4()), parent_type="planner_iteration", parent_id=iteration_entity_id,
                              payload=terminal_error, trigger=reason)
                await observe("orchestrator_checkpoint_finished", entity_type="orchestrator_checkpoint", entity_id=checkpoint_id,
                              parent_type="orchestrator", parent_id=orchestrator_id,
                              payload={"kind": "planner", "mode": "replan", "status": "failed", "reason": str(exc)}, trigger=reason)
                await observe("agent_end", entity_type="agent_execution", entity_id=planner_executor_id,
                              parent_type="step", parent_id=planner_step_id,
                              payload={"agent_execution_id": planner_executor_id, "agent_slug": "planner", "status": "failed"}, trigger=reason)
                await observe("step_end", entity_type="step", entity_id=planner_step_id,
                              parent_type="planner_iteration", parent_id=iteration_entity_id,
                              payload={"step_number": 1, "status": "failed", "outcome": "plan_patch_invalid"}, trigger=reason)
                return str(exc)
            invocation = await self.store.session.get(RuntimePlannerInvocation, invocation_id, with_for_update=True)
            if invocation:
                invocation.status, invocation.revision_after, invocation.finished_at = "completed", updated.revision, datetime.now(timezone.utc)
            await observe("planner_invocation_finished", entity_type="planner_invocation", entity_id=str(invocation_id), parent_type="orchestrator", parent_id=orchestrator_id,
                          payload={"status": "completed", "revision_before": current["revision"], "revision_after": updated.revision}, trigger=reason)
            await observe("plan_patch_applied", entity_type="plan", entity_id=str(plan_id), parent_type="agent_execution", parent_id=planner_executor_id,
                          payload={"mode": "replan", "revision_before": current["revision"], "revision_after": updated.revision,
                                   "decision": patch.decision.value, "patch": patch.model_dump(mode="json")}, trigger=reason)
            if patch.decision.value == "ask_user":
                await observe("waiting_input", entity_type="interaction", entity_id=str(uuid4()), parent_type="planner_iteration", parent_id=iteration_entity_id,
                              payload={"question": patch.question, "interaction_kind": "clarify"}, trigger=reason)
            await observe("orchestrator_checkpoint_finished", entity_type="orchestrator_checkpoint", entity_id=checkpoint_id,
                          parent_type="orchestrator", parent_id=orchestrator_id,
                          payload={"kind": "planner", "mode": "replan", "status": "completed", "revision": updated.revision}, trigger=reason)
            await observe("agent_end", entity_type="agent_execution", entity_id=planner_executor_id, parent_type="step", parent_id=planner_step_id, payload={"agent_execution_id": planner_executor_id, "agent_slug": "planner", "status": "completed"}, trigger=reason)
            await observe("step_end", entity_type="step", entity_id=planner_step_id, parent_type="planner_iteration", parent_id=iteration_entity_id, payload={"step_number": 1, "status": "completed", "outcome": "success"}, trigger=reason)
            return None
        if force_replan:
            replan_error = await revise(reason="user_input")
            if replan_error:
                closed = close_active_iteration(status="failed", outcome="plan_patch_invalid")
                if closed is not None:
                    yield closed
                yield OrchestratorEvent(type="plan_terminal", plan_id=str(plan_id), status="failed", error=replan_error)
                return
            plan = await self.store.snapshot(plan_id)

        if not plan["tasks"] and not force_replan:
            invocation_id = uuid4()
            checkpoint_id = make_checkpoint_id(str(root_run_id), "planner", str(invocation_id))
            await observe("orchestrator_checkpoint_started", entity_type="orchestrator_checkpoint", entity_id=checkpoint_id,
                          parent_type="orchestrator", parent_id=orchestrator_id,
                          payload={"kind": "planner", "mode": "initial", "revision": plan["revision"]}, trigger="initial")
            self.store.session.add(RuntimePlannerInvocation(
                id=invocation_id, run_id=root_run_id, orchestrator_id=orchestrator_id,
                plan_id=plan_id, trigger="initial", status="running", revision_before=plan["revision"], context_snapshot={"goal": goal},
            ))
            await self.store.session.flush()
            await observe("planner_invocation_started", entity_type="planner_invocation", entity_id=str(invocation_id), parent_type="orchestrator", parent_id=orchestrator_id, payload={"trigger": "initial", "revision": plan["revision"]}, trigger="initial")
            iteration_id = make_iteration_id(str(root_run_id), iteration_number)
            active_iteration_id = iteration_id
            active_iteration_type = "decision"
            active_step_number = 2
            iteration_open = True
            step_id = make_step_id(iteration_id, 1, "plan")
            planner_executor_id = make_agent_execution_id(iteration_id, "planner", 1)
            yield OrchestratorEvent(type="planner_iteration_start", entity_id=iteration_id,
                                    planner_iteration_id=iteration_id, parent_entity_type="orchestrator",
                                    parent_entity_id=orchestrator_id, iteration=iteration_number,
                                    iteration_number=iteration_number, iteration_type="decision", mode="initial")
            yield OrchestratorEvent(type="step_start", entity_id=step_id, entity_type="step",
                                    parent_entity_type="planner_iteration", parent_entity_id=iteration_id,
                                    step_number=1, kind="plan", title="Сформировать план", objective=goal)
            yield OrchestratorEvent(type="agent_start", entity_id=planner_executor_id,
                                    agent_execution_id=planner_executor_id, parent_entity_type="step",
                                    parent_entity_id=step_id, agent_slug="planner", role="planner",
                                    executor_type="planner", executor_name="Планер", task_title=goal)
            yield OrchestratorEvent(type="rbac_snapshot", entity_type="agent_execution", entity_id=planner_executor_id,
                                    parent_entity_type="step", parent_entity_id=step_id,
                                    rbac=planner_rbac_audit)
            try:
                patch = await self.planner.plan(request=PlanRequest(
                    goal=goal, available_agents=available_agents, plan=plan,
                    completed_outputs=self._completed_outputs(plan),
                    memory_context=list(planner_kwargs.get("planner_memory_context") or []),
                    available_artifacts=self._available_artifacts(plan, available_artifacts),
                    trigger="initial", run_id=root_run_id, plan_id=plan_id,
                    trace_parent_id=iteration_id,
                ), **{**llm_kwargs, "agent_execution_id": UUID(planner_executor_id), "event_sink": self.event_sink})
                await observe("planner_decision", entity_type="planner_iteration", entity_id=iteration_id,
                              parent_type="orchestrator", parent_id=orchestrator_id,
                              payload={"mode": "initial", "decision": patch.decision.value,
                                       "revision_before": plan["revision"], "task_count": len(patch.tasks),
                                       "remove_task_count": len(patch.remove_task_ids)}, trigger="initial")
                if self.budget_service is not None:
                    decision = await self.budget_service.consume(run_id=root_run_id, owner_type="run", owner_id=str(root_run_id), metric="plan_revisions", limit=limits.get("plan_revisions"), reason="initial_plan")
                    if not decision.allowed:
                        raise RuntimeError("plan revision budget exceeded")
                updated = await self.store.apply_patch(plan_id, patch, reason="initial_plan", planner_invocation_id=str(invocation_id))
            except Exception as exc:
                failure = {"code": type(exc).__name__, "message": str(exc), "trigger": "initial"}
                invocation = await self.store.session.get(RuntimePlannerInvocation, invocation_id, with_for_update=True)
                if invocation is not None:
                    invocation.status = "failed"
                    invocation.error = str(exc)
                    invocation.finished_at = datetime.now(timezone.utc)
                await self.store.mark_failed(plan_id, failure)
                await observe("planner_invocation_finished", entity_type="planner_invocation", entity_id=str(invocation_id), parent_type="orchestrator", parent_id=orchestrator_id,
                              payload={"status": "failed", "revision_before": plan["revision"], "error_code": type(exc).__name__}, trigger="initial")
                terminal_error = {"error": str(exc), "error_code": "plan_patch_invalid", "recoverable": False}
                if getattr(exc, "llm_call_id", None):
                    terminal_error["llm_call_id"] = str(exc.llm_call_id)
                await observe("error", entity_type="error", entity_id=str(uuid4()), parent_type="planner_iteration", parent_id=iteration_id,
                              payload=terminal_error, trigger="initial")
                await observe("orchestrator_checkpoint_finished", entity_type="orchestrator_checkpoint", entity_id=checkpoint_id,
                              parent_type="orchestrator", parent_id=orchestrator_id,
                              payload={"kind": "planner", "mode": "initial", "status": "failed", "reason": str(exc)}, trigger="initial")
                yield OrchestratorEvent(type="agent_end", entity_id=planner_executor_id,
                                        agent_execution_id=planner_executor_id, parent_entity_type="step",
                                        parent_entity_id=step_id, agent_slug="planner", role="planner", status="failed")
                yield OrchestratorEvent(type="step_end", entity_id=step_id, entity_type="step",
                                        parent_entity_type="planner_iteration", parent_entity_id=iteration_id,
                                        step_number=1, status="failed", outcome="plan_patch_invalid")
                closed = close_active_iteration(status="failed", outcome="plan_patch_invalid")
                if closed is not None:
                    yield closed
                yield OrchestratorEvent(type="plan_terminal", plan_id=str(plan_id), status="failed", error=str(exc))
                return
            invocation = await self.store.session.get(RuntimePlannerInvocation, invocation_id, with_for_update=True)
            if invocation is not None:
                invocation.status = "completed"
                invocation.revision_after = updated.revision
                invocation.finished_at = datetime.now(timezone.utc)
            await observe("planner_invocation_finished", entity_type="planner_invocation", entity_id=str(invocation_id), parent_type="orchestrator", parent_id=orchestrator_id,
                          payload={"status": "completed", "revision_before": plan["revision"], "revision_after": updated.revision}, trigger="initial")
            await observe("plan_created", entity_type="plan", entity_id=str(plan_id), parent_type="agent_execution", parent_id=planner_executor_id,
                          payload={"revision_before": plan["revision"], "revision_after": updated.revision,
                                   "mode": "initial", "decision": patch.decision.value, "patch": patch.model_dump(mode="json")}, trigger="initial")
            if patch.decision.value == "ask_user":
                await observe("waiting_input", entity_type="interaction", entity_id=str(uuid4()), parent_type="planner_iteration", parent_id=iteration_id,
                              payload={"question": patch.question, "interaction_kind": "clarify"}, trigger="initial")
            await observe("orchestrator_checkpoint_finished", entity_type="orchestrator_checkpoint", entity_id=checkpoint_id,
                          parent_type="orchestrator", parent_id=orchestrator_id,
                          payload={"kind": "planner", "mode": "initial", "status": "completed", "revision": updated.revision}, trigger="initial")
            yield OrchestratorEvent(type="agent_end", entity_id=planner_executor_id,
                                    agent_execution_id=planner_executor_id, parent_entity_type="step",
                                    parent_entity_id=step_id, agent_slug="planner", role="planner", status="completed")
            yield OrchestratorEvent(type="step_end", entity_id=step_id, entity_type="step",
                                    parent_entity_type="planner_iteration", parent_entity_id=iteration_id,
                                    step_number=1, status="completed", outcome="success", summary="План сформирован")
            yield OrchestratorEvent(type="plan_created", entity_type="plan", entity_id=str(plan_id),
                                    parent_entity_type="agent_execution", parent_entity_id=planner_executor_id,
                                    plan_id=str(plan_id), revision_before=plan["revision"], revision_after=updated.revision, mode="initial",
                                    patch=patch.model_dump(mode="json"))
        elif not force_replan:
            # A resumed persisted plan has no new planner call in this run,
            # but its task steps still need one explicit execution iteration.
            active_iteration_id = make_iteration_id(str(root_run_id), iteration_number)
            active_iteration_type = "execution"
            active_step_number = 1
            iteration_open = True
            yield OrchestratorEvent(type="planner_iteration_start", entity_id=active_iteration_id,
                                    planner_iteration_id=active_iteration_id, parent_entity_type="orchestrator",
                                    parent_entity_id=orchestrator_id, iteration=iteration_number,
                                    iteration_number=iteration_number, iteration_type="execution", mode="resume")
        for _ in range(max_steps):
            plan = await self.store.snapshot(plan_id)
            if plan["status"] in {"completed", "waiting_input", "failed", "cancelled"}:
                closed = close_active_iteration(status=plan["status"])
                if closed is not None:
                    yield closed
                yield OrchestratorEvent(type="plan_terminal", plan_id=str(plan_id), status=plan["status"])
                return
            task = await self.store.claim_ready(plan_id)
            if task is None:
                pending_needs = [
                    {
                        "task_id": task_id,
                        **need,
                    }
                    for task_id, task_data in plan.get("tasks", {}).items()
                    for need in task_data.get("needs", [])
                    if need.get("required", True)
                    and need.get("status") != "resolved"
                ]
                if pending_needs:
                    closed = close_active_iteration(status="needs_dependency", outcome="needs_dependency")
                    if closed is not None:
                        yield closed
                    replan_error = await revise(reason="pending_need")
                    if replan_error:
                        closed = close_active_iteration(status="failed", outcome="plan_patch_invalid")
                        if closed is not None:
                            yield closed
                        yield OrchestratorEvent(type="plan_terminal", plan_id=str(plan_id), status="failed", error=replan_error)
                        return
                    revised_plan = await self.store.snapshot(plan_id)
                    if revised_plan["status"] == "active" and not self._has_declared_resolvers(
                        revised_plan, pending_needs
                    ):
                        failure = {
                            "code": "unresolvable_dependency",
                            "message": "planner did not declare a producer or request user input for pending needs",
                            "needs": [
                                {"task_id": need["task_id"], "key": need["key"]}
                                for need in pending_needs
                            ],
                        }
                        await self.store.mark_failed(plan_id, failure)
                        await observe(
                            "error",
                            entity_type="error",
                            entity_id=str(uuid4()),
                            parent_type="planner_iteration",
                            parent_id=active_iteration_id,
                            payload={
                                "error": failure["message"],
                                "error_code": failure["code"],
                                "recoverable": False,
                            },
                            trigger="pending_need",
                        )
                        closed = close_active_iteration(
                            status="failed", outcome="unresolvable_dependency"
                        )
                        if closed is not None:
                            yield closed
                        yield OrchestratorEvent(
                            type="plan_terminal",
                            plan_id=str(plan_id),
                            status="failed",
                            error=failure["message"],
                        )
                        return
                    continue
                closed = close_active_iteration(status="stalled")
                if closed is not None:
                    yield closed
                yield OrchestratorEvent(type="plan_stalled", plan_id=str(plan_id))
                return
            if active_iteration_id is None:
                raise RuntimeError("task execution requires an active planner iteration")
            task_id = task.task_id
            snapshot = await self.store.snapshot(plan_id)
            dependencies = {}
            for dep in snapshot["tasks"].get(task_id, {}).get("depends_on", []):
                result_data = snapshot["tasks"].get(dep, {}).get("result", {})
                if not isinstance(result_data, dict):
                    continue
                dependencies[dep] = {
                    "summary": result_data.get("summary", ""),
                    "outputs": result_data.get("outputs", {}),
                    "evidence": result_data.get("evidence", {}),
                }
            request = TaskRequest(task_id=task_id, intent=task.intent, instructions=task.instructions,
                                  executor=task.executor, inputs={
                                      **(task.inputs or {}),
                                      "resolved_needs": [
                                          {
                                              "ref": need.get("ref") or need.get("key"),
                                              "key": need.get("key"),
                                              "value": need.get("resolved_value"),
                                              "resolver_task_id": need.get("resolver_task_id"),
                                          }
                                          for need in snapshot["tasks"].get(task_id, {}).get("needs", [])
                                          if need.get("status") == "resolved"
                                      ],
                                  },
                                  needs=snapshot["tasks"].get(task_id, {}).get("needs", []),
                                  checkpoint=task.checkpoint or {}, dependency_outputs=dependencies,
                                  memory_context=(
                                      planner_kwargs["durable_memory_snapshot"].agent_context(
                                          query=f"{task.intent} {task.instructions}"
                                      )
                                      if planner_kwargs.get("durable_memory_snapshot") is not None
                                      else []
                                  ))
            checkpoint_id = make_checkpoint_id(str(root_run_id), "task", f"{task_id}:{task.attempts}")
            executor_id = make_agent_execution_id(active_iteration_id, task_id, task.attempts)
            await observe("orchestrator_checkpoint_started", entity_type="orchestrator_checkpoint", entity_id=checkpoint_id,
                          parent_type="orchestrator", parent_id=orchestrator_id,
                          payload={"kind": "task", "task_id": task_id, "attempt": task.attempts, "executor": task.executor})
            await observe("task_started", entity_type="task", entity_id=task_id, parent_type="plan", parent_id=str(plan_id), payload={"attempt": task.attempts, "checkpoint_id": checkpoint_id})
            attempt_entity_id = make_attempt_id(task_id, task.attempts)
            await observe("attempt_started", entity_type="attempt", entity_id=attempt_entity_id, parent_type="task", parent_id=task_id, payload={"attempt": task.attempts, "attempt_number": task.attempts})
            if self.budget_service is not None:
                decision = await self.budget_service.consume(run_id=root_run_id, owner_type="run", owner_id=str(root_run_id), metric="task_attempts", limit=limits.get("task_attempts"), reason="task_started")
                if not decision.allowed:
                    raise RuntimeError("task attempt budget exceeded")
            yield OrchestratorEvent(type="task_started", entity_type="task", entity_id=task_id,
                                    parent_entity_type="plan", parent_entity_id=str(plan_id),
                                    plan_id=str(plan_id), task_id=task_id, attempt=task.attempts)
            step_number = active_step_number
            step_id = make_step_id(active_iteration_id, step_number, task_id)
            yield OrchestratorEvent(type="step_start", entity_id=step_id, entity_type="step",
                                    parent_entity_type="planner_iteration", parent_entity_id=active_iteration_id,
                                    step_number=step_number, kind="call_agent", title=task.intent, objective=task.instructions,
                                    intent=task.intent, inputs=task.inputs or {})
            yield OrchestratorEvent(type="agent_start", entity_id=executor_id, agent_execution_id=executor_id,
                                    parent_entity_type="step", parent_entity_id=step_id,
                                    agent_slug=task.executor, task_id=task_id, attempt=task.attempts,
                                    task_title=task.intent, task_objective=task.instructions,
                                    executor_type="agent", executor_name=task.executor,
                                    task_inputs=task.inputs or {}, expected_outputs=[
                                        item.model_dump(mode="json") if hasattr(item, "model_dump") else item
                                        for item in (task.expected_outputs or [])
                                    ])
            try:
                task_executor_kwargs = dict(planner_kwargs)
                task_executor_kwargs["runtime_run_id"] = str(root_run_id)
                task_executor_kwargs["lifecycle_agent_execution_id"] = executor_id
                task_executor_kwargs["runtime_log_parent"] = {"entity_type": "step", "entity_id": step_id}
                task_executor_kwargs["iteration_id"] = active_iteration_id
                result = await self.executor.execute_task(request=request, **task_executor_kwargs)
            except Exception as exc:
                if isinstance(exc, TaskExecutionError):
                    failure = TaskAttemptFailure(
                        code=exc.code,
                        message=str(exc) or "task execution failed",
                        retryable=exc.retryable,
                        details=exc.details,
                    )
                else:
                    failure = TaskAttemptFailure(
                        code=type(exc).__name__,
                        message=str(exc) or "task execution failed",
                        retryable=True,
                    )
                retry_after_ms = failure.details.get("retry_after_ms")
                retry_delay = self.retry_delay_seconds
                if isinstance(retry_after_ms, int) and retry_after_ms > 0:
                    retry_delay = max(1, min(30, (retry_after_ms + 999) // 1000))
                await self.store.record_failure(plan_id, task_id, failure,
                    retry_at=datetime.now(timezone.utc) + timedelta(seconds=retry_delay),
                    max_attempts=self.max_attempts)
                await observe("attempt_failed", entity_type="attempt", entity_id=attempt_entity_id, parent_type="task", parent_id=task_id, payload={"error": failure.model_dump(mode="json")}, trigger="technical_failure")
                await observe("orchestrator_checkpoint_finished", entity_type="orchestrator_checkpoint", entity_id=checkpoint_id,
                              parent_type="orchestrator", parent_id=orchestrator_id,
                              payload={"kind": "task", "task_id": task_id, "attempt": task.attempts, "status": "failed_technical", "error": failure.model_dump(mode="json")}, trigger="technical_failure")
                yield OrchestratorEvent(type="agent_end", entity_id=executor_id, agent_execution_id=executor_id,
                                        parent_entity_type="step", parent_entity_id=step_id,
                                        agent_slug=task.executor, task_id=task_id, status="failed",
                                        task_title=task.intent, task_objective=task.instructions)
                yield OrchestratorEvent(type="step_end", entity_id=step_id, entity_type="step",
                                        parent_entity_type="planner_iteration", parent_entity_id=active_iteration_id,
                                        step_number=step_number, status="failed", outcome="technical_failure", summary=failure.message)
                yield OrchestratorEvent(type="task_attempt_failed", plan_id=str(plan_id), task_id=task_id,
                                        error=failure.model_dump(mode="json"))
                active_step_number += 1
                if not failure.retryable or task.attempts >= self.max_attempts:
                    closed = close_active_iteration(status="failed", outcome="technical_failure")
                    if closed is not None:
                        yield closed
                    replan_error = await revise(reason="technical_failure", last_failure=failure.model_dump(mode="json"))
                    if replan_error:
                        closed = close_active_iteration(status="failed", outcome="plan_patch_invalid")
                        if closed is not None:
                            yield closed
                        yield OrchestratorEvent(type="plan_terminal", plan_id=str(plan_id), status="failed", error=replan_error)
                        return
                continue
            await self.store.apply_result(plan_id, task_id, result)
            result_event = "task_completed" if result.outcome.value == "completed" else "status"
            await observe(result_event, entity_type="task", entity_id=task_id, parent_type="plan", parent_id=str(plan_id), payload={"outcome": result.outcome.value, "summary": result.summary, "outputs": result.outputs}, trigger=result.outcome.value)
            await observe("attempt_succeeded", entity_type="attempt", entity_id=attempt_entity_id, parent_type="task", parent_id=task_id, payload={"outcome": result.outcome.value, "attempt_number": task.attempts})
            await observe("orchestrator_checkpoint_finished", entity_type="orchestrator_checkpoint", entity_id=checkpoint_id,
                          parent_type="orchestrator", parent_id=orchestrator_id,
                          payload={"kind": "task", "task_id": task_id, "attempt": task.attempts, "status": result.outcome.value, "summary": result.summary}, trigger=result.outcome.value)
            yield OrchestratorEvent(type="agent_end", entity_id=executor_id, agent_execution_id=executor_id,
                                    parent_entity_type="step", parent_entity_id=step_id,
                                    agent_slug=task.executor, task_id=task_id,
                                    task_title=task.intent, task_objective=task.instructions,
                                    summary=result.summary,
                                    outcome=result.outcome.value,
                                    status="completed" if result.outcome.value == "completed" else result.outcome.value)
            yield OrchestratorEvent(type="step_end", entity_id=step_id, entity_type="step",
                                    parent_entity_type="planner_iteration", parent_entity_id=active_iteration_id,
                                    step_number=step_number, status="completed" if result.outcome.value == "completed" else result.outcome.value,
                                    outcome=result.outcome.value, summary=result.summary,
                                    sufficient_for_phase=result.outcome.value == "completed")
            yield OrchestratorEvent(type=("task_completed" if result.outcome.value == "completed" else "task_unfulfillable"),
                                    entity_type="task", entity_id=task_id,
                                    parent_entity_type="plan", parent_entity_id=str(plan_id),
                                    plan_id=str(plan_id), task_id=task_id, outcome=result.outcome.value)
            active_step_number += 1
            success_action = getattr(task, "on_success", TaskSuccessAction.CONTINUE.value)
            if (
                result.outcome == TaskOutcome.COMPLETED
                and str(getattr(success_action, "value", success_action)) == TaskSuccessAction.REPLAN.value
            ):
                closed = close_active_iteration(status="completed", outcome="replan")
                if closed is not None:
                    yield closed
                replan_error = await revise(reason="task_completed")
                if replan_error:
                    closed = close_active_iteration(status="failed", outcome="plan_patch_invalid")
                    if closed is not None:
                        yield closed
                    yield OrchestratorEvent(type="plan_terminal", plan_id=str(plan_id), status="failed", error=replan_error)
                    return
                continue
            if result.outcome in {TaskOutcome.NEEDS_DEPENDENCY, TaskOutcome.UNFULFILLABLE}:
                closed = close_active_iteration(status=result.outcome.value, outcome=result.outcome.value)
                if closed is not None:
                    yield closed
                replan_error = await revise(reason=result.outcome.value)
                if replan_error:
                    closed = close_active_iteration(status="failed", outcome="plan_patch_invalid")
                    if closed is not None:
                        yield closed
                    yield OrchestratorEvent(type="plan_terminal", plan_id=str(plan_id), status="failed", error=replan_error)
                    return
        closed = close_active_iteration(status="max_steps")
        if closed is not None:
            yield closed
        yield OrchestratorEvent(type="max_steps", plan_id=str(plan_id))

    @staticmethod
    def _completed_outputs(plan: Dict[str, Any]) -> Dict[str, Any]:
        return {
            task_id: dict(task.get("result", {}).get("outputs", {}))
            for task_id, task in dict(plan.get("tasks") or {}).items()
            if task.get("status") == "completed" and isinstance(task.get("result"), dict)
        }

    @staticmethod
    def _available_artifacts(
        plan: Dict[str, Any],
        input_artifacts: Optional[list[dict[str, Any]]] = None,
    ) -> list[dict[str, Any]]:
        artifacts: list[dict[str, Any]] = []
        for item in input_artifacts or []:
            if not isinstance(item, dict):
                continue
            ref = item.get("ref") if isinstance(item.get("ref"), dict) else item
            artifact_id = str(ref.get("artifact_id") or item.get("artifact_id") or "").strip()
            if not artifact_id or str(ref.get("status") or item.get("status") or "active") == "deleted":
                continue
            artifacts.append({
                "artifact_id": artifact_id,
                "file_name": ref.get("file_name") or item.get("file_name") or "artifact",
                "content_type": ref.get("content_type") or item.get("content_type"),
                "size_bytes": ref.get("size_bytes") or item.get("size_bytes"),
                "snippet": item.get("snippet") or "",
                "snippet_status": item.get("snippet_status") or "missing",
                "readable": bool(item.get("readable")),
                "truncated": bool(item.get("truncated")),
            })
        for task in dict(plan.get("tasks") or {}).values():
            outputs = dict(task.get("result", {}).get("outputs", {})) if isinstance(task.get("result"), dict) else {}
            for item in [*(outputs.get("artifacts", []) or []), *(outputs.get("attachments", []) or [])]:
                if isinstance(item, dict) and item.get("artifact_id") and item.get("status") != "deleted":
                    artifacts.append(dict(item))
        seen: set[str] = set()
        return [
            item for item in artifacts
            if isinstance(item, dict)
            and (artifact_id := str(item.get("artifact_id") or "").strip())
            and not (artifact_id in seen or seen.add(artifact_id))
        ]
