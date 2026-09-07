"""Thin execution loop for the strict iterative runtime."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator, Dict, Optional, Protocol
from uuid import UUID

from app.runtime.events import RuntimeEvent, RuntimeEventType
from app.runtime.entity_ids import (
    agent_execution_id, planner_iteration_id, runtime_attempt_id, step_id,
)
from app.runtime.orchestrator_contracts import (
    AgentExecutionResult, IterationProposal, PlanRequest, PlannerContext,
    SchedulerActionKind, TaskAttemptFailure, TaskConfirmationRequired, TaskExecutionError, TaskRequest,
)
from app.runtime.plan_store import PlanValidationError
from app.runtime.synthesis_context import SynthesisContextBuilder, SynthesisContextError
from app.runtime.task_result_reducer import TaskAttemptResultReducer


class Planner(Protocol):
    async def plan(self, *, request: PlanRequest, **kwargs: Any) -> IterationProposal: ...


class TaskExecutor(Protocol):
    async def execute_attempt(self, *, request: TaskRequest, **kwargs: Any) -> AgentExecutionResult: ...


class OrchestratorEvent(dict):
    def to_runtime_event(self) -> RuntimeEvent:
        if self.get("type") == "_runtime_event" and isinstance(self.get("runtime_event"), RuntimeEvent):
            return self["runtime_event"]
        event_name = str(self.get("type") or "")
        plan_id = str(self.get("plan_id") or "")
        task_id = str(self.get("task_id") or "")
        if event_name in {"iteration_created", "planner_checkpoint_completed"}:
            iteration_id = self.get("applied_iteration_id") or self.get("iteration_id")
            return RuntimeEvent.plan_lifecycle(
                RuntimeEventType.PLAN_ITERATION_APPLIED,
                plan_id=plan_id,
                parent_entity_type="planner_iteration",
                parent_entity_id=iteration_id,
                trigger=self.get("trigger"),
                iteration_id=iteration_id,
                terminal=self.get("terminal"),
                proposal=self.get("proposal"),
            )
        if event_name == "plan_terminal":
            status = str(self.get("status") or "")
            event_type = {
                "completed": RuntimeEventType.PLAN_COMPLETED,
                "failed": RuntimeEventType.PLAN_FAILED,
                "waiting_input": RuntimeEventType.PLAN_WAITING_INPUT,
            }.get(status)
            if event_type is not None:
                return RuntimeEvent.plan_lifecycle(
                    event_type,
                    plan_id=plan_id,
                    status=status,
                    error_code=(self.get("error_code") or "runtime_execution_failed") if status == "failed" else None,
                )
        if event_name in {"task_started", "task_completed"}:
            outcome = str(self.get("outcome") or "")
            lifecycle_type = {
                "needs_dependency": RuntimeEventType.TASK_NEEDS_DEPENDENCY,
                "unfulfillable": RuntimeEventType.TASK_UNFULFILLABLE,
            }.get(outcome, RuntimeEventType.TASK_STARTED if event_name == "task_started" else RuntimeEventType.TASK_COMPLETED)
            return RuntimeEvent.task_lifecycle(
                lifecycle_type,
                plan_id=plan_id,
                task_id=task_id,
                outcome=self.get("outcome"),
            )
        if event_name in {"task_blocked", "task_paused", "task_resumed", "task_failed"}:
            lifecycle_type = {
                "task_blocked": RuntimeEventType.TASK_BLOCKED,
                "task_paused": RuntimeEventType.TASK_PAUSED,
                "task_resumed": RuntimeEventType.TASK_RESUMED,
                "task_failed": RuntimeEventType.TASK_FAILED,
            }[event_name]
            return RuntimeEvent.task_lifecycle(
                lifecycle_type, plan_id=plan_id, task_id=task_id,
                attempt=self.get("attempt"),
            )
        if event_name == "task_attempt_failed":
            error = self.get("error") if isinstance(self.get("error"), dict) else {}
            attempt = int(self.get("attempt") or 0)
            return RuntimeEvent.attempt_lifecycle(
                RuntimeEventType.ATTEMPT_FAILED,
                task_id=task_id, attempt_id=runtime_attempt_id(task_id, attempt),
                plan_id=plan_id, attempt=attempt, error_code=error.get("code"), retryable=bool(error.get("retryable")),
            )
        if event_name in {"task_attempt_started", "task_attempt_succeeded"}:
            attempt = int(self.get("attempt") or 0)
            return RuntimeEvent.attempt_lifecycle(
                RuntimeEventType.ATTEMPT_STARTED if event_name == "task_attempt_started" else RuntimeEventType.ATTEMPT_SUCCEEDED,
                task_id=task_id, attempt_id=runtime_attempt_id(task_id, attempt),
                plan_id=plan_id, attempt=attempt,
            )
        if event_name == "task_retry_scheduled":
            attempt = int(self.get("attempt") or 0)
            return RuntimeEvent.attempt_lifecycle(
                RuntimeEventType.ATTEMPT_RETRY_SCHEDULED,
                task_id=task_id, attempt_id=runtime_attempt_id(task_id, attempt),
                plan_id=plan_id, attempt=attempt,
            )
        if event_name == "confirmation_required":
            payload = dict(self)
            payload.pop("type", None)
            payload.update({"entity_type": "task", "entity_id": task_id, "parent_entity_type": "plan", "parent_entity_id": plan_id})
            return RuntimeEvent(RuntimeEventType.CONFIRMATION_REQUIRED, payload)
        try:
            event_type = RuntimeEventType(event_name)
        except ValueError:
            return RuntimeEvent.status("orchestrator", **dict(self))
        payload = dict(self)
        payload.pop("type", None)
        return RuntimeEvent(event_type, payload)


class GraphOrchestrator:
    """Executes typed store decisions; it never derives task state from text."""

    def __init__(self, *, store: Any, planner: Planner, executor: TaskExecutor,
                 synthesizer: Optional[Any] = None, max_attempts: int = 3,
                 retry_delay_seconds: int = 60, event_sink: Optional[Any] = None,
                 logging_level: str = "brief") -> None:
        self.store = store
        self.planner = planner
        self.executor = executor
        self.synthesizer = synthesizer
        self.max_attempts = max(1, max_attempts)
        self.retry_delay_seconds = max(1, retry_delay_seconds)
        self.event_sink = event_sink
        self.logging_level = logging_level
        self.reducer = TaskAttemptResultReducer()

    async def _planner_request(self, *, plan_id: UUID, goal: str, trigger: str,
                               available_agents: list[dict[str, Any]], available_artifacts: list[dict[str, Any]],
                               planner_kwargs: Dict[str, Any]) -> PlanRequest:
        snapshot = await self.store.snapshot(plan_id)
        ledger = self._planner_ledger(snapshot)
        ledger_size = len(json.dumps(ledger, ensure_ascii=False, default=str))
        max_ledger_chars = int(planner_kwargs.get("planner_ledger_max_chars") or 160_000)
        if ledger_size > max_ledger_chars:
            raise PlanValidationError(
                f"planner execution ledger exceeds hard limit ({ledger_size}>{max_ledger_chars})"
            )
        return PlanRequest(
            context=PlannerContext(goal=goal, trigger=trigger, execution_ledger=ledger,
                                   available_agents=available_agents, available_artifacts=available_artifacts,
                                   memory_context=list(planner_kwargs.get("planner_memory_context") or [])),
            plan_id=plan_id,
            run_id=UUID(str(snapshot["root_run_id"])),
        )

    @staticmethod
    def _planner_ledger(snapshot: Dict[str, Any]) -> Dict[str, Any]:
        """A complete structural index. No status or failure is silently dropped."""
        tasks = []
        for task_id, task in sorted(dict(snapshot.get("tasks") or {}).items(), key=lambda item: (item[1].get("iteration_id", ""), item[1].get("planned_order", 0), item[0])):
            result = task.get("result") if isinstance(task.get("result"), dict) else {}
            verified = result.get("verified") if isinstance(result.get("verified"), dict) else {}
            # Agent transcripts and internal telemetry are not planner context.
            # The planner receives only runtime-owned evidence metadata.
            evidence = {key: verified.get(key) for key in ("receipts", "evidence", "artifacts", "sources", "fresh_retrieval") if key in verified}
            tasks.append({"task_id": task_id, "iteration_id": task.get("iteration_id"), "intent": task.get("intent"),
                          "executor": task.get("executor"), "instructions": task.get("instructions"), "inputs": task.get("inputs", {}),
                          "expected_outputs": task.get("expected_outputs", []), "freshness_policy": task.get("freshness_policy"),
                          "status": task.get("status"), "depends_on": task.get("depends_on", []), "attempts": task.get("attempts", 0),
                          "result": {"description": result.get("description"), "reason_code": result.get("reason_code"), "outputs": result.get("outputs", {}), "limitation": result.get("limitation"), "evidence": evidence}})
        return {"plan_status": snapshot.get("status"), "iterations": snapshot.get("iterations", []), "tasks": tasks,
                "needs": snapshot.get("needs", []), "bindings": snapshot.get("bindings", []),
                "resolutions": snapshot.get("resolutions", [])}

    @staticmethod
    def _latest_resolutions(resolutions: list[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """One task has one current disposition: the latest iteration wins."""
        latest: Dict[str, Dict[str, Any]] = {}
        for item in resolutions:
            task_id = str(item.get("task_id") or "")
            if task_id:
                latest[task_id] = item
        return latest

    @staticmethod
    def _compile(proposal: IterationProposal, available_agents: list[dict[str, Any]], ledger: Dict[str, Any]) -> IterationProposal:
        available = {str(item.get("slug") or "") for item in available_agents if isinstance(item, dict)}
        unknown = sorted({task.executor for task in proposal.tasks if task.executor not in available})
        if unknown:
            raise PlanValidationError(f"planner selected unavailable executors: {unknown}")
        prior_tasks = {str(item.get("task_id")): item for item in ledger.get("tasks", [])}
        need_items = {(str(item.get("task_id")), str(item.get("ref"))): item for item in ledger.get("needs", [])}
        proposed = {task.task_id: task for task in proposal.tasks}
        for resolution in proposal.resolutions:
            prior = prior_tasks.get(resolution.task_id)
            if prior is None or prior.get("status") == "completed":
                raise PlanValidationError(f"resolution must target a prior incomplete task: {resolution.task_id}")
            outputs = set((prior.get("result") or {}).get("outputs") or {})
            if any(key not in outputs for key in resolution.output_keys):
                raise PlanValidationError(f"resolution accepts an absent output on {resolution.task_id}")
        resolution_map = {item.task_id: item for item in proposal.resolutions}
        def continuation_completed(item: Dict[str, Any]) -> bool:
            replacements = item.get("replacement_task_ids") or []
            return bool(replacements) and all(
                prior_tasks.get(str(task_id), {}).get("status") == "completed"
                for task_id in replacements
            )

        latest_resolutions = GraphOrchestrator._latest_resolutions(list(ledger.get("resolutions", [])))
        previously_resolved = {
            task_id for task_id, item in latest_resolutions.items()
            if item.get("action") in {"accept_partial", "exclude_from_scope", "report_unresolved"}
            or (item.get("action") == "continue_with_tasks" and continuation_completed(item))
        }
        unresolved = {
            task_id for task_id, task in prior_tasks.items()
            if task.get("status") != "completed" and task_id not in previously_resolved
        }
        proposed_resolutions = {item.task_id for item in proposal.resolutions}
        if missing := unresolved - proposed_resolutions:
            raise PlanValidationError(f"iteration must resolve prior incomplete tasks: {sorted(missing)}")
        bound_inputs: set[tuple[str, str]] = set()
        for binding in proposal.bindings:
            need = need_items.get((binding.need_task_id, binding.need_ref))
            if need is None:
                raise PlanValidationError("binding targets an unknown discovered need")
            producer, consumer = proposed.get(binding.producer_task_id), proposed.get(binding.consumer_task_id)
            if producer is None or consumer is None:
                raise PlanValidationError("binding producer and consumer must belong to the new iteration")
            if binding.producer_task_id not in consumer.depends_on:
                raise PlanValidationError("binding consumer must depend on producer")
            output_spec = next((item for item in producer.expected_outputs if item.key == binding.output_key), None)
            if output_spec is None or not output_spec.required:
                raise PlanValidationError("binding output is not declared by producer")
            need_schema = need.get("schema") if isinstance(need.get("schema"), dict) else {}
            if need_schema and output_spec.json_schema != need_schema:
                raise PlanValidationError("binding producer output schema must equal the discovered need schema")
            resolution = resolution_map.get(binding.need_task_id)
            if resolution is None or resolution.action.value != "continue_with_tasks":
                raise PlanValidationError("binding need task must be continued with replacement tasks")
            if binding.consumer_task_id not in resolution.replacement_task_ids:
                raise PlanValidationError("binding consumer must be a replacement for the need task")
            target = (binding.consumer_task_id, binding.consumer_input_key)
            if target in bound_inputs or binding.consumer_input_key in consumer.inputs:
                raise PlanValidationError("binding writes a duplicate consumer input")
            bound_inputs.add(target)
        return proposal

    async def _invoke_planner(self, *, plan_id: UUID, goal: str, trigger: str,
                              available_agents: list[dict[str, Any]], available_artifacts: list[dict[str, Any]],
                              planner_kwargs: Dict[str, Any]) -> IterationProposal:
        request = await self._planner_request(plan_id=plan_id, goal=goal, trigger=trigger,
                                              available_agents=available_agents, available_artifacts=available_artifacts,
                                              planner_kwargs=planner_kwargs)
        iteration_number = len(request.context.execution_ledger.get("iterations", [])) + 1
        iteration_entity_id = UUID(planner_iteration_id(str(request.run_id), iteration_number))
        planner_kwargs.setdefault("event_sink", self.event_sink)
        proposal = await self.planner.plan(
            request=request,
            planner_iteration_trace_id=str(iteration_entity_id),
            **planner_kwargs,
        )
        proposal = self._compile(proposal, available_agents, request.context.execution_ledger)
        if proposal.synthesis_brief is not None and proposal.synthesis_brief.user_question != goal:
            raise PlanValidationError("synthesis brief user_question must equal the immutable plan goal")
        await self.store.apply_iteration(plan_id, proposal, iteration_id=iteration_entity_id)
        return proposal

    async def run(self, *, plan_id: UUID, goal: str, available_agents: list[dict[str, Any]],
                  available_artifacts: Optional[list[dict[str, Any]]] = None, max_steps: int = 80,
                  max_task_executions: Optional[int] = None,
                  planner_kwargs: Optional[Dict[str, Any]] = None) -> AsyncIterator[OrchestratorEvent]:
        planner_kwargs = dict(planner_kwargs or {})
        artifacts = list(available_artifacts or [])
        async def fail(code: str, exc: BaseException | str) -> None:
            await self.store.mark_failed(plan_id, code, str(exc))
        await self.store.recover_stale_claims(
            plan_id,
            stale_before=datetime.now(timezone.utc) - timedelta(minutes=5),
        )
        snapshot = await self.store.snapshot(plan_id)
        if not snapshot.get("iterations"):
            planner_parent = str(planner_kwargs.get("planner_budget_entity_id") or snapshot["root_run_id"])
            trace_iteration_id = planner_iteration_id(str(snapshot["root_run_id"]), 1)
            yield OrchestratorEvent(type="_runtime_event", runtime_event=RuntimeEvent.planner_iteration_start(
                iteration_id=trace_iteration_id, orchestrator_id=planner_parent, iteration=1,
            ))
            try:
                proposal = await self._invoke_planner(plan_id=plan_id, goal=goal, trigger="initial", available_agents=available_agents,
                                                      available_artifacts=artifacts, planner_kwargs=planner_kwargs)
                yield OrchestratorEvent(type="iteration_created", plan_id=str(plan_id), trigger="initial", terminal=proposal.terminal.value,
                                        iteration_id=(await self.store.snapshot(plan_id))["iterations"][-1]["id"], proposal=proposal.model_dump(mode="json"))
                yield OrchestratorEvent(type="_runtime_event", runtime_event=RuntimeEvent.planner_iteration_end(
                    iteration_id=trace_iteration_id, orchestrator_id=planner_parent, iteration=1, status="completed",
                ))
            except Exception as exc:
                yield OrchestratorEvent(type="_runtime_event", runtime_event=RuntimeEvent.planner_iteration_end(
                    iteration_id=trace_iteration_id, orchestrator_id=planner_parent, iteration=1, status="failed",
                ))
                await fail("initial_planning_failed", exc)
                yield OrchestratorEvent(type="plan_terminal", plan_id=str(plan_id), status="failed", error_code="initial_planning_failed")
                return
        # ``max_steps`` is the iteration budget. Task count is deliberately
        # independent: a large valid iteration must not be mistaken for a loop.
        for _ in range(max(80, max_steps * 100)):
            before_decision = await self.store.snapshot(plan_id)
            decision = await self.store.next_decision(plan_id)
            after_decision = await self.store.snapshot(plan_id)
            for changed_task_id, changed_task in dict(after_decision.get("tasks") or {}).items():
                previous = dict(before_decision.get("tasks") or {}).get(changed_task_id, {})
                if previous.get("status") != "blocked" and changed_task.get("status") == "blocked":
                    yield OrchestratorEvent(type="task_blocked", plan_id=str(plan_id), task_id=changed_task_id)
            if decision.kind == SchedulerActionKind.TERMINAL:
                yield OrchestratorEvent(type="plan_terminal", plan_id=str(plan_id), status=decision.reason)
                return
            if decision.kind == SchedulerActionKind.WAIT_INPUT:
                yield OrchestratorEvent(type="plan_terminal", plan_id=str(plan_id), status="waiting_input")
                return
            if decision.kind == SchedulerActionKind.WAIT_RETRY:
                if decision.retry_at:
                    retry_at = datetime.fromisoformat(decision.retry_at)
                    delay = max(0, (retry_at - datetime.now(timezone.utc)).total_seconds())
                    if delay:
                        await asyncio.sleep(min(delay, 30))
                    continue
                yield OrchestratorEvent(type="plan_terminal", plan_id=str(plan_id), status="waiting_checkpoint")
                return
            if decision.kind == SchedulerActionKind.INVOKE_PLANNER:
                current_snapshot = await self.store.snapshot(plan_id)
                iteration_count = len(current_snapshot.get("iterations", []))
                if iteration_count >= max_steps:
                    await fail("iteration_limit_exceeded", "Planner iteration limit exceeded")
                    yield OrchestratorEvent(
                        type="plan_terminal", plan_id=str(plan_id), status="failed",
                        error_code="iteration_limit_exceeded",
                    )
                    return
                await self.store.claim_checkpoint(plan_id, decision.kind)
                next_iteration_number = len(current_snapshot.get("iterations", [])) + 1
                planner_parent = str(planner_kwargs.get("planner_budget_entity_id") or current_snapshot["root_run_id"])
                trace_iteration_id = planner_iteration_id(str(current_snapshot["root_run_id"]), next_iteration_number)
                yield OrchestratorEvent(type="_runtime_event", runtime_event=RuntimeEvent.planner_iteration_start(
                    iteration_id=trace_iteration_id, orchestrator_id=planner_parent, iteration=next_iteration_number,
                ))
                try:
                    proposal = await self._invoke_planner(plan_id=plan_id, goal=goal, trigger=decision.reason or "planner_checkpoint",
                                                          available_agents=available_agents, available_artifacts=artifacts, planner_kwargs=planner_kwargs)
                    yield OrchestratorEvent(type="planner_checkpoint_completed", plan_id=str(plan_id), iteration_id=decision.iteration_id,
                                            trigger=decision.reason, terminal=proposal.terminal.value,
                                            applied_iteration_id=(await self.store.snapshot(plan_id))["iterations"][-1]["id"], proposal=proposal.model_dump(mode="json"))
                    yield OrchestratorEvent(type="_runtime_event", runtime_event=RuntimeEvent.planner_iteration_end(
                        iteration_id=trace_iteration_id, orchestrator_id=planner_parent, iteration=next_iteration_number, status="completed",
                    ))
                    continue
                except Exception as exc:
                    yield OrchestratorEvent(type="_runtime_event", runtime_event=RuntimeEvent.planner_iteration_end(
                        iteration_id=trace_iteration_id, orchestrator_id=planner_parent, iteration=next_iteration_number, status="failed",
                    ))
                    await fail("planner_checkpoint_failed", exc)
                    yield OrchestratorEvent(type="plan_terminal", plan_id=str(plan_id), status="failed", error_code="planner_checkpoint_failed")
                    return
            if decision.kind == SchedulerActionKind.INVOKE_SYNTHESIS:
                if self.synthesizer is None:
                    await fail("synthesizer_missing", "terminal synthesis executor is not configured")
                    yield OrchestratorEvent(type="plan_terminal", plan_id=str(plan_id), status="failed", error_code="synthesizer_missing")
                    return
                iteration = await self.store.claim_checkpoint(plan_id, decision.kind)
                try:
                    context_limit = int(planner_kwargs.get("synthesis_context_max_chars") or 120_000)
                    runtime_state = planner_kwargs.get("runtime_state")
                    context = SynthesisContextBuilder(max_chars=context_limit).build(
                        plan=await self.store.snapshot(plan_id),
                        iteration_id=str(iteration.id if hasattr(iteration, "id") else iteration["id"]),
                        deleted_artifact_ids=list(getattr(runtime_state, "deleted_artifact_ids", []) or []),
                    )
                except (TypeError, ValueError, SynthesisContextError) as exc:
                    await fail("synthesis_context_invalid", exc)
                    yield OrchestratorEvent(type="plan_terminal", plan_id=str(plan_id), status="failed", error_code="synthesis_context_invalid")
                    return
                snapshot = await self.store.snapshot(plan_id)
                try:
                    async for event in self.synthesizer.stream(runtime_state=runtime_state, run_id=UUID(str(snapshot["root_run_id"])), synthesis_context=context,
                                                               model=planner_kwargs.get("model"), platform_config=planner_kwargs.get("platform_config"),
                                                               sandbox_overrides=planner_kwargs.get("sandbox_overrides"), logging_level=self.logging_level,
                                                               budget_registry=planner_kwargs.get("budget_registry"), budget_resolver=planner_kwargs.get("budget_resolver")):
                        yield OrchestratorEvent(type="_runtime_event", runtime_event=event)
                except Exception as exc:
                    await fail("synthesis_failed", exc)
                    yield OrchestratorEvent(type="plan_terminal", plan_id=str(plan_id), status="failed", error_code="synthesis_failed")
                    return
                if not getattr(runtime_state, "final_answer", None):
                    await fail("synthesis_failed", "synthesis did not produce a final answer")
                    yield OrchestratorEvent(type="plan_terminal", plan_id=str(plan_id), status="failed", error_code="synthesis_failed")
                    return
                await self.store.complete_synthesis(plan_id)
                yield OrchestratorEvent(type="plan_terminal", plan_id=str(plan_id), status="completed")
                return
            if decision.kind == SchedulerActionKind.EXECUTE_TASK:
                if max_task_executions is not None:
                    current = await self.store.snapshot(plan_id)
                    attempts_used = sum(
                        int(task.get("attempts") or 0)
                        for task in dict(current.get("tasks") or {}).values()
                    )
                    if attempts_used >= max_task_executions:
                        await fail("task_execution_limit_exceeded", "Task execution limit exceeded")
                        yield OrchestratorEvent(type="plan_terminal", plan_id=str(plan_id), status="failed", error_code="task_execution_limit_exceeded")
                        return
                task = await self.store.claim_task(plan_id, decision.task_id)
                task_id = task.task_id if hasattr(task, "task_id") else task["task_id"]
                attempt = task.attempts if hasattr(task, "attempts") else task["attempts"]
                iteration_id = str(task.iteration_id if hasattr(task, "iteration_id") else task["iteration_id"])
                planned_order = int(task.planned_order if hasattr(task, "planned_order") else task.get("planned_order", 0))
                execution_id = agent_execution_id(iteration_id, task_id, attempt)
                current_step_id = step_id(iteration_id, planned_order + 1, f"{task_id}:{attempt}")
                await self.store.link_attempt_execution(plan_id, task_id, UUID(execution_id))
                yield OrchestratorEvent(type="_runtime_event", runtime_event=RuntimeEvent.step_start(
                    step_id=current_step_id, iteration_id=iteration_id, kind="agent_task",
                    title=(task.intent if hasattr(task, "intent") else task.get("intent")),
                    objective=(task.instructions if hasattr(task, "instructions") else task.get("instructions")),
                ))
                yield OrchestratorEvent(type="task_started", plan_id=str(plan_id), task_id=task_id, attempt=attempt)
                yield OrchestratorEvent(type="task_attempt_started", plan_id=str(plan_id), task_id=task_id, attempt=attempt)
                task_executor = task.executor if hasattr(task, "executor") else task.get("executor")
                task_intent = task.intent if hasattr(task, "intent") else task.get("intent")
                yield OrchestratorEvent(type="_runtime_event", runtime_event=RuntimeEvent.agent_start(
                    agent_execution_id=execution_id,
                    parent_entity_type="step",
                    parent_entity_id=current_step_id,
                    agent_slug=str(task_executor or "agent"),
                    task_title=str(task_intent or task_id),
                    task_id=task_id,
                    attempt=attempt,
                ))
                try:
                    request = TaskRequest.model_validate(await self.store.task_request(plan_id, task_id))
                    request = request.model_copy(update={"memory_context": list(planner_kwargs.get("planner_memory_context") or [])})
                    execution = await self.executor.execute_attempt(
                        request=request,
                        lifecycle_agent_execution_id=execution_id,
                        runtime_log_parent={"entity_type": "step", "entity_id": current_step_id},
                        **planner_kwargs,
                    )
                    if not isinstance(execution, AgentExecutionResult):
                        raise TypeError("executor must return AgentExecutionResult")
                    result = self.reducer.reduce(request=request, execution=execution)
                    await self.store.finish_attempt(plan_id, task_id, execution=execution, result=result)
                    runtime_state = planner_kwargs.get("runtime_state")
                    if runtime_state is not None and hasattr(runtime_state, "add_task_result"):
                        runtime_state.add_task_result({"task_id": task_id, **result.model_dump(mode="json")})
                    yield OrchestratorEvent(type="task_attempt_succeeded", plan_id=str(plan_id), task_id=task_id, attempt=attempt)
                    yield OrchestratorEvent(type="task_completed", plan_id=str(plan_id), task_id=task_id, outcome=result.outcome.value)
                    yield OrchestratorEvent(type="_runtime_event", runtime_event=RuntimeEvent.agent_end(
                        agent_execution_id=execution_id,
                        parent_entity_type="step",
                        parent_entity_id=current_step_id,
                        agent_slug=str(task_executor or "agent"),
                        status="completed",
                        outcome=result.outcome.value,
                        task_id=task_id,
                        attempt=attempt,
                    ))
                    yield OrchestratorEvent(type="_runtime_event", runtime_event=RuntimeEvent.step_end(
                        step_id=current_step_id, iteration_id=iteration_id, status="completed",
                        outcome=result.outcome.value, summary=result.description,
                    ))
                except TaskConfirmationRequired as exc:
                    await self.store.pause_confirmation(plan_id, task_id, exc.payload)
                    yield OrchestratorEvent(type="task_paused", plan_id=str(plan_id), task_id=task_id, attempt=attempt)
                    yield OrchestratorEvent(type="_runtime_event", runtime_event=RuntimeEvent.agent_end(
                        agent_execution_id=execution_id,
                        parent_entity_type="step",
                        parent_entity_id=current_step_id,
                        agent_slug=str(task_executor or "agent"),
                        status="paused",
                        outcome="confirmation_required",
                        task_id=task_id,
                        attempt=attempt,
                    ))
                    yield OrchestratorEvent(type="_runtime_event", runtime_event=RuntimeEvent.step_end(
                        step_id=current_step_id, iteration_id=iteration_id, status="paused",
                        outcome="confirmation_required", summary="Task requires confirmation",
                    ))
                    yield OrchestratorEvent(type="confirmation_required", plan_id=str(plan_id), task_id=task_id, **exc.payload)
                    yield OrchestratorEvent(type="plan_terminal", plan_id=str(plan_id), status="waiting_input")
                    return
                except TaskExecutionError as exc:
                    failure = TaskAttemptFailure(code=exc.code, message=str(exc), retryable=exc.retryable, details=exc.details)
                    retry_after_ms = exc.details.get("retry_after_ms") if isinstance(exc.details, dict) else None
                    retry_delay = max(0, int(retry_after_ms) / 1000) if isinstance(retry_after_ms, int) else self.retry_delay_seconds
                    failed_task = await self.store.finish_failure(plan_id, task_id, failure, max_attempts=self.max_attempts, retry_at=datetime.now(timezone.utc) + timedelta(seconds=retry_delay))
                    yield OrchestratorEvent(type="task_attempt_failed", plan_id=str(plan_id), task_id=task_id, attempt=(failed_task.attempts if hasattr(failed_task, "attempts") else failed_task.get("attempts")), error=failure.model_dump(mode="json"))
                    failed_status = failed_task.status if hasattr(failed_task, "status") else failed_task.get("status")
                    yield OrchestratorEvent(type=("task_retry_scheduled" if failed_status == "waiting_retry" else "task_failed"), plan_id=str(plan_id), task_id=task_id, attempt=attempt)
                    yield OrchestratorEvent(type="_runtime_event", runtime_event=RuntimeEvent.agent_end(
                        agent_execution_id=execution_id,
                        parent_entity_type="step",
                        parent_entity_id=current_step_id,
                        agent_slug=str(task_executor or "agent"),
                        status="failed",
                        outcome="retry_scheduled" if failed_status == "waiting_retry" else "failed",
                        task_id=task_id,
                        attempt=attempt,
                    ))
                    yield OrchestratorEvent(type="_runtime_event", runtime_event=RuntimeEvent.step_end(step_id=current_step_id, iteration_id=iteration_id, status=failed_status, outcome="failed", summary="Task execution failed"))
                except Exception as exc:
                    failure = TaskAttemptFailure(code=type(exc).__name__, message=str(exc) or "task execution failed", retryable=False)
                    failed_task = await self.store.finish_failure(plan_id, task_id, failure, max_attempts=self.max_attempts)
                    yield OrchestratorEvent(type="task_attempt_failed", plan_id=str(plan_id), task_id=task_id, attempt=(failed_task.attempts if hasattr(failed_task, "attempts") else failed_task.get("attempts")), error=failure.model_dump(mode="json"))
                    yield OrchestratorEvent(type="task_failed", plan_id=str(plan_id), task_id=task_id, attempt=attempt)
                    yield OrchestratorEvent(type="_runtime_event", runtime_event=RuntimeEvent.agent_end(
                        agent_execution_id=execution_id,
                        parent_entity_type="step",
                        parent_entity_id=current_step_id,
                        agent_slug=str(task_executor or "agent"),
                        status="failed",
                        outcome="failed",
                        task_id=task_id,
                        attempt=attempt,
                    ))
                    yield OrchestratorEvent(type="_runtime_event", runtime_event=RuntimeEvent.step_end(step_id=current_step_id, iteration_id=iteration_id, status="failed", outcome="failed", summary="Task execution failed"))
                continue
        await fail("scheduler_action_limit_exceeded", "iteration did not reach a terminal decision")
        yield OrchestratorEvent(type="plan_terminal", plan_id=str(plan_id), status="failed", error_code="scheduler_action_limit_exceeded")
