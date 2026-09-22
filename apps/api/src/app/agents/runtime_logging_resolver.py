"""Resolve the level configured on the concrete agent."""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from app.services.runtime_event_logger import RuntimeLoggingLevel

if TYPE_CHECKING:
    from app.agents.context import ToolContext


class RuntimeLoggingResolver:
    async def resolve_logging_level(
        self,
        ctx: "ToolContext",
        agent_logging_level: Optional[str] = None,
    ) -> RuntimeLoggingLevel:
        # A task executor may already have created an agent_execution scope.
        # Its level is the authoritative observation policy for every nested
        # runtime invocation.  Do not re-resolve it from a model attribute and
        # accidentally downgrade an observed child.  A chat root at ``none``
        # is deliberately not inherited: a directly invoked agent must still
        # use its configured level to establish its first scope.
        inherited = getattr(ctx, "extra", {}).get("runtime_event_logger")
        context = getattr(inherited, "context", None)
        if context is not None:
            if getattr(context, "origin", None) == "sandbox":
                return RuntimeLoggingLevel.FULL
            if getattr(context, "entity_type", None) == "agent_execution":
                return RuntimeLoggingLevel.parse(getattr(context, "level", None))
        return RuntimeLoggingLevel.parse(agent_logging_level)
