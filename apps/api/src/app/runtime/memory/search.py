"""Bounded, ACL-aware semantic memory search shared by runtime tools."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import MemoryRelation
from app.runtime.memory.fact_store import FactStore
from app.runtime.memory.recall import MemoryRecallService, _matching_glossary_terms
from app.runtime.memory.service import MemoryService
from app.runtime.memory.semantic_index import MemorySemanticIndex
from app.services.glossary_service import GlossaryService


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
        kinds: list[str] = (),
        entity_ids: list[str] = (),
        direction: str | None = None,
        limit: int = 8,
    ) -> dict[str, Any]:
        projects = await GlossaryService(self._session).list_project_terms()
        confirmed_glossary = await GlossaryService(self._session).list_confirmed_terms(tenant_id=tenant_id)
        glossary_terms = _matching_glossary_terms(query, confirmed_glossary, limit=12)
        project_key_set = {str(key).strip().lower() for key in project_keys if str(key).strip()}
        known_project_keys = {str(item.get("key") or "").strip().lower() for item in projects}
        unknown_project_keys = sorted(project_key_set - known_project_keys)
        if unknown_project_keys:
            return _empty_result(
                direction=direction, entity_ids=entity_ids, kinds=kinds,
                uncertainties=[f"unknown_project_key:{key}" for key in unknown_project_keys],
            )
        selected = [
            item for item in projects
            if not project_key_set or str(item.get("key") or "").strip().lower() in project_key_set
        ]
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
        allowed_kinds = {str(kind).strip() for kind in kinds if str(kind).strip()}
        if not allowed_kinds:
            allowed_kinds = _kinds_for_direction(direction)
        if allowed_kinds:
            items = [item for item in items if str(item.get("kind")) in allowed_kinds]
        values = [
            {
                "id": str(item["id"]), "project_id": str(item["project_id"]) if item.get("project_id") else None,
                "kind": item["kind"], "subject": item["subject"], "content": item["content"],
                "confidence": item["confidence"], "state": item["state"], "observed_at": item.get("observed_at"),
                "source_references": item["source_references"],
            }
            for item in items[:max(1, min(int(limit), 12))]
        ]
        snapshot = await MemoryService(fact_store=FactStore(self._session)).read_snapshot(
            user_id=user_id, tenant_id=tenant_id, limit=12,
        )
        durable_facts = snapshot.agent_context(query=query, limit=8)
        return {
            "items": values,
            "projects": [{"key": item["key"], "name": item["name"]} for item in selected],
            "glossary": [{
                "term": item.get("term"), "description": item.get("description"),
                "aliases": list(item.get("aliases") or []), "scope": item.get("scope"),
            } for item in glossary_terms],
            "count": len(values),
            "search_scope": {
                "direction": str(direction or "").strip() or None,
                "entity_ids": normalized_entity_ids,
                "kinds": sorted(allowed_kinds),
            },
            "memory_context": _memory_context(values, selected, durable_facts, glossary_terms),
        }


def _kinds_for_direction(direction: str | None) -> set[str]:
    """Turn a declared retrieval intent into a restrictive kind filter."""
    value = str(direction or "").strip().lower()
    if any(token in value for token in ("rule", "policy", "правил", "регламент")):
        return {"rule", "constraint"}
    if any(token in value for token in ("procedure", "process", "процедур", "процесс")):
        return {"procedure"}
    if any(token in value for token in ("term", "definition", "термин", "определени")):
        return {"term", "description"}
    return set()


def _empty_result(*, direction: str | None, entity_ids: list[str], kinds: list[str], uncertainties: list[str]) -> dict[str, Any]:
    return {"items": [], "projects": [], "count": 0,
            "search_scope": {"direction": str(direction or "").strip() or None, "entity_ids": list(entity_ids), "kinds": list(kinds)},
            "memory_context": {"type": "memory_recall", "resolved_terms": [], "resolved_entities": [], "relevant_projects": [], "relevant_knowledge": [], "applicable_rules": [], "applicable_procedures": [], "known_constraints": [], "durable_facts": [], "uncertainties": uncertainties, "source_references": [], "rag_required": False, "tool_required": False}}


def _memory_context(
    items: list[dict[str, Any]], projects: list[dict[str, Any]],
    durable_facts: list[dict[str, object]], glossary: list[dict[str, Any]],
) -> dict[str, Any]:
    def typed(kind: str) -> list[dict[str, Any]]:
        return [item for item in items if item.get("kind") == kind]
    refs = [ref for item in items for ref in item.get("source_references") or [] if isinstance(ref, dict)]
    uncertain = [item for item in items if item.get("state") != "active"]
    return {"type": "memory_recall", "resolved_terms": glossary, "resolved_entities": [], "relevant_projects": [{"key": item.get("key"), "name": item.get("name")} for item in projects], "relevant_knowledge": [item for item in items if item.get("kind") not in {"rule", "constraint", "procedure"}], "applicable_rules": typed("rule"), "applicable_procedures": typed("procedure"), "known_constraints": typed("constraint"), "durable_facts": durable_facts, "uncertainties": [f"uncertain_memory:{item.get('id')}" for item in uncertain], "source_references": refs[:24], "rag_required": bool(uncertain), "tool_required": False}
