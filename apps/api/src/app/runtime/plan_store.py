"""Persistence and deterministic scheduling for immutable runtime iterations."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.runtime_plan import (
    RuntimeNeedBinding, RuntimePause, RuntimePlan, RuntimePlanIteration,
    RuntimePlanTask, RuntimeTaskAttempt, RuntimeToolResult, RuntimeTaskDependency, RuntimeTaskNeed,
    RuntimeTaskResolution,
)
from app.runtime.orchestrator_contracts import (
    TaskExecutionReceipt, AttemptStatus, IterationProposal, IterationStatus,
    PlanStatus, ResolutionAction, SchedulerActionKind, SchedulerDecision,
    TERMINAL_TASK_STATUSES, TaskAttemptFailure, TaskOutcome, TaskResult, TaskStatus,
    TerminalKind,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class PlanValidationError(ValueError):
    pass


class TaskNotFoundError(KeyError):
    pass


def _safe_failure_limitation(code: str) -> Dict[str, Any]:
    """Keep provider/exception details in the attempt journal, never synthesis."""
    return {
        "code": str(code or "task_execution_failed"),
        "message": "The task could not be completed due to an execution problem.",
        "action": "retry_later",
    }


def _binding_value(value: Any, schema: Optional[Dict[str, Any]] = None) -> Any:
    """Validate a concrete bound value against the consumer's discovered need."""
    if schema:
        try:
            import jsonschema
            jsonschema.Draft202012Validator(schema).validate(value)
        except Exception as exc:
            raise PlanValidationError(f"bound output does not satisfy consumer need schema: {exc}") from exc
    return value


def _required_outputs_fulfilled(expected_outputs: list[Dict[str, Any]], result: TaskResult) -> list[str]:
    """Use reducer-owned output states instead of inferring from JSON values."""
    states = result.output_states or {}
    return [
        str(item["key"])
        for item in expected_outputs
        if item.get("required", True)
        and str((states.get(str(item["key"])) or {}).get("status") or "") != "fulfilled"
    ]


def validate_iteration(proposal: IterationProposal) -> None:
    """Validate graph-local invariants before it reaches either store."""
    tasks = {item.task_id: item for item in proposal.tasks}
    for task in proposal.tasks:
        if any(dep not in tasks for dep in task.depends_on):
            raise PlanValidationError(f"task {task.task_id} depends outside its iteration")
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(task_id: str) -> None:
        if task_id in visiting:
            raise PlanValidationError("iteration task graph contains a cycle")
        if task_id in visited:
            return
        visiting.add(task_id)
        for dependency in tasks[task_id].depends_on:
            visit(dependency)
        visiting.remove(task_id)
        visited.add(task_id)

    for task_id in tasks:
        visit(task_id)


def _is_terminal(status: str) -> bool:
    return status in {item.value for item in TERMINAL_TASK_STATUSES}


def _is_failure(status: str) -> bool:
    return status != TaskStatus.COMPLETED.value and _is_terminal(status)


def _block_dependents(tasks: Dict[str, Dict[str, Any]]) -> list[str]:
    blocked: list[str] = []
    changed = True
    while changed:
        changed = False
        for task_id, task in tasks.items():
            if task["status"] != TaskStatus.PENDING.value:
                continue
            failed = [dep for dep in task["depends_on"] if _is_failure(tasks[dep]["status"])]
            if failed:
                task["status"] = TaskStatus.BLOCKED.value
                task["result"] = {
                    "outcome": TaskOutcome.UNFULFILLABLE.value,
                    "description": "Blocked by an unsuccessful dependency",
                    "reason_code": "dependency_failed",
                    "blocked_by": failed,
                    "outputs": {},
                }
                blocked.append(task_id)
                changed = True
    return blocked


def _ready_tasks(tasks: Dict[str, Dict[str, Any]]) -> list[Dict[str, Any]]:
    return sorted(
        (
            task for task in tasks.values()
            if task["status"] == TaskStatus.PENDING.value
            and all(tasks[dep]["status"] == TaskStatus.COMPLETED.value for dep in task["depends_on"])
        ),
        key=lambda item: (item["planned_order"], item["task_id"]),
    )


