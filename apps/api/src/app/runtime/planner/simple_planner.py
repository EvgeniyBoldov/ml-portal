"""Small deterministic planner used by the first canonical orchestrator cutover.

It deliberately consumes the existing short agent catalogue only.  The full
LLM DAG planner can replace this implementation behind ``PlannerPort`` without
changing orchestration or task contracts.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

from app.runtime.orchestrator_contracts import PlanPatch, PlanRequest, PlannedTask


class SimplePlanner:
    """Create a single executable task from the current short agent summaries."""

    def create_or_revise(self, *, request: PlanRequest) -> PlanPatch:
        current = request.plan or {}
        revision = int(current.get("revision") or 0)
        tasks = current.get("tasks") if isinstance(current.get("tasks"), dict) else {}
        if tasks:
            # The bootstrap planner does not rewrite a valid graph.  The
            # orchestrator can ask the eventual LLM planner for a patch later.
            return PlanPatch(expected_revision=revision, decision="revise_plan")

        selected = self._select_agent(request.available_agents)
        if selected is None:
            return PlanPatch(expected_revision=revision, decision="fail_plan", failure_reason="No executable agent is available")
        slug = str(selected.get("slug"))
        task_id = f"task-{slug}-1"
        return PlanPatch(
            expected_revision=revision,
            decision="create_plan" if revision == 0 else "revise_plan",
            tasks=[
                PlannedTask(
                    task_id=task_id,
                    title=f"Выполнить задачу агентом {slug}",
                    objective=request.goal,
                    agent_slug=slug,
                    inputs={"query": request.goal},
                )
            ],
        )

    async def plan(self, *, request: PlanRequest, **_: Any) -> PlanPatch:
        return self.create_or_revise(request=request)

    @staticmethod
    def _select_agent(agents: List[Dict[str, Any]]) -> Dict[str, Any] | None:
        usable = [item for item in agents if str(item.get("slug") or "").strip()]
        if not usable:
            return None
        # Explicit default/main agents win; otherwise preserve platform order.
        for item in usable:
            slug = str(item.get("slug") or "").lower()
            if slug in {"default", "general", "assistant"}:
                return item
        return usable[0]
