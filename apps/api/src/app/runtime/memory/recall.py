"""Structured, mandatory semantic-memory recall before planning."""
from __future__ import annotations
import json

from dataclasses import dataclass, replace
from difflib import SequenceMatcher
from typing import Any, Awaitable, Callable
from uuid import UUID

import re

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import MemoryClaim, MemoryItem, MemoryRelation
from app.models.memory_scope import MemoryClaimScope, MemoryScope
from app.models.rag import RAGDocument
from app.models.document_memory_staging import MemoryExtractionCandidate
from app.runtime.memory.read_policy import published_claim, source_access, applicable_claim, live_item, allowed_source_collections
from app.runtime.events import RuntimeEvent
from app.runtime.memory.dto import FactDTO
from app.runtime.memory.preparer import MemoryPreparer, PreparedMemoryContext
from app.runtime.memory.semantic_index import MemorySemanticIndex
from app.runtime.memory.scope_precedence import apply_scope_precedence
from app.services.glossary_service import GlossaryService, ambiguous_glossary_aliases, matching_glossary_terms
from app.services.project_catalog_service import ProjectCatalogService


@dataclass(frozen=True)
class MemoryRecallContext:
    """The only long-term-memory payload visible to planner and sub-agents."""

    resolved_terms: list[dict[str, Any]]
    resolved_entities: list[dict[str, Any]]
    relevant_projects: list[str]
    relevant_knowledge: list[dict[str, Any]]
    applicable_rules: list[dict[str, Any]]
    applicable_procedures: list[dict[str, Any]]
    known_constraints: list[dict[str, Any]]
    durable_facts: list[dict[str, Any]]
    uncertainties: list[str]
    source_references: list[dict[str, Any]]
    rag_required: bool
    rag_reasons: list[str]
    tool_required: bool = False
    clarification_required: bool = False
    clarification_reasons: list[str] | None = None

    def as_item(self) -> dict[str, Any]:
        return {
            "type": "memory_recall",
            "resolved_terms": self.resolved_terms,
            "resolved_entities": self.resolved_entities,
            "relevant_projects": self.relevant_projects,
            "relevant_knowledge": self.relevant_knowledge,
            "applicable_rules": self.applicable_rules,
            "applicable_procedures": self.applicable_procedures,
            "known_constraints": self.known_constraints,
            "durable_facts": self.durable_facts,
            "uncertainties": self.uncertainties,
            "source_references": self.source_references,
            "rag_required": self.rag_required,
            "rag_reasons": self.rag_reasons,
            "tool_required": self.tool_required,
            "clarification_required": self.clarification_required,
            "clarification_reasons": self.clarification_reasons or [],
        }