class _MemoryStateMachine:
    """Pure lifecycle core used by the in-memory store and SQL adapter."""

    @staticmethod
    def next_decision(plan: Dict[str, Any], *, now: datetime) -> SchedulerDecision:
        if plan["status"] != PlanStatus.ACTIVE.value:
            return SchedulerDecision(kind=SchedulerActionKind.TERMINAL, reason=plan["status"])
        active = [item for item in plan["iterations"] if item["status"] == IterationStatus.ACTIVE.value]
        if len(active) != 1:
            raise PlanValidationError("active plan must have exactly one active iteration")
        iteration = active[0]
        tasks = {task_id: task for task_id, task in plan["tasks"].items() if task["iteration_id"] == iteration["id"]}
        for task in tasks.values():
            if task["status"] == TaskStatus.WAITING_RETRY.value:
                if task["next_retry_at"] and datetime.fromisoformat(task["next_retry_at"]) > now:
                    continue
                task["status"] = TaskStatus.PENDING.value
                task["next_retry_at"] = None
        _block_dependents(tasks)
        waiting = [task for task in tasks.values() if task["status"] == TaskStatus.WAITING_CONFIRMATION.value]
        if waiting:
            return SchedulerDecision(kind=SchedulerActionKind.WAIT_INPUT, iteration_id=iteration["id"])
        ready = _ready_tasks(tasks)
        if ready:
            return SchedulerDecision(kind=SchedulerActionKind.EXECUTE_TASK, task_id=ready[0]["task_id"], iteration_id=iteration["id"])
        retries = [task["next_retry_at"] for task in tasks.values() if task["status"] == TaskStatus.WAITING_RETRY.value and task["next_retry_at"]]
        if retries:
            return SchedulerDecision(kind=SchedulerActionKind.WAIT_RETRY, iteration_id=iteration["id"], retry_at=min(retries))
        if not all(_is_terminal(task["status"]) for task in tasks.values()):
            raise PlanValidationError("iteration has no schedulable task")
        if iteration["checkpoint_status"] != "idle":
            return SchedulerDecision(kind=SchedulerActionKind.WAIT_RETRY, iteration_id=iteration["id"], reason="checkpoint_claimed")
        failed = any(_is_failure(task["status"]) for task in tasks.values())
        kind = SchedulerActionKind.INVOKE_PLANNER if failed or iteration["terminal"] == TerminalKind.PLANNER.value else SchedulerActionKind.INVOKE_SYNTHESIS
        return SchedulerDecision(kind=kind, iteration_id=iteration["id"], reason="task_failure" if failed else "terminal")


