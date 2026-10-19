"""Typed, serializable scope context shared by turns, plans and task tools."""
from __future__ import annotations
import json

from typing import Any, Literal

from pydantic import BaseModel, Field, computed_field, field_validator


ScopeSource = Literal["turn", "chat_focus", "user_project_default", "user_default", "tenant_default", "task", "none"]


class ScopeIdentity(BaseModel):
    id: str | None = None
    key: str = Field(min_length=1, max_length=180)
    type: str = Field(default="scope", min_length=1, max_length=24)
    name: str = Field(default="", max_length=255)
    source: ScopeSource = "none"
    matched_forms: list[str] = Field(default_factory=list, max_length=12)
    rationale: str = Field(default="", max_length=600)


class ScopeSelection(BaseModel):
    model_config = {"extra": "forbid"}
    keys: list[str] = Field(default_factory=list, max_length=120,
                           description="Catalog scope slugs selected by the user. Empty inherit preserves focus; empty replace explicitly clears it.")
    mode: Literal["inherit", "replace"] = "inherit"
    mentioned_keys: list[str] = Field(default_factory=list, max_length=30)
    rationale: str = Field(default="", max_length=600)

    @field_validator("keys", "mentioned_keys")
    @classmethod
    def normalize_keys(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(str(value).strip().casefold() for value in values if str(value).strip()))


class EffectiveScopeContext(BaseModel):
    version: int = 1
    revision: int = 0
    selected: list[ScopeIdentity] = Field(default_factory=list, max_length=120)
    mentioned: list[ScopeIdentity] = Field(default_factory=list, max_length=30)
    ambiguities: list[dict[str, Any]] = Field(default_factory=list, max_length=20)
    mode: Literal["inherit", "replace"] = "inherit"
    explicit_clear: bool = False
    ceiling_keys: list[str] = Field(default_factory=list, max_length=120)

    @computed_field
    @property
    def keys(self) -> list[str]:
        return list(dict.fromkeys(scope.key for scope in self.selected))

    def model_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def merge_selection(
    parent: EffectiveScopeContext,
    selection: ScopeSelection,
    identities: dict[str, ScopeIdentity],
    *, source: ScopeSource,
    ceiling_keys: list[str] | None = None,
) -> EffectiveScopeContext:
    """An explicit selection replaces the flat scope set; absent selection inherits."""
    unknown = set(selection.keys + selection.mentioned_keys) - set(identities)
    if unknown:
        raise ValueError(f"unknown_scope_keys:{','.join(sorted(unknown))}")
    parent_rows = [] if selection.mode == "replace" or selection.keys else list(parent.selected)
    kept = parent_rows
    incoming = [identities[key].model_copy(update={"source": source}) for key in selection.keys if key in identities]
    combined = {row.key: row for row in [*kept, *incoming]}
    keys = list(combined)
    ceiling = list(parent.ceiling_keys if ceiling_keys is None else ceiling_keys)
    if selection.mode == "replace":
        ceiling = keys
    return EffectiveScopeContext(
        revision=parent.revision + 1,
        selected=list(combined.values()),
        mentioned=[identities[key].model_copy(update={"source": source}) for key in selection.mentioned_keys if key in identities],
        ambiguities=list(parent.ambiguities),
        mode=selection.mode,
        explicit_clear=(selection.mode == "replace" and not keys) or
                       (selection.mode == "inherit" and not selection.keys and parent.explicit_clear),
        ceiling_keys=list(dict.fromkeys(ceiling)),
    )


def scope_selection_changes(parent: EffectiveScopeContext, selection: ScopeSelection) -> bool:
    return bool(selection.keys or selection.mode == "replace") and set(selection.keys) != set(parent.keys)


def task_scope(parent: EffectiveScopeContext, selection: ScopeSelection) -> EffectiveScopeContext:
    keys = selection.keys
    chosen = keys if keys or selection.mode == "replace" else parent.keys
    ceiling = set(parent.ceiling_keys)
    if not set(chosen).issubset(ceiling):
        raise ValueError("scope_widening_denied")
    if selection.mode == "inherit" and not set(keys).issubset(ceiling):
        raise ValueError("scope_widening_denied")
    if not set(keys).issubset(parent.keys):
        raise ValueError("scope_identity_missing")
    selected = [row.model_copy(update={"source": "task", "rationale": selection.rationale or row.rationale})
                for row in parent.selected if row.key in chosen]
    return EffectiveScopeContext(revision=parent.revision, selected=selected, mode=selection.mode,
                                 explicit_clear=selection.mode == "replace" and not selected,
                                 ceiling_keys=[row.key for row in selected])


