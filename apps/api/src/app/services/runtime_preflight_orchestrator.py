from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

from app.agents.execution_preflight import AgentUnavailableError
from app.agents.runtime.events import RuntimeEvent
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class PreflightOutcome:
    exec_request: Optional[Any] = None
    events: List[RuntimeEvent] = field(default_factory=list)
    should_stop: bool = False


class RuntimePreflightOrchestrator:
    """Coordinates execution preflight and fail-open/fail-closed behavior."""

    def __init__(self, trace_logger: Any) -> None:
        self.trace_logger = trace_logger

    @staticmethod
    def _preflight_fail_open_enabled(platform_config: Dict[str, Any]) -> bool:
        return bool((platform_config or {}).get("preflight_fail_open", False))

    @staticmethod
    def _preflight_fail_open_message(platform_config: Dict[str, Any]) -> str:
        msg = str((platform_config or {}).get("preflight_fail_open_message") or "").strip()
        if msg:
            return msg
        return (
            "Не удалось подготовить выполнение с инструментами. "
            "Сформулируйте запрос иначе или обратитесь к администратору."
        )

    async def execute(
        self,
        *,
        prepare_execution: Callable[..., Awaitable[Any]],
        prepare_kwargs: Dict[str, Any],
        platform_config: Dict[str, Any],
        pipeline_run: Any,
    ) -> PreflightOutcome:
        try:
            exec_request = await prepare_execution(**prepare_kwargs)
            return PreflightOutcome(exec_request=exec_request)
        except AgentUnavailableError as error:
            await self.trace_logger.log_error(
                pipeline_run.run_id,
                stage="preflight",
                error=error,
                data={"error_type": "agent_unavailable"},
            )
            await pipeline_run.finish("failed", str(error))
            return PreflightOutcome(
                events=[RuntimeEvent.error(str(error))],
                should_stop=True,
            )
        except Exception as error:
            if self._preflight_fail_open_enabled(platform_config):
                logger.warning("[Pipeline] Preflight failed (fail-open): %s", error)
                await pipeline_run.log_step(
                    "preflight_fallback_final",
                    {"error": str(error), "policy": "fail_open"},
                )
                await pipeline_run.finish("completed")
                return PreflightOutcome(
                    events=[
                        RuntimeEvent.status("preflight_degraded"),
                        RuntimeEvent.final(
                            self._preflight_fail_open_message(platform_config),
                            sources=[],
                            run_id=str(pipeline_run.run_id) if pipeline_run.run_id else None,
                        ),
                    ],
                    should_stop=True,
                )

            await self.trace_logger.log_error(
                pipeline_run.run_id,
                stage="preflight",
                error=error,
                data={"error_type": "preflight_error", "policy": "fail_closed"},
            )
            await pipeline_run.finish("failed", str(error))
            return PreflightOutcome(
                events=[RuntimeEvent.error(f"Preflight failed: {error}")],
                should_stop=True,
            )
