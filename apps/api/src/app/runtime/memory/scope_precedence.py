"""Apply only evidence-backed project overrides; compatible duties accumulate."""
from __future__ import annotations
from typing import Any
from uuid import UUID


def apply_scope_precedence(items: list[dict[str, Any]], project_ids: list[UUID]) -> tuple[list[dict[str, Any]], list[str]]:
    suppressed = {str(value) for item in items for value in item.get("overrides_claim_ids", [])}
    seen = set()
    result = []
    for item in items:
        if str(item.get("selected_claim_id")) in suppressed:
            continue
        key = (str(item.get("selected_claim_id") or item.get("id")), tuple(sorted(item.get("scope_keys") or [])))
        if key not in seen:
            result.append(item)
            seen.add(key)
    return result, []


def scope_sets_overlap(left: set[str], right: set[str]) -> bool:
    for branch in ("team", "project"):
        a = {key for key in left if key.startswith(f"{branch}.")}
        b = {key for key in right if key.startswith(f"{branch}.")}
        if branch == "project" and bool(a) != bool(b):
            return False
        if a and b and not a.intersection(b) and f"{branch}.all" not in a | b:
            return False
    return True


def has_project_override(left: set[str], right: set[str]) -> bool:
    def concrete(keys: set[str]) -> bool:
        return any(key.startswith("project.") and key != "project.all" for key in keys)
    return ("project.all" in left and concrete(right)) or ("project.all" in right and concrete(left))
