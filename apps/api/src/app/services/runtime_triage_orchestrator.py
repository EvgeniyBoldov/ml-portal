from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Optional

from app.agents.contracts import RuntimeTriageDecision
from app.core.logging import get_logger

logger = get_logger(__name__)


class RuntimeTriageOrchestrator:
    """Coordinates triage execution and fail-open/fail-closed policy."""

    def __init__(self, trace_logger: Any) -> None:
        self.trace_logger = trace_logger

    @staticmethod
    def _triage_fail_open_enabled(platform_config: Dict[str, Any]) -> bool:
        return bool((platform_config or {}).get("triage_fail_open", True))

    async def execute(
        self,
        *,
        run_triage: Callable[..., Awaitable[RuntimeTriageDecision]],
        request_text: str,
        messages: List[Dict[str, Any]],
        platform_config: Dict[str, Any],
        routable_agents: Optional[List[Any]],
        pipeline_run: Any,
    ) -> Optional[RuntimeTriageDecision]:
        try:
            result = await run_triage(
                request_text=request_text,
                messages=messages,
                platform_config=platform_config,
                routable_agents=routable_agents,
            )
            return RuntimeTriageDecision.model_validate(result)
        except Exception as error:
            if self._triage_fail_open_enabled(platform_config):
                logger.warning("[Pipeline] Triage failed (fail-open): %s", error)
                await pipeline_run.log_step(
                    "triage_fallback_orchestrate",
                    {"error": str(error), "policy": "fail_open"},
                )
                return RuntimeTriageDecision(
                    type="orchestrate",
                    confidence=0.0,
                    goal=request_text,
                    inputs={},
                )

            logger.error("[Pipeline] Triage failed (fail-closed): %s", error, exc_info=True)
            await self.trace_logger.log_error(
                pipeline_run.run_id,
                stage="triage",
                error=error,
                data={"error_type": "triage_error", "policy": "fail_closed"},
            )
            await pipeline_run.finish("failed", str(error))
            return None
