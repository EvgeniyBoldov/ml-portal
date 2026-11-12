"""Durable admission guard for non-cacheable runtime tool calls.

The guard is a versioned sibling envelope on RuntimeTaskAttempt.execution_result.
It records fingerprints and outcomes only; arguments, credentials and tool bodies
remain in their existing, bounded result surfaces.
"""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.runtime_plan import RuntimePlan, RuntimePlanTask, RuntimeTaskAttempt


GUARD_KEY = "operation_guard"
GUARD_VERSION = 1


class RuntimeExecutionGuardError(RuntimeError):
    """Admission could not be made durable or the request is already guarded."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _fingerprint(operation: str, target: str, arguments: dict[str, Any]) -> str:
    payload = f"{operation}\0{target}\0{_canonical_json(arguments)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _read_envelope(value: Any, *, present: bool) -> dict[str, Any]:
    if not present:
        return {"version": GUARD_VERSION, "calls": {}}
    if not isinstance(value, dict) or value.get("version") != GUARD_VERSION or not isinstance(value.get("calls"), dict):
        raise RuntimeExecutionGuardError("execution_guard_invalid", "Saved execution guard is invalid; tool execution is blocked.")
    for key, call in value["calls"].items():
        if not isinstance(key, str) or not isinstance(call, dict) or call.get("status") not in {"admitted", "completed", "unknown"}:
            raise RuntimeExecutionGuardError("execution_guard_invalid", "Saved execution guard is invalid; tool execution is blocked.")
    return value


class RuntimeExecutionGuardService:
    """Short-transaction operation admission and completion recorder."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession], *, root_run_id: UUID,
                 task_id: str, expected_attempt_number: int) -> None:
        self._session_factory = session_factory
        self.root_run_id = root_run_id
        self.task_id = task_id
        self.expected_attempt_number = expected_attempt_number

    async def _lineage(self, session: AsyncSession, plan: RuntimePlan, task: RuntimePlanTask) -> list[RuntimePlanTask]:
        rows = (await session.execute(select(RuntimePlanTask).where(RuntimePlanTask.plan_id == plan.id))).scalars().all()
        by_id = {row.task_id: row for row in rows}
        lineage: list[RuntimePlanTask] = []
        seen: set[str] = set()
        current: RuntimePlanTask | None = task
        while current is not None:
            if current.task_id in seen:
                raise RuntimeExecutionGuardError("execution_guard_invalid", "Task continuation lineage is invalid; tool execution is blocked.")
            seen.add(current.task_id)
            lineage.append(current)
            if current.continuation_of and current.continuation_of not in by_id:
                raise RuntimeExecutionGuardError("execution_guard_invalid", "Task continuation lineage is incomplete; tool execution is blocked.")
            current = by_id.get(current.continuation_of) if current.continuation_of else None
        return lineage

    async def _current(self, session: AsyncSession, *, lock: bool) -> tuple[RuntimePlan, RuntimePlanTask, RuntimeTaskAttempt]:
        plan_query = select(RuntimePlan).where(RuntimePlan.root_run_id == self.root_run_id)
        if lock:
            plan_query = plan_query.with_for_update()
        plan = (await session.execute(plan_query)).scalar_one_or_none()
        if plan is None:
            raise RuntimeExecutionGuardError("execution_guard_unavailable", "Durable execution guard is unavailable; tool execution is blocked.")
        if plan.status != "active":
            raise RuntimeExecutionGuardError("execution_guard_stale", "Runtime plan is no longer active; tool execution is blocked.")
        task_query = select(RuntimePlanTask).where(
            RuntimePlanTask.plan_id == plan.id, RuntimePlanTask.task_id == self.task_id,
        )
        if lock:
            task_query = task_query.with_for_update()
        task = (await session.execute(task_query)).scalar_one_or_none()
        if (task is None or task.status != "running" or task.attempts < 1
                or task.attempts != self.expected_attempt_number):
            raise RuntimeExecutionGuardError("execution_guard_stale", "Task execution claim is no longer current; tool execution is blocked.")
        attempt_query = select(RuntimeTaskAttempt).where(
            RuntimeTaskAttempt.task_row_id == task.id,
            RuntimeTaskAttempt.attempt_number == task.attempts,
        )
        if lock:
            attempt_query = attempt_query.with_for_update()
        attempt = (await session.execute(attempt_query)).scalar_one_or_none()
        if (attempt is None or attempt.status != "running"
                or attempt.attempt_number != self.expected_attempt_number):
            raise RuntimeExecutionGuardError("execution_guard_stale", "Task attempt is no longer current; tool execution is blocked.")
        return plan, task, attempt

    async def _prior_calls(self, session: AsyncSession, plan: RuntimePlan, task: RuntimePlanTask) -> dict[str, dict[str, Any]]:
        lineage = await self._lineage(session, plan, task)
        prior: dict[str, dict[str, Any]] = {}
        for ancestor in reversed(lineage):
            attempts = (await session.execute(select(RuntimeTaskAttempt).where(
                RuntimeTaskAttempt.task_row_id == ancestor.id,
            ).order_by(RuntimeTaskAttempt.attempt_number))).scalars().all()
            for attempt in attempts:
                execution = attempt.execution_result
                if execution is not None and not isinstance(execution, dict):
                    raise RuntimeExecutionGuardError("execution_guard_invalid", "Saved execution guard is invalid; tool execution is blocked.")
                envelope = _read_envelope(
                    execution.get(GUARD_KEY) if isinstance(execution, dict) else None,
                    present=isinstance(execution, dict) and GUARD_KEY in execution,
                )
                prior.update(envelope["calls"])
        return prior

    async def admit(self, *, operation: str, target: str, arguments: dict[str, Any]) -> str:
        key = _fingerprint(operation, target, arguments)
        async with self._session_factory() as session:
            async with session.begin():
                plan, task, attempt = await self._current(session, lock=True)
                prior = await self._prior_calls(session, plan, task)
                previous = prior.get(key)
                if previous is not None:
                    status = str(previous.get("status"))
                    code = "tool_outcome_unknown" if status in {"admitted", "unknown"} else "duplicate_execution_blocked"
                    message = ("A prior matching operation may have executed; verify its result before retrying."
                               if code == "tool_outcome_unknown" else
                               "This matching operation already ran; its original outcome is in the task receipt, so it was not repeated.")
                    raise RuntimeExecutionGuardError(code, message)
                raw = attempt.execution_result
                if raw is None:
                    raw = {}
                if not isinstance(raw, dict):
                    raise RuntimeExecutionGuardError("execution_guard_invalid", "Saved execution guard is invalid; tool execution is blocked.")
                envelope = deepcopy(_read_envelope(raw.get(GUARD_KEY), present=GUARD_KEY in raw))
                envelope["calls"][key] = {"status": "admitted"}
                attempt.execution_result = {**raw, GUARD_KEY: envelope}
                await session.flush()
        return key

    async def complete(self, key: str, *, success: bool | None = None) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                plan, task, attempt = await self._current(session, lock=True)
                raw = attempt.execution_result
                if raw is None:
                    raw = {}
                if not isinstance(raw, dict):
                    raise RuntimeExecutionGuardError("execution_guard_invalid", "Saved execution guard is invalid; tool execution is blocked.")
                envelope = deepcopy(_read_envelope(raw.get(GUARD_KEY), present=GUARD_KEY in raw))
                call = envelope["calls"].get(key)
                if call is None:
                    raise RuntimeExecutionGuardError("execution_guard_fence", "Execution guard admission was lost; tool result cannot be recorded safely.")
                call["status"] = "unknown" if success is None else "completed"
                call["outcome"] = "unknown" if success is None else "succeeded" if success else "failed"
                attempt.execution_result = {**raw, GUARD_KEY: envelope}
                await session.flush()
