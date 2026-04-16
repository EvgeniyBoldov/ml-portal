"""RuntimeLoggingResolver — resolve effective runtime logging level."""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from app.agents.runtime.logging import LoggingConfig, LoggingLevel

if TYPE_CHECKING:
    from app.agents.context import ToolContext


class RuntimeLoggingResolver:
    async def resolve_logging_level(
        self,
        ctx: "ToolContext",
        agent_logging_level: Optional[str] = None,
    ) -> LoggingLevel:
        return await LoggingConfig.resolve(ctx, agent_logging_level)
