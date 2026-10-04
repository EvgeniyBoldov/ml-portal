"""Administrative editing of a published atom's scope and terminology links."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_memory_staging import (
    GlossaryTerm, MemoryCandidateDecision, MemoryCandidateProjectBinding, MemoryExtractionCandidate,
)
from app.models.memory import MemoryClaim, MemoryItem
from app.models.memory_scope import MemoryClaimScope, MemoryScope
from app.runtime.memory.shadow_memory_publication import ShadowMemoryPublicationService, _scope_signature
from app.services.glossary_service import GlossaryService


class MemoryLinksService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def update_item(
        self, *, item_id: UUID, actor_id: UUID, scope_ids: list[UUID],
        glossary_term_ids: list[UUID], reason: str = "",
    ) -> None:
        item = await self._session.scalar(select(MemoryItem).where(
            MemoryItem.id == item_id, MemoryItem.lifecycle_status == "active",
        ).with_for_update())
        if item is None:
            raise ValueError("Memory item not found")
        ids = set(scope_ids)
        scopes = list((await self._session.scalars(select(MemoryScope).where(
            MemoryScope.id.in_(ids), MemoryScope.lifecycle_status == "active",
        ))).all()) if ids else []
        if {scope.id for scope in scopes} != ids:
            raise ValueError("Выберите действующие скоупы")
        if any(scope.is_all and any(other.scope_type == scope.scope_type and not other.is_all
                                   for other in scopes) for scope in scopes):
            raise ValueError("Область «все» не совмещается с отдельными областями того же типа")
        term_ids = set(glossary_term_ids)
        terms = list((await self._session.scalars(GlossaryService.published_terms_query().where(
            GlossaryTerm.id.in_(term_ids),
        ))).all()) if term_ids else []
        if {term.id for term in terms} != term_ids:
            raise ValueError("Выберите существующие опубликованные термины")
        claims = list((await self._session.scalars(select(MemoryClaim).where(
            MemoryClaim.memory_item_id == item.id,
        ).order_by(MemoryClaim.id).with_for_update())).all())
        if not claims or not any(claim.approved_candidate_id for claim in claims):
            raise ValueError("Memory item has no approved source candidates")
        signature = _scope_signature(scopes)
        collision = await self._session.scalar(select(MemoryItem.id).where(
            MemoryItem.id != item.id, MemoryItem.scope == "company", MemoryItem.project_id.is_(None),
            MemoryItem.item_type == item.item_type, MemoryItem.normalized_subject == item.normalized_subject,
            MemoryItem.scope_signature == signature,
        ).limit(1))
        if collision:
            raise ValueError("Атом с этой темой, типом и скоупами уже существует")
        candidate_ids = {claim.approved_candidate_id for claim in claims if claim.approved_candidate_id}
        candidates = list((await self._session.scalars(select(MemoryExtractionCandidate).where(
            MemoryExtractionCandidate.id.in_(candidate_ids), MemoryExtractionCandidate.resolution_status == "resolved",
        ).order_by(MemoryExtractionCandidate.id).with_for_update())).all())
        if {candidate.id for candidate in candidates} != candidate_ids:
            raise ValueError("Memory source candidates are no longer approved")
        reason = reason.strip() or "Связи атома изменены администратором"
        publisher = ShadowMemoryPublicationService(self._session)
        for candidate in candidates:
            before = {"scope": candidate.scope_candidate, "related_entities": candidate.related_entities,
                      "item_scope_signature": item.scope_signature}
            await publisher._confirm_scope_bindings(candidate.id, scopes)
            candidate.related_entities = [entity for entity in candidate.related_entities or []
                                          if entity.get("type") != "glossary_term"] + [
                {"type": "glossary_term", "id": str(term.id), "name": term.canonical_term} for term in terms
            ]
            candidate.related_project_keys = [scope.key.removeprefix("project.") for scope in scopes
                                              if scope.scope_type == "project" and not scope.is_all]
            candidate.scope_candidate = "scoped" if scopes else "global"
            candidate.resolution_method = "manual"
            candidate.resolution_rationale = reason
            project_bindings = list((await self._session.scalars(select(MemoryCandidateProjectBinding).where(
                MemoryCandidateProjectBinding.candidate_id == candidate.id,
                MemoryCandidateProjectBinding.role == "applies_to",
            ))).all())
            projects = {scope.project_id for scope in scopes if scope.project_id}
            for binding in project_bindings:
                binding.status = "confirmed" if binding.project_id in projects else "rejected"
            bound_projects = {binding.project_id for binding in project_bindings}
            for project_id in projects - bound_projects:
                self._session.add(MemoryCandidateProjectBinding(candidate_id=candidate.id, project_id=project_id,
                    role="applies_to", status="confirmed", method="manual", confidence=1.0, rationale=reason))
            self._session.add(MemoryCandidateDecision(candidate_id=candidate.id, actor_user_id=actor_id,
                action="edit", reason=reason, payload={"published_item_id": str(item.id), "before": before,
                    "scope_ids": [str(scope.id) for scope in scopes], "glossary_term_ids": [str(term.id) for term in terms]}))
        await self._session.execute(delete(MemoryClaimScope).where(
            MemoryClaimScope.claim_id.in_([claim.id for claim in claims]),
        ))
        for claim in claims:
            claim.scope, claim.project_id, claim.scope_signature = "company", None, signature
            self._session.add_all([MemoryClaimScope(claim_id=claim.id, scope_id=scope.id) for scope in scopes])
        item.scope, item.project_id, item.scope_signature = "company", None, signature
        item.owner_type, item.owner_id = "company", None
        await self._session.flush()