class InMemoryPlanStore:
    """Test adapter for the exact iterative runtime contract."""

    def __init__(self) -> None:
        self.plans: Dict[str, Dict[str, Any]] = {}

    def create(self, *, goal: str, root_run_id: str, tenant_id: str, chat_id: Optional[str] = None) -> Dict[str, Any]:
        plan = {"id": str(uuid4()), "goal": goal, "root_run_id": root_run_id, "tenant_id": tenant_id, "contract_version": 2,
                "chat_id": chat_id, "status": PlanStatus.DRAFT.value, "last_failure": None,
                "iterations": [], "tasks": {}, "attempts": {}, "needs": [], "bindings": [], "resolutions": [], "pauses": []}
        self.plans[plan["id"]] = plan
        return plan

    def get(self, plan_id: str) -> Dict[str, Any]:
        try:
            return self.plans[plan_id]
        except KeyError as exc:
            raise KeyError(plan_id) from exc

    def snapshot(self, plan_id: str) -> Dict[str, Any]:
        return deepcopy(self.get(plan_id))

    def mark_failed(self, plan_id: str, code: str, message: str) -> None:
        plan = self.get(plan_id)
        plan["status"] = PlanStatus.FAILED.value
        plan["last_failure"] = {"code": code, "message": message}

    def apply_iteration(
        self, plan_id: str, proposal: IterationProposal, *, iteration_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        validate_iteration(proposal)
        plan = self.get(plan_id)
        existing_ids = set(plan["tasks"])
        proposed_ids = {task.task_id for task in proposal.tasks}
        if existing_ids & proposed_ids:
            raise PlanValidationError("task ids are immutable and cannot be reused")
        active = [item for item in plan["iterations"] if item["status"] == IterationStatus.ACTIVE.value]
        if active:
            if len(active) != 1 or active[0]["checkpoint_status"] != "planner_running":
                raise PlanValidationError("new iteration requires a claimed planner checkpoint")
            active[0]["status"] = IterationStatus.CLOSED.value
            active[0]["checkpoint_status"] = "completed"
            active[0]["checkpoint_claimed_at"] = None
            active[0]["closed_at"] = _now().isoformat()
        iteration = {"id": str(iteration_id or uuid4()), "sequence": len(plan["iterations"]) + 1,
                     "status": IterationStatus.ACTIVE.value, "terminal": proposal.terminal.value,
                     "synthesis_brief": proposal.synthesis_brief.model_dump(mode="json") if proposal.synthesis_brief else None,
                     "proposal": proposal.model_dump(mode="json"), "checkpoint_status": "idle", "checkpoint_claimed_at": None}
        plan["iterations"].append(iteration)
        for order, task in enumerate(proposal.tasks):
            plan["tasks"][task.task_id] = {**task.model_dump(mode="json"), "iteration_id": iteration["id"],
                                             "planned_order": order, "status": TaskStatus.PENDING.value,
                                             "result": None, "attempts": 0, "next_retry_at": None}
        plan["bindings"].extend(item.model_dump(mode="json") for item in proposal.bindings)
        plan["resolutions"].extend({**item.model_dump(mode="json"), "iteration_id": iteration["id"]} for item in proposal.resolutions)
        plan["status"] = PlanStatus.ACTIVE.value
        return plan

    def next_decision(self, plan_id: str, *, now: Optional[datetime] = None) -> SchedulerDecision:
        return _MemoryStateMachine.next_decision(self.get(plan_id), now=now or _now())

    def claim_task(self, plan_id: str, task_id: str) -> Dict[str, Any]:
        plan = self.get(plan_id)
        decision = self.next_decision(plan_id)
        if decision.kind != SchedulerActionKind.EXECUTE_TASK or decision.task_id != task_id:
            raise PlanValidationError("task is not the current scheduler decision")
        task = plan["tasks"][task_id]
        task["status"] = TaskStatus.RUNNING.value
        task["attempts"] += 1
        plan["attempts"].setdefault(task_id, []).append({"attempt_number": task["attempts"], "status": AttemptStatus.RUNNING.value, "started_at": _now().isoformat()})
        return deepcopy(task)

    def claim_checkpoint(self, plan_id: str, kind: SchedulerActionKind) -> Dict[str, Any]:
        if kind not in {SchedulerActionKind.INVOKE_PLANNER, SchedulerActionKind.INVOKE_SYNTHESIS}:
            raise PlanValidationError("invalid checkpoint kind")
        plan = self.get(plan_id)
        decision = self.next_decision(plan_id)
        if decision.kind != kind:
            raise PlanValidationError("checkpoint is not the current scheduler decision")
        iteration = next(item for item in plan["iterations"] if item["id"] == decision.iteration_id)
        iteration["checkpoint_status"] = "planner_running" if kind == SchedulerActionKind.INVOKE_PLANNER else "synthesis_running"
        iteration["checkpoint_claimed_at"] = _now().isoformat()
        return deepcopy(iteration)

    def finish_attempt(self, plan_id: str, task_id: str, *, execution: TaskExecutionReceipt, result: TaskResult) -> Dict[str, Any]:
        plan, task = self.get(plan_id), self.get(plan_id)["tasks"].get(task_id)
        if task is None:
            raise TaskNotFoundError(task_id)
        if task["status"] != TaskStatus.RUNNING.value:
            raise PlanValidationError("task is not running")
        if result.outcome == TaskOutcome.COMPLETED:
            missing = _required_outputs_fulfilled(task["expected_outputs"], result)
            if missing:
                raise PlanValidationError(f"task is missing required outputs: {missing}")
            task["status"] = TaskStatus.COMPLETED.value
        elif result.outcome == TaskOutcome.NEEDS_DEPENDENCY:
            task["status"] = TaskStatus.NEEDS_DEPENDENCY.value
            plan["needs"].extend({**need.model_dump(mode="json"), "task_id": task_id} for need in result.needs)
        else:
            task["status"] = TaskStatus.UNFULFILLABLE.value
        task["result"] = result.model_dump(mode="json")
        attempt = plan["attempts"][task_id][-1]
        attempt.update({"status": AttemptStatus.COMPLETED.value, "execution_result": execution.model_dump(mode="json"), "finished_at": _now().isoformat()})
        return deepcopy(task)

    def finish_failure(self, plan_id: str, task_id: str, failure: TaskAttemptFailure, *, max_attempts: int, retry_at: Optional[datetime] = None) -> Dict[str, Any]:
        plan, task = self.get(plan_id), self.get(plan_id)["tasks"].get(task_id)
        if task is None or task["status"] != TaskStatus.RUNNING.value:
            raise PlanValidationError("task is not running")
        attempt = plan["attempts"][task_id][-1]
        attempt.update({"status": AttemptStatus.TIMED_OUT.value if failure.timed_out else AttemptStatus.FAILED.value, "error": failure.model_dump(mode="json"), "finished_at": _now().isoformat()})
        if failure.retryable and task["attempts"] < max_attempts:
            task["status"] = TaskStatus.WAITING_RETRY.value
            task["next_retry_at"] = (retry_at or _now()).isoformat()
        else:
            limitation = _safe_failure_limitation(failure.code)
            task["status"] = TaskStatus.FAILED.value
            task["result"] = {"outcome": TaskOutcome.UNFULFILLABLE.value, "description": limitation["message"], "reason_code": failure.code, "outputs": {}, "limitation": limitation}
        return deepcopy(task)

    def task_request(self, plan_id: str, task_id: str) -> Dict[str, Any]:
        plan = self.get(plan_id)
        task = plan["tasks"].get(task_id)
        if task is None:
            raise TaskNotFoundError(task_id)
        inputs = deepcopy(task["inputs"])
        for binding in plan["bindings"]:
            if binding["consumer_task_id"] == task_id:
                source = plan["tasks"][binding["producer_task_id"]]["result"] or {}
                source_outputs = source.get("outputs") or {}
                if binding["output_key"] not in source_outputs:
                    raise PlanValidationError("ready bound task has no producer output")
                value = source_outputs[binding["output_key"]]
                need = next((item for item in plan["needs"] if item.get("task_id") == binding["need_task_id"] and item.get("ref") == binding["need_ref"]), {})
                inputs[binding["consumer_input_key"]] = _binding_value(value, need.get("schema") if isinstance(need, dict) else None)
        dependencies = {dep: plan["tasks"][dep]["result"] for dep in task["depends_on"]}
        return {"task_id": task_id, "executor": task["executor"], "intent": task["intent"], "instructions": task["instructions"],
                "inputs": inputs, "dependency_outputs": dependencies,
                "expected_outputs": task["expected_outputs"], "contract": task.get("contract", {}), "freshness_policy": task["freshness_policy"]}

    def pause_confirmation(self, plan_id: str, task_id: str, payload: Dict[str, Any]) -> None:
        plan = self.get(plan_id)
        task = plan["tasks"].get(task_id)
        fingerprint = str(payload.get("operation_fingerprint") or "").strip()
        if task is None or task["status"] != TaskStatus.RUNNING.value or not fingerprint:
            raise PlanValidationError("confirmation pause requires a running task and operation fingerprint")
        task["status"] = TaskStatus.WAITING_CONFIRMATION.value
        attempt = plan["attempts"].get(task_id, [])[-1]
        attempt.update({"status": AttemptStatus.CANCELLED.value, "error": {"code": "confirmation_required", "message": "Operation requires confirmation"}, "finished_at": _now().isoformat()})
        plan["pauses"].append({"task_id": task_id, "kind": "confirmation", "operation_fingerprint": fingerprint, "payload": deepcopy(payload), "status": "waiting"})
        plan["status"] = PlanStatus.WAITING_INPUT.value

    def resume_confirmation(self, plan_id: str, task_id: str, operation_fingerprint: str) -> None:
        plan = self.get(plan_id)
        pause = next((item for item in reversed(plan["pauses"]) if item["task_id"] == task_id and item["status"] == "waiting"), None)
        if pause is None or pause["operation_fingerprint"] != operation_fingerprint:
            raise PlanValidationError("confirmation does not match active pause")
        plan["tasks"][task_id]["status"] = TaskStatus.PENDING.value
        pause["status"] = "approved"
        plan["status"] = PlanStatus.ACTIVE.value

    def reject_confirmation(self, plan_id: str, task_id: str, operation_fingerprint: str) -> None:
        plan = self.get(plan_id)
        pause = next((item for item in reversed(plan["pauses"]) if item["task_id"] == task_id and item["status"] == "waiting"), None)
        if pause is None or pause["operation_fingerprint"] != operation_fingerprint:
            raise PlanValidationError("confirmation does not match active pause")
        task = plan["tasks"][task_id]
        task["status"] = TaskStatus.CANCELLED.value
        task["result"] = {"outcome": TaskOutcome.UNFULFILLABLE.value, "description": "Required operation was rejected", "reason_code": "confirmation_rejected", "outputs": {}, "limitation": {"code": "confirmation_rejected", "message": "The required operation was not approved.", "action": "none"}}
        pause["status"] = "rejected"
        plan["status"] = PlanStatus.ACTIVE.value

    def complete_synthesis(self, plan_id: str) -> None:
        plan = self.get(plan_id)
        active = next(item for item in plan["iterations"] if item["status"] == IterationStatus.ACTIVE.value)
        if active["checkpoint_status"] != "synthesis_running":
            raise PlanValidationError("synthesis was not claimed")
        active["status"], active["checkpoint_status"], plan["status"] = IterationStatus.CLOSED.value, "completed", PlanStatus.COMPLETED.value
        active["checkpoint_claimed_at"] = None

    def recover_stale_claims(self, plan_id: str, *, stale_before: datetime) -> None:
        plan = self.get(plan_id)
        for task_id, task in plan["tasks"].items():
            if task["status"] != TaskStatus.RUNNING.value:
                continue
            attempts = plan["attempts"].get(task_id, [])
            started_at = datetime.fromisoformat(attempts[-1]["started_at"]) if attempts else _now()
            if started_at >= stale_before:
                continue
            task["status"] = TaskStatus.PENDING.value
            if attempts and attempts[-1]["status"] == AttemptStatus.RUNNING.value:
                attempts[-1].update({"status": AttemptStatus.FAILED.value, "error": {"code": "claim_lease_expired", "message": "Execution claim expired"}, "finished_at": _now().isoformat()})
        for iteration in plan["iterations"]:
            claimed_at = iteration.get("checkpoint_claimed_at")
            if iteration["status"] == IterationStatus.ACTIVE.value and iteration["checkpoint_status"] in {"planner_running", "synthesis_running"} and claimed_at and datetime.fromisoformat(claimed_at) < stale_before:
                iteration["checkpoint_status"] = "idle"
                iteration["checkpoint_claimed_at"] = None

    def link_attempt_execution(self, plan_id: str, task_id: str, agent_execution_id: UUID) -> None:
        attempt = self.get(plan_id)["attempts"][task_id][-1]
        attempt["agent_execution_id"] = str(agent_execution_id)


class SqlPlanStore:
    """PostgreSQL adapter. Every lifecycle mutation locks the plan row."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_run(self, root_run_id: UUID) -> Optional[RuntimePlan]:
        return (await self._session.execute(select(RuntimePlan).where(RuntimePlan.root_run_id == root_run_id))).scalar_one_or_none()

    async def create(self, *, goal: str, root_run_id: UUID, tenant_id: UUID, chat_id: Optional[UUID] = None) -> RuntimePlan:
        plan = RuntimePlan(goal=goal, root_run_id=root_run_id, tenant_id=tenant_id, chat_id=chat_id)
        self._session.add(plan)
        await self._session.flush()
        return plan

    async def mark_failed(self, plan_id: UUID, code: str, message: str) -> None:
        plan = await self._plan(plan_id, lock=True)
        plan.status, plan.last_failure = PlanStatus.FAILED.value, {"code": code, "message": message}
        await self._session.flush()

    async def _plan(self, plan_id: UUID, *, lock: bool = False) -> RuntimePlan:
        query = select(RuntimePlan).where(RuntimePlan.id == plan_id)
        if lock:
            query = query.with_for_update()
        plan = (await self._session.execute(query)).scalar_one_or_none()
        if plan is None:
            raise KeyError(str(plan_id))
        return plan

    async def _active_iteration(self, plan_id: UUID, *, lock: bool = False) -> Optional[RuntimePlanIteration]:
        query = select(RuntimePlanIteration).where(RuntimePlanIteration.plan_id == plan_id, RuntimePlanIteration.status == IterationStatus.ACTIVE.value)
        if lock:
            query = query.with_for_update()
        rows = (await self._session.execute(query)).scalars().all()
        if len(rows) > 1:
            raise PlanValidationError("plan has more than one active iteration")
        return rows[0] if rows else None

    async def apply_iteration(
        self, plan_id: UUID, proposal: IterationProposal, *, iteration_id: Optional[UUID] = None,
    ) -> RuntimePlan:
        validate_iteration(proposal)
        plan = await self._plan(plan_id, lock=True)
        active = await self._active_iteration(plan_id, lock=True)
        if active is not None:
            if active.checkpoint_status != "planner_running":
                raise PlanValidationError("new iteration requires a claimed planner checkpoint")
            active.status, active.checkpoint_status, active.closed_at = IterationStatus.CLOSED.value, "completed", _now()
            active.checkpoint_claimed_at = None
        existing = set((await self._session.execute(select(RuntimePlanTask.task_id).where(RuntimePlanTask.plan_id == plan_id))).scalars().all())
        ids = {task.task_id for task in proposal.tasks}
        if existing & ids:
            raise PlanValidationError("task ids are immutable and cannot be reused")
        sequence = (max((await self._session.execute(select(RuntimePlanIteration.sequence).where(RuntimePlanIteration.plan_id == plan_id))).scalars().all(), default=0) + 1)
        iteration = RuntimePlanIteration(id=iteration_id or uuid4(), plan_id=plan_id, sequence=sequence, terminal=proposal.terminal.value,
                                         synthesis_brief=proposal.synthesis_brief.model_dump(mode="json") if proposal.synthesis_brief else None,
                                         proposal=proposal.model_dump(mode="json"))
        self._session.add(iteration)
        await self._session.flush()
        for order, task in enumerate(proposal.tasks):
            row = RuntimePlanTask(plan_id=plan_id, iteration_id=iteration.id, task_id=task.task_id, planned_order=order,
                                  executor=task.executor, intent=task.intent, instructions=task.instructions, inputs=task.inputs,
                                  expected_outputs=[item.model_dump(mode="json", by_alias=True) for item in task.expected_outputs],
                                  compiled_contract=task.contract.model_dump(mode="json"),
                                  freshness_policy=task.freshness_policy.value)
            self._session.add(row)
            await self._session.flush()
            self._session.add_all([RuntimeTaskDependency(task_row_id=row.id, depends_on_task_id=dep) for dep in task.depends_on])
        self._session.add_all([RuntimeNeedBinding(plan_id=plan_id, **item.model_dump(mode="json")) for item in proposal.bindings])
        self._session.add_all([RuntimeTaskResolution(iteration_id=iteration.id, **item.model_dump(mode="json")) for item in proposal.resolutions])
        plan.status = PlanStatus.ACTIVE.value
        await self._session.flush()
        return plan

    async def snapshot(self, plan_id: UUID) -> Dict[str, Any]:
        plan = await self._plan(plan_id)
        iterations = (await self._session.execute(select(RuntimePlanIteration).where(RuntimePlanIteration.plan_id == plan_id).order_by(RuntimePlanIteration.sequence))).scalars().all()
        tasks = (await self._session.execute(select(RuntimePlanTask).where(RuntimePlanTask.plan_id == plan_id))).scalars().all()
        deps = (await self._session.execute(select(RuntimeTaskDependency).join(RuntimePlanTask).where(RuntimePlanTask.plan_id == plan_id))).scalars().all()
        dependency_map: Dict[UUID, list[str]] = {}
        for dep in deps:
            dependency_map.setdefault(dep.task_row_id, []).append(dep.depends_on_task_id)
        needs = (await self._session.execute(select(RuntimeTaskNeed).join(RuntimePlanTask).where(RuntimePlanTask.plan_id == plan_id))).scalars().all()
        resolutions = (await self._session.execute(
            select(RuntimeTaskResolution)
            .join(RuntimePlanIteration)
            .where(RuntimePlanIteration.plan_id == plan_id)
            .order_by(RuntimePlanIteration.sequence, RuntimeTaskResolution.id)
        )).scalars().all()
        bindings = (await self._session.execute(select(RuntimeNeedBinding).where(RuntimeNeedBinding.plan_id == plan_id))).scalars().all()
        return {
            "id": str(plan.id), "goal": plan.goal, "root_run_id": str(plan.root_run_id), "status": plan.status, "contract_version": plan.contract_version, "last_failure": plan.last_failure,
            "iterations": [{"id": str(row.id), "sequence": row.sequence, "terminal": row.terminal, "synthesis_brief": row.synthesis_brief, "status": row.status, "checkpoint_status": row.checkpoint_status, "checkpoint_claimed_at": row.checkpoint_claimed_at.isoformat() if row.checkpoint_claimed_at else None} for row in iterations],
            "tasks": {row.task_id: {"task_id": row.task_id, "iteration_id": str(row.iteration_id), "planned_order": row.planned_order, "executor": row.executor, "intent": row.intent, "instructions": row.instructions, "inputs": row.inputs, "expected_outputs": row.expected_outputs, "contract": row.compiled_contract, "freshness_policy": row.freshness_policy, "depends_on": dependency_map.get(row.id, []), "status": row.status, "result": row.result, "attempts": row.attempts, "next_retry_at": row.next_retry_at.isoformat() if row.next_retry_at else None, "updated_at": row.updated_at.isoformat()} for row in tasks},
            "needs": [{"task_id": next(row.task_id for row in tasks if row.id == need.task_row_id), "ref": need.need_ref, "key": need.need_key, "kind": need.kind, "description": need.description, "schema": need.schema, "context": need.context, "required": need.required} for need in needs],
            "resolutions": [{"iteration_id": str(row.iteration_id), "task_id": row.task_id, "action": row.action, "output_keys": row.output_keys, "replacement_task_ids": row.replacement_task_ids, "reason": row.reason} for row in resolutions],
            "bindings": [{"need_task_id": row.need_task_id, "need_ref": row.need_ref, "producer_task_id": row.producer_task_id, "output_key": row.output_key, "consumer_task_id": row.consumer_task_id, "consumer_input_key": row.consumer_input_key} for row in bindings],
        }

    async def next_decision(self, plan_id: UUID) -> SchedulerDecision:
        await self._plan(plan_id, lock=True)
        return await self._prepared_decision(plan_id)

    async def _prepared_decision(self, plan_id: UUID) -> SchedulerDecision:
        """Persist deterministic retry promotion and dependency blocking first."""
        before = await self.snapshot(plan_id)
        working = deepcopy(before)
        decision = _MemoryStateMachine.next_decision(working, now=_now())
        for task_id, current in working["tasks"].items():
            original = before["tasks"][task_id]
            if current["status"] == original["status"] and current["next_retry_at"] == original["next_retry_at"]:
                continue
            row = (await self._session.execute(select(RuntimePlanTask).where(RuntimePlanTask.plan_id == plan_id, RuntimePlanTask.task_id == task_id).with_for_update())).scalar_one()
            row.status = current["status"]
            row.next_retry_at = datetime.fromisoformat(current["next_retry_at"]) if current["next_retry_at"] else None
            if current["result"] != original["result"]:
                row.result = current["result"]
        await self._session.flush()
        return decision

    async def claim_task(self, plan_id: UUID, task_id: str) -> RuntimePlanTask:
        plan = await self._plan(plan_id, lock=True)
        decision = await self._prepared_decision(plan_id)
        if decision.kind != SchedulerActionKind.EXECUTE_TASK or decision.task_id != task_id:
            raise PlanValidationError("task is not the current scheduler decision")
        row = (await self._session.execute(select(RuntimePlanTask).where(RuntimePlanTask.plan_id == plan_id, RuntimePlanTask.task_id == task_id).with_for_update())).scalar_one_or_none()
        if row is None:
            raise TaskNotFoundError(task_id)
        row.status, row.attempts, row.next_retry_at = TaskStatus.RUNNING.value, row.attempts + 1, None
        self._session.add(RuntimeTaskAttempt(task_row_id=row.id, attempt_number=row.attempts))
        await self._session.flush()
        return row

    async def claim_checkpoint(self, plan_id: UUID, kind: SchedulerActionKind) -> RuntimePlanIteration:
        if kind not in {SchedulerActionKind.INVOKE_PLANNER, SchedulerActionKind.INVOKE_SYNTHESIS}:
            raise PlanValidationError("invalid checkpoint kind")
        await self._plan(plan_id, lock=True)
        decision = await self._prepared_decision(plan_id)
        if decision.kind != kind:
            raise PlanValidationError("checkpoint is not the current scheduler decision")
        row = await self._active_iteration(plan_id, lock=True)
        assert row is not None
        row.checkpoint_status = "planner_running" if kind == SchedulerActionKind.INVOKE_PLANNER else "synthesis_running"
        row.checkpoint_claimed_at = _now()
        await self._session.flush()
        return row

    async def task_request(self, plan_id: UUID, task_id: str) -> Dict[str, Any]:
        snapshot = await self.snapshot(plan_id)
        task = snapshot["tasks"].get(task_id)
        if task is None:
            raise TaskNotFoundError(task_id)
        inputs = dict(task["inputs"])
        for binding in snapshot.get("bindings", []):
            if binding["consumer_task_id"] == task_id:
                source = snapshot["tasks"][binding["producer_task_id"]].get("result") or {}
                source_outputs = source.get("outputs") or {}
                if binding["output_key"] not in source_outputs:
                    raise PlanValidationError("ready bound task has no producer output")
                value = source_outputs[binding["output_key"]]
                need = next((item for item in snapshot.get("needs", []) if item.get("task_id") == binding["need_task_id"] and item.get("ref") == binding["need_ref"]), {})
                inputs[binding["consumer_input_key"]] = _binding_value(value, need.get("schema") if isinstance(need, dict) else None)
        return {"task_id": task_id, "executor": task["executor"], "intent": task["intent"], "instructions": task["instructions"], "inputs": inputs, "dependency_outputs": {dep: snapshot["tasks"][dep]["result"] for dep in task["depends_on"]}, "expected_outputs": task["expected_outputs"], "contract": task.get("contract", {}), "freshness_policy": task["freshness_policy"]}

    async def pause_confirmation(self, plan_id: UUID, task_id: str, payload: Dict[str, Any]) -> None:
        plan = await self._plan(plan_id, lock=True)
        fingerprint = str(payload.get("operation_fingerprint") or "").strip()
        row = (await self._session.execute(select(RuntimePlanTask).where(RuntimePlanTask.plan_id == plan_id, RuntimePlanTask.task_id == task_id).with_for_update())).scalar_one_or_none()
        if row is None or row.status != TaskStatus.RUNNING.value or not fingerprint:
            raise PlanValidationError("confirmation pause requires a running task and operation fingerprint")
        row.status, plan.status = TaskStatus.WAITING_CONFIRMATION.value, PlanStatus.WAITING_INPUT.value
        attempt = (await self._session.execute(select(RuntimeTaskAttempt).where(RuntimeTaskAttempt.task_row_id == row.id, RuntimeTaskAttempt.attempt_number == row.attempts).with_for_update())).scalar_one()
        attempt.status, attempt.error, attempt.finished_at = AttemptStatus.CANCELLED.value, {"code": "confirmation_required", "message": "Operation requires confirmation"}, _now()
        self._session.add(RuntimePause(plan_id=plan_id, task_id=task_id, kind="confirmation", operation_fingerprint=fingerprint, payload=payload))
        await self._session.flush()

    async def resume_confirmation(self, plan_id: UUID, task_id: str, operation_fingerprint: str) -> None:
        plan = await self._plan(plan_id, lock=True)
        pause = (await self._session.execute(select(RuntimePause).where(RuntimePause.plan_id == plan_id, RuntimePause.task_id == task_id, RuntimePause.status == "waiting").with_for_update())).scalar_one_or_none()
        if pause is None or pause.operation_fingerprint != operation_fingerprint:
            raise PlanValidationError("confirmation does not match active pause")
        row = (await self._session.execute(select(RuntimePlanTask).where(RuntimePlanTask.plan_id == plan_id, RuntimePlanTask.task_id == task_id).with_for_update())).scalar_one_or_none()
        if row is None or row.status != TaskStatus.WAITING_CONFIRMATION.value:
            raise PlanValidationError("confirmation task is not waiting")
        row.status, pause.status, pause.resolved_at, plan.status = TaskStatus.PENDING.value, "approved", _now(), PlanStatus.ACTIVE.value
        await self._session.flush()

    async def reject_confirmation(self, plan_id: UUID, task_id: str, operation_fingerprint: str) -> None:
        plan = await self._plan(plan_id, lock=True)
        pause = (await self._session.execute(select(RuntimePause).where(RuntimePause.plan_id == plan_id, RuntimePause.task_id == task_id, RuntimePause.status == "waiting").with_for_update())).scalar_one_or_none()
        if pause is None or pause.operation_fingerprint != operation_fingerprint:
            raise PlanValidationError("confirmation does not match active pause")
        row = (await self._session.execute(select(RuntimePlanTask).where(RuntimePlanTask.plan_id == plan_id, RuntimePlanTask.task_id == task_id).with_for_update())).scalar_one_or_none()
        if row is None or row.status != TaskStatus.WAITING_CONFIRMATION.value:
            raise PlanValidationError("confirmation task is not waiting")
        row.status = TaskStatus.CANCELLED.value
        row.result = {"outcome": TaskOutcome.UNFULFILLABLE.value, "description": "Required operation was rejected", "reason_code": "confirmation_rejected", "outputs": {}, "limitation": {"code": "confirmation_rejected", "message": "The required operation was not approved.", "action": "none"}}
        pause.status, pause.resolved_at, plan.status = "rejected", _now(), PlanStatus.ACTIVE.value
        await self._session.flush()

    async def finish_attempt(self, plan_id: UUID, task_id: str, *, execution: TaskExecutionReceipt, result: TaskResult) -> RuntimePlanTask:
        await self._plan(plan_id, lock=True)
        row = (await self._session.execute(select(RuntimePlanTask).where(RuntimePlanTask.plan_id == plan_id, RuntimePlanTask.task_id == task_id).with_for_update())).scalar_one_or_none()
        if row is None or row.status != TaskStatus.RUNNING.value:
            raise PlanValidationError("task is not running")
        if result.outcome == TaskOutcome.COMPLETED:
            missing = _required_outputs_fulfilled(row.expected_outputs, result)
            if missing:
                raise PlanValidationError(f"task is missing required fulfilled outputs: {sorted(missing)}")
            row.status = TaskStatus.COMPLETED.value
        elif result.outcome == TaskOutcome.NEEDS_DEPENDENCY:
            row.status = TaskStatus.NEEDS_DEPENDENCY.value
            self._session.add_all([RuntimeTaskNeed(task_row_id=row.id, need_ref=item.ref, need_key=item.key, kind=item.kind, description=item.description, schema=item.json_schema, context=item.context, required=item.required) for item in result.needs])
        else:
            row.status = TaskStatus.UNFULFILLABLE.value
        row.result = result.model_dump(mode="json")
        attempt = (await self._session.execute(select(RuntimeTaskAttempt).where(RuntimeTaskAttempt.task_row_id == row.id, RuntimeTaskAttempt.attempt_number == row.attempts).with_for_update())).scalar_one()
        attempt.status, attempt.execution_result, attempt.finished_at = AttemptStatus.COMPLETED.value, execution.model_dump(mode="json"), _now()
        expires_at = _now() + timedelta(hours=24)
        for item in result.verified.get("result_records") or []:
            if not isinstance(item, dict) or not item.get("result_ref"):
                continue
            self._session.add(RuntimeToolResult(
                attempt_id=attempt.id,
                result_ref=str(item["result_ref"]),
                call_id=str(item.get("call_id") or ""),
                operation=str(item.get("operation") or ""),
                status=str(item.get("status") or "unknown"),
                success=bool(item.get("success")),
                result_fingerprint=(str(item["result_fingerprint"]) if item.get("result_fingerprint") else None),
                payload=item.get("payload"),
                payload_ref=item.get("payload_ref"),
                expires_at=expires_at,
            ))
        await self._session.flush()
        return row

    async def finish_failure(self, plan_id: UUID, task_id: str, failure: TaskAttemptFailure, *, max_attempts: int, retry_at: Optional[datetime] = None) -> RuntimePlanTask:
        await self._plan(plan_id, lock=True)
        row = (await self._session.execute(select(RuntimePlanTask).where(RuntimePlanTask.plan_id == plan_id, RuntimePlanTask.task_id == task_id).with_for_update())).scalar_one_or_none()
        if row is None or row.status != TaskStatus.RUNNING.value:
            raise PlanValidationError("task is not running")
        attempt = (await self._session.execute(select(RuntimeTaskAttempt).where(RuntimeTaskAttempt.task_row_id == row.id, RuntimeTaskAttempt.attempt_number == row.attempts).with_for_update())).scalar_one()
        attempt.status, attempt.error, attempt.finished_at = (AttemptStatus.TIMED_OUT.value if failure.timed_out else AttemptStatus.FAILED.value), failure.model_dump(mode="json"), _now()
        if failure.retryable and row.attempts < max_attempts:
            row.status, row.next_retry_at = TaskStatus.WAITING_RETRY.value, retry_at or _now()
        else:
            limitation = _safe_failure_limitation(failure.code)
            row.status, row.result = TaskStatus.FAILED.value, {
                "outcome": TaskOutcome.UNFULFILLABLE.value,
                "description": limitation["message"],
                "reason_code": failure.code,
                "outputs": {},
                "limitation": limitation,
            }
        await self._session.flush()
        return row

    async def link_attempt_execution(self, plan_id: UUID, task_id: str, agent_execution_id: UUID) -> None:
        await self._plan(plan_id, lock=True)
        row = (await self._session.execute(
            select(RuntimePlanTask).where(
                RuntimePlanTask.plan_id == plan_id,
                RuntimePlanTask.task_id == task_id,
            ).with_for_update()
        )).scalar_one_or_none()
        if row is None or row.status != TaskStatus.RUNNING.value:
            raise PlanValidationError("attempt execution link requires a running task")
        attempt = (await self._session.execute(
            select(RuntimeTaskAttempt).where(
                RuntimeTaskAttempt.task_row_id == row.id,
                RuntimeTaskAttempt.attempt_number == row.attempts,
            ).with_for_update()
        )).scalar_one()
        attempt.agent_execution_id = agent_execution_id
        await self._session.flush()

    async def complete_synthesis(self, plan_id: UUID) -> None:
        plan = await self._plan(plan_id, lock=True)
        iteration = await self._active_iteration(plan_id, lock=True)
        if iteration is None or iteration.checkpoint_status != "synthesis_running":
            raise PlanValidationError("synthesis was not claimed")
        iteration.status, iteration.checkpoint_status, iteration.closed_at = IterationStatus.CLOSED.value, "completed", _now()
        iteration.checkpoint_claimed_at = None
        plan.status = PlanStatus.COMPLETED.value
        await self._session.flush()

    async def recover_stale_claims(self, plan_id: UUID, *, stale_before: datetime) -> None:
        await self._plan(plan_id, lock=True)
        rows = (await self._session.execute(
            select(RuntimePlanTask).where(
                RuntimePlanTask.plan_id == plan_id,
                RuntimePlanTask.status == TaskStatus.RUNNING.value,
                RuntimePlanTask.updated_at < stale_before,
            ).with_for_update()
        )).scalars().all()
        for row in rows:
            row.status = TaskStatus.PENDING.value
            attempt = (await self._session.execute(
                select(RuntimeTaskAttempt).where(
                    RuntimeTaskAttempt.task_row_id == row.id,
                    RuntimeTaskAttempt.attempt_number == row.attempts,
                    RuntimeTaskAttempt.status == AttemptStatus.RUNNING.value,
                ).with_for_update()
            )).scalar_one_or_none()
            if attempt is not None:
                attempt.status = AttemptStatus.FAILED.value
                attempt.error = {"code": "claim_lease_expired", "message": "Execution claim expired"}
                attempt.finished_at = _now()
        iteration = await self._active_iteration(plan_id, lock=True)
        if iteration is not None and iteration.checkpoint_status in {"planner_running", "synthesis_running"} and iteration.checkpoint_claimed_at and iteration.checkpoint_claimed_at < stale_before:
            iteration.checkpoint_status = "idle"
            iteration.checkpoint_claimed_at = None
        await self._session.flush()
