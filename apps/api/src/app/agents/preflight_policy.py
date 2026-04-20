from __future__ import annotations

from typing import Any, Dict, List, Set

from app.agents.contracts import ResolvedOperation


def apply_operation_policy_filter(
    *,
    operation_result: Any,
    platform_config: Dict[str, Any],
) -> Set[str]:
    """
    Remove operations disallowed by platform policy from preflight snapshot.

    Mutates operation_result fields:
    - resolved_operations
    - execution_graph
    """
    forbid_destructive = bool(platform_config.get("forbid_destructive", False))
    forbid_write_in_prod = bool(platform_config.get("forbid_write_in_prod", False))
    forbid_high_risk = bool(platform_config.get("forbid_high_risk", False))

    if not (forbid_destructive or forbid_write_in_prod or forbid_high_risk):
        return set()

    kept_operations: List[ResolvedOperation] = []
    filtered_slugs: Set[str] = set()
    for operation in operation_result.resolved_operations:
        side_effects = operation.side_effects
        blocked = False
        if forbid_destructive and side_effects == "destructive":
            blocked = True
        if forbid_write_in_prod and side_effects in {"write", "destructive"}:
            blocked = True
        if forbid_high_risk and operation.risk_level == "high":
            blocked = True

        if blocked:
            filtered_slugs.add(operation.operation_slug)
        else:
            kept_operations.append(operation)

    if not filtered_slugs:
        return set()

    operation_result.resolved_operations = kept_operations
    allowed_slugs = {operation.operation_slug for operation in kept_operations}
    operation_result.execution_graph.filter_by_operation_slugs(allowed_slugs)

    return filtered_slugs
