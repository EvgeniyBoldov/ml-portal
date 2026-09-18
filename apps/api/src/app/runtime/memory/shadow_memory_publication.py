"""Transactional manual publication of approved shadow candidates."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_memory_staging import (
    DocumentMemorySnapshot, GlossaryMeaning, GlossaryMeaningProjectBinding,
    MemoryCandidateDecision, MemoryCandidateProjectBinding, MemoryExtractionCandidate,
)
from app.models.glossary import GlossaryEntry
from app.models.memory import MemoryClaim, MemoryItem, MemoryItemSource
from app.models.project import Project


class ShadowMemoryPublicationService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def approve(self, *, candidate_id: UUID, actor_id: UUID | None, reason: str | None,
                      content: dict | None = None, scope: str | None = None,
                      project_id: UUID | None = None, promote_to_company: bool = False,
                      automatic: bool = False) -> MemoryExtractionCandidate:
        candidate = await self._required_candidate(candidate_id)
        if candidate.resolution_status not in {"needs_review", "conflict"}:
            return candidate
        snapshot = await self._session.get(DocumentMemorySnapshot, candidate.snapshot_id)
        if snapshot is None:
            raise ValueError("Candidate snapshot is unavailable")
        if content is not None:
            candidate.content = content
            candidate.content_text = json.dumps(content, ensure_ascii=False, sort_keys=True)
        chosen_scope = scope or candidate.scope_candidate
        if chosen_scope not in {"global", "project"}:
            raise ValueError("Choose global or project applicability before approval")
        project = await self._project_for(candidate, project_id, chosen_scope)
        visibility = None if promote_to_company else candidate.visibility_tenant_id
        if candidate.candidate_type == "term":
            await self._publish_term(candidate, project, visibility)
        else:
            await self._publish_memory(candidate, snapshot, project, visibility)
        candidate.scope_candidate = chosen_scope
        candidate.visibility_tenant_id = visibility
        candidate.resolution_status = "resolved"
        candidate.resolution_method = "manual" if not automatic else "content_evidence"
        candidate.resolution_rationale = reason
        self._session.add(MemoryCandidateDecision(
            candidate_id=candidate.id, actor_user_id=actor_id,
            action="autoapprove" if automatic else "approve", reason=reason,
            payload={"scope": chosen_scope, "project_id": str(project.id) if project else None,
                     "promote_to_company": promote_to_company},
        ))
        await self._update_snapshot(snapshot)
        return candidate

    async def reject(self, *, candidate_id: UUID, actor_id: UUID | None, reason: str | None) -> MemoryExtractionCandidate:
        candidate = await self._required_candidate(candidate_id)
        candidate.resolution_status = "rejected"
        candidate.resolution_method = "manual"
        candidate.resolution_rationale = reason
        await self._session.execute(
            update(GlossaryMeaning).where(GlossaryMeaning.candidate_id == candidate.id)
            .values(resolution_status="rejected", resolution_method="manual", resolution_rationale=reason)
        )
        self._session.add(MemoryCandidateDecision(candidate_id=candidate.id, actor_user_id=actor_id, action="reject", reason=reason))
        snapshot = await self._session.get(DocumentMemorySnapshot, candidate.snapshot_id)
        if snapshot:
            await self._update_snapshot(snapshot)
        return candidate

    async def _required_candidate(self, candidate_id: UUID) -> MemoryExtractionCandidate:
        candidate = await self._session.get(MemoryExtractionCandidate, candidate_id)
        if candidate is None:
            raise ValueError("Memory candidate not found")
        return candidate

    async def _project_for(self, candidate: MemoryExtractionCandidate, project_id: UUID | None, scope: str) -> Project | None:
        if scope == "global":
            return None
        binding = (await self._session.execute(select(MemoryCandidateProjectBinding).where(
            MemoryCandidateProjectBinding.candidate_id == candidate.id,
            MemoryCandidateProjectBinding.project_id == project_id,
        ))).scalar_one_or_none() if project_id else None
        if binding is None:
            raise ValueError("A project candidate requires an explicit project binding")
        binding.status = "confirmed"
        project = await self._session.get(Project, project_id)
        if project is None:
            raise ValueError("Project not found")
        return project

    async def _publish_memory(self, candidate: MemoryExtractionCandidate, snapshot: DocumentMemorySnapshot,
                              project: Project | None, visibility: UUID | None) -> None:
        scope = "project" if project else "company"
        item = (await self._session.execute(select(MemoryItem).where(
            MemoryItem.scope == scope, MemoryItem.item_type == candidate.candidate_type,
            MemoryItem.normalized_subject == candidate.normalized_subject,
            MemoryItem.project_id == project.id if project else MemoryItem.project_id.is_(None),
        ))).scalar_one_or_none()
        if item is None:
            item = MemoryItem(scope=scope, item_type=candidate.candidate_type, project_id=project.id if project else None,
                owner_type="project" if project else "company", owner_id=project.id if project else None,
                subject=candidate.subject, normalized_subject=candidate.normalized_subject,
                content=dict(candidate.content or {}), content_text=candidate.content_text,
                confidence=candidate.extraction_confidence, extraction_confidence=candidate.extraction_confidence,
                state="active", visibility={"mode": "source"})
            self._session.add(item); await self._session.flush()
        claim = (await self._session.execute(select(MemoryClaim).where(
            MemoryClaim.document_id == snapshot.document_id, MemoryClaim.canonical_checksum == snapshot.canonical_checksum,
            MemoryClaim.scope == scope, MemoryClaim.item_type == candidate.candidate_type,
            MemoryClaim.normalized_subject == candidate.normalized_subject,
            MemoryClaim.project_id == project.id if project else MemoryClaim.project_id.is_(None),
        ))).scalar_one_or_none()
        if claim is None:
            claim = MemoryClaim(memory_item_id=item.id, document_id=snapshot.document_id, canonical_checksum=snapshot.canonical_checksum,
                scope=scope, item_type=candidate.candidate_type, project_id=project.id if project else None,
                visibility_tenant_id=visibility, normalized_subject=candidate.normalized_subject,
                content=dict(candidate.content or {}), content_text=candidate.content_text,
                evidence_section_ids=list(candidate.evidence_section_ids or []), confidence=candidate.extraction_confidence,
                extraction_confidence=candidate.extraction_confidence, state="active")
            self._session.add(claim)
        for section_id in candidate.evidence_section_ids or []:
            exists = (await self._session.execute(select(MemoryItemSource.id).where(
                MemoryItemSource.memory_item_id == item.id, MemoryItemSource.document_id == snapshot.document_id,
                MemoryItemSource.canonical_checksum == snapshot.canonical_checksum, MemoryItemSource.section_id == section_id,
            ))).scalar_one_or_none()
            if not exists:
                self._session.add(MemoryItemSource(memory_item_id=item.id, document_id=snapshot.document_id,
                    canonical_checksum=snapshot.canonical_checksum, section_id=section_id))

    async def _publish_term(self, candidate: MemoryExtractionCandidate, project: Project | None, visibility: UUID | None) -> None:
        scope = "project" if project else ("tenant" if visibility else "global")
        entry = (await self._session.execute(select(GlossaryEntry).where(
            GlossaryEntry.scope == scope, GlossaryEntry.tenant_id == visibility,
            GlossaryEntry.project_id == (project.id if project else None), GlossaryEntry.canonical_term == candidate.subject,
        ))).scalar_one_or_none()
        if entry is None:
            entry = GlossaryEntry(scope=scope, tenant_id=visibility if scope == "tenant" else None,
                project_id=project.id if project else None, canonical_term=candidate.subject,
                aliases=list(candidate.aliases or []), description=str(candidate.content.get("definition") or ""), status="confirmed")
            self._session.add(entry)
        await self._session.execute(
            update(GlossaryMeaning).where(GlossaryMeaning.candidate_id == candidate.id)
            .values(resolution_status="resolved", resolution_method="manual", visibility_tenant_id=visibility)
        )

    async def _update_snapshot(self, snapshot: DocumentMemorySnapshot) -> None:
        open_count = (await self._session.execute(select(MemoryExtractionCandidate.id).where(
            MemoryExtractionCandidate.snapshot_id == snapshot.id,
            MemoryExtractionCandidate.resolution_status.in_(("extracted", "needs_review", "conflict")),
        ).limit(1))).scalar_one_or_none()
        if open_count is None:
            snapshot.status = "approved"
