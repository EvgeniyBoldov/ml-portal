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
        scoped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            if row.get("project_id") is not None:
                scoped.setdefault(str(row["project_id"]), []).append(row)
        effective = [row for project_id in sorted(project_set)
                     for row in (scoped.get(project_id) or globals_)] if project_set else rows
        if project_set:
            effective.extend(typed)
        if len({str(row.get("content_text")) for row in effective}) > 1:
            uncertainties.append(f"project_memory_divergence:{identity[0]}:{identity[1]}")
        seen = set()
        for row in effective:
            key = (str(row.get("selected_claim_id") or row.get("id")),
                   tuple(sorted(row.get("scope_keys") or [])), str(row.get("content_text")))
            if key not in seen:
                result.append(row)
                seen.add(key)
    return result, uncertainties
