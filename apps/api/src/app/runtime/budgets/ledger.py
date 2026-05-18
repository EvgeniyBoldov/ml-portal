from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional, Literal

from .errors import BudgetExceededError
from .schema import BudgetLimits, EntityLimits, RunLimits
from .sub_ledger import SubBudgetLedger

BudgetEmitCallback = Callable[[dict], None]


class RunBudgetLedger:
    """Single mutable budget ledger for one runtime run.

    This class intentionally keeps the old tracker-like API so existing runtime
    call-sites can migrate without behavior changes.
    """

    def __init__(self, *, limits: BudgetLimits, emit: Optional[BudgetEmitCallback] = None) -> None:
        self.budget = limits
        self._emit = emit
        self._started_at = time.monotonic()
        self._planner_iterations = 0
        self._agent_steps = 0
        self._tool_calls = 0
        self._retries = 0
        self._tokens_in = 0
        self._tokens_out = 0
        self._tokens_total = 0
        self._subs: Dict[str, SubBudgetLedger] = {}

    def register_sub(self, *, owner_scope: str, owner_id: str, limits: Optional[BudgetLimits] = None) -> SubBudgetLedger:
        sub = SubBudgetLedger(owner_scope=owner_scope, owner_id=owner_id, limits=limits or self.budget)
        self._subs[owner_id] = sub
        return sub

    def remaining_wall_time_ms(self) -> int:
        elapsed = int((time.monotonic() - self._started_at) * 1000)
        return max(0, self.budget.max_wall_time_ms - elapsed)

    def can_run_planner_iteration(self) -> bool:
        return self._planner_iterations < self.budget.max_planner_iterations and self.remaining_wall_time_ms() > 0

    def record_planner_iteration(self, *, owner_id: Optional[str] = None) -> None:
        self._planner_iterations += 1
        if owner_id and owner_id in self._subs:
            self._subs[owner_id].planner_iterations += 1
        self._emit_snapshot(owner_scope="orchestrator", owner_id=owner_id, reason="planner_iteration", delta={"planner_iterations": 1})

    def can_run_agent_step(self) -> bool:
        return self._agent_steps < self.budget.max_agent_steps and self.remaining_wall_time_ms() > 0

    def record_agent_step(self, *, owner_id: Optional[str] = None) -> None:
        self._agent_steps += 1
        if owner_id and owner_id in self._subs:
            self._subs[owner_id].agent_steps += 1
        self._emit_snapshot(owner_scope="agent", owner_id=owner_id, reason="agent_step", delta={"agent_steps": 1})

    def can_consume_tool_call(self) -> bool:
        return self._tool_calls < self.budget.max_tool_calls_total and self.remaining_wall_time_ms() > 0

    def record_tool_call(self, *, owner_id: Optional[str] = None) -> None:
        self._tool_calls += 1
        if owner_id and owner_id in self._subs:
            self._subs[owner_id].tool_calls += 1
        self._emit_snapshot(owner_scope="agent", owner_id=owner_id, reason="tool_call", delta={"tool_calls": 1})

    def record_retry(self, *, owner_id: Optional[str] = None) -> None:
        self._retries += 1
        if owner_id and owner_id in self._subs:
            self._subs[owner_id].retries += 1
        self._emit_snapshot(owner_scope="agent", owner_id=owner_id, reason="retry", delta={"retries": 1})

    def record_tokens(self, *, tokens_in: int = 0, tokens_out: int = 0, owner_id: Optional[str] = None) -> None:
        in_used = max(0, int(tokens_in))
        out_used = max(0, int(tokens_out))
        total_used = in_used + out_used
        if self.budget.max_tokens_total is not None and (self._tokens_total + total_used) > self.budget.max_tokens_total:
            raise BudgetExceededError(
                scope="agent",
                metric="tokens_total",
                used=self._tokens_total + total_used,
                limit=self.budget.max_tokens_total,
            )
        self._tokens_in += in_used
        self._tokens_out += out_used
        self._tokens_total += total_used
        if owner_id and owner_id in self._subs:
            self._subs[owner_id].tokens_total += total_used
        self._emit_snapshot(
            owner_scope="agent",
            owner_id=owner_id,
            reason="tokens",
            delta={"tokens_in": in_used, "tokens_out": out_used, "tokens_total": total_used},
        )

    def consume(self, metric: str, amount: int, *, owner_scope: str, owner_id: Optional[str] = None, reason: str = "consume") -> None:
        if amount <= 0:
            return
        if metric == "planner_iterations":
            if self._planner_iterations + amount > self.budget.max_planner_iterations:
                raise BudgetExceededError(scope=owner_scope, metric=metric, used=self._planner_iterations + amount, limit=self.budget.max_planner_iterations)
            for _ in range(amount):
                self.record_planner_iteration(owner_id=owner_id)
            return
        if metric == "agent_steps":
            if self._agent_steps + amount > self.budget.max_agent_steps:
                raise BudgetExceededError(scope=owner_scope, metric=metric, used=self._agent_steps + amount, limit=self.budget.max_agent_steps)
            for _ in range(amount):
                self.record_agent_step(owner_id=owner_id)
            return
        if metric == "tool_calls":
            if self._tool_calls + amount > self.budget.max_tool_calls_total:
                raise BudgetExceededError(scope=owner_scope, metric=metric, used=self._tool_calls + amount, limit=self.budget.max_tool_calls_total)
            for _ in range(amount):
                self.record_tool_call(owner_id=owner_id)
            return
        if metric == "retries":
            if self._retries + amount > self.budget.max_retries:
                raise BudgetExceededError(scope=owner_scope, metric=metric, used=self._retries + amount, limit=self.budget.max_retries)
            for _ in range(amount):
                self.record_retry(owner_id=owner_id)
            return
        if metric == "tokens_total":
            self.record_tokens(tokens_in=0, tokens_out=amount, owner_id=owner_id)
            return

    def snapshot(self) -> dict:
        used_wall_time = max(0, self.budget.max_wall_time_ms - self.remaining_wall_time_ms())
        return {
            "max_planner_iterations": self.budget.max_planner_iterations,
            "max_agent_steps": self.budget.max_agent_steps,
            "max_tool_calls_total": self.budget.max_tool_calls_total,
            "max_wall_time_ms": self.budget.max_wall_time_ms,
            "per_tool_timeout_ms": self.budget.per_tool_timeout_ms,
            "max_steps_without_success": self.budget.max_steps_without_success,
            "loop_threshold": self.budget.loop_threshold,
            "consumed_planner_iterations": self._planner_iterations,
            "consumed_agent_steps": self._agent_steps,
            "consumed_tool_calls": self._tool_calls,
            "remaining_wall_time_ms": self.remaining_wall_time_ms(),
            "used_wall_time_ms": used_wall_time,
            "consumed_retries": self._retries,
            "tokens_in": self._tokens_in,
            "tokens_out": self._tokens_out,
            "tokens_total": self._tokens_total,
        }

    def _emit_snapshot(self, *, owner_scope: str, owner_id: Optional[str], reason: str, delta: dict) -> None:
        if self._emit is None:
            return
        snap = self.snapshot()
        payload = {
            "owner_scope": owner_scope,
            "owner_id": owner_id,
            "reason": reason,
            "delta": delta,
            "snapshot": {
                "planner_iterations": {
                    "used": snap["consumed_planner_iterations"],
                    "limit": self.budget.max_planner_iterations,
                    "remaining": self.budget.max_planner_iterations - snap["consumed_planner_iterations"],
                },
                "agent_steps": {
                    "used": snap["consumed_agent_steps"],
                    "limit": self.budget.max_agent_steps,
                    "remaining": self.budget.max_agent_steps - snap["consumed_agent_steps"],
                },
                "tool_calls": {
                    "used": snap["consumed_tool_calls"],
                    "limit": self.budget.max_tool_calls_total,
                    "remaining": self.budget.max_tool_calls_total - snap["consumed_tool_calls"],
                },
                "wall_time_ms": {
                    "used": snap["used_wall_time_ms"],
                    "limit": self.budget.max_wall_time_ms,
                    "remaining": snap["remaining_wall_time_ms"],
                },
                "retries": {
                    "used": snap["consumed_retries"],
                    "limit": self.budget.max_retries,
                    "remaining": self.budget.max_retries - snap["consumed_retries"],
                },
                "tokens_in": {
                    "used": snap["tokens_in"],
                    "limit": None,
                    "remaining": None,
                },
                "tokens_out": {
                    "used": snap["tokens_out"],
                    "limit": None,
                    "remaining": None,
                },
                "tokens_total": {
                    "used": snap["tokens_total"],
                    "limit": self.budget.max_tokens_total,
                    "remaining": (
                        None
                        if self.budget.max_tokens_total is None
                        else self.budget.max_tokens_total - snap["tokens_total"]
                    ),
                },
            },
            "at_ms": int(time.time() * 1000),
        }
        self._emit(payload)


