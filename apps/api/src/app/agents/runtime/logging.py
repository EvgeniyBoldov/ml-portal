"""
Runtime logging levels — configurable verbosity for runtime execution.

Levels:
- NONE:  Only errors and critical events (minimal overhead)
- BRIEF: User request + final answer + errors (production default)
- FULL:  All steps, tool calls, reasoning, triage (sandbox/debug)

Resolution priority: sandbox_override > user > tenant > platform > agent_version > "brief"
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional, TYPE_CHECKING

from app.core.logging import get_logger
from app.core.db import get_session_factory

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.agents.context import ToolContext

logger = get_logger(__name__)


class LoggingLevel(str, Enum):
    NONE = "none"
    BRIEF = "brief"
    FULL = "full"


# Step types visible at each level
_BRIEF_STEP_TYPES = frozenset({
    "user_request", "routing_complete", "triage_complete",
    "error", "final", "final_content", "done",
})

_FULL_STEP_TYPES = frozenset({
    # All brief types +
    "user_request", "routing_complete", "triage_complete",
    "error", "final", "final_content", "done",
    # Detailed types
    "status", "thinking", "operation_call", "operation_result", "tool_call", "tool_result",
    "delta", "planner_action", "planner_fact",
    "confirmation_required", "waiting_input", "stop",
    "agent_selected", "agent_tool_loop_started",
    "synthesis_started",
})


def should_log_step(level: LoggingLevel, step_type: str) -> bool:
    """Check if a step type should be logged at the given level."""
    if level == LoggingLevel.NONE:
        return step_type == "error"
    if level == LoggingLevel.BRIEF:
        return step_type in _BRIEF_STEP_TYPES
    # FULL — log everything
    return True


def should_emit_event(level: LoggingLevel, event_type: str) -> bool:
    """Check if an SSE event should be emitted at the given level.

    SSE events are always emitted for delta/final/error/done regardless of level.
    Other events (tool_call, thinking, etc.) depend on level.
    """
    # Always emit these (client needs them for rendering)
    always_emit = {"delta", "final", "final_content", "error", "done",
                   "routing_complete", "triage_complete"}
    if event_type in always_emit:
        return True
    if level == LoggingLevel.FULL:
        return True
    if level == LoggingLevel.BRIEF:
        return event_type in {"status", "user_message"}
    # NONE — only always_emit
    return False


class LoggingConfig:
    """Resolve effective logging level from context hierarchy."""

    @staticmethod
    async def resolve(
        ctx: ToolContext,
        agent_logging_level: Optional[str] = None,
    ) -> LoggingLevel:
        """Resolve effective logging level.

        Priority: sandbox_override > user > tenant > platform > agent_version > "brief"
        """
        # 1. Sandbox override (always full)
        sandbox_ov = ctx.extra.get("sandbox_overrides", {})
        sandbox_level = sandbox_ov.get("logging_level")
        if sandbox_level:
            try:
                return LoggingLevel(sandbox_level)
            except ValueError:
                pass

        # 2. User preference (from ctx.extra if set)
        user_level = ctx.extra.get("logging_level")
        if user_level:
            try:
                return LoggingLevel(user_level)
            except ValueError:
                pass

        # 3. Tenant / Platform settings (from DB)
        runtime_deps = None
        get_runtime_deps = getattr(ctx, "get_runtime_deps", None)
        if callable(get_runtime_deps):
            try:
                runtime_deps = get_runtime_deps()
            except Exception:
                runtime_deps = None
        session_factory = (
            getattr(runtime_deps, "session_factory", None)
            if runtime_deps is not None
            else None
        )
        if session_factory is None:
            try:
                session_factory = get_session_factory()
            except RuntimeError:
                session_factory = None
        if session_factory:
            try:
                from app.services.platform_settings_service import (
                    PlatformSettingsProvider,
                )
                async with session_factory() as session:
                    platform_config = await PlatformSettingsProvider.get_instance().get_config(session)
                    platform_level = platform_config.get("default_logging_level")
                    if platform_level:
                        return LoggingLevel(platform_level)
            except (ValueError, Exception) as e:
                logger.debug(f"Failed to resolve platform logging level: {e}")

        # 4. Agent version level
        if agent_logging_level:
            try:
                return LoggingLevel(agent_logging_level)
            except ValueError:
                pass

        # 5. Default
        return LoggingLevel.BRIEF
