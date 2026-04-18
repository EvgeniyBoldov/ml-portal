from __future__ import annotations

from typing import Any, AsyncGenerator, Dict, Optional

from app.agents.runtime.events import RuntimeEvent, RuntimeEventType
from app.core.logging import get_logger
from app.services.runtime_terminal_status import planner_terminal_from_event

logger = get_logger(__name__)


class RuntimePlannerOrchestrator:
    """Coordinates planner streaming and planner fail-open/fail-closed behavior."""

    def __init__(self, trace_logger: Any) -> None:
        self.trace_logger = trace_logger
        self.last_status: str = "completed"
        self.last_error: Optional[str] = None

    @staticmethod
    def _planner_fail_open_enabled(platform_config: Dict[str, Any]) -> bool:
        return bool((platform_config or {}).get("planner_fail_open", False))

    @staticmethod
    def _planner_fail_open_message(platform_config: Dict[str, Any]) -> str:
        msg = str((platform_config or {}).get("planner_fail_open_message") or "").strip()
        if msg:
            return msg
        return (
            "Во время выполнения произошла ошибка планировщика. "
            "Попробуйте повторить запрос позже."
        )

    async def _handle_planner_error(
        self,
        *,
        error: Exception,
        platform_config: Dict[str, Any],
        exec_request: Any,
        pipeline_run: Any,
    ) -> bool:
        if self._planner_fail_open_enabled(platform_config):
            logger.warning("[Pipeline] Planner failed (fail-open): %s", error)
            await pipeline_run.log_step(
                "planner_fallback_final",
                {"error": str(error), "policy": "fail_open"},
            )
            return True

        await self.trace_logger.log_error(
            pipeline_run.run_id,
            stage="planner",
            error=error,
            data={
                "error_type": "planner_error",
                "policy": "fail_closed",
                "run_id": str(exec_request.run_id),
            },
        )
        return False

    async def stream(
        self,
        *,
        execute_planner_use_case: Any,
        exec_request: Any,
        messages: list[dict[str, Any]],
        ctx: Any,
        model: Optional[str],
        enable_logging: bool,
        platform_config: Dict[str, Any],
        pipeline_run: Any,
        state_store: Optional[Any] = None,
        state_chat_id: Optional[str] = None,
        state_tenant_id: Optional[str] = None,
    ) -> AsyncGenerator[RuntimeEvent, None]:
        self.last_status = "completed"
        self.last_error = None
        try:
            async for event in execute_planner_use_case.execute(
                exec_request=exec_request,
                messages=messages,
                ctx=ctx,
                model=model,
                enable_logging=enable_logging,
            ):
                terminal = planner_terminal_from_event(event)
                if terminal:
                    status, terminal_error = terminal
                    self.last_status = status.value
                    self.last_error = terminal_error
                    if state_store:
                        try:
                            await state_store.update(
                                exec_request.run_id,
                                chat_id=state_chat_id,
                                tenant_id=state_tenant_id,
                                patch={
                                    "run_status": self.last_status,
                                    "meta": {
                                        "stage": "planner_terminal",
                                        "terminal_error": self.last_error,
                                    },
                                },
                            )
                        except Exception as state_error:
                            logger.warning("Failed to persist planner terminal state: %s", state_error)
                if event.type == RuntimeEventType.PLANNER_ACTION and state_store:
                    try:
                        await state_store.update(
                            exec_request.run_id,
                            chat_id=state_chat_id,
                            tenant_id=state_tenant_id,
                            current_phase_id=str(event.data.get("phase_id") or "") or None,
                            current_agent_slug=str(event.data.get("agent_slug") or "") or None,
                            patch={
                                "run_status": "planner_running",
                                "meta": {
                                    "stage": "planner_action",
                                    "action_type": event.data.get("action_type"),
                                    "iteration": event.data.get("iteration"),
                                },
                            },
                        )
                    except Exception as state_error:
                        logger.warning("Failed to persist planner action state: %s", state_error)
                if event.type == RuntimeEventType.FINAL:
                    event.data.setdefault("run_id", str(exec_request.run_id))
                yield event
        except Exception as error:
            handled = await self._handle_planner_error(
                error=error,
                platform_config=platform_config,
                exec_request=exec_request,
                pipeline_run=pipeline_run,
            )
            if handled:
                self.last_status = "completed"
                self.last_error = None
                if state_store:
                    try:
                        await state_store.update(
                            exec_request.run_id,
                            chat_id=state_chat_id,
                            tenant_id=state_tenant_id,
                            patch={"run_status": "completed", "meta": {"stage": "planner_degraded"}},
                        )
                    except Exception as state_error:
                        logger.warning("Failed to persist planner degraded state: %s", state_error)
                yield RuntimeEvent.status("planner_degraded")
                yield RuntimeEvent.final(
                    self._planner_fail_open_message(platform_config),
                    sources=[],
                    run_id=str(exec_request.run_id),
                )
            else:
                self.last_status = "failed"
                self.last_error = str(error)
                if state_store:
                    try:
                        await state_store.update(
                            exec_request.run_id,
                            chat_id=state_chat_id,
                            tenant_id=state_tenant_id,
                            patch={
                                "run_status": "failed",
                                "meta": {"stage": "planner_failed", "planner_error": self.last_error},
                            },
                        )
                    except Exception as state_error:
                        logger.warning("Failed to persist planner failed state: %s", state_error)
                yield RuntimeEvent.error(f"Planner failed: {error}")