MetricName = Literal[
    "planner_steps",
    "agent_steps",
    "tool_calls",
    "tokens_in",
    "tokens_out",
    "tokens_total",
    "retries",
    "wall_time_ms",
]


@dataclass
class EntityLedger:
    """Per-entity counters for the new budget model."""

    entity_type: str
    entity_id: str
    parent_entity_id: Optional[str]
    role: Optional[str] = None
    limits: Optional[EntityLimits] = None
    started_at_monotonic: float = field(default_factory=time.monotonic)
    own: Dict[str, int] = field(default_factory=dict)

    def consume(self, metric: MetricName, amount: int = 1, *, reason: str = "consume") -> None:
        if amount <= 0:
            return
        current = int(self.own.get(metric, 0))
        next_used = current + int(amount)
        limit = self._limit_of(metric)
        if limit is not None and next_used > limit:
            raise BudgetExceededError(scope="orchestrator", metric=metric, used=next_used, limit=limit)
        self.own[metric] = next_used

    def can_consume(self, metric: MetricName, amount: int = 1) -> bool:
        limit = self._limit_of(metric)
        if limit is None:
            return True
        return int(self.own.get(metric, 0)) + max(0, int(amount)) <= limit

    def _limit_of(self, metric: MetricName) -> Optional[int]:
        if self.limits is None:
            return None
        return getattr(self.limits, metric, None)

    def snapshot_payload(self, *, reason: str, at_ms: Optional[int] = None, delta: Optional[Dict[str, int]] = None) -> dict:
        limits_payload = None
        if self.limits is not None:
            limits_payload = {
                "planner_steps": self.limits.planner_steps,
                "agent_steps": self.limits.agent_steps,
                "tool_calls": self.limits.tool_calls,
                "tokens_total": self.limits.tokens_total,
                "retries": self.limits.retries,
                "wall_time_ms": self.limits.wall_time_ms,
            }
            limits_payload = {k: v for k, v in limits_payload.items() if v is not None}
        return {
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "parent_entity_id": self.parent_entity_id,
            "role": self.role,
            "reason": reason,
            "at_ms": at_ms if at_ms is not None else int(time.time() * 1000),
            "own": dict(self.own),
            "limits": limits_payload,
            "delta": dict(delta or {}),
        }


