"""Transactional state transitions for the persisted runtime task graph."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.runtime_plan import (
    RuntimePlan,
    RuntimePlanRevision,
    RuntimePlanTask,
    RuntimeTaskAttempt,
    RuntimeTaskDependency,
    RuntimeTaskNeed,
)
from app.runtime.orchestrator_contracts import (
    AgentTaskResult,
    AttemptStatus,
    PlanPatch,
    PlanStatus,
    PlannedTask,
    RequirementStatus,
    TaskAttemptFailure,
    TaskOutcome,
    TaskStatus,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


TERMINAL_TASK_STATUSES = {
    TaskStatus.COMPLETED.value,
    TaskStatus.UNFULFILLABLE.value,
    TaskStatus.FAILED.value,
    TaskStatus.CANCELLED.value,
}


class PlanConflictError(ValueError):
    pass


class PlanValidationError(ValueError):
    pass


class TaskNotFoundError(KeyError):
    pass


def validate_task_graph(tasks: Iterable[PlannedTask]) -> None:
    """Reject unknown dependencies and cycles before touching persistence."""
    task_list = list(tasks)
    ids = {item.task_id for item in task_list}
    for item in task_list:
        if len(item.depends_on) != len(set(item.depends_on)):
            raise PlanValidationError(f"task {item.task_id} contains duplicate dependencies")
        if item.task_id in item.depends_on:
            raise PlanValidationError(f"task {item.task_id} cannot depend on itself")
    graph = {item.task_id: set(item.depends_on) for item in task_list}
    for task_id, dependencies in graph.items():
        unknown = dependencies - ids
        if unknown:
            raise PlanValidationError(f"task {task_id} depends on unknown tasks: {sorted(unknown)}")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(task_id: str) -> None:
        if task_id in visiting:
            raise PlanValidationError("plan task graph contains a cycle")
        if task_id in visited:
            return
        visiting.add(task_id)
        for dependency in graph[task_id]:
            visit(dependency)
        visiting.remove(task_id)
        visited.add(task_id)

    for task_id in graph:
        visit(task_id)


def task_is_ready(task: Dict[str, Any], all_tasks: Dict[str, Dict[str, Any]]) -> bool:
    if task.get("status") not in {TaskStatus.PENDING.value, TaskStatus.READY.value}:
        return False
    dependencies_ready = all(
        all_tasks.get(dep, {}).get("status") == TaskStatus.COMPLETED.value
        for dep in task.get("depends_on", [])
    )
    needs_ready = all(
        not need.get("required", True)
        or need.get("status") == RequirementStatus.RESOLVED.value
        for need in task.get("needs", [])
    )
    return dependencies_ready and needs_ready


def _missing_contract_outputs(task: Dict[str, Any], result: AgentTaskResult) -> List[str]:
    outputs = result.outputs or {}
    return [
        str(spec.get("key"))
        for spec in task.get("expected_outputs", [])
        if isinstance(spec, dict)
        and spec.get("required", True)
        and str(spec.get("key") or "") not in outputs
    ]


class InMemoryPlanStore:
    """Deterministic store for orchestration tests and local adapters."""

    def __init__(self) -> None:
        self.plans: Dict[str, Dict[str, Any]] = {}
        self.revisions: Dict[str, List[Dict[str, Any]]] = {}
        self.attempts: Dict[str, List[Dict[str, Any]]] = {}

    def create(self, *, goal: str, root_run_id: str, tenant_id: str, chat_id: Optional[str] = None) -> Dict[str, Any]:
        plan_id = str(uuid4())
        plan = {
            "id": plan_id,
            "goal": goal,
            "root_run_id": root_run_id,
            "tenant_id": tenant_id,
            "chat_id": chat_id,
            "status": PlanStatus.DRAFT.value,
            "revision": 0,
            "tasks": {},
            "needs": {},
            "answer_brief": None,
            "last_failure": None,
        }
        self.plans[plan_id] = plan
        self.revisions[plan_id] = []
        return plan

    def get(self, plan_id: str) -> Dict[str, Any]:
        if plan_id not in self.plans:
            raise KeyError(plan_id)
        return self.plans[plan_id]

    def apply_patch(self, plan_id: str, patch: PlanPatch, *, reason: str = "planner", planner_invocation_id: Optional[str] = None) -> Dict[str, Any]:
        plan = self.get(plan_id)
        if patch.expected_revision != plan["revision"]:
            raise PlanConflictError(f"expected revision {patch.expected_revision}, current {plan['revision']}")
        existing = [
            PlannedTask(
                task_id=task_id,
                intent=task["intent"],
                instructions=task["instructions"],
                executor=task["executor"],
                inputs=task.get("inputs", {}),
                expected_outputs=task.get("expected_outputs", []),
                depends_on=task.get("depends_on", []),
                needs=task.get("needs", []),
                on_success=task.get("on_success", "continue"),
            )
            for task_id, task in plan["tasks"].items()
            if task_id not in set(patch.remove_task_ids)
        ]
        merged = {task.task_id: task for task in existing}
        merged.update({task.task_id: task for task in patch.tasks})
        validate_task_graph(merged.values())

        for task_id in patch.remove_task_ids:
            plan["tasks"].pop(task_id, None)
        for index, task in enumerate(patch.tasks):
            old = plan["tasks"].get(task.task_id)
            if old and old.get("status") in {TaskStatus.RUNNING.value, TaskStatus.COMPLETED.value}:
                raise PlanValidationError(f"cannot replace active or completed task {task.task_id}")
            old_needs = [
                value for value in plan["needs"].values()
                if value.get("task_id") == task.task_id
            ]
            effective_task = task
            if old and not task.needs and old_needs:
                effective_task = task.model_copy(update={"needs": old_needs})
            for need_key in [key for key, value in plan["needs"].items() if value.get("task_id") == task.task_id]:
                plan["needs"].pop(need_key, None)
            plan["tasks"][task.task_id] = {
                **effective_task.model_dump(mode="json", by_alias=True),
                "status": (
                    TaskStatus.PENDING.value
                    if old and old.get("status") not in {
                        TaskStatus.RUNNING.value,
                        TaskStatus.COMPLETED.value,
                    }
                    else old.get("status", TaskStatus.PENDING.value) if old else TaskStatus.PENDING.value
                ),
                "checkpoint": (
                    {}
                    if old and old.get("status") not in {
                        TaskStatus.RUNNING.value,
                        TaskStatus.COMPLETED.value,
                    }
                    else old.get("checkpoint", {}) if old else {}
                ),
                "result": (
                    None
                    if old and old.get("status") not in {
                        TaskStatus.RUNNING.value,
                        TaskStatus.COMPLETED.value,
                    }
                    else old.get("result") if old else None
                ),
                "attempts": old.get("attempts", 0) if old else 0,
                "planned_order": old.get("planned_order", index) if old else index,
            }
            for need in effective_task.needs:
                plan["needs"][f"{task.task_id}:{need.key}"] = {
                    "task_id": task.task_id,
                    **need.model_dump(mode="json", by_alias=True),
                    "status": RequirementStatus.PENDING.value,
                    "resolved_value": None,
                }
        plan["revision"] += 1
        if patch.goal:
            plan["goal"] = patch.goal
        if patch.decision.value == "ask_user":
            plan["status"] = PlanStatus.WAITING_INPUT.value
        elif patch.decision.value == "complete_plan":
            plan["status"] = PlanStatus.COMPLETED.value
        elif patch.decision.value == "fail_plan":
            plan["status"] = PlanStatus.FAILED.value
        else:
            plan["status"] = PlanStatus.ACTIVE.value
        if patch.decision.value == "ask_user":
            for need in plan["needs"].values():
                if need.get("status") == RequirementStatus.PENDING.value:
                    need["status"] = RequirementStatus.WAITING_USER.value
        if patch.answer_brief is not None:
            plan["answer_brief"] = patch.answer_brief
        self.revisions[plan_id].append({
            "revision": plan["revision"],
            "reason": reason,
            "planner_invocation_id": planner_invocation_id,
            "patch": patch.model_dump(mode="json", by_alias=True),
            "created_at": _now().isoformat(),
        })
        self.refresh_ready(plan_id)
        return plan

    def mark_failed(self, plan_id: str, failure: Dict[str, Any]) -> None:
        plan = self.get(plan_id)
        plan["status"] = PlanStatus.FAILED.value
        plan["last_failure"] = dict(failure)

    def refresh_ready(self, plan_id: str) -> None:
        plan = self.get(plan_id)
        tasks = plan["tasks"]
        for task in tasks.values():
            task_for_readiness = dict(task)
            task_for_readiness["needs"] = [
                {
                    **need,
                    **next(
                        (
                            requirement
                            for requirement in plan["needs"].values()
                            if requirement.get("task_id") == task.get("task_id")
                            and requirement.get("key") == need.get("key")
                        ),
                        {},
                    ),
                }
                for need in task.get("needs", [])
            ]
            if task_is_ready(task_for_readiness, tasks):
                task["status"] = TaskStatus.READY.value

    def claim_ready_batch(self, plan_id: str, limit: int = 1) -> List[Dict[str, Any]]:
        plan = self.get(plan_id)
        self.refresh_ready(plan_id)
        ready = sorted(
            (task for task in plan["tasks"].values() if task["status"] == TaskStatus.READY.value),
            key=lambda item: (int(item.get("planned_order", 0)), item["task_id"]),
        )
        claimed: List[Dict[str, Any]] = []
        for task in ready[: max(1, int(limit))]:
            task["status"] = TaskStatus.RUNNING.value
            task["attempts"] += 1
            self.attempts.setdefault(task["task_id"], []).append({
                "attempt_number": task["attempts"],
                "status": AttemptStatus.RUNNING.value,
                "started_at": _now().isoformat(),
            })
            claimed.append(task)
        return claimed

    def claim_ready(self, plan_id: str) -> Optional[Dict[str, Any]]:
        return next(iter(self.claim_ready_batch(plan_id, limit=1)), None)

    def apply_result(self, plan_id: str, task_id: str, result: AgentTaskResult) -> Dict[str, Any]:
        plan = self.get(plan_id)
        task = plan["tasks"].get(task_id)
        if task is None:
            raise TaskNotFoundError(task_id)
        if task["status"] != TaskStatus.RUNNING.value:
            raise PlanValidationError(f"task {task_id} is not running")
        if result.outcome == TaskOutcome.COMPLETED:
            missing_outputs = _missing_contract_outputs(task, result)
            pending_needs = [
                need.get("key") for need in task.get("needs", [])
                if need.get("required", True)
                and plan["needs"].get(f"{task_id}:{need.get('key')}", {}).get("status")
                != RequirementStatus.RESOLVED.value
            ]
            if pending_needs:
                raise PlanValidationError(
                    f"task {task_id} cannot complete with unresolved needs: {pending_needs}"
                )
            if missing_outputs:
                raise PlanValidationError(
                    f"task {task_id} is missing required outputs: {missing_outputs}"
                )
        task["result"] = result.model_dump(mode="json")
        task["checkpoint"] = dict(result.checkpoint)
        if result.outcome == TaskOutcome.COMPLETED:
            task["status"] = TaskStatus.COMPLETED.value
            for req in plan["needs"].values():
                consumer = plan["tasks"].get(req.get("task_id"), {})
                if (
                    req["status"] == RequirementStatus.PENDING.value
                    and req["task_id"] != task_id
                    and task_id in consumer.get("depends_on", [])
                ):
                    key = req.get("key") or req.get("need_key")
                    if key in result.outputs:
                        req["status"] = RequirementStatus.RESOLVED.value
                        req["resolved_value"] = result.outputs[key]
                        req["resolver_task_id"] = task_id
        elif result.outcome == TaskOutcome.NEEDS_DEPENDENCY:
            task["status"] = TaskStatus.WAITING_DEPENDENCY.value
            for need in result.needs:
                plan["needs"][f"{task_id}:{need.key}"] = {
                    "task_id": task_id, **need.model_dump(mode="json", by_alias=True),
                    "status": RequirementStatus.PENDING.value, "resolved_value": None,
                }
        else:
            task["status"] = TaskStatus.UNFULFILLABLE.value
        self.refresh_ready(plan_id)
        self._refresh_plan_status(plan_id)
        return task

    def record_failure(self, plan_id: str, task_id: str, failure: TaskAttemptFailure, *, retry_at: Optional[datetime] = None, max_attempts: int = 3) -> Dict[str, Any]:
        plan = self.get(plan_id)
        task = plan["tasks"].get(task_id)
        if task is None:
            raise TaskNotFoundError(task_id)
        attempts = self.attempts.setdefault(task_id, [])
        if attempts:
            attempts[-1].update({"status": AttemptStatus.TIMED_OUT.value if failure.timed_out else AttemptStatus.FAILED.value, "error": failure.model_dump(mode="json"), "finished_at": _now().isoformat()})
        if failure.retryable and task["attempts"] < max_attempts:
            task["status"] = TaskStatus.WAITING_RETRY.value
            task["next_retry_at"] = retry_at.isoformat() if retry_at else None
        else:
            task["status"] = TaskStatus.FAILED.value
            plan["last_failure"] = {"task_id": task_id, **failure.model_dump(mode="json")}
        self._refresh_plan_status(plan_id)
        return task

    def resume_task(self, plan_id: str, task_id: str) -> Dict[str, Any]:
        task = self.get(plan_id)["tasks"].get(task_id)
        if task is None:
            raise TaskNotFoundError(task_id)
        if task["status"] not in {TaskStatus.WAITING_DEPENDENCY.value, TaskStatus.WAITING_USER.value, TaskStatus.WAITING_RETRY.value}:
            raise PlanValidationError(f"task {task_id} is not resumable")
        task["status"] = TaskStatus.PENDING.value
        self.get(plan_id)["status"] = PlanStatus.ACTIVE.value
        self.refresh_ready(plan_id)
        return task

    def resolve_waiting_need(self, plan_id: str, *, user_input: str) -> Optional[str]:
        value = str(user_input or "").strip()
        if not value:
            return None
        plan = self.get(plan_id)
        candidates = sorted(
            (
                key,
                need,
            )
            for key, need in plan["needs"].items()
            if need.get("status") == RequirementStatus.WAITING_USER.value
        )
        if not candidates:
            return None
        key, need = candidates[0]
        need["status"] = RequirementStatus.RESOLVED.value
        need["resolved_value"] = value
        need["resolver_task_id"] = "user"
        task = plan["tasks"].get(need["task_id"])
        if task is not None:
            task.setdefault("checkpoint", {})["user_input"] = value
            if task.get("status") in {TaskStatus.WAITING_DEPENDENCY.value, TaskStatus.WAITING_USER.value}:
                task["status"] = TaskStatus.PENDING.value
        plan["status"] = PlanStatus.ACTIVE.value
        self.refresh_ready(plan_id)
        return str(need.get("key") or key)

    def _refresh_plan_status(self, plan_id: str) -> None:
        plan = self.get(plan_id)
        statuses = {task["status"] for task in plan["tasks"].values()}
        if statuses and statuses <= TERMINAL_TASK_STATUSES and TaskStatus.FAILED.value not in statuses and TaskStatus.UNFULFILLABLE.value not in statuses:
            plan["status"] = PlanStatus.COMPLETED.value
        elif TaskStatus.WAITING_USER.value in statuses:
            plan["status"] = PlanStatus.WAITING_INPUT.value


class SqlPlanStore:
    """Persistence adapter; lifecycle validation is shared with InMemoryPlanStore."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_run(self, root_run_id: UUID) -> Optional[RuntimePlan]:
        result = await self.session.execute(select(RuntimePlan).where(RuntimePlan.root_run_id == root_run_id))
        return result.scalar_one_or_none()

    async def create(self, *, goal: str, root_run_id: UUID, tenant_id: UUID, chat_id: Optional[UUID] = None) -> RuntimePlan:
        plan = RuntimePlan(goal=goal, root_run_id=root_run_id, tenant_id=tenant_id, chat_id=chat_id)
        self.session.add(plan)
        await self.session.flush()
        return plan


    async def apply_patch(
        self,
        plan_id: UUID,
        patch: PlanPatch,
        *,
        reason: str = "planner",
        planner_invocation_id: Optional[str] = None,
    ) -> RuntimePlan:
        result = await self.session.execute(
            select(RuntimePlan).where(RuntimePlan.id == plan_id).with_for_update()
        )
        plan = result.scalar_one_or_none()
        if plan is None:
            raise KeyError(str(plan_id))
        if plan.revision != patch.expected_revision:
            raise PlanConflictError(f"expected revision {patch.expected_revision}, current {plan.revision}")
        existing_rows = (await self.session.execute(
            select(RuntimePlanTask).where(RuntimePlanTask.plan_id == plan_id)
        )).scalars().all()
        protected_removals = {
            row.task_id for row in existing_rows
            if row.task_id in set(patch.remove_task_ids)
            and row.status in {TaskStatus.RUNNING.value, TaskStatus.COMPLETED.value}
        }
        if protected_removals:
            raise PlanValidationError(f"cannot remove active or completed tasks: {sorted(protected_removals)}")
        existing_ids = {row.task_id for row in existing_rows if row.task_id not in set(patch.remove_task_ids)}
        dependencies_by_task: Dict[str, List[str]] = {task_id: [] for task_id in existing_ids}
        dep_rows = (await self.session.execute(
            select(RuntimeTaskDependency).where(RuntimeTaskDependency.plan_id == plan_id)
        )).scalars().all()
        for dependency in dep_rows:
            if dependency.task_id in dependencies_by_task:
                dependencies_by_task[dependency.task_id].append(dependency.depends_on_task_id)
        need_rows = (await self.session.execute(
            select(RuntimeTaskNeed).join(RuntimePlanTask).where(RuntimePlanTask.plan_id == plan_id)
        )).scalars().all()
        needs_by_task_row: Dict[UUID, List[dict]] = {}
        for need in need_rows:
            needs_by_task_row.setdefault(need.task_row_id, []).append({
                "ref": (need.need_metadata or {}).get("ref") or need.need_key,
                "key": need.need_key,
                "kind": need.kind,
                "description": need.description,
                "schema": need.schema or {},
                "required": (need.need_metadata or {}).get("required", True),
                "context": (need.need_metadata or {}).get("context", {}),
                "status": need.status,
                "resolved_value": need.resolved_value,
            })
        combined = {row.task_id: PlannedTask(
            task_id=row.task_id, intent=row.intent, instructions=row.instructions,
            executor=row.executor, inputs=row.inputs or {},
            depends_on=dependencies_by_task[row.task_id],
            needs=needs_by_task_row.get(row.id, []),
            on_success=row.on_success,
        ) for row in existing_rows if row.task_id in existing_ids}
        # ``revise_plan`` is a delta: a supplied task replaces its own
        # definition and dependencies; omitted tasks stay untouched.
        combined.update({item.task_id: item.model_copy(deep=True) for item in patch.tasks})
        validate_task_graph(combined.values())
        try:
            async with self.session.begin_nested():
                if patch.remove_task_ids:
                    await self.session.execute(
                        delete(RuntimePlanTask).where(
                            RuntimePlanTask.plan_id == plan_id,
                            RuntimePlanTask.task_id.in_(patch.remove_task_ids),
                            RuntimePlanTask.status.not_in([TaskStatus.RUNNING.value, TaskStatus.COMPLETED.value]),
                        )
                    )
                for index, item in enumerate(patch.tasks):
                    existing_result = await self.session.execute(
                        select(RuntimePlanTask).where(
                            RuntimePlanTask.plan_id == plan_id,
                            RuntimePlanTask.task_id == item.task_id,
                        ).with_for_update()
                    )
                    task = existing_result.scalar_one_or_none()
                    if task is not None and task.status in {TaskStatus.RUNNING.value, TaskStatus.COMPLETED.value}:
                        raise PlanValidationError(f"cannot replace active or completed task {item.task_id}")
                    existing_needs = needs_by_task_row.get(task.id, []) if task is not None else []
                    existing_need_state = {
                        need.need_key: need
                        for need in need_rows
                        if task is not None and need.task_row_id == task.id
                    }
                    effective_item = item
                    if task is not None and not item.needs and existing_needs:
                        effective_item = item.model_copy(update={"needs": existing_needs})
                    if task is None:
                        task = RuntimePlanTask(
                            plan_id=plan_id, task_id=effective_item.task_id, intent=effective_item.intent,
                            instructions=effective_item.instructions, executor=effective_item.executor, inputs=effective_item.inputs,
                            expected_outputs=[output.model_dump(mode="json", by_alias=True) for output in effective_item.expected_outputs],
                            on_success=effective_item.on_success.value,
                            planned_order=index, status=TaskStatus.PENDING.value,
                        )
                        self.session.add(task)
                        await self.session.flush()
                    else:
                        task.intent, task.instructions, task.executor = effective_item.intent, effective_item.instructions, effective_item.executor
                        task.inputs = effective_item.inputs
                        task.expected_outputs = [output.model_dump(mode="json", by_alias=True) for output in effective_item.expected_outputs]
                        task.on_success = effective_item.on_success.value
                        task.planned_order = index
                        # A replan may replace a failed/unfulfillable task
                        # with another executor.  The new definition must be
                        # executable; retaining the terminal status would
                        # make the scheduler report ``plan_stalled`` without
                        # ever claiming the replacement.
                        task.status = TaskStatus.PENDING.value
                        task.result = None
                        task.checkpoint = {}
                    await self.session.execute(delete(RuntimeTaskDependency).where(
                        RuntimeTaskDependency.plan_id == plan_id, RuntimeTaskDependency.task_id == effective_item.task_id,
                    ))
                    for dependency in effective_item.depends_on:
                        self.session.add(RuntimeTaskDependency(plan_id=plan_id, task_id=effective_item.task_id, depends_on_task_id=dependency))
                    await self.session.execute(delete(RuntimeTaskNeed).where(RuntimeTaskNeed.task_row_id == task.id))
                    for need in effective_item.needs:
                        prior = existing_need_state.get(need.key)
                        self.session.add(RuntimeTaskNeed(
                            task_row_id=task.id, need_key=need.key, kind=need.kind,
                            description=need.description, schema=need.json_schema,
                            need_metadata={
                                "ref": need.ref or need.key,
                                "required": need.required,
                                "context": need.context,
                            },
                            status=prior.status if prior is not None else RequirementStatus.PENDING.value,
                            resolved_value=prior.resolved_value if prior is not None else None,
                            resolver_task_id=prior.resolver_task_id if prior is not None else None,
                        ))
                plan.revision += 1
                plan.status = {
                    "ask_user": PlanStatus.WAITING_INPUT.value,
                    "complete_plan": PlanStatus.COMPLETED.value,
                    "fail_plan": PlanStatus.FAILED.value,
                }.get(patch.decision.value, PlanStatus.ACTIVE.value)
                if patch.decision.value == "ask_user":
                    await self.session.execute(
                        RuntimeTaskNeed.__table__.update()
                        .where(
                            RuntimeTaskNeed.status == RequirementStatus.PENDING.value,
                            RuntimeTaskNeed.task_row_id.in_(
                                select(RuntimePlanTask.id).where(RuntimePlanTask.plan_id == plan_id)
                            ),
                        )
                        .values(status=RequirementStatus.WAITING_USER.value)
                    )
                if patch.answer_brief is not None:
                    plan.answer_brief = patch.answer_brief
                self.session.add(RuntimePlanRevision(
                    plan_id=plan_id, revision=plan.revision, reason=reason,
                    patch=patch.model_dump(mode="json", by_alias=True), planner_invocation_id=planner_invocation_id,
                ))
                await self.session.flush()
        except IntegrityError as exc:
            raise PlanValidationError("plan patch violates persistence constraints") from exc
        return plan

    async def resolve_waiting_need(self, plan_id: UUID, *, user_input: str) -> Optional[str]:
        """Resolve the oldest user-routed need and reactivate its task."""
        value = str(user_input or "").strip()
        if not value:
            return None
        result = await self.session.execute(
            select(RuntimeTaskNeed, RuntimePlanTask).join(
                RuntimePlanTask, RuntimePlanTask.id == RuntimeTaskNeed.task_row_id
            ).where(
                RuntimePlanTask.plan_id == plan_id,
                RuntimeTaskNeed.status == RequirementStatus.WAITING_USER.value,
            ).order_by(RuntimeTaskNeed.id).with_for_update()
        )
        pair = result.first()
        if pair is None:
            return None
        need, task = pair
        need.status = RequirementStatus.RESOLVED.value
        need.resolved_value = value
        need.resolver_task_id = "user"
        checkpoint = dict(task.checkpoint or {})
        checkpoint["user_input"] = value
        task.checkpoint = checkpoint
        if task.status in {TaskStatus.WAITING_DEPENDENCY.value, TaskStatus.WAITING_USER.value}:
            task.status = TaskStatus.PENDING.value
        plan = await self.session.get(RuntimePlan, plan_id, with_for_update=True)
        if plan is not None:
            plan.status = PlanStatus.ACTIVE.value
        await self.session.flush()
        return need.need_key

    async def mark_failed(self, plan_id: UUID, failure: Dict[str, Any]) -> None:
        plan = await self.session.get(RuntimePlan, plan_id, with_for_update=True)
        if plan is None:
            raise KeyError(str(plan_id))
        plan.status = PlanStatus.FAILED.value
        plan.last_failure = dict(failure)
        await self.session.flush()

    async def snapshot(self, plan_id: UUID) -> Dict[str, Any]:
        result = await self.session.execute(select(RuntimePlan).where(RuntimePlan.id == plan_id))
        plan = result.scalar_one_or_none()
        if plan is None:
            raise KeyError(str(plan_id))
        task_result = await self.session.execute(select(RuntimePlanTask).where(RuntimePlanTask.plan_id == plan_id))
        dependency_result = await self.session.execute(select(RuntimeTaskDependency).where(RuntimeTaskDependency.plan_id == plan_id))
        need_result = await self.session.execute(
            select(RuntimeTaskNeed).join(RuntimePlanTask).where(RuntimePlanTask.plan_id == plan_id)
        )
        task_rows = task_result.scalars().all()
        tasks = {task.task_id: {
            "task_id": task.task_id,
            "intent": task.intent,
            "instructions": task.instructions,
            "executor": task.executor,
            "status": task.status,
            "inputs": task.inputs or {},
            "expected_outputs": task.expected_outputs or [],
            "on_success": task.on_success,
            "checkpoint": task.checkpoint or {},
            "result": task.result,
                "attempts": task.attempts,
                "planned_order": task.planned_order,
        } for task in task_rows}
        for dependency in dependency_result.scalars().all():
            tasks.setdefault(dependency.task_id, {}).setdefault("depends_on", []).append(dependency.depends_on_task_id)
        task_rows_by_id = {task.id: task.task_id for task in task_rows}
        for need in need_result.scalars().all():
            task_id = task_rows_by_id.get(need.task_row_id)
            if task_id:
                tasks.setdefault(task_id, {}).setdefault("needs", []).append({
                    "ref": (need.need_metadata or {}).get("ref") or need.need_key,
                    "key": need.need_key,
                    "kind": need.kind,
                    "description": need.description,
                    "schema": need.schema or {},
                    "required": (need.need_metadata or {}).get("required", True),
                    "context": (need.need_metadata or {}).get("context", {}),
                    "status": need.status,
                    "resolved_value": need.resolved_value,
                    "resolver_task_id": need.resolver_task_id,
                })
        return {
            "id": str(plan.id),
            "goal": plan.goal,
            "root_run_id": str(plan.root_run_id),
            "tenant_id": str(plan.tenant_id),
            "chat_id": str(plan.chat_id) if plan.chat_id else None,
            "status": plan.status,
            "revision": plan.revision,
            "tasks": tasks,
            "last_failure": plan.last_failure,
        }

    async def claim_ready_batch(self, plan_id: UUID, limit: int = 1) -> List[RuntimePlanTask]:
        """Atomically claim an ordered batch of dependency-ready tasks."""
        snapshot = await self.snapshot(plan_id)
        candidates = []
        for task in snapshot["tasks"].values():
            if task.get("status") not in {TaskStatus.PENDING.value, TaskStatus.READY.value}:
                continue
            dependencies = task.get("depends_on", [])
            if task_is_ready(task, snapshot["tasks"]):
                candidates.append((int(task.get("planned_order", 0)), task["task_id"]))
        claimed: List[RuntimePlanTask] = []
        for _, task_id in sorted(candidates)[: max(1, int(limit))]:
            result = await self.session.execute(
                select(RuntimePlanTask).where(
                    RuntimePlanTask.plan_id == plan_id,
                    RuntimePlanTask.task_id == task_id,
                ).with_for_update()
            )
            task = result.scalar_one_or_none()
            if task is None or task.status == TaskStatus.RUNNING.value:
                continue
            task.status = TaskStatus.RUNNING.value
            task.attempts += 1
            self.session.add(RuntimeTaskAttempt(task_row_id=task.id, attempt_number=task.attempts))
            claimed.append(task)
        await self.session.flush()
        return claimed

    async def claim_ready(self, plan_id: UUID) -> Optional[RuntimePlanTask]:
        return next(iter(await self.claim_ready_batch(plan_id, limit=1)), None)

    async def resume_waiting_tasks(self, plan_id: UUID, *, user_input: str) -> None:
        """Resume the same persisted plan after a chat continuation."""
        rows = (await self.session.execute(
            select(RuntimePlanTask).where(
                RuntimePlanTask.plan_id == plan_id,
                RuntimePlanTask.status.in_([
                    TaskStatus.WAITING_USER.value,
                    TaskStatus.WAITING_DEPENDENCY.value,
                    TaskStatus.WAITING_RETRY.value,
                ]),
            ).with_for_update()
        )).scalars().all()
        for row in rows:
            checkpoint = dict(row.checkpoint or {})
            if user_input:
                checkpoint["user_input"] = user_input
            row.checkpoint = checkpoint
            row.status = TaskStatus.PENDING.value
        plan = await self.session.get(RuntimePlan, plan_id, with_for_update=True)
        if plan is not None and rows:
            plan.status = PlanStatus.ACTIVE.value
        await self.session.flush()

    async def resume_planner_pause(self, plan_id: UUID) -> None:
        """Reactivate a plan paused by the planner's ``ask_user`` decision.

        Planner pauses do not belong to a task, so task-level resume cannot
        make progress.  The continuation is handled by a new planner replan.
        """
        plan = await self.session.get(RuntimePlan, plan_id, with_for_update=True)
        if plan is None:
            raise KeyError(str(plan_id))
        if plan.status != PlanStatus.WAITING_INPUT.value:
            raise PlanValidationError(f"plan {plan_id} is not waiting for planner input")
        plan.status = PlanStatus.ACTIVE.value
        await self.session.flush()

    async def _refresh_status(self, plan_id: UUID) -> None:
        plan = await self.session.get(RuntimePlan, plan_id, with_for_update=True)
        if plan is None:
            return
        rows = (await self.session.execute(select(RuntimePlanTask).where(RuntimePlanTask.plan_id == plan_id))).scalars().all()
        statuses = {row.status for row in rows}
        if statuses and statuses <= TERMINAL_TASK_STATUSES and not ({TaskStatus.FAILED.value, TaskStatus.UNFULFILLABLE.value} & statuses):
            plan.status = PlanStatus.COMPLETED.value
        elif TaskStatus.WAITING_USER.value in statuses:
            plan.status = PlanStatus.WAITING_INPUT.value
        elif statuses and statuses <= {TaskStatus.FAILED.value, TaskStatus.UNFULFILLABLE.value}:
            plan.status = PlanStatus.FAILED.value

    async def apply_result(self, plan_id: UUID, task_id: str, result: AgentTaskResult) -> RuntimePlanTask:
        lookup = await self.session.execute(select(RuntimePlanTask).where(
            RuntimePlanTask.plan_id == plan_id, RuntimePlanTask.task_id == task_id
        ).with_for_update())
        row = lookup.scalar_one_or_none()
        if row is None:
            raise TaskNotFoundError(str(task_id))
        if row.status != TaskStatus.RUNNING.value:
            raise PlanValidationError(f"task {row.task_id} is not running")
        task_snapshot = await self.snapshot(plan_id)
        task_data = task_snapshot["tasks"].get(task_id, {})
        if result.outcome == TaskOutcome.COMPLETED:
            missing_outputs = _missing_contract_outputs(task_data, result)
            pending_needs = [
                need.get("key") for need in task_data.get("needs", [])
                if need.get("required", True)
                and need.get("status") != RequirementStatus.RESOLVED.value
            ]
            if pending_needs:
                raise PlanValidationError(
                    f"task {task_id} cannot complete with unresolved needs: {pending_needs}"
                )
            if missing_outputs:
                raise PlanValidationError(
                    f"task {task_id} is missing required outputs: {missing_outputs}"
                )
        row.result = result.model_dump(mode="json", by_alias=True)
        row.checkpoint = dict(result.checkpoint)
        if result.outcome == TaskOutcome.COMPLETED:
            row.status = TaskStatus.COMPLETED.value
            produced = result.outputs or {}
            pending_needs = (await self.session.execute(
                select(RuntimeTaskNeed).join(RuntimePlanTask).where(
                    RuntimePlanTask.plan_id == plan_id,
                    RuntimeTaskNeed.status == RequirementStatus.PENDING.value,
                    RuntimeTaskNeed.task_row_id != row.id,
                ).with_for_update()
            )).scalars().all()
            for need in pending_needs:
                consumer_row = await self.session.get(RuntimePlanTask, need.task_row_id)
                consumer_task_id = consumer_row.task_id if consumer_row is not None else None
                if (
                    need.need_key in produced
                    and consumer_task_id is not None
                    and task_id in task_snapshot["tasks"].get(consumer_task_id, {}).get("depends_on", [])
                ):
                    need.status = RequirementStatus.RESOLVED.value
                    need.resolved_value = produced[need.need_key]
                    need.resolver_task_id = task_id
        elif result.outcome == TaskOutcome.NEEDS_DEPENDENCY:
            row.status = TaskStatus.WAITING_DEPENDENCY.value
            await self.session.execute(delete(RuntimeTaskNeed).where(RuntimeTaskNeed.task_row_id == row.id))
            for need in result.needs:
                self.session.add(RuntimeTaskNeed(
                    task_row_id=row.id,
                    need_key=need.key,
                    kind=need.kind,
                    description=need.description,
                    schema=need.json_schema,
                    need_metadata={
                        "ref": need.ref or need.key,
                        "required": need.required,
                        "context": need.context,
                    },
                    status=RequirementStatus.PENDING.value,
                ))
        else:
            row.status = TaskStatus.UNFULFILLABLE.value
        await self._refresh_status(plan_id)
        await self.session.flush()
        return row

    async def record_failure(
        self,
        plan_id: UUID,
        task_id: str,
        failure: TaskAttemptFailure,
        *,
        retry_at: Optional[datetime] = None,
        max_attempts: int = 3,
    ) -> RuntimePlanTask:
        lookup = await self.session.execute(select(RuntimePlanTask).where(
            RuntimePlanTask.plan_id == plan_id, RuntimePlanTask.task_id == task_id
        ).with_for_update())
        row = lookup.scalar_one_or_none()
        if row is None:
            raise TaskNotFoundError(str(task_id))
        attempt_result = await self.session.execute(
            select(RuntimeTaskAttempt).where(
                RuntimeTaskAttempt.task_row_id == row.id,
                RuntimeTaskAttempt.attempt_number == row.attempts,
            ).with_for_update()
        )
        attempt = attempt_result.scalar_one_or_none()
        if attempt is not None:
            attempt.status = AttemptStatus.TIMED_OUT.value if failure.timed_out else AttemptStatus.FAILED.value
            attempt.error = failure.model_dump(mode="json")
            attempt.finished_at = _now()
            attempt.next_retry_at = retry_at
        if failure.retryable and row.attempts < max_attempts:
            row.status = TaskStatus.WAITING_RETRY.value
            row.next_retry_at = retry_at
        else:
            row.status = TaskStatus.FAILED.value
        await self._refresh_status(plan_id)
        await self.session.flush()
        return row


# Public test/local implementation name. Production wiring uses SqlPlanStore
# through the same lifecycle methods and port boundary.
PlanStore = InMemoryPlanStore