class MemoryRecallService:
    """Loads semantic memory and turns it into one bounded Recall decision."""

    def __init__(self, *, session: AsyncSession, preparer: MemoryPreparer) -> None:
        self._session = session
        self._preparer = preparer

    async def recall(
        self,
        *,
        request_text: str,
        facts: list[FactDTO],
        user_id: UUID | None,
        tenant_id: UUID | None,
        chat_id: UUID | None,
        sandbox_overrides: dict[str, Any] | None,
        event_sink: Callable[[RuntimeEvent], Awaitable[None]] | None = None,
        agent_execution_id: str | None = None,
    ) -> tuple[MemoryRecallContext, PreparedMemoryContext]:
        # Resolve exact company names from the whole catalogue before applying
        # the prompt budget.  A tenant must not lose project #201 merely
        # because projects are alphabetically ordered.
        all_projects = await ProjectCatalogService(self._session).list_projects()
        project_ids = _query_project_ids(request_text, all_projects)
        all_glossary = await GlossaryService(self._session).list_confirmed_terms()
        glossary = matching_glossary_terms(request_text, all_glossary)
        project_by_id = {str(item["id"]): item for item in all_projects if item.get("id")}
        projects = [item for item in all_projects if item.get("id") in set(project_ids)]
        scope_keys = [f"project.{item['key']}" for item in projects if item["id"] in project_ids]
        collection_ids = await allowed_source_collections(self._session, user_id=user_id, tenant_id=tenant_id)
        read_args = {"project_ids": project_ids, "tenant_id": tenant_id, "user_id": user_id,
                     "context_scope_keys": scope_keys, "collection_ids": collection_ids}
        eligible_ids = await self.eligible_item_ids(**read_args)
        semantic_ids = await MemorySemanticIndex(self._session).search_ids(request_text, limit=48, eligible_ids=eligible_ids)
        lexical_ids = await self._lexical_ids(request_text, limit=48, eligible_ids=eligible_ids, **read_args)
        related_ids = await self._visible_relation_item_ids([
                MemoryRelation.target_type == "project", MemoryRelation.target_id.in_([str(value) for value in project_ids]),
            ] if project_ids else [], eligible_ids=eligible_ids, **read_args)
        term_ids = await self._term_linked_item_ids([UUID(str(term["id"])) for term in glossary],
                                                   eligible_ids=eligible_ids, **read_args)
        candidate_ids = list(dict.fromkeys([*term_ids, *semantic_ids, *lexical_ids, *related_ids]))
        semantic_items = await self._accessible_semantic_items(semantic_ids=candidate_ids, **read_args)
        semantic_items, scope_uncertainties = apply_scope_precedence(semantic_items, project_ids)
        project_facts = [{
            "project_id": item["project_id"],
            "project_key": project_by_id.get(str(item["project_id"]), {}).get("key"),
            "kind": item["kind"], "subject": item["subject"],
            # Ranking needs a bounded projection; the selected item below
            # retains the full structured content and procedures are never
            # cut through a JSON string on their way to the agent.
            "value": _selection_text(item["kind"], item["content"]),
            "content": item["content"],
            "confidence": item["confidence"], "source_ref": f"memory_item:{item['id']}",
            "memory_item_id": str(item["id"]),
            "observed_at": item["observed_at"], "state": item["state"],
            "source_references": item["source_references"],
            # These ids are internal provenance for evidence feedback.  They
            # are claims that passed this tenant's ACL, never all claims of
            # the shared MemoryItem.
            "claim_ids": item["claim_ids"],
        } for item in semantic_items]
        prepared = await self._preparer.prepare(
            request_text=request_text, facts=facts, projects=projects,
            project_facts=project_facts,
            glossary=glossary,
            user_id=user_id, tenant_id=tenant_id, chat_id=chat_id,
            sandbox_overrides=sandbox_overrides, event_sink=event_sink,
            agent_execution_id=agent_execution_id,
        )
        ambiguous_terms = [f"ambiguous_glossary_alias:{form}" for form in
                           ambiguous_glossary_aliases(request_text, glossary)]
        if ambiguous_terms:
            prepared = replace(prepared, ambiguities=[*prepared.ambiguities, *ambiguous_terms])
        if scope_uncertainties:
            prepared = replace(
                prepared, needs_source_check=True,
                source_check_reasons=[*prepared.source_check_reasons, *scope_uncertainties],
            )
        return self._structure(prepared), prepared

    def _eligible_claim_query(self, *, project_ids: list[UUID], tenant_id: UUID | None,
                              context_scope_keys: list[str], user_id: UUID | None = None,
                              collection_ids: list[UUID] = ()):
        return select(MemoryItem, MemoryClaim).join(
            MemoryClaim, MemoryClaim.memory_item_id == MemoryItem.id,
        ).join(RAGDocument, RAGDocument.id == MemoryClaim.document_id).where(
            live_item(), published_claim(),
            source_access(tenant_id=tenant_id, user_id=user_id, collection_ids=collection_ids),
            applicable_claim(project_ids=project_ids, scope_keys=context_scope_keys, tenant_id=tenant_id),
        )

    async def eligible_item_ids(self, *, project_ids: list[UUID], tenant_id: UUID | None,
                               context_scope_keys: list[str], user_id: UUID | None = None,
                               collection_ids: list[UUID] = (), kinds: set[str] = (), categories: set[str] = ()) -> list[UUID]:
        query = self._eligible_claim_query(project_ids=project_ids, tenant_id=tenant_id,
            context_scope_keys=context_scope_keys, user_id=user_id, collection_ids=collection_ids)
        if kinds:
            query = query.where(MemoryItem.item_type.in_(kinds))
        if categories:
            scoped = select(MemoryClaimScope.scope_id).where(MemoryClaimScope.claim_id == MemoryClaim.id).correlate(MemoryClaim)
            from sqlalchemy import exists
            category_match = [exists(scoped.join(MemoryScope, MemoryScope.id == MemoryClaimScope.scope_id).where(
                MemoryScope.scope_type.in_(set(categories).intersection({"project", "team"})), MemoryScope.lifecycle_status == "active"))]
            if "global" in categories:
                category_match.append(and_(~exists(scoped), MemoryItem.project_id.is_(None)))
            if "project" in categories:
                category_match.append(MemoryItem.project_id.is_not(None))
            query = query.where(or_(*category_match))
        rows = await self._session.execute(query.with_only_columns(MemoryItem.id).distinct())
        return list(rows.scalars().all())

    async def _visible_relation_item_ids(self, clauses: list[Any], *, tenant_id: UUID | None,
                                        user_id: UUID | None = None, project_ids: list[UUID] = (),
                                        context_scope_keys: list[str] = (), collection_ids: list[UUID] = (),
                                        eligible_ids: list[UUID] | None = None) -> list[UUID]:
        if not clauses:
            return []
        query = self._eligible_claim_query(project_ids=project_ids, tenant_id=tenant_id,
            context_scope_keys=context_scope_keys, user_id=user_id, collection_ids=collection_ids).join(
                MemoryRelation, and_(MemoryRelation.memory_item_id == MemoryItem.id,
                                     MemoryRelation.document_id == MemoryClaim.document_id),
            ).where(or_(*clauses))
        if eligible_ids is not None:
            query = query.where(MemoryItem.id.in_(eligible_ids))
        rows = await self._session.execute(query.with_only_columns(MemoryItem.id).distinct().limit(48))
        return list(rows.scalars().all())

    async def _term_linked_item_ids(self, term_ids: list[UUID], *, eligible_ids: list[UUID],
                                    tenant_id: UUID | None, user_id: UUID | None, project_ids: list[UUID],
                                    context_scope_keys: list[str], collection_ids: list[UUID]) -> list[UUID]:
        if not term_ids or not eligible_ids:
            return []
        query = self._eligible_claim_query(project_ids=project_ids, tenant_id=tenant_id,
            context_scope_keys=context_scope_keys, user_id=user_id, collection_ids=collection_ids).join(
                MemoryExtractionCandidate, MemoryExtractionCandidate.id == MemoryClaim.approved_candidate_id,
            ).where(MemoryItem.id.in_(eligible_ids), or_(*[
                MemoryExtractionCandidate.related_entities.contains([{"type": "glossary_term", "id": str(id_)}])
                for id_ in term_ids
            ]))
        rows = await self._session.execute(query.with_only_columns(MemoryItem.id).distinct().limit(48))
        return list(rows.scalars().all())

    async def _lexical_ids(self, request_text: str, *, limit: int, eligible_ids: list[UUID] | None = None,
                           tenant_id: UUID | None = None, user_id: UUID | None = None,
                           project_ids: list[UUID] = (), context_scope_keys: list[str] = (),
                           collection_ids: list[UUID] = ()) -> list[UUID]:
        tokens = _query_tokens(request_text)
        if not tokens or eligible_ids == []:
            return []
        clauses = []
        for token in tokens[:8]:
            pattern = f"%{token}%"
            clauses.extend((MemoryItem.subject.ilike(pattern), MemoryClaim.content_text.ilike(pattern)))
        query = self._eligible_claim_query(project_ids=project_ids, tenant_id=tenant_id,
            context_scope_keys=context_scope_keys, user_id=user_id, collection_ids=collection_ids).where(or_(*clauses))
        if eligible_ids is not None:
            query = query.where(MemoryItem.id.in_(eligible_ids))
        # Ranking uses visible claim wording; inaccessible claims cannot affect it.
        from sqlalchemy import func
        rows = await self._session.execute(query.with_only_columns(MemoryItem.id).group_by(MemoryItem.id)
            .order_by(func.max(MemoryClaim.updated_at).desc(), MemoryItem.id).limit(limit))
        return list(rows.scalars().all())

    async def _accessible_semantic_items(self, *, project_ids: list[UUID], semantic_ids: list[UUID],
                                        tenant_id: UUID | None, context_scope_keys: list[str] = (),
                                        user_id: UUID | None = None, collection_ids: list[UUID] | None = None) -> list[dict[str, Any]]:
        if not project_ids and not semantic_ids:
            return []
        if collection_ids is None:
            collection_ids = await allowed_source_collections(self._session, user_id=user_id, tenant_id=tenant_id)
        query = self._eligible_claim_query(project_ids=project_ids, tenant_id=tenant_id,
            context_scope_keys=context_scope_keys, user_id=user_id, collection_ids=collection_ids)
        candidate_filter = MemoryItem.id.in_(semantic_ids) if semantic_ids else MemoryItem.project_id.in_(project_ids)
        rows = await self._session.execute(query.where(candidate_filter))
        # An item is an identity. Its text must be resolved from claims whose
        # document is visible to this tenant; using the globally consolidated
        # winner here can disclose a claim from another department.
        by_item: dict[UUID, tuple[MemoryItem, list[MemoryClaim]]] = {}
        for item, claim in rows.all():
            current = by_item.get(item.id)
            if current is None:
                by_item[item.id] = (item, [claim])
            else:
                current[1].append(claim)
        claim_ids = [claim.id for _, claims in by_item.values() for claim in claims]
        scope_rows = (await self._session.execute(
            select(MemoryClaimScope.claim_id, MemoryScope)
            .join(MemoryScope, MemoryScope.id == MemoryClaimScope.scope_id)
            .where(MemoryClaimScope.claim_id.in_(claim_ids))
        )).all() if claim_ids else []
        claim_scopes: dict[UUID, list[MemoryScope]] = {}
        for claim_id, scope in scope_rows:
            claim_scopes.setdefault(claim_id, []).append(scope)
        trusted_scope_keys = {str(key).strip().lower() for key in context_scope_keys}
        rank = {item_id: index for index, item_id in enumerate(semantic_ids)}
        result: list[dict[str, Any]] = []
        for item_id, (item, claims) in by_item.items():
            applicable_claims = [claim for claim in claims if
                _item_is_applicable(item, project_ids, tenant_id, claim.applicability)
                and _claim_scopes_apply(claim_scopes.get(claim.id, []), project_ids, trusted_scope_keys,
                    legacy_project_id=getattr(claim, "project_id", None) or item.project_id,
                    legacy_applicability=claim.applicability)]
            if not applicable_claims:
                continue
            by_scope: dict[tuple[tuple[str, ...], str], list[MemoryClaim]] = {}
            for claim in applicable_claims:
                signature = (tuple(sorted(scope.key for scope in claim_scopes.get(claim.id, [])
                                          if getattr(scope, "lifecycle_status", "active") == "active")),
                             json.dumps(claim.applicability or {}, sort_keys=True))
                by_scope.setdefault(signature, []).append(claim)
            for claims in by_scope.values():
                result.append(self._scoped_item_projection(item, claims, claim_scopes, rank))
        return sorted(result, key=lambda item: (item["rank"], -float(item["confidence"])))

    @staticmethod
    def _scoped_item_projection(item, claims, claim_scopes, rank) -> dict[str, Any]:
        # Resolve wording independently for each applicability group. Two
        # selected scopes may legitimately have different source claims.
        claims.sort(key=lambda claim: (claim.confidence, claim.updated_at), reverse=True)
        winner = claims[0]
        # A tenant-local claim must not poison the effective truth seen by
        # other departments.  State is derived from claims visible for
        # this recall; the consolidated item remains an identity/index
        # record, not an ACL-blind read model.
        conflicting = len({claim.content_text for claim in claims}) > 1
        return {
            "id": item.id, "project_id": item.project_id, "kind": item.item_type,
            "applicability": dict(winner.applicability or {}),
            "scope_keys": sorted(scope.key for scope in claim_scopes.get(winner.id, [])
                                 if getattr(scope, "lifecycle_status", "active") == "active"),
            "subject": item.subject, "content": dict(winner.content or {}), "content_text": winner.content_text,
            "confidence": winner.confidence,
            # Item-level uncertainty can come from an inaccessible tenant
            # claim.  This context is based solely on visible claims.
            "state": "uncertain" if conflicting else "active",
            "observed_at": item.last_verified_at.isoformat() if item.last_verified_at else None,
            "source_references": [
                {"document_id": str(claim.document_id), "checksum": claim.canonical_checksum,
                 "section_id": section_id, "label": section_id}
                for claim in claims for section_id in list(claim.evidence_section_ids or [])[:3]
            ][:3],
            "claim_ids": [str(claim.id) for claim in claims],
            # The first claim is the ACL-visible winner.  Feedback must
            # evaluate this exact wording, not an arbitrary row returned
            # by a later SQL query.
            "selected_claim_id": str(winner.id),
            "approved_candidate_id": str(winner.approved_candidate_id) if getattr(winner, "approved_candidate_id", None) else None,
            "rank": rank.get(item.id, len(rank)),
        }

    @staticmethod
    def _structure(
        prepared: PreparedMemoryContext, *, resolved_entities: list[dict[str, Any]] | None = None,
        entity_ambiguities: list[str] | None = None,
    ) -> MemoryRecallContext:
        facts = [item for item in prepared.items if item.get("type") == "fact"]
        knowledge = [
            item for item in prepared.items
            if item.get("type") in {"company_knowledge", "project_knowledge"}
        ]
        def typed(kind: str) -> list[dict[str, Any]]:
            return [item for item in knowledge if item.get("kind") == kind]
        glossary_items = [item for item in prepared.items if item.get("type") == "glossary"]
        source_refs = [
            ref for item in [*knowledge, *glossary_items] for ref in item.get("source_references", [])
            if isinstance(ref, dict)
        ]
        return MemoryRecallContext(
            resolved_terms=prepared.resolved_terms,
            resolved_entities=resolved_entities or [],
            relevant_projects=prepared.resolved_projects,
            relevant_knowledge=[item for item in knowledge if item.get("kind") not in {"rule", "constraint", "procedure"}],
            applicable_rules=typed("rule"), applicable_procedures=typed("procedure"),
            known_constraints=typed("constraint"), durable_facts=facts,
            uncertainties=[*prepared.ambiguities, *prepared.source_check_reasons, *(entity_ambiguities or [])],
            source_references=source_refs,
            rag_required=prepared.needs_source_check,
            rag_reasons=prepared.source_check_reasons,
            tool_required=prepared.tool_required or prepared.intent == "action",
            clarification_required=bool(prepared.ambiguities or entity_ambiguities),
            clarification_reasons=[*prepared.ambiguities, *(entity_ambiguities or [])],
        )


