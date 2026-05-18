from __future__ import annotations

from dataclasses import dataclass

from .schema import BudgetLimits


@dataclass
class SubBudgetLedger:
    owner_scope: str
    owner_id: str
    limits: BudgetLimits
    planner_iterations: int = 0
    agent_steps: int = 0
    tool_calls: int = 0
    retries: int = 0
    tokens_total: int = 0

    def snapshot(self) -> dict:
        return {
            "owner_scope": self.owner_scope,
            "owner_id": self.owner_id,
            "planner_iterations": self.planner_iterations,
            "agent_steps": self.agent_steps,
            "tool_calls": self.tool_calls,
            "retries": self.retries,
            "tokens_total": self.tokens_total,
        }
