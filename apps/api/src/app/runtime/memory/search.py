"""Bounded, ACL-aware semantic memory search shared by runtime tools."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_memory_staging import MemoryConflictCase, MemoryConflictMember

from app.models.memory import FactScope, MemoryClaim, MemoryRelation
from app.runtime.memory.read_policy import allowed_source_collections
from app.runtime.memory.fact_store import FactStore
from app.runtime.memory.recall import MemoryRecallService
from app.runtime.memory.semantic_index import MemorySemanticIndex
from app.runtime.memory.scope_precedence import apply_scope_precedence as _apply_project_precedence
from app.services.glossary_service import GlossaryService, ambiguous_glossary_aliases, matching_glossary_terms
from app.services.memory_scope_catalog import list_memory_scopes, resolve_memory_scopes


class MemorySearchService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def search(self, *, team_keys: list[str] | None = None,
                     project_keys: list[str] | None = None, enforce_context: bool = False,
                     **kwargs: Any) -> dict[str, Any]:
        """Resolve each branch independently; explicit [] clears its chat default.

        Each concrete project is searched separately so an override in A can
        never suppress an obligation in B. Source ACLs run in every search.
        """
        inherited = list(kwargs.get("context_scope_keys") or [])
        internal = list(kwargs.get("scope_keys") or [])
        mode = kwargs.get("scope_mode", "inherit")
        teams = list(team_keys) if team_keys is not None else [
            key for key in ([key for key in internal if key.startswith("team.")] or (inherited if mode == "inherit" else [])) if key.startswith("team.")]
        if project_keys is not None:
            projects = list(project_keys)
        else:
            projects = [key for key in internal if key.startswith("project.")]
            if not projects and mode == "inherit":
                projects = [key for key in inherited if key.startswith("project.")]
                if not projects:
                    projects = list(kwargs.get("fallback_project_keys") or [])
        try:
            if mode not in {"inherit", "replace"}:
                raise ValueError("invalid_scope_mode")
            if any(key.partition(".")[0] not in {"team", "project"} for key in internal):
                raise ValueError("invalid_query_scope")
            explicit_projects = normalize_query_keys([key for key in internal if key.startswith("project.")], "project")
            if project_keys is not None and explicit_projects and set(normalize_query_keys(project_keys, "project")) != set(explicit_projects):
                raise ValueError("conflicting_project_scope")
            teams = normalize_query_keys(teams, "team")
            projects = normalize_query_keys(projects, "project")
            if enforce_context:
                context_teams = normalize_query_keys([key for key in inherited if key.startswith("team.")], "team")
                context_projects = normalize_query_keys([key for key in inherited if key.startswith("project.")], "project")
                if set(teams) != set(context_teams):
                    raise ValueError("context_teams_required")
                if not set(projects).issubset({*context_projects, "project.all"}):
                    raise ValueError("project_not_in_execution_context")
        except ValueError as exc:
            return _empty_result(direction=kwargs.get("direction"), entity_ids=kwargs.get("entity_ids", []),
                                 kinds=kwargs.get("kinds", []), uncertainties=[str(exc)])
        forwarded = {key: value for key, value in kwargs.items() if key not in {
            "context_scope_keys", "scope_keys", "scope_mode", "scope_ceiling_keys", "fallback_project_keys"}}
        groups = []
        concrete_projects = [key for key in projects if key != "project.all"]
        # Concrete groups already include common rules. All alone reads only
        # project.all bindings, never every concrete project in the catalogue.
        for project in concrete_projects or (["project.all"] if "project.all" in projects else [None]):
            result = await self._search_context(**forwarded,
                scope_keys=[*teams, *([project] if project else [])])
            if result.get("success") is False:
                return result
            groups.append({"team_keys": teams, "project_keys": [project] if project else [],
                           "items": result["items"], "uncertainties": result["uncertainties"]})
            if len(groups) == 1:
                combined = {**result, "items": list(result["items"]), "projects": list(result["projects"]),
                            "uncertainties": list(result["uncertainties"])}
            else:
                combined["items"].extend(result["items"])
                combined["projects"].extend(result["projects"])
                combined["uncertainties"].extend(result["uncertainties"])
        combined["groups"] = groups
        combined["search_scope"].update(team_keys=teams, project_keys=projects,
                                      scope_keys=[*teams, *projects])
        combined["count"] = len(combined["items"]) + len(combined["facts"])
        combined["memory_context"] = _memory_context(combined["items"], combined["projects"],
            combined["facts"], combined["glossary"], combined["uncertainties"])
        combined["memory_context"]["scope_groups"] = groups
        return combined

    async def _search_context(
        self,
        *,
        query: str,
        tenant_id: UUID | None,
        user_id: UUID | None = None,
        scope_keys: list[str] | tuple[str, ...] = (),
        scopes: list[str] = (),
        kinds: list[str] = (),
        entity_ids: list[str] = (),
        direction: str | None = None,
        limit: int = 8,
        fact_subject: str | None = None,
    ) -> dict[str, Any]:
        confirmed_glossary = await GlossaryService(self._session).list_confirmed_terms()
        enabled_scopes = {str(scope).strip().lower() for scope in scopes if str(scope).strip()} or {"glossary", "project", "team", "global", "user", "tenant"}
        glossary_terms = matching_glossary_terms(query, confirmed_glossary, limit=12) if "glossary" in enabled_scopes else []
        glossary_uncertainties = [f"ambiguous_glossary_alias:{form}" for form in
                                  ambiguous_glossary_aliases(query, glossary_terms)]
        glossary_definitions = [{
            "id": str(item["id"]), "term": item["term"], "definition": item["definition"],
            "aliases": list(item.get("aliases") or []),
            "source_references": list(item.get("source_references") or []),
        } for item in glossary_terms]
        effective_scope_keys = set(scope_keys)
        project_key_set = {key.removeprefix("project.") for key in effective_scope_keys if key.startswith("project.")}
        try:
            resolved_scopes = await resolve_memory_scopes(self._session, sorted(effective_scope_keys - {"project.all"}))
        except ValueError:
            unknown = sorted(effective_scope_keys - {
                row.key for row in await list_memory_scopes(self._session)
            })
            return _empty_result(direction=direction, entity_ids=entity_ids, kinds=kinds,
                                 uncertainties=[f"unknown_scope_key:{key}" for key in unknown] or ["invalid_scope_key"])
        # MemoryScope is authoritative; legacy Project IDs are optional.
        selected = [{"id": row.project_id, "key": row.key.removeprefix("project."), "name": row.name}
                    for row in resolved_scopes if row.scope_type == "project" and not row.is_all]
        project_ids = [item["id"] for item in selected if item["id"] is not None]
        recall = MemoryRecallService(session=self._session, preparer=None)  # type: ignore[arg-type]
        allowed_kinds = {str(kind).strip() for kind in kinds if str(kind).strip()} or _kinds_for_direction(direction)
        collection_ids = await allowed_source_collections(self._session, user_id=user_id, tenant_id=tenant_id)
        read_args = {"project_ids": project_ids, "tenant_id": tenant_id, "user_id": user_id,
                     "context_scope_keys": sorted(effective_scope_keys), "collection_ids": collection_ids}
        eligible_ids = await recall.eligible_item_ids(**read_args, kinds=allowed_kinds, categories=enabled_scopes)
        semantic_ids = await MemorySemanticIndex(self._session).search_ids(query, limit=48, eligible_ids=eligible_ids)
        lexical_ids = await recall._lexical_ids(query, limit=48, eligible_ids=eligible_ids, **read_args)
        term_related_ids = await recall._term_linked_item_ids(
            [UUID(str(term["id"])) for term in glossary_terms], eligible_ids=eligible_ids, **read_args)
        normalized_entity_ids = [str(item).strip() for item in entity_ids if str(item).strip()]
        entity_related_ids = await recall._visible_relation_item_ids(
            [MemoryRelation.target_id.in_(normalized_entity_ids)] if normalized_entity_ids else [],
            eligible_ids=eligible_ids, **read_args,
        )
        selected_ids = list(dict.fromkeys([*term_related_ids, *semantic_ids, *lexical_ids, *entity_related_ids]))
        selected_ids.extend(await self._conflict_related_item_ids(selected_ids, eligible_ids))
        items = await recall._accessible_semantic_items(
            project_ids=project_ids,
            semantic_ids=list(dict.fromkeys(selected_ids)),
            tenant_id=tenant_id,
            context_scope_keys=sorted(effective_scope_keys), user_id=user_id, collection_ids=collection_ids,
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
        project_keys_by_id = {str(project["id"]): f"project.{project['key']}" for project in selected if project["id"] is not None}
        for item in items:
            bound_projects = set(str(value) for value in (item.get("applicability") or {}).get("project_ids") or [])
            if item.get("project_id") is not None:
                bound_projects.add(str(item["project_id"]))
            legacy_keys = [project_keys_by_id[value] for value in sorted(bound_projects) if value in project_keys_by_id]
            if legacy_keys and not any(key.startswith("project.") for key in item.get("scope_keys") or []):
                item["scope_keys"] = [*(item.get("scope_keys") or []), *legacy_keys]
        from app.runtime.memory.effective_scope import memory_visible_for_scope
        items = [item for item in items if memory_visible_for_scope(item, effective_scope_keys)]
        if allowed_kinds:
            items = [item for item in items if str(item.get("kind")) in allowed_kinds]
        items = [item for item in items if _scope_categories(item).intersection(enabled_scopes)]
        await self._attach_project_overrides(items)
        items, precedence_uncertainties = _apply_project_precedence(items, project_ids)
        values = [
            {
                "id": str(item["id"]), "project_id": str(item["project_id"]) if item.get("project_id") else None,
                "selected_claim_id": item.get("selected_claim_id"),
                "scope_keys": list(item.get("scope_keys") or []),
                "query_scope_keys": sorted(effective_scope_keys),
                "kind": item["kind"], "subject": item["subject"], "content": item["content"],
                "confidence": item["confidence"], "state": item["state"], "observed_at": item.get("observed_at"),
                "source_references": item["source_references"],
            }
            for item in items[:max(1, min(int(limit), 12))]
        ]
        fact_scopes = [FactScope(value) for value in ("user", "tenant") if value in enabled_scopes]
        facts = await FactStore(self._session).search(query=query, user_id=user_id, tenant_id=tenant_id,
            scopes=fact_scopes, subject=fact_subject, limit=max(1, min(int(limit), 12))) if fact_scopes and (not allowed_kinds or "fact" in allowed_kinds) else []
        fact_values = [{"id": str(fact.id), "scope": fact.scope.value, "owner_type": fact.owner_type,
            "owner_id": str(fact.owner_id), "kind": fact.kind, "subject": fact.subject,
            "value": fact.value[:2000], "truncated": len(fact.value) > 2000, "confidence": fact.confidence,
            "observed_at": fact.observed_at.isoformat(), "source_ref": fact.source_ref} for fact in facts]
        fact_subjects = {fact.subject for fact in facts}
        fact_uncertainties = [f"fact_conflict:{subject}" for subject in sorted(fact_subjects)
            if len({" ".join(fact.value.casefold().split()) for fact in facts if fact.subject == subject}) > 1]
        return {
            "facts": fact_values,
            "items": values,
            "projects": [{"key": item["key"], "name": item["name"]} for item in selected],
            "glossary": glossary_definitions,
            "count": len(values) + len(fact_values),
            "search_scope": {
                "direction": str(direction or "").strip() or None,
                "entity_ids": normalized_entity_ids,
                "kinds": sorted(allowed_kinds), "scope_keys": sorted(effective_scope_keys),
                "team_keys": sorted(key for key in effective_scope_keys if key.startswith("team.")),
                "project_keys": sorted(key for key in effective_scope_keys if key.startswith("project.")),
            },
            "uncertainties": [*precedence_uncertainties, *glossary_uncertainties, *fact_uncertainties],
            "memory_context": _memory_context(values, selected, fact_values, glossary_definitions,
                                              [*precedence_uncertainties, *glossary_uncertainties, *fact_uncertainties]),
        }

    async def _conflict_related_item_ids(self, selected_ids: list[UUID], eligible_ids: list[UUID]) -> list[UUID]:
        if not selected_ids or not eligible_ids:
            return []
        selected_candidates = select(MemoryClaim.approved_candidate_id).where(MemoryClaim.memory_item_id.in_(selected_ids))
        case_ids = select(MemoryConflictMember.conflict_id).join(MemoryConflictCase,
            MemoryConflictCase.id == MemoryConflictMember.conflict_id).where(
            MemoryConflictMember.candidate_id.in_(selected_candidates), MemoryConflictCase.kind == "scope_override",
            MemoryConflictCase.status == "resolved", MemoryConflictCase.evidence["scope_policy"].astext == "two_branch_v1")
        counterparts = select(MemoryConflictMember.candidate_id).where(MemoryConflictMember.conflict_id.in_(case_ids))
        return list((await self._session.scalars(select(MemoryClaim.memory_item_id).where(
            MemoryClaim.approved_candidate_id.in_(counterparts), MemoryClaim.memory_item_id.in_(eligible_ids)))).all())

    async def _attach_project_overrides(self, items: list[dict[str, Any]]) -> None:
        candidates = {UUID(item["approved_candidate_id"]): item for item in items if item.get("approved_candidate_id")}
        if len(candidates) < 2:
            return
        rows = (await self._session.execute(select(MemoryConflictMember.conflict_id, MemoryConflictMember.candidate_id)
            .join(MemoryConflictCase, MemoryConflictCase.id == MemoryConflictMember.conflict_id)
            .where(MemoryConflictMember.candidate_id.in_(candidates), MemoryConflictCase.kind == "scope_override",
                   MemoryConflictCase.status == "resolved",
                   MemoryConflictCase.evidence["scope_policy"].astext == "two_branch_v1"))).all()
        cases: dict[UUID, list[dict[str, Any]]] = {}
        for case_id, candidate_id in rows:
            cases.setdefault(case_id, []).append(candidates[candidate_id])
        for members in cases.values():
            universals = [item for item in members if "project.all" in item.get("scope_keys", [])]
            specifics = [item for item in members if any(key.startswith("project.") and key != "project.all"
                         for key in item.get("scope_keys", []))]
            for item in specifics:
                item["overrides_claim_ids"] = list(dict.fromkeys([
                    *item.get("overrides_claim_ids", []), *[row["selected_claim_id"] for row in universals]]))


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
            "uncertainties": uncertainties, "items": [], "projects": [], "glossary": [], "facts": [], "count": 0,
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
    clarification_reasons = [reason for reason in uncertainties if reason.startswith(("ambiguous_glossary_alias:", "fact_conflict:"))]
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


def normalize_query_keys(values: list[str], branch: str) -> list[str]:
    result = []
    if len(values) > 30:
        raise ValueError("too_many_scope_keys")
    for value in values:
        key = str(value).strip().casefold()
        if not key:
            raise ValueError("invalid_scope_key")
        if "." not in key:
            key = f"{branch}.{key}"
        if not key.startswith(f"{branch}.") or key == "team.all":
            raise ValueError("invalid_query_scope:all_or_wrong_branch")
        if key not in result:
            result.append(key)
    return result