def _query_tokens(value: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r"[\wа-яА-ЯёЁ-]{3,}", str(value or "").casefold())))


def _selection_text(kind: str, content: dict[str, Any]) -> str:
    if kind == "procedure":
        steps = content.get("steps") if isinstance(content.get("steps"), list) else []
        return " ".join([
            str(content.get("goal") or ""),
            *(str(step.get("instruction") or "") for step in steps if isinstance(step, dict)),
        ])[:2_000]
    return str(content)[:2_000]


def _query_project_ids(request_text: str, projects: list[dict[str, Any]]) -> list[UUID]:
    query = " ".join(_query_tokens(request_text))
    result: list[UUID] = []
    for project in projects:
        raw_id = project.get("id")
        if not raw_id:
            continue
        forms = [project.get("key"), project.get("name"), *(project.get("aliases") or [])]
        if any(_project_form_matches(str(form or ""), query) for form in forms):
            result.append(raw_id)
    return list(dict.fromkeys(result))


def _project_form_matches(form: str, query: str) -> bool:
    normalized = form.casefold().strip()
    # Short forms are common company abbreviations.  Accept only an exact
    # token for them; fuzzy matching stays limited to substantive names.
    if normalized and normalized in query.split():
        return True
    if len(normalized) < 3:
        return False
    if normalized in query:
        return True
    return any(
        len(token) >= 4 and SequenceMatcher(a=normalized, b=token).ratio() >= 0.8
        for token in query.split()
    )


