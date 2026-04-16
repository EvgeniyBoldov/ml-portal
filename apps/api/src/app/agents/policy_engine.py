"""
PolicyEngine — last-gate enforcement before tool execution.

Checks:
- Action is in AvailableActions whitelist
- Side effects / risk gates (from PlatformSettings)
- Write/destructive confirmation requirement
- Hard block for forbidden operations
- Loop guard (max iters, repeated actions)
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from app.agents.contracts import (
    ActionType,
    AvailableActions,
    NextAction,
    PolicyDecision,
    PolicyDecisionType,
)
from app.agents.run_context_compact import LOOP_THRESHOLD, RunContextCompact
from app.agents.planner import validate_next_action
from app.core.logging import get_logger

logger = get_logger(__name__)

DEFAULT_MAX_ITERS = 25


class PolicyEngine:
    """Evaluates NextAction against policies/caps before execution."""

    def __init__(
        self,
        *,
        max_iters: int = DEFAULT_MAX_ITERS,
        require_confirmation_for_write: bool = False,
        require_confirmation_for_destructive: bool = False,
        forbid_destructive: bool = False,
        forbid_write_in_prod: bool = False,
    ) -> None:
        self.max_iters = max_iters
        self.require_confirmation_for_write = require_confirmation_for_write
        self.require_confirmation_for_destructive = require_confirmation_for_destructive
        self.forbid_destructive = forbid_destructive
        self.forbid_write_in_prod = forbid_write_in_prod

    @classmethod
    def from_platform_config(
        cls,
        platform_config: Dict[str, Any],
        *,
        max_iters: int = DEFAULT_MAX_ITERS,
    ) -> PolicyEngine:
        """Create PolicyEngine from PlatformSettingsProvider config dict."""
        return cls(
            max_iters=max_iters,
            require_confirmation_for_write=platform_config.get("require_confirmation_for_write", False),
            require_confirmation_for_destructive=platform_config.get("require_confirmation_for_destructive", False),
            forbid_destructive=platform_config.get("forbid_destructive", False),
            forbid_write_in_prod=platform_config.get("forbid_write_in_prod", False),
        )

    def evaluate(
        self,
        action: NextAction,
        context: RunContextCompact,
        available_actions: AvailableActions,
    ) -> PolicyDecision:
        """
        Evaluate action. Returns PolicyDecision.

        Checks in order:
        1. Max iterations
        2. Loop detection
        3. Whitelist membership
        4. Side effects / confirmation gates
        """
        # 1. Max iterations
        if context.iter_count >= self.max_iters:
            return PolicyDecision(
                decision=PolicyDecisionType.BLOCK,
                reason=f"Maximum iterations ({self.max_iters}) reached",
            )

        # 2. Loop detection
        if context.is_looping():
            return PolicyDecision(
                decision=PolicyDecisionType.REQUIRE_INPUT,
                reason=(
                    f"Detected repeated action ({LOOP_THRESHOLD}x). "
                    "Please clarify what you need."
                ),
            )

        # Non-operation actions (ask_user, final) are always allowed
        if action.type in (ActionType.ASK_USER, ActionType.FINAL):
            return PolicyDecision(
                decision=PolicyDecisionType.ALLOW,
                reason="Non-tool action, always allowed",
            )

        # 3. Whitelist check
        whitelist_error = validate_next_action(action, available_actions)
        if whitelist_error:
            return PolicyDecision(
                decision=PolicyDecisionType.BLOCK,
                reason=f"Action not in whitelist: {whitelist_error}",
            )

        # Agent calls: allowed after whitelist check (no side-effects gate)
        if action.type == ActionType.AGENT_CALL:
            return PolicyDecision(
                decision=PolicyDecisionType.ALLOW,
                reason="Agent call passed whitelist check",
            )

        # 4. Side effects / confirmation gates
        if action.type == ActionType.OPERATION_CALL and action.operation:
            operation_slug = action.operation.intent.operation_slug
            op = action.operation.intent.op

            # Find matching OperationAction for metadata
            matched = next(
                (
                    item
                    for item in available_actions.operations
                    if item.operation_slug == operation_slug and item.op == op
                ),
                None,
            )

            if matched:
                # Hard block: destructive operations forbidden
                if matched.side_effects == "destructive" and self.forbid_destructive:
                    return PolicyDecision(
                        decision=PolicyDecisionType.BLOCK,
                        reason=(
                            f"Operation '{operation_slug}.{op}' has destructive side effects. "
                            "Destructive operations are forbidden by platform policy."
                        ),
                    )

                # Hard block: write operations forbidden in production
                if matched.side_effects in ("write", "destructive") and self.forbid_write_in_prod:
                    return PolicyDecision(
                        decision=PolicyDecisionType.BLOCK,
                        reason=(
                            f"Operation '{operation_slug}.{op}' has '{matched.side_effects}' side effects. "
                            "Write operations are forbidden in production by platform policy."
                        ),
                    )

                # Confirmation gate: destructive
                if (
                    matched.side_effects == "destructive"
                    and self.require_confirmation_for_destructive
                ):
                    return PolicyDecision(
                        decision=PolicyDecisionType.REQUIRE_CONFIRMATION,
                        reason=(
                            f"Operation '{operation_slug}.{op}' has destructive side effects. "
                            "Confirmation required."
                        ),
                    )

                # Confirmation gate: write
                if (
                    matched.side_effects == "write"
                    and self.require_confirmation_for_write
                ):
                    return PolicyDecision(
                        decision=PolicyDecisionType.REQUIRE_CONFIRMATION,
                        reason=(
                            f"Operation '{operation_slug}.{op}' has write side effects. "
                            "Confirmation required."
                        ),
                    )

        return PolicyDecision(
            decision=PolicyDecisionType.ALLOW,
            reason="All checks passed",
        )
