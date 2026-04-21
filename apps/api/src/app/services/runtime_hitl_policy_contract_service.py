from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.agents.contracts import ResolvedOperation


class RuntimeHitlPolicyContractService:
    """Builds explicit human-in-the-loop contract from runtime policy inputs."""

    def build(
        self,
        *,
        platform_config: Dict[str, Any],
        operations: List[ResolvedOperation],
        max_iters: int = 25,
    ) -> Dict[str, Any]:
        require_confirmation_for_write = bool(platform_config.get("require_confirmation_for_write", False))
        require_confirmation_for_destructive = bool(
            platform_config.get("require_confirmation_for_destructive", False)
        )
        forbid_destructive = bool(platform_config.get("forbid_destructive", False))
        forbid_write_in_prod = bool(platform_config.get("forbid_write_in_prod", False))

        operation_policies = [
            self._build_operation_policy(
                operation=operation,
                require_confirmation_for_write=require_confirmation_for_write,
                require_confirmation_for_destructive=require_confirmation_for_destructive,
                forbid_destructive=forbid_destructive,
                forbid_write_in_prod=forbid_write_in_prod,
            )
            for operation in operations
        ]

        return {
            "global": {
                "require_confirmation_for_write": require_confirmation_for_write,
                "require_confirmation_for_destructive": require_confirmation_for_destructive,
                "forbid_destructive": forbid_destructive,
                "forbid_write_in_prod": forbid_write_in_prod,
                "max_iters": max_iters,
            },
            "conditions": [
                {
                    "condition_id": "ask_user_action",
                    "decision": "require_input",
                    "when": "Planner returns ask_user next action",
                    "reason": "Runtime pauses and waits for user's answer.",
                },
                {
                    "condition_id": "loop_detected",
                    "decision": "require_input",
                    "when": "Repeated action loop detected",
                    "reason": "Runtime pauses and asks for clarification.",
                },
                {
                    "condition_id": "max_iters_reached",
                    "decision": "block",
                    "when": "Iteration counter reaches max_iters",
                    "reason": "Runtime stops to avoid endless execution.",
                },
                {
                    "condition_id": "operation_requires_confirmation",
                    "decision": "require_confirmation",
                    "when": "Operation semantics or platform policy requires confirmation",
                    "reason": "Runtime pauses and requires explicit approve/reject.",
                },
            ],
            "operation_policies": operation_policies,
            "resume_contract": {
                "pause_statuses": ["waiting_input", "waiting_confirmation"],
                "resume_endpoint": "/api/v1/chats/runs/{run_id}/resume",
                "resume_payload": {
                    "decision": "confirm | reject",
                    "answer": "optional string",
                },
            },
        }

    def _build_operation_policy(
        self,
        *,
        operation: ResolvedOperation,
        require_confirmation_for_write: bool,
        require_confirmation_for_destructive: bool,
        forbid_destructive: bool,
        forbid_write_in_prod: bool,
    ) -> Dict[str, Any]:
        reasons: List[str] = []
        decision = "allow"

        is_write_like = bool(operation.side_effects) or operation.risk_level in {"write", "destructive"}
        is_destructive = operation.risk_level == "destructive"

        if is_destructive and forbid_destructive:
            decision = "block"
            reasons.append("Blocked by platform setting forbid_destructive=true")
        elif is_write_like and forbid_write_in_prod:
            decision = "block"
            reasons.append("Blocked by platform setting forbid_write_in_prod=true")
        elif operation.requires_confirmation:
            decision = "require_confirmation"
            reasons.append("Operation semantics requires confirmation")
        elif is_destructive and require_confirmation_for_destructive:
            decision = "require_confirmation"
            reasons.append("Platform requires confirmation for destructive operations")
        elif is_write_like and require_confirmation_for_write:
            decision = "require_confirmation"
            reasons.append("Platform requires confirmation for write operations")
        else:
            reasons.append("No blocking/confirmation gates matched")

        return {
            "operation_slug": operation.operation_slug,
            "operation": operation.operation,
            "name": operation.name,
            "side_effects": operation.side_effects,
            "risk_level": operation.risk_level,
            "requires_confirmation_semantic": operation.requires_confirmation,
            "effective_decision": decision,
            "reasons": reasons,
        }