def _item_is_applicable(
    item: MemoryItem, project_ids: list[UUID], tenant_id: UUID | None,
    claim_applicability: dict[str, Any] | None = None,
) -> bool:
    """Enforce declared applicability/visibility after source ACL filtering.

    Only the documented source visibility and project/tenant applicability
    contract is accepted.  Unknown non-empty restrictions fail closed: an
    extractor must never accidentally widen access to a scoped procedure.
    """
    visibility = dict(item.visibility or {})
    if visibility.get("mode", "source") != "source":
        return False
    if set(visibility).difference({"mode", "tenant_ids", "denied_tenant_ids"}):
        return False
    tenant_key = str(tenant_id) if tenant_id is not None else None
    allowed_tenants = {str(value) for value in visibility.get("tenant_ids") or []}
    denied_tenants = {str(value) for value in visibility.get("denied_tenant_ids") or []}
    if tenant_key in denied_tenants or (allowed_tenants and tenant_key not in allowed_tenants):
        return False
    applicability = dict(claim_applicability if claim_applicability is not None else item.applicability or {})
    if set(applicability).difference({"project_ids", "tenant_ids"}):
        return False
    scope = getattr(item, "scope", None)
    owner_type = getattr(item, "owner_type", None)
    owner_id = getattr(item, "owner_id", None)
    project_id = getattr(item, "project_id", None)
    # Old rows/tests may predate explicit owner columns; a real persisted row
    # is validated below, while compatibility-shaped objects keep the ACL test
    # focused on their declared JSON restrictions.
    if scope == "project" and owner_type is not None and (owner_type != "project" or owner_id != project_id):
        return False
    if scope == "company" and owner_type is not None and owner_type != "company":
        return False
    required_projects = {str(value) for value in applicability.get("project_ids") or []}
    if required_projects and not required_projects.intersection(str(value) for value in project_ids):
        return False
    required_tenants = {str(value) for value in applicability.get("tenant_ids") or []}
    return not required_tenants or tenant_key in required_tenants


