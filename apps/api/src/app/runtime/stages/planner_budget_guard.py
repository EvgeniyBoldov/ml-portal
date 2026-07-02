from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from app.runtime.budgets import BudgetExceededError, BudgetRegistry
from app.runtime.envelope import PhasedEvent
from app.runtime.events import OrchestrationPhase, RuntimeEvent


@dataclass
class BudgetGuardResult:
    ok: bool
    error_message: Optional[str] = None
    final_error: Optional[str] = None
    error_event: Optional[PhasedEvent] = None
    snapshot_event: Optional[PhasedEvent] = None


class PlannerBudgetGuard:
    @staticmethod
    def consume_step(
        *,
        planner_registry: Optional[BudgetRegistry],
        orchestrator_id: str,
        run_id: str,
    ) -> BudgetGuardResult:
        if planner_registry is None:
            return BudgetGuardResult(ok=True)
        try:
            planner_registry.consume(
                orchestrator_id,
                "planner_steps",
                1,
                reason="step",
            )
        except BudgetExceededError as exc:
            return BudgetGuardResult(
                ok=False,
                error_message=str(exc),
                final_error=f"budget_exceeded: {exc.metric}",
                error_event=PhasedEvent(
                    RuntimeEvent.error(
                        f"Planner budget exceeded: {exc.metric}",
                        recoverable=False,
                        user_message=f"Planner budget exceeded: {exc.metric}",
                        operator_message=str(exc),
                        source="runtime",
                        parent_entity_type="orchestrator",
                        parent_entity_id=orchestrator_id,
                    ),
                    OrchestrationPhase.PLANNER,
                ),
            )
        planner_payload = planner_registry.emit_snapshot(
            orchestrator_id,
            reason="step",
            delta={"planner_steps": 1},
        ) or {}
        return BudgetGuardResult(
            ok=True,
            snapshot_event=PhasedEvent(
                RuntimeEvent.budget_snapshot(
                    entity_type="orchestrator",
                    entity_id=orchestrator_id,
                    parent_entity_type="run",
                    parent_entity_id=run_id,
                    role="planner",
                    own=planner_payload.get("own", {}),
                    limits=planner_payload.get("limits"),
                    delta={"planner_steps": 1},
                    reason="step",
                    at_ms=planner_payload.get("at_ms"),
                ),
                OrchestrationPhase.PLANNER,
            ),
        )

    @staticmethod
    def consume_planner_llm_trace(
        *,
        planner_registry: Optional[BudgetRegistry],
        orchestrator_id: str,
        run_id: str,
        llm_trace: Any,
    ) -> BudgetGuardResult:
        if planner_registry is None:
            return BudgetGuardResult(ok=True)
        try:
            if llm_trace.tokens_in > 0:
                planner_registry.consume(
                    orchestrator_id,
                    "tokens_in",
                    llm_trace.tokens_in,
                    reason="tokens",
                )
            if llm_trace.tokens_out > 0:
                planner_registry.consume(
                    orchestrator_id,
                    "tokens_out",
                    llm_trace.tokens_out,
                    reason="tokens",
                )
            if llm_trace.tokens_total > 0:
                planner_registry.consume(
                    orchestrator_id,
                    "tokens_total",
                    llm_trace.tokens_total,
                    reason="tokens",
                )
            if llm_trace.duration_ms > 0:
                planner_registry.consume(
                    orchestrator_id,
                    "wall_time_ms",
                    llm_trace.duration_ms,
                    reason="wall_time",
                )
        except BudgetExceededError as exc:
            return BudgetGuardResult(
                ok=False,
                error_message=str(exc),
                final_error=f"budget_exceeded: {exc.metric}",
                error_event=PhasedEvent(
                    RuntimeEvent.error(
                        f"Planner budget exceeded: {exc.metric}",
                        recoverable=False,
                        user_message=f"Planner budget exceeded: {exc.metric}",
                        operator_message=str(exc),
                        source="runtime",
                        parent_entity_type="orchestrator",
                        parent_entity_id=orchestrator_id,
                    ),
                    OrchestrationPhase.PLANNER,
                ),
            )

        delta: Dict[str, int] = {}
        if llm_trace.tokens_in > 0:
            delta["tokens_in"] = llm_trace.tokens_in
        if llm_trace.tokens_out > 0:
            delta["tokens_out"] = llm_trace.tokens_out
        if llm_trace.tokens_total > 0:
            delta["tokens_total"] = llm_trace.tokens_total
        if llm_trace.duration_ms > 0:
            delta["wall_time_ms"] = llm_trace.duration_ms
        if not delta:
            return BudgetGuardResult(ok=True)
        planner_payload = planner_registry.emit_snapshot(
            orchestrator_id,
            reason="tokens",
            delta=delta,
        ) or {}
        return BudgetGuardResult(
            ok=True,
            snapshot_event=PhasedEvent(
                RuntimeEvent.budget_snapshot(
                    entity_type="orchestrator",
                    entity_id=orchestrator_id,
                    parent_entity_type="run",
                    parent_entity_id=run_id,
                    role="planner",
                    own=planner_payload.get("own", {}),
                    limits=planner_payload.get("limits"),
                    delta=delta,
                    reason="tokens",
                    at_ms=planner_payload.get("at_ms"),
                ),
                OrchestrationPhase.PLANNER,
            ),
        )
