"""Bounded, ACL-aware semantic memory search shared by runtime tools."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import MemoryRelation
from app.runtime.memory.recall import MemoryRecallService
from app.runtime.memory.semantic_index import MemorySemanticIndex
from app.runtime.memory.scope_precedence import apply_scope_precedence as _apply_project_precedence
from app.services.glossary_service import GlossaryService, ambiguous_glossary_aliases, matching_glossary_terms
from app.services.project_catalog_service import ProjectCatalogService
from app.services.memory_scope_catalog import list_memory_scopes, resolve_memory_scopes


class MemorySearchService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def search(
        self,
        *,
        query: str,
        tenant_id: UUID | None,
        user_id: UUID | None = None,
        project_keys: list[str] = (),
        fallback_project_keys: list[str] | tuple[str, ...] = (),
        context_scope_keys: list[str] | tuple[str, ...] = (),
        scope_keys: list[str] | tuple[str, ...] = (),
        scope_mode: str = "inherit",
        scope_ceiling_keys: list[str] | tuple[str, ...] | None = None,
        scopes: list[str] = (),
        kinds: list[str] = (),
        entity_ids: list[str] = (),
        direction: str | None = None,
        limit: int = 8,
    ) -> dict[str, Any]:
        projects = await ProjectCatalogService(self._session).list_projects()
        confirmed_glossary = await GlossaryService(self._session).list_confirmed_terms()
        enabled_scopes = {str(scope).strip().lower() for scope in scopes if str(scope).strip()} or {"glossary", "project", "product", "team", "global"}
        glossary_terms = matching_glossary_terms(query, confirmed_glossary, limit=12) if "glossary" in enabled_scopes else []
        glossary_uncertainties = [f"ambiguous_glossary_alias:{form}" for form in
                                  ambiguous_glossary_aliases(query, glossary_terms)]
        glossary_definitions = [{
            "id": str(item["id"]), "term": item["term"], "definition": item["definition"],
            "aliases": list(item.get("aliases") or []),
            "source_references": list(item.get("source_references") or []),
        } for item in glossary_terms]
        if scope_mode not in {"inherit", "replace"}:
            return _empty_result(direction=direction, entity_ids=entity_ids, kinds=kinds,
                                 uncertainties=["invalid_scope_mode"])
        requested_scope_keys = {str(key).strip().lower() for key in scope_keys if str(key).strip()}
        inherited_scope_keys = {str(key).strip().lower() for key in context_scope_keys if str(key).strip()}
        requested_keys = {str(key).strip().lower() for key in project_keys if str(key).strip()}
        explicit_projects = {key.removeprefix("project.") for key in requested_scope_keys
                             if key.startswith("project.") and key != "project.all"}
        if requested_keys and ((explicit_projects and requested_keys != explicit_projects)
                               or "project.all" in requested_scope_keys):
            return _empty_result(direction=direction, entity_ids=entity_ids, kinds=kinds,
                                 uncertainties=["conflicting_project_scope"])
        replaced_types = {key.partition(".")[0] for key in requested_scope_keys}
        if requested_keys:
            replaced_types.add("project")
        effective_scope_keys = set(requested_scope_keys) if scope_mode == "replace" else {
            key for key in inherited_scope_keys if key.partition(".")[0] not in replaced_types
        } | requested_scope_keys
        scope_projects = {key.removeprefix("project.") for key in effective_scope_keys
                          if key.startswith("project.") and key != "project.all"}
        project_key_set = requested_keys or scope_projects or (
            {str(key).strip().lower() for key in fallback_project_keys if str(key).strip()}
            if scope_mode == "inherit" and "project.all" not in effective_scope_keys else set()
        )
        effective_scope_keys |= {f"project.{key}" for key in project_key_set}
        if scope_ceiling_keys is not None:
            ceiling = {str(key).strip().lower() for key in scope_ceiling_keys if str(key).strip()}
            if not effective_scope_keys.issubset(ceiling):
                return _empty_result(direction=direction, entity_ids=entity_ids, kinds=kinds,
                                     uncertainties=["scope_widening_denied"])
        try:
            await resolve_memory_scopes(self._session, sorted(effective_scope_keys))
        except ValueError:
            unknown = sorted(effective_scope_keys - {
                row.key for row in await list_memory_scopes(self._session)
            })
            return _empty_result(direction=direction, entity_ids=entity_ids, kinds=kinds,
                                 uncertainties=[f"unknown_scope_key:{key}" for key in unknown] or ["invalid_scope_key"])
        known_project_keys = {str(item.get("key") or "").strip().lower() for item in projects}
        unknown_project_keys = sorted(project_key_set - known_project_keys)
        if unknown_project_keys:
            return _empty_result(
                direction=direction, entity_ids=entity_ids, kinds=kinds,
                uncertainties=[f"unknown_project_key:{key}" for key in unknown_project_keys],
            )
        selected = [item for item in projects if str(item.get("key") or "").strip().lower() in project_key_set]
        project_ids = [item["id"] for item in selected]
        # Reuse the read-side ACL/applicability implementation; no selector LLM
        # participates in this operation.
        recall = MemoryRecallService(session=self._session, preparer=None)  # type: ignore[arg-type]
        semantic_ids = await MemorySemanticIndex(self._session).search_ids(query, limit=48)
        lexical_ids = await recall._lexical_ids(query, limit=48)
        normalized_entity_ids = [str(item).strip() for item in entity_ids if str(item).strip()]
        entity_related_ids = await recall._visible_relation_item_ids(
            [MemoryRelation.target_id.in_(normalized_entity_ids)] if normalized_entity_ids else [],
            tenant_id=tenant_id,
        )
        items = await recall._accessible_semantic_items(
            project_ids=project_ids,
            semantic_ids=list(dict.fromkeys([*semantic_ids, *lexical_ids, *entity_related_ids])),
            tenant_id=tenant_id,
            context_scope_keys=sorted(effective_scope_keys),
        )
        if normalized_entity_ids:
            entity_item_id_set = set(entity_related_ids)
            items = [item for item in items if item.get("id") in entity_item_id_set]
        # ``_accessible_semantic_items`` applies ACL; explicit project scope
        # remains the caller's contract and must not be broadened by a
        # semantic hit from a different project.
        if project_key_set:
            project_id_set = set(project_ids)
            items = [item for item in items if item.get("project_id") in project_id_set or item.get("project_id") is None]
        project_keys_by_id = {str(project["id"]): f"project.{project['key']}" for project in selected}
        for item in items:
            bound_projects = set(str(value) for value in (item.get("applicability") or {}).get("project_ids") or [])
            if item.get("project_id") is not None:
                bound_projects.add(str(item["project_id"]))
            legacy_keys = [project_keys_by_id[value] for value in sorted(bound_projects) if value in project_keys_by_id]
            if legacy_keys and not any(key.startswith("project.") for key in item.get("scope_keys") or []):
                item["scope_keys"] = [*(item.get("scope_keys") or []), *legacy_keys]
        allowed_kinds = {str(kind).strip() for kind in kinds if str(kind).strip()}
        if not allowed_kinds:
            allowed_kinds = _kinds_for_direction(direction)
        if allowed_kinds:
            items = [item for item in items if str(item.get("kind")) in allowed_kinds]
        items = [item for item in items if _scope_categories(item).intersection(enabled_scopes)]
        items, precedence_uncertainties = _apply_project_precedence(items, project_ids)
        values = [
            {
                "id": str(item["id"]), "project_id": str(item["project_id"]) if item.get("project_id") else None,
                "selected_claim_id": item.get("selected_claim_id"),
                "scope_keys": list(item.get("scope_keys") or []),
                "kind": item["kind"], "subject": item["subject"], "content": item["content"],
                "confidence": item["confidence"], "state": item["state"], "observed_at": item.get("observed_at"),
                "source_references": item["source_references"],
            }
            for item in items[:max(1, min(int(limit), 12))]
        ]
        return {
            "items": values,
            "projects": [{"key": item["key"], "name": item["name"]} for item in selected],
            "glossary": glossary_definitions,
            "count": len(values),
            "search_scope": {
                "direction": str(direction or "").strip() or None,
                "entity_ids": normalized_entity_ids,
                "kinds": sorted(allowed_kinds), "scope_keys": sorted(effective_scope_keys),
                "scope_mode": scope_mode,
            },
            "uncertainties": [*precedence_uncertainties, *glossary_uncertainties],
            "memory_context": _memory_context(values, selected, [], glossary_definitions,
                                              [*precedence_uncertainties, *glossary_uncertainties]),
        }


def _kinds_for_direction(direction: str | None) -> set[str]:
    """Turn a declared retrieval intent into a restrictive kind filter."""
    value = str(direction or "").strip().lower()
    if any(token in value for token in ("rule", "policy", "правил", "регламент")):
        return {"rule", "constraint"}
    if any(token in value for token in ("procedure", "process", "процедур", "процесс")):
        return {"procedure"}
    if any(token in value for token in ("term", "definition", "термин", "определени")):
        return {"description"}
    return set()


def _scope_categories(item: dict[str, Any]) -> set[str]:
    keys = item.get("scope_keys") or []
    if keys:
        return {str(key).split(".", 1)[0] for key in keys}
    return {"project" if item.get("project_id") else "global"}


def _empty_result(*, direction: str | None, entity_ids: list[str], kinds: list[str], uncertainties: list[str]) -> dict[str, Any]:
    return {"success": False, "error_code": uncertainties[0].split(":", 1)[0],
            "uncertainties": uncertainties, "items": [], "projects": [], "glossary": [], "count": 0,
            "search_scope": {"direction": str(direction or "").strip() or None, "entity_ids": list(entity_ids), "kinds": list(kinds)},
            "memory_context": {"type": "memory_recall", "resolved_terms": [], "resolved_entities": [], "relevant_projects": [], "relevant_knowledge": [], "applicable_rules": [], "applicable_procedures": [], "known_constraints": [], "durable_facts": [], "uncertainties": uncertainties, "source_references": [], "rag_required": False, "tool_required": False}}


def _memory_context(
    items: list[dict[str, Any]], projects: list[dict[str, Any]],
    durable_facts: list[dict[str, object]], glossary: list[dict[str, Any]], uncertainties: list[str] = (),
) -> dict[str, Any]:
    def typed(kind: str) -> list[dict[str, Any]]:
        return [item for item in items if item.get("kind") == kind]
    refs = [ref for item in [*items, *glossary] for ref in item.get("source_references") or [] if isinstance(ref, dict)]
    uncertain = [item for item in items if item.get("state") != "active"]
    clarification_reasons = [reason for reason in uncertainties if reason.startswith("ambiguous_glossary_alias:")]
    source_uncertainties = [reason for reason in uncertainties if reason not in clarification_reasons]
    return {
        "type": "memory_recall",
        "resolved_terms": glossary,
        "resolved_entities": [],
        "relevant_projects": [{"key": item.get("key"), "name": item.get("name")} for item in projects],
        "relevant_knowledge": [item for item in items if item.get("kind") not in {"rule", "constraint", "procedure"}],
        "applicable_rules": typed("rule"),
        "applicable_procedures": typed("procedure"),
        "known_constraints": typed("constraint"),
        "durable_facts": durable_facts,
        "uncertainties": [*uncertainties, *[f"uncertain_memory:{item.get('id')}" for item in uncertain]],
        "source_references": refs[:24],
        "rag_required": bool(uncertain or source_uncertainties),
        "tool_required": False,
        "clarification_required": bool(clarification_reasons),
        "clarification_reasons": clarification_reasons,
    }
