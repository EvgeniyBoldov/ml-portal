from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional, Literal

from .errors import BudgetExceededError
from .schema import EntityLimits, RunLimits

BudgetEmitCallback = Callable[[dict], None]


MetricName = Literal[
    "plan_revisions",
    "task_attempts",
    "agent_runs",
    "llm_calls",
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
                "plan_revisions": self.limits.plan_revisions,
                "task_attempts": self.limits.task_attempts,
                "agent_runs": self.limits.agent_runs,
                "llm_calls": self.limits.llm_calls,
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