class BudgetRegistry:
    """Run-wide registry of entity ledgers with run-cap checks."""

    def __init__(self, *, run_limits: RunLimits, emit: Optional[BudgetEmitCallback] = None) -> None:
        self.run_limits = run_limits
        self._emit = emit
        self._ledgers: Dict[str, EntityLedger] = {}

    def register(
        self,
        *,
        entity_type: str,
        entity_id: str,
        parent_entity_id: Optional[str],
        role: Optional[str] = None,
        limits: Optional[EntityLimits] = None,
    ) -> EntityLedger:
        existing = self._ledgers.get(entity_id)
        if existing is not None:
            return existing
        ledger = EntityLedger(
            entity_type=entity_type,
            entity_id=entity_id,
            parent_entity_id=parent_entity_id,
            role=role,
            limits=limits,
        )
        self._ledgers[entity_id] = ledger
        return ledger

    def get(self, entity_id: str) -> EntityLedger:
        return self._ledgers[entity_id]

    def consume(self, entity_id: str, metric: MetricName, amount: int = 1, *, reason: str) -> None:
        ledger = self.get(entity_id)
        ledger.consume(metric, amount, reason=reason)
        agg = self.aggregated_used()
        run_limit = getattr(self.run_limits, metric, None)
        if run_limit is not None and int(agg.get(metric, 0)) > run_limit:
            raise BudgetExceededError(scope="run", metric=metric, used=int(agg.get(metric, 0)), limit=run_limit)
        self.emit_snapshot(entity_id, reason=reason, delta={metric: amount})

    def aggregated_used(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for ledger in self._ledgers.values():
            for key, value in ledger.own.items():
                out[key] = int(out.get(key, 0)) + int(value)
        return out

    def emit_snapshot(self, entity_id: str, *, reason: str, delta: Optional[Dict[str, int]] = None) -> Optional[dict]:
        if entity_id not in self._ledgers:
            return None
        payload = self._ledgers[entity_id].snapshot_payload(reason=reason, delta=delta)
        if self._emit is not None:
            self._emit(payload)
        return payload