def memory_visible_for_scope(item: dict[str, Any], scope_keys: list[str] | set[str]) -> bool:
    """Applicability is the intersection with exact catalog slugs."""
    bound = set(item.get("scope_keys") or ([item["scope_slug"]] if item.get("scope_slug") else []))
    return bool(bound.intersection(scope_keys))


def project_memory_context(value: dict[str, Any], scope_keys: list[str] | set[str]) -> dict[str, Any]:
    """Filter nested recall/search evidence together with its source references."""
    if value.get("backend") == "hipporag" and isinstance(value.get("groups"), list):
        groups = [group for group in value["groups"] if group.get("scope_slug") in scope_keys]
        return {**value, "groups": groups, "group_count": len(groups),
                "partial": any(not group.get("success", True) for group in groups)}
    result = dict(value)
    selected = set(scope_keys)
    item_lists = ("items", "relevant_knowledge", "applicable_rules", "applicable_procedures", "known_constraints")
    for key in item_lists:
        if isinstance(result.get(key), list):
            result[key] = [item for item in result[key] if isinstance(item, dict)
                           and memory_visible_for_scope(item, selected)]
    for key in ("groups", "scope_groups"):
        if isinstance(result.get(key), list):
            result[key] = [project_memory_context(group, selected) for group in result[key]
                           if isinstance(group, dict) and (
                               group.get("project_keys") == ["project.all"]
                               or not group.get("project_keys") and not any(value.startswith("project.") for value in selected)
                               or bool(set(group.get("project_keys", [])).intersection(selected)))]
    for key in ("result", "memory_context"):
        if isinstance(result.get(key), dict):
            result[key] = project_memory_context(result[key], selected)
    for key in ("projects", "relevant_projects"):
        if isinstance(result.get(key), list):
            result[key] = [item for item in result[key] if isinstance(item, dict)
                           and f"project.{item.get('key')}" in selected]
    if isinstance(result.get("scope_candidates"), list):
        result["scope_candidates"] = [item for item in result["scope_candidates"] if item.get("key") in selected]
    if isinstance(result.get("scope_ambiguities"), list):
        result["scope_ambiguities"] = [{**item, "keys": [key for key in item.get("keys", []) if key in selected]}
                                       for item in result["scope_ambiguities"]
                                       if len(selected.intersection(item.get("keys", []))) > 1]
    if "count" in result and isinstance(result.get("items"), list):
        result["count"] = len(result["items"]) + len(result.get("facts") or [])
    if "source_references" in result and any(key in result for key in item_lists):
        evidence = [item for key in (*item_lists, "resolved_terms", "glossary")
                    for item in result.get(key, []) if isinstance(item, dict)]
        references = []
        for item in evidence:
            for ref in item.get("source_references") or []:
                if isinstance(ref, dict) and ref not in references:
                    references.append(ref)
        result["source_references"] = references[:24]
        if isinstance(result.get("uncertainties"), list):
            ids = {str(item.get("id")) for item in evidence}
            def relevant_uncertainty(reason: str) -> bool:
                if reason.startswith("uncertain_memory:"):
                    return reason.removeprefix("uncertain_memory:") in ids
                if reason.startswith("project_memory_divergence:"):
                    _, kind, subject = reason.split(":", 2)
                    contents = {json.dumps(item.get("content", item.get("value")), sort_keys=True, default=str)
                                for item in evidence if item.get("kind") == kind
                                and str(item.get("subject", "")).casefold() == subject}
                    return len(contents) > 1
                return True
            result["uncertainties"] = [reason for reason in result["uncertainties"] if relevant_uncertainty(reason)]
            if "rag_required" in result and "rag_reasons" not in result:
                result["rag_required"] = bool(
                    any(item.get("state", "active") != "active" for item in evidence)
                    or any(not reason.startswith(("ambiguous_glossary_alias:", "fact_conflict:")) for reason in result["uncertainties"])
                )
    return result
