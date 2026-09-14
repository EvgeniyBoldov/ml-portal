"""Structured, mandatory semantic-memory recall before planning."""
from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Awaitable, Callable
from uuid import UUID

import re

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import MemoryClaim, MemoryItem, MemoryRelation
from app.models.knowledge_entity import KnowledgeEntity, KnowledgeEntitySource
from app.models.rag import RAGDocument
from app.runtime.events import RuntimeEvent
from app.runtime.memory.dto import FactDTO
from app.runtime.memory.preparer import MemoryPreparer, PreparedMemoryContext
from app.runtime.memory.semantic_index import MemorySemanticIndex
from app.services.glossary_service import GlossaryService


@dataclass(frozen=True)
class MemoryRecallContext:
    """The only long-term-memory payload visible to planner and sub-agents."""

    resolved_terms: list[str]
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
        all_project_glossary = await GlossaryService(self._session).list_project_terms()
        project_ids = _query_project_ids(request_text, all_project_glossary)
        project_glossary = [item for item in all_project_glossary if item.get("id") in set(project_ids)]
        all_glossary = await GlossaryService(self._session).list_confirmed_terms(tenant_id=tenant_id)
        glossary = _matching_glossary_terms(request_text, all_glossary)
        entity_refs = _query_glossary_entity_refs(request_text, glossary)
        glossary_project_ids = _glossary_project_ids(glossary)
        resolved_entities, entity_project_ids, entity_ambiguities = await self._resolve_visible_entities(
            entity_refs=entity_refs, tenant_id=tenant_id, explicit_project_ids=project_ids,
        )
        project_ids = list(dict.fromkeys([*project_ids, *glossary_project_ids, *entity_project_ids]))
        project_by_id = {str(item["id"]): item for item in all_project_glossary if item.get("id")}
        project_glossary = [item for item in all_project_glossary if item.get("id") in set(project_ids)]
        semantic_ids = await MemorySemanticIndex(self._session).search_ids(request_text, limit=48)
        lexical_ids = await self._lexical_ids(request_text, limit=48)
        related_ids = await self._visible_relation_item_ids(
            [and_(
                MemoryRelation.target_type == "project",
                MemoryRelation.target_id.in_([str(value) for value in project_ids]),
            )] if project_ids else [],
            tenant_id=tenant_id,
        )
        entity_related_ids: list[UUID] = []
        if entity_refs:
            clauses = [and_(MemoryRelation.target_type == item["type"], MemoryRelation.target_id == item["id"])
                       for item in entity_refs]
            entity_related_ids = await self._visible_relation_item_ids(clauses, tenant_id=tenant_id)
        candidate_ids = list(dict.fromkeys([*semantic_ids, *lexical_ids, *related_ids, *entity_related_ids]))
        semantic_items = await self._accessible_semantic_items(
            project_ids=project_ids, semantic_ids=candidate_ids, tenant_id=tenant_id,
        )
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
            request_text=request_text, facts=facts, project_glossary=project_glossary,
            project_facts=project_facts,
            glossary=glossary,
            user_id=user_id, tenant_id=tenant_id, chat_id=chat_id,
            sandbox_overrides=sandbox_overrides, event_sink=event_sink,
            agent_execution_id=agent_execution_id,
        )
        return self._structure(
            prepared, resolved_entities=resolved_entities, entity_ambiguities=entity_ambiguities,
        ), prepared

    async def _resolve_visible_entities(
        self, *, entity_refs: list[dict[str, str]], tenant_id: UUID | None,
        explicit_project_ids: list[UUID],
    ) -> tuple[list[dict[str, Any]], list[UUID], list[str]]:
        refs = [item for item in entity_refs if item.get("type") != "project"]
        if not refs:
            return [], [], []
        entity_ids: list[UUID] = []
        for ref in refs:
            try:
                entity_ids.append(UUID(str(ref["id"])))
            except (KeyError, TypeError, ValueError):
                continue
        if not entity_ids:
            return [], [], []
        visibility = KnowledgeEntitySource.visibility_tenant_id.is_(None)
        document_access = RAGDocument.scope == "global"
        if tenant_id is not None:
            visibility = or_(visibility, KnowledgeEntitySource.visibility_tenant_id == tenant_id)
            document_access = or_(document_access, RAGDocument.tenant_id == tenant_id)
        rows = (await self._session.execute(
            select(KnowledgeEntity, KnowledgeEntitySource)
            .join(KnowledgeEntitySource, KnowledgeEntitySource.entity_id == KnowledgeEntity.id)
            .join(RAGDocument, RAGDocument.id == KnowledgeEntitySource.document_id)
            .where(
                KnowledgeEntity.id.in_(entity_ids), KnowledgeEntity.is_active.is_(True), visibility,
                document_access, RAGDocument.status != "archived",
            )
        )).all()
        sources_by_entity: dict[UUID, list[KnowledgeEntitySource]] = {}
        entities: dict[UUID, KnowledgeEntity] = {}
        for entity, source in rows:
            entities[entity.id] = entity
            sources_by_entity.setdefault(entity.id, []).append(source)
        explicit = set(explicit_project_ids)
        resolved: list[dict[str, Any]] = []
        inferred_projects: list[UUID] = []
        ambiguities: list[str] = []
        matched_forms = {
            str(ref["id"]): ref.get("matched_form")
            for ref in refs if ref.get("id")
        }
        for entity_id, sources in sources_by_entity.items():
            entity = entities[entity_id]
            project_ids = {source.project_id for source in sources if source.project_id is not None}
            candidates = project_ids.intersection(explicit) if explicit else project_ids
            if len(candidates) == 1:
                inferred_projects.extend(candidates)
            elif len(candidates) > 1:
                ambiguities.append(f"ambiguous_entity_project:{entity.canonical_name}")
            resolved.append({
                "id": str(entity.id), "type": entity.entity_type,
                "canonical_name": entity.canonical_name,
                "matched_form": matched_forms.get(str(entity.id)),
                "project_ids": [str(value) for value in sorted(project_ids, key=str)],
                "source_references": [
                    {"document_id": str(source.document_id), "section_id": section_id}
                    for source in sources for section_id in list(source.evidence_section_ids or [])[:2]
                ][:3],
            })
        return resolved, list(dict.fromkeys(inferred_projects)), ambiguities

    async def _visible_relation_item_ids(
        self, clauses: list[Any], *, tenant_id: UUID | None,
    ) -> list[UUID]:
        """Use graph edges only when their originating claim is visible.

        Relations are derived data.  Filtering the final MemoryItem alone is
        insufficient: an inaccessible document could otherwise alter which
        project/entity makes an otherwise visible item retrievable.
        """
        if not clauses:
            return []
        document_access = RAGDocument.scope == "global"
        claim_visibility = MemoryClaim.visibility_tenant_id.is_(None)
        if tenant_id is not None:
            document_access = or_(document_access, RAGDocument.tenant_id == tenant_id)
            claim_visibility = or_(claim_visibility, MemoryClaim.visibility_tenant_id == tenant_id)
        rows = await self._session.execute(
            select(MemoryRelation.memory_item_id)
            .join(
                MemoryClaim,
                and_(
                    MemoryClaim.memory_item_id == MemoryRelation.memory_item_id,
                    MemoryClaim.document_id == MemoryRelation.document_id,
                ),
            )
            .join(RAGDocument, RAGDocument.id == MemoryRelation.document_id)
            .where(
                or_(*clauses),
                MemoryClaim.state == "active",
                claim_visibility,
                document_access,
                RAGDocument.status != "archived",
            )
            .limit(96)
        )
        return list(dict.fromkeys(rows.scalars().all()))[:48]

    async def _lexical_ids(self, request_text: str, *, limit: int) -> list[UUID]:
        """Exact terms/codes complement vector search and survive its outage."""
        tokens = _query_tokens(request_text)
        if not tokens:
            return []
        clauses = []
        for token in tokens[:8]:
            pattern = f"%{token}%"
            clauses.extend((MemoryItem.subject.ilike(pattern), MemoryItem.content_text.ilike(pattern)))
        rows = await self._session.execute(
            select(MemoryItem.id).where(
                MemoryItem.state.in_(("active", "uncertain")), or_(*clauses),
            ).order_by(MemoryItem.last_verified_at.desc()).limit(limit)
        )
        return list(rows.scalars().all())

    async def _accessible_semantic_items(
        self, *, project_ids: list[UUID], semantic_ids: list[UUID], tenant_id: UUID | None,
    ) -> list[dict[str, Any]]:
        if not project_ids and not semantic_ids:
            return []
        document_access = RAGDocument.scope == "global"
        if tenant_id is not None:
            document_access = or_(document_access, RAGDocument.tenant_id == tenant_id)
        candidate_filter = MemoryItem.id.in_(semantic_ids) if semantic_ids else MemoryItem.project_id.in_(project_ids)
        claim_visibility = MemoryClaim.visibility_tenant_id.is_(None)
        if tenant_id is not None:
            claim_visibility = or_(claim_visibility, MemoryClaim.visibility_tenant_id == tenant_id)
        rows = await self._session.execute(
            select(MemoryItem, MemoryClaim)
            .join(MemoryClaim, MemoryClaim.memory_item_id == MemoryItem.id)
            .join(RAGDocument, RAGDocument.id == MemoryClaim.document_id)
            .where(
                candidate_filter,
                MemoryItem.state.in_(("active", "uncertain")),
                MemoryClaim.state == "active",
                claim_visibility,
                document_access,
                RAGDocument.status != "archived",
            )
            .limit(2400)
        )
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
        rank = {item_id: index for index, item_id in enumerate(semantic_ids)}
        result: list[dict[str, Any]] = []
        for item_id, (item, claims) in by_item.items():
            applicable_claims = [claim for claim in claims if _item_is_applicable(item, project_ids, tenant_id, claim.applicability)]
            if not applicable_claims:
                continue
            claims = applicable_claims
            claims.sort(key=lambda claim: (claim.confidence, claim.updated_at), reverse=True)
            winner = claims[0]
            # A tenant-local claim must not poison the effective truth seen by
            # other departments.  State is derived from claims visible for
            # this recall; the consolidated item remains an identity/index
            # record, not an ACL-blind read model.
            conflicting = len({claim.content_text for claim in claims}) > 1
            result.append({
                "id": item.id, "project_id": item.project_id, "kind": item.item_type,
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
                "rank": rank.get(item_id, len(rank)),
            })
        return sorted(result, key=lambda item: (item["rank"], -float(item["confidence"])))

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
        source_refs = [
            ref for item in knowledge for ref in item.get("source_references", [])
            if isinstance(ref, dict)
        ]
        # `prepare` keeps compatibility-shaped entries; sources are restored
        # below by their stable source_ref in a following normalization pass.
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


