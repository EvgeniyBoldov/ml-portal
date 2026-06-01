from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from app.runtime.ports import PlannerServicePort
from app.runtime.turn_state import RuntimeTurnState


class PlannerNextStepInvoker:
    @staticmethod
    async def invoke(
        *,
        planner: PlannerServicePort,
        runtime_state: RuntimeTurnState,
        available_agents: List[Dict[str, Any]],
        outline: Optional[Dict[str, Any]],
        platform_config: Dict[str, Any],
        chat_id: Optional[UUID],
        tenant_id: UUID,
        user_id: UUID,
        agent_run_id: UUID,
        planner_iteration_id: str,
        sandbox_overrides: Optional[Dict[str, Any]],
    ) -> Tuple[Any, list[Any]]:
        planner_result = await planner.next_step(
            runtime_state=runtime_state,
            available_agents=available_agents,
            outline=outline,
            platform_config=platform_config,
            chat_id=chat_id,
            tenant_id=tenant_id,
            user_id=user_id,
            agent_run_id=agent_run_id,
            planner_iteration_id=planner_iteration_id,
            sandbox_overrides=sandbox_overrides,
        )
        if isinstance(planner_result, tuple):
            step = planner_result[0]
            traces = planner_result[1] if len(planner_result) > 1 else []
            if traces is None:
                traces = []
            elif not isinstance(traces, (list, tuple)):
                traces = [traces]
            return step, list(traces)
        return planner_result, []
