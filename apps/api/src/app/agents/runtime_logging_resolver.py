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
        del ctx
        return RuntimeLoggingLevel.parse(agent_logging_level)
