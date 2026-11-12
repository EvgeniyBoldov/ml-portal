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
        from app.runtime.memory.tool_ledger import canonical_operation_name
        canonical_operation = canonical_operation_name(operation_slug)
        if canonical_operation == "file.read" or canonical_operation.startswith("file.data."):
            # Access, source revisions and temporary-index readiness must be
            # revalidated even for identical calls within the same turn.
            return None
        ledger = ctx.extra.get("runtime_execution_tool_ledger") or ctx.extra.get("runtime_tool_ledger")
        if ledger is None or not hasattr(ledger, "find_successful_result"):
            return None

        execution_id = str(
            ctx.extra.get("runtime_agent_execution_id") or ctx.extra.get("lifecycle_agent_execution_id") or ""
        ) or None
        target_identity = ctx.extra.get("runtime_tool_target_identity")
        if hasattr(ledger, "find_execution_guard"):
            prior = ledger.find_execution_guard(
                operation=operation_slug, arguments=arguments or {}, phase_id=execution_id,
                execution_id=execution_id,
                target_identity=target_identity,
                exclude_call_id=str(ctx.extra.get("runtime_active_tool_call_id") or "") or None,
            )
            if prior is not None and prior.status != "succeeded":
                unknown = prior.status == "outcome_unknown" or prior.outcome_unknown
                return ToolResult.fail(
                    ("This identical operation already has an unknown execution outcome; verify its state "
                     "before choosing whether another call is safe." if unknown else
                     "This identical tool call already has an unresolved execution in this agent run."),
                    error_code="tool_outcome_unknown" if unknown else "duplicate_execution_blocked", retryable=False,
                    outcome_unknown=unknown,
                    reused_from_call_id=prior.call_id,
                ), []

        reused = ledger.find_successful_result(
            operation=operation_slug,
            arguments=arguments or {},
            # Task continuations may share a turn ledger. Reuse belongs to one
            # concrete agent execution, regardless of retrieval policy.
            execution_id=execution_id,
            target_identity=target_identity,
            max_age_seconds=None,
        )
        if reused is None:
            return None

        if not reused.result_data_available and not reused.stored_result_id:
            return ToolResult.fail(
                "This identical tool call already succeeded, but its result is no longer available. "
                "If you have a saved result id, inspect it with result.read or result.sql.",
                error_code="duplicate_result_unavailable",
                retryable=False,
                reused_from_call_id=reused.call_id,
            ), []

        result = ToolResult.ok(
            reused.result_data,
            delivery=reused.result_delivery,
            reused=True,
            reused_from_call_id=reused.call_id,
        )
        if reused.stored_result_id:
            result.metadata["stored_result"] = {
                **(reused.result_data if isinstance(reused.result_data, dict) else {}),
                "result_id": reused.stored_result_id, "inline_complete": False,
            }
            if reused.result_delivery == "direct" and not reused.result_data_available:
                observation = reused.result_observation or {}
                result.metadata["direct_recovery"] = {
                    "result_id": reused.stored_result_id,
                    "revision": observation.get("revision") or 1,
                    "reason": observation.get("recovery_reason") or "batch_context_budget",
                }
        return result, [dict(source) for source in (reused.sources or []) if isinstance(source, dict)]
