"""Transactional manual publication of approved shadow candidates."""
from __future__ import annotations

import json
import hashlib
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_memory_staging import (
    DocumentMemorySnapshot, GlossaryTerm,
    MemoryCandidateDecision, MemoryCandidateProjectBinding, MemoryExtractionCandidate,
)
from app.models.memory import MemoryClaim, MemoryItem, MemoryItemSource
from app.models.memory_scope import MemoryCandidateScope, MemoryClaimScope, MemoryScope
from app.models.project import Project
from app.models.rag import RAGDocument
from app.runtime.memory.content_contracts import normalize_memory_content


def _scope_signature(scopes: list[MemoryScope], *, legacy_project: bool = False) -> str:
    if legacy_project or not scopes:
        return "legacy"
    return "s:" + hashlib.sha256(
        ",".join(sorted(str(row.id) for row in scopes)).encode("ascii")
    ).hexdigest()


class ShadowMemoryPublicationService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def approve(self, *, candidate_id: UUID, actor_id: UUID | None, reason: str | None,
                      content: dict | None = None, scope: str | None = None,
                      project_id: UUID | None = None, promote_to_company: bool = False,
                      scope_ids: list[UUID] | None = None,
                      replace_existing_definition: bool = False,
                      automatic: bool = False) -> MemoryExtractionCandidate:
        candidate = await self._required_candidate(candidate_id)
        if candidate.resolution_status not in {"extracted", "needs_review", "conflict"}:
            if replace_existing_definition:
                raise ValueError("Only an open term candidate can replace a glossary definition")
            return candidate
        snapshot = await self._session.get(DocumentMemorySnapshot, candidate.snapshot_id)
        if snapshot is None:
            raise ValueError("Candidate snapshot is unavailable")
        if content is not None:
            candidate.content = content
            candidate.content_text = json.dumps(content, ensure_ascii=False, sort_keys=True)
        is_term = candidate.candidate_type == "term"
        if replace_existing_definition and (not is_term or automatic or not str(reason or "").strip()):
            raise ValueError("Replacing a glossary definition requires manual approval and a reason")
        if is_term:
            document = await self._session.get(RAGDocument, snapshot.document_id)
            if document is None or document.scope != "global" or document.status == "archived":
                raise ValueError("Glossary publication requires a global source document")
            if snapshot.status in {"superseded", "failed", "rejected"}:
                raise ValueError("Glossary publication requires a current document snapshot")
            newer_snapshot = await self._session.scalar(select(DocumentMemorySnapshot.id).where(
                DocumentMemorySnapshot.document_id == snapshot.document_id,
                DocumentMemorySnapshot.created_at > snapshot.created_at,
            ).limit(1))
            if newer_snapshot is not None:
                raise ValueError("Glossary publication requires the latest document snapshot")
            if not candidate.evidence_section_ids:
                raise ValueError("Glossary definition requires document section evidence")
        try:
            normalized_content = normalize_memory_content(candidate.candidate_type, dict(candidate.content or {}))
        except ValueError as exc:
            raise ValueError(f"Invalid candidate content: {exc}") from exc
        candidate.content = normalized_content
        candidate.content_text = json.dumps(normalized_content, ensure_ascii=False, sort_keys=True)
        chosen_scope = None if is_term else (scope or candidate.scope_candidate)
        if not is_term and chosen_scope not in {"global", "project", "scoped"}:
            raise ValueError("Choose global or scoped applicability before approval")
        if chosen_scope == "global" and scope_ids:
            raise ValueError("Global applicability cannot include typed memory scopes")
        selected_scopes = [] if is_term or chosen_scope == "global" else await self._scopes_for(
            candidate, scope_ids or [], project_id,
        )
        if chosen_scope == "scoped" and not selected_scopes:
            raise ValueError("Scoped knowledge requires at least one confirmed memory scope")
        project = None if is_term else await self._project_for(candidate, project_id, chosen_scope)
        if chosen_scope == "project" and project is not None and not selected_scopes:
            selected_scopes = list((await self._session.execute(select(MemoryScope).where(
                MemoryScope.project_id == project.id,
                MemoryScope.lifecycle_status == "active",
            ))).scalars().all())
            if not selected_scopes:
                raise ValueError("Project has no active memory scope; add it in the scope catalog")
        if chosen_scope == "project" and (len(selected_scopes) != 1 or selected_scopes[0].project_id != project.id):
            raise ValueError("Project applicability must use exactly the selected project scope")
        visibility = None if is_term or promote_to_company else candidate.visibility_tenant_id
        if not is_term:
            await self._confirm_scope_bindings(candidate.id, selected_scopes)
        if is_term:
            await self._publish_term(candidate, replace_existing_definition=replace_existing_definition)
        else:
            await self._publish_memory(candidate, snapshot, project, visibility, selected_scopes)
        candidate.scope_candidate = chosen_scope
        candidate.visibility_tenant_id = visibility
        candidate.resolution_status = "resolved"
        candidate.resolution_method = "manual" if not automatic else "content_evidence"
        candidate.resolution_rationale = reason
        self._session.add(MemoryCandidateDecision(
            candidate_id=candidate.id, actor_user_id=actor_id,
            action="autoapprove" if automatic else "approve", reason=reason,
            payload={"scope": chosen_scope, "project_id": str(project.id) if project else None,
                     "scope_ids": [str(row.id) for row in selected_scopes],
                     "promote_to_company": promote_to_company,
                     "replace_existing_definition": replace_existing_definition},
        ))
        await self._update_snapshot(snapshot)
        return candidate

    async def reject(self, *, candidate_id: UUID, actor_id: UUID | None, reason: str | None) -> MemoryExtractionCandidate:
        candidate = await self._required_candidate(candidate_id)
        candidate.resolution_status = "rejected"
        candidate.resolution_method = "manual"
        candidate.resolution_rationale = reason
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
        if scope != "project":
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

    async def _scopes_for(self, candidate: MemoryExtractionCandidate, scope_ids: list[UUID],
                          project_id: UUID | None) -> list[MemoryScope]:
        if project_id and not scope_ids:
            return list((await self._session.execute(select(MemoryScope).where(
                MemoryScope.project_id == project_id,
                MemoryScope.lifecycle_status == "active",
            ))).scalars().all())
        selected_ids = list(dict.fromkeys(scope_ids))
        rows = list((await self._session.execute(select(MemoryScope).where(
            MemoryScope.id.in_(selected_ids),
            MemoryScope.lifecycle_status == "active",
        ))).scalars().all()) if selected_ids else []
        if len(rows) != len(selected_ids):
            raise ValueError("Unknown memory scope ID")
        return rows

    async def _confirm_scope_bindings(self, candidate_id: UUID, selected_scopes: list[MemoryScope]) -> None:
        bindings = list((await self._session.execute(select(MemoryCandidateScope).where(
            MemoryCandidateScope.candidate_id == candidate_id,
            MemoryCandidateScope.role == "applies_to",
        ))).scalars().all())
        selected_by_id = {scope.id: scope for scope in selected_scopes}
        bound_ids = set()
        for binding in bindings:
            binding.status = "confirmed" if binding.scope_id in selected_by_id else "rejected"
            bound_ids.add(binding.scope_id)
        for scope_id in selected_by_id.keys() - bound_ids:
            self._session.add(MemoryCandidateScope(
                candidate_id=candidate_id, scope_id=scope_id, role="applies_to",
                status="confirmed", method="manual", confidence=1.0,
                rationale="Selected by administrator during approval",
            ))

    async def _publish_memory(self, candidate: MemoryExtractionCandidate, snapshot: DocumentMemorySnapshot,
                              project: Project | None, visibility: UUID | None,
                              selected_scopes: list[MemoryScope]) -> None:
        scope = "project" if project else "company"
        signature = _scope_signature(selected_scopes, legacy_project=project is not None)
        item = (await self._session.execute(select(MemoryItem).where(
            MemoryItem.scope == scope, MemoryItem.item_type == candidate.candidate_type,
            MemoryItem.normalized_subject == candidate.normalized_subject,
            MemoryItem.scope_signature == signature,
            MemoryItem.project_id == project.id if project else MemoryItem.project_id.is_(None),
        ))).scalar_one_or_none()
        if item is None:
            item = MemoryItem(scope=scope, item_type=candidate.candidate_type, project_id=project.id if project else None,
                scope_signature=signature,
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
            MemoryClaim.scope_signature == signature,
            MemoryClaim.project_id == project.id if project else MemoryClaim.project_id.is_(None),
        ))).scalar_one_or_none()
        if claim is None:
            claim = MemoryClaim(memory_item_id=item.id, document_id=snapshot.document_id, canonical_checksum=snapshot.canonical_checksum,
                approved_candidate_id=candidate.id,
                scope=scope, item_type=candidate.candidate_type, project_id=project.id if project else None,
                scope_signature=signature,
                visibility_tenant_id=visibility, normalized_subject=candidate.normalized_subject,
                content=dict(candidate.content or {}), content_text=candidate.content_text,
                evidence_section_ids=list(candidate.evidence_section_ids or []), confidence=candidate.extraction_confidence,
                extraction_confidence=candidate.extraction_confidence, state="active")
            self._session.add(claim)
            await self._session.flush()
        elif claim.content_text != candidate.content_text:
            raise ValueError("A different claim already exists for this document and subject")
        else:
            claim.approved_candidate_id = candidate.id
        existing_scope_ids = set((await self._session.execute(select(MemoryClaimScope.scope_id).where(
            MemoryClaimScope.claim_id == claim.id,
        ))).scalars().all())
        if existing_scope_ids and existing_scope_ids != {row.id for row in selected_scopes}:
            raise ValueError("A claim with different applicability already exists for this document and subject")
        for selected_scope in selected_scopes:
            if selected_scope.id not in existing_scope_ids:
                self._session.add(MemoryClaimScope(claim_id=claim.id, scope_id=selected_scope.id))
        for section_id in candidate.evidence_section_ids or []:
            exists = (await self._session.execute(select(MemoryItemSource.id).where(
                MemoryItemSource.memory_item_id == item.id, MemoryItemSource.document_id == snapshot.document_id,
                MemoryItemSource.canonical_checksum == snapshot.canonical_checksum, MemoryItemSource.section_id == section_id,
            ))).scalar_one_or_none()
            if not exists:
                self._session.add(MemoryItemSource(memory_item_id=item.id, document_id=snapshot.document_id,
                    canonical_checksum=snapshot.canonical_checksum, section_id=section_id))


    async def _publish_term(self, candidate: MemoryExtractionCandidate,
                            *, replace_existing_definition: bool = False) -> None:
        definition = str(candidate.content["definition"]).strip()
        term = (await self._session.execute(select(GlossaryTerm).where(
            GlossaryTerm.normalized_term == candidate.normalized_subject,
        ))).scalar_one_or_none()
        if term is None:
            term = GlossaryTerm(canonical_term=candidate.subject,
                                normalized_term=candidate.normalized_subject,
                                definition=definition,
                                approved_candidate_id=candidate.id,
                                aliases=list(candidate.aliases or []))
            self._session.add(term)
        else:
            different_definition = " ".join(term.definition.split()).casefold() != definition.casefold()
            if different_definition and not replace_existing_definition:
                raise ValueError("Term already has a different canonical definition")
            term.definition = definition
            term.approved_candidate_id = candidate.id
            term.is_active = True
            aliases = [] if different_definition else list(term.aliases or [])
            seen = {value.casefold() for value in aliases}
            for value in candidate.aliases or []:
                if value.casefold() not in seen and value.casefold() != term.normalized_term:
                    aliases.append(value)
                    seen.add(value.casefold())
            term.aliases = aliases

    async def _update_snapshot(self, snapshot: DocumentMemorySnapshot) -> None:
        open_count = (await self._session.execute(select(MemoryExtractionCandidate.id).where(
            MemoryExtractionCandidate.snapshot_id == snapshot.id,
            MemoryExtractionCandidate.resolution_status.in_(("extracted", "needs_review", "conflict")),
        ).limit(1))).scalar_one_or_none()
        if open_count is None:
            snapshot.status = "approved"
