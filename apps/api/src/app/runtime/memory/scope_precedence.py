"""Resolve overlapping scoped memory before it reaches a model."""
from __future__ import annotations

from typing import Any
from uuid import UUID


def apply_scope_precedence(items: list[dict[str, Any]], project_ids: list[UUID]) -> tuple[list[dict[str, Any]], list[str]]:
    by_identity: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for item in items:
        by_identity.setdefault((str(item.get("kind")), str(item.get("subject")).casefold()), []).append(item)
    result: list[dict[str, Any]] = []
    uncertainties: list[str] = []
    project_set = {str(value) for value in project_ids}
    for identity, rows in by_identity.items():
        globals_ = [row for row in rows if row.get("project_id") is None and not row.get("scope_keys")]
        typed = [row for row in rows if row.get("project_id") is None and row.get("scope_keys")]
        scoped = {str(row.get("project_id")): row for row in rows if row.get("project_id") is not None}
        effective = [scoped.get(project_id) or (globals_[0] if globals_ else None) for project_id in project_set] if project_set else rows
        effective = [row for row in effective if row is not None]
        if project_set:
            effective.extend(typed)
        if len({str(row.get("content_text")) for row in effective}) > 1:
            uncertainties.append(f"project_memory_divergence:{identity[0]}:{identity[1]}")
            continue
        if effective:
            result.append(effective[0])
    return result, uncertainties