def _claim_scopes_apply(
    scopes: list[MemoryScope], project_ids: list[UUID], context_scope_keys: set[str], *, legacy_project_id: UUID | None = None,
    legacy_applicability: dict[str, Any] | None = None,
) -> bool:
    """Use the same branch semantics as SQL and task context projection."""
    from app.runtime.memory.effective_scope import memory_visible_for_scope
    keys = set(context_scope_keys)
    active = [scope for scope in scopes if getattr(scope, "lifecycle_status", "active") == "active"]
    types = {scope.scope_type for scope in scopes}
    if any(not any(scope.scope_type == type_ for scope in active) for type_ in types):
        return False
    if project_ids:
        keys.add("project._legacy_selected")
    if not any(scope.scope_type == "project" for scope in scopes):
        required = {str(value) for value in (legacy_applicability or {}).get("project_ids", [])}
        if legacy_project_id is not None:
            required.add(str(legacy_project_id))
        if required:
            if not required.intersection(str(value) for value in project_ids):
                return False
            keys = {key for key in keys if not key.startswith("project.")}
    # Legacy Project IDs can select a typed scope without a key in the caller.
    for scope in active:
        if scope.scope_type == "project" and scope.project_id in set(project_ids):
            keys.add(scope.key)
    return memory_visible_for_scope({"scope_keys": [scope.key for scope in active]}, keys)
