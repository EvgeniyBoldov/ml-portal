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
        # A task that explicitly requires fresh retrieval must never satisfy
        # that requirement from an earlier receipt, even within one turn.
        if str(ctx.extra.get("task_freshness_policy") or "") == "require_retrieval":
            return None

        ledger = ctx.extra.get("runtime_tool_ledger")
        if ledger is None or not hasattr(ledger, "find_successful_result"):
            return None

        reused = ledger.find_successful_result(
            operation=operation_slug,
            arguments=arguments or {},
            phase_id=str(ctx.extra.get("runtime_task_id") or "") or None,
        )
        if reused is None:
            return None

        result = ToolResult.ok(
            reused.result_data,
            reused=True,
            reused_from_call_id=reused.call_id,
        )
        return result, [dict(source) for source in (reused.sources or []) if isinstance(source, dict)]
