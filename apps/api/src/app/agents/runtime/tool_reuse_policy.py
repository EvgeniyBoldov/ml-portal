"""Tool call reuse policy for turn-scoped duplicate operations."""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from app.agents.context import ToolContext, ToolResult


class ToolCallReusePolicy:
    """Checks whether an operation call can be served from in-turn ledger."""

    def maybe_reuse(
        self,
        *,
        operation_slug: str,
        arguments: Dict[str, Any],
        ctx: ToolContext,
    ) -> Optional[Tuple[ToolResult, list[dict]]]:
        if not bool(ctx.extra.get("runtime_tool_reuse_enabled", True)):
            return None

        ledger = ctx.extra.get("runtime_tool_ledger")
        if ledger is None or not hasattr(ledger, "find_successful_result"):
            return None

        reused = ledger.find_successful_result(
            operation=operation_slug,
            arguments=arguments or {},
        )
        if reused is None:
            return None

        result = ToolResult.ok(
            reused.result_data,
            reused=True,
            reused_from_call_id=reused.call_id,
        )
        return result, []