def _glossary_project_ids(glossary: list[dict[str, Any]]) -> list[UUID]:
    result: list[UUID] = []
    for term in glossary:
        raw = term.get("project_id")
        if raw is None and term.get("entity_type") == "project":
            raw = term.get("entity_id")
        try:
            result.append(UUID(str(raw)))
        except (TypeError, ValueError):
            continue
    return list(dict.fromkeys(result))


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


def _query_glossary_entity_refs(request_text: str, glossary: list[dict[str, Any]]) -> list[dict[str, str]]:
    query = " ".join(_query_tokens(request_text))
    result: list[dict[str, str]] = []
    for term in glossary:
        entity_type = str(term.get("entity_type") or "").strip()
        entity_id = str(term.get("entity_id") or "").strip()
        forms = [term.get("term"), *(term.get("aliases") or [])]
        matched_form = next(
            (str(form) for form in forms if _project_form_matches(str(form or ""), query)),
            None,
        )
        if entity_type and entity_id and matched_form is not None:
            # One entity can be represented by several safe source aliases;
            # retain one form for observability without duplicating the graph
            # lookup and its relation candidates.
            if not any(ref["type"] == entity_type and ref["id"] == entity_id for ref in result):
                result.append({"type": entity_type, "id": entity_id, "matched_form": matched_form})
    return result


def _matching_glossary_terms(request_text: str, glossary: list[dict[str, Any]], *, limit: int = 24) -> list[dict[str, Any]]:
    query = " ".join(_query_tokens(request_text))
    return [
        term for term in glossary
        if any(_project_form_matches(str(form or ""), query) for form in [term.get("term"), *(term.get("aliases") or [])])
    ][:limit]


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
