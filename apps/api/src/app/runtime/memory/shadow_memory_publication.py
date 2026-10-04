"""Transactional manual publication of approved shadow candidates."""
from __future__ import annotations

import json
import hashlib
import re
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_memory_staging import (
    DocumentMemorySnapshot, DocumentMemoryExtractionAttempt, GlossaryTerm,
    MemoryCandidateDecision, MemoryCandidateProjectBinding, MemoryConflictCase, MemoryConflictMember,
    MemoryCandidateScopeProposal, MemoryExtractionCandidate, MemoryScopeProposal,
)
from app.models.memory import MemoryClaim, MemoryItem, MemoryItemSource
from app.models.memory_scope import (
    MemoryCandidateScope, MemoryClaimScope, MemoryScope, MemoryScopeGlossaryTerm,
)
from app.models.project import Project
from app.models.rag import RAGDocument
from app.runtime.memory.content_contracts import normalize_memory_content
from app.services.glossary_service import GlossaryService


def _scope_signature(scopes: list[MemoryScope], *, legacy_project: bool = False) -> str:
    if legacy_project or not scopes:
        return "legacy"
    return "s:" + hashlib.sha256(
        ",".join(sorted(str(row.id) for row in scopes)).encode("ascii")
    ).hexdigest()


class ShadowMemoryPublicationService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.published_item_ids: set[UUID] = set()

    async def update_review_tags(
        self, *, candidate_id: UUID, actor_id: UUID | None,
        scope_ids: list[UUID], glossary_term_ids: list[UUID], reason: str = "",
    ) -> MemoryExtractionCandidate:
        """Save a reviewer's applicability and term links without publishing."""
        candidate = await self._required_candidate(candidate_id, lock=True)
        if candidate.resolution_status not in {"extracted", "needs_review", "conflict"}:
            raise ValueError("Можно менять связи только кандидата на проверке")
        snapshot = await self._session.get(DocumentMemorySnapshot, candidate.snapshot_id)
        if snapshot is None or snapshot.status not in {"awaiting_review", "approved", "rejected"}:
            raise ValueError("Дождитесь завершения извлечения документа")
        if snapshot.active_attempt_id and candidate.attempt_id != snapshot.active_attempt_id:
            raise ValueError("Кандидат относится к предыдущей попытке извлечения")
        reason = reason.strip() or "Связи изменены проверяющим"
        if candidate.candidate_type == "term" and scope_ids:
            raise ValueError("Определение термина относится к общему глоссарию")
        scopes = await self._scopes_for(candidate, scope_ids, None)
        # Within one type an all-scope already covers every specific value.
        if any(scope.is_all and any(other.scope_type == scope.scope_type and not other.is_all
                                   for other in scopes) for scope in scopes):
            raise ValueError("Область «все» не совмещается с отдельными областями того же типа")
        term_ids = list(dict.fromkeys(glossary_term_ids))
        terms = list((await self._session.scalars(GlossaryService.published_terms_query().where(
            GlossaryTerm.id.in_(term_ids),
        ))).all()) if term_ids else []
        if len(terms) != len(term_ids):
            raise ValueError("Выберите существующие опубликованные термины")
        previous_bindings = list((await self._session.scalars(select(MemoryCandidateScope).where(
            MemoryCandidateScope.candidate_id == candidate.id, MemoryCandidateScope.role == "applies_to",
        ))).all())
        previous = {
            "scope": candidate.scope_candidate,
            "scope_ids": [str(binding.scope_id) for binding in previous_bindings if binding.status != "rejected"],
            "related_entities": list(candidate.related_entities or []),
            "unresolved_scope_references": list(candidate.unresolved_scope_references or []),
        }
        await self._confirm_scope_bindings(candidate.id, scopes)
        projects = list((await self._session.scalars(select(MemoryCandidateProjectBinding).where(
            MemoryCandidateProjectBinding.candidate_id == candidate.id,
            MemoryCandidateProjectBinding.role == "applies_to",
        ))).all())
        selected_projects = {scope.project_id for scope in scopes if scope.project_id}
        for binding in projects:
            binding.status = "confirmed" if binding.project_id in selected_projects else "rejected"
        candidate.related_project_keys = [scope.key.removeprefix("project.") for scope in scopes
                                          if scope.scope_type == "project" and not scope.is_all]
        for binding in previous_bindings:
            if binding.scope_id in {scope.id for scope in scopes}:
                binding.method, binding.rationale = "manual", reason.strip()
        proposals = list((await self._session.scalars(select(MemoryCandidateScopeProposal).where(
            MemoryCandidateScopeProposal.candidate_id == candidate.id,
            MemoryCandidateScopeProposal.role == "applies_to",
            MemoryCandidateScopeProposal.status != "superseded",
        ))).all())
        for binding in proposals:
            binding.status = "superseded"
            binding.rationale = reason.strip()
        candidate.scope_candidate = (None if candidate.candidate_type == "term" else
                                     "scoped" if scopes else "global")
        candidate.unresolved_scope_references = []
        candidate.related_entities = [entity for entity in candidate.related_entities or []
                                      if entity.get("type") != "glossary_term"] + [
            {"type": "glossary_term", "id": str(term.id), "name": term.canonical_term} for term in terms
        ]
        candidate.resolution_method = "manual"
        candidate.resolution_rationale = reason.strip()
        self._session.add(MemoryCandidateDecision(
            candidate_id=candidate.id, actor_user_id=actor_id, action="edit", reason=reason.strip(),
            payload={"review_tags": True, "before": previous, "scope": candidate.scope_candidate,
                     "scope_ids": [str(scope.id) for scope in scopes], "glossary_term_ids": [str(term.id) for term in terms],
                     "superseded_proposal_bindings": [str(binding.id) for binding in proposals]},
        ))
        await self._session.flush()
        return candidate

    async def approve(self, *, candidate_id: UUID, actor_id: UUID | None, reason: str | None,
                      content: dict | None = None, scope: str | None = None,
                      project_id: UUID | None = None, promote_to_company: bool = False,
                      scope_ids: list[UUID] | None = None,
                      replace_existing_definition: bool = False,
                      automatic: bool = False) -> MemoryExtractionCandidate:
        candidate = await self._required_candidate(candidate_id, lock=True)
        if candidate.resolution_status not in {"extracted", "needs_review", "conflict"}:
            if candidate.resolution_status == "resolved" and not replace_existing_definition:
                return candidate
            raise ValueError("Only an open candidate can be approved")
        snapshot = await self._session.get(DocumentMemorySnapshot, candidate.snapshot_id)
        if snapshot is None:
            raise ValueError("Candidate snapshot is unavailable")
        blocking_conflict = await self._session.scalar(select(MemoryConflictCase.id).join(
            MemoryConflictMember, MemoryConflictMember.conflict_id == MemoryConflictCase.id,
        ).where(
            MemoryConflictMember.candidate_id == candidate.id,
            MemoryConflictCase.status == "open",
            MemoryConflictCase.kind.in_(("contradiction", "insufficient_evidence")),
        ).limit(1))
        if blocking_conflict is not None:
            raise ValueError("Candidate has an unresolved contradiction or insufficient evidence")
        if content is not None:
            candidate.content = content
            candidate.content_text = json.dumps(content, ensure_ascii=False, sort_keys=True)
        is_term = candidate.candidate_type == "term"
        if is_term and automatic:
            raise ValueError("Terms require manual administrator approval")
        if not is_term and candidate.unresolved_scope_references:
            raise ValueError("Memory has unresolved required scope references; reject it for re-extraction")
        if replace_existing_definition and (not is_term or automatic or not str(reason or "").strip()):
            raise ValueError("Replacing a glossary definition requires manual approval and a reason")
        if is_term:
            document = await self._session.get(RAGDocument, snapshot.document_id)
            if document is None or document.status == "archived":
                raise ValueError("Term approval requires an available source document")
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
        if not is_term and chosen_scope not in {"global", "project", "scoped"} and scope is None:
            known_scope = await self._session.scalar(select(MemoryScope.id).join(
                MemoryCandidateScope, MemoryCandidateScope.scope_id == MemoryScope.id,
            ).where(
                MemoryCandidateScope.candidate_id == candidate.id,
                MemoryCandidateScope.role == "applies_to",
                MemoryCandidateScope.status != "rejected",
                MemoryScope.lifecycle_status == "active",
            ).limit(1))
            if known_scope is not None:
                chosen_scope = "scoped"
            elif not automatic:
                # A manual approval with no selected scopes confirms empty branches.
                chosen_scope = "global"
        if not is_term and chosen_scope not in {"global", "project", "scoped"}:
            raise ValueError("Не удалось определить применимость извлечённого знания")
        if chosen_scope == "global" and scope_ids:
            raise ValueError("Global applicability cannot include typed memory scopes")
        inferred_project_id = project_id
        if not is_term and chosen_scope == "project" and inferred_project_id is None:
            project_ids = list((await self._session.scalars(select(MemoryCandidateProjectBinding.project_id).where(
                MemoryCandidateProjectBinding.candidate_id == candidate.id,
                MemoryCandidateProjectBinding.role == "applies_to",
                MemoryCandidateProjectBinding.status != "rejected",
            ))).all())
            if len(project_ids) == 1:
                inferred_project_id = project_ids[0]
        inferred_scope_ids = list(scope_ids or [])
        if not is_term and chosen_scope == "scoped" and not inferred_scope_ids:
            inferred_scope_ids = list((await self._session.scalars(select(MemoryCandidateScope.scope_id).where(
                MemoryCandidateScope.candidate_id == candidate.id,
                MemoryCandidateScope.role == "applies_to",
                MemoryCandidateScope.status != "rejected",
            ))).all())
        selected_scopes = [] if is_term or chosen_scope == "global" else await self._scopes_for(
            candidate, inferred_scope_ids, inferred_project_id,
        )
        if chosen_scope == "scoped" and not selected_scopes:
            raise ValueError("Scoped knowledge requires at least one confirmed memory scope")
        project = None if is_term else await self._project_for(candidate, inferred_project_id, chosen_scope)
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
            await self._require_scope_proposals_approved(candidate.id)
            await self._confirm_scope_bindings(candidate.id, selected_scopes)
        if is_term:
            await self._publish_term(candidate, replace_existing_definition=replace_existing_definition)
        else:
            await self._publish_memory(candidate, snapshot, project, visibility, selected_scopes)
        candidate.scope_candidate = chosen_scope
        candidate.visibility_tenant_id = visibility
        candidate.resolution_status = "resolved"
        candidate.resolution_method = "manual" if not automatic else "content_evidence"
        candidate.resolution_rationale = reason if reason is not None else candidate.resolution_rationale
        if is_term:
            await self._activate_linked_scope_proposals(candidate.id)
        self._session.add(MemoryCandidateDecision(
            candidate_id=candidate.id, actor_user_id=actor_id,
            action="autoapprove" if automatic else "approve", reason=reason,
            payload={"scope": chosen_scope, "project_id": str(project.id) if project else None,
                     "scope_ids": [str(row.id) for row in selected_scopes],
                     "glossary_term_ids": [entity["id"] for entity in candidate.related_entities or []
                                           if entity.get("type") == "glossary_term"],
                     "promote_to_company": promote_to_company,
                     "replace_existing_definition": replace_existing_definition},
        ))
        await self._update_snapshot(snapshot)
        return candidate

    async def reject(self, *, candidate_id: UUID, actor_id: UUID | None, reason: str | None) -> MemoryExtractionCandidate:
        if not str(reason or "").strip():
            raise ValueError("A rejection reason is required")
        candidate = await self._required_candidate(candidate_id, lock=True)
        if candidate.resolution_status not in {"extracted", "needs_review", "conflict"}:
            raise ValueError("Only an open candidate can be rejected")
        candidate.resolution_status = "rejected"
        candidate.resolution_method = "manual"
        candidate.resolution_rationale = reason
        open_cases = (await self._session.scalars(select(MemoryConflictCase).join(
            MemoryConflictMember, MemoryConflictMember.conflict_id == MemoryConflictCase.id,
        ).where(MemoryConflictMember.candidate_id == candidate.id,
                MemoryConflictCase.status == "open"))).all()
        for case in open_cases:
            case.status = "dismissed"
        self._session.add(MemoryCandidateDecision(candidate_id=candidate.id, actor_user_id=actor_id, action="reject", reason=reason))
        snapshot = await self._session.get(DocumentMemorySnapshot, candidate.snapshot_id)
        if snapshot:
            await self._update_snapshot(snapshot)
        return candidate

    async def _required_candidate(self, candidate_id: UUID, *, lock: bool = False) -> MemoryExtractionCandidate:
        stmt = select(MemoryExtractionCandidate).where(MemoryExtractionCandidate.id == candidate_id)
        if lock:
            snapshot_id = await self._session.scalar(select(MemoryExtractionCandidate.snapshot_id).where(
                MemoryExtractionCandidate.id == candidate_id,
            ))
            if snapshot_id is None:
                raise ValueError("Memory candidate not found")
            snapshot = await self._session.scalar(select(DocumentMemorySnapshot).where(
                DocumentMemorySnapshot.id == snapshot_id,
            ).with_for_update().execution_options(populate_existing=True))
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        candidate = await self._session.scalar(stmt)
        if candidate is None:
            raise ValueError("Memory candidate not found")
        if lock and candidate.resolution_status != "resolved" and (
            snapshot is None or snapshot.status == "superseded"
            or candidate.attempt_id != snapshot.active_attempt_id
        ):
            raise ValueError("Candidate belongs to an inactive extraction attempt")
        return candidate

    async def approve_scope_proposal(
        self, *, proposal_id: UUID, actor_id: UUID | None, reason: str | None = None,
    ) -> MemoryScopeProposal:
        proposal = await self._required_scope_proposal(proposal_id)
        if proposal.status == "approved":
            return proposal
        if proposal.status != "needs_review":
            raise ValueError("Scope proposal is waiting for its glossary term or was rejected")
        term_id = await self._approved_proposal_term_id(proposal)
        if term_id is None and (proposal.term_candidate_id or proposal.glossary_term_id):
            raise ValueError("Scope proposal requires its referenced term to be approved and active")
        existing = await self._session.scalar(select(MemoryScope).where(
            MemoryScope.scope_type == proposal.scope_type,
            MemoryScope.key == proposal.proposed_key,
        ).with_for_update())
        if existing is not None and existing.lifecycle_status != "active":
            raise ValueError("A matching scope exists but is deprecated; restore it before approving this proposal")
        scope = existing or MemoryScope(
            scope_type=proposal.scope_type, key=proposal.proposed_key, project_type=proposal.project_type,
            name=proposal.name, aliases=list(proposal.aliases or []),
        )
        if existing is None:
            if proposal.scope_type == "project":
                project_key = proposal.proposed_key.removeprefix("project.")
                scope.project_id = await self._session.scalar(select(Project.id).where(
                    Project.key == project_key,
                ))
            self._session.add(scope)
            await self._session.flush()
        else:
            scope.aliases = list(dict.fromkeys([*(scope.aliases or []), *(proposal.aliases or [])]))
        if term_id is not None:
            term_binding = await self._session.get(MemoryScopeGlossaryTerm, scope.id)
            if term_binding is not None and term_binding.glossary_term_id != term_id:
                raise ValueError("Scope key is already linked to a different glossary term")
            if term_binding is None:
                duplicate_term_scope = await self._session.scalar(select(MemoryScopeGlossaryTerm.scope_id).where(
                    MemoryScopeGlossaryTerm.glossary_term_id == term_id,
                ))
                if duplicate_term_scope is not None and duplicate_term_scope != scope.id:
                    raise ValueError("Glossary term is already linked to a different scope")
                self._session.add(MemoryScopeGlossaryTerm(scope_id=scope.id, glossary_term_id=term_id))
        proposal.memory_scope_id = scope.id
        proposal.status = "approved"
        proposal.rejection_reason = None
        proposal.reviewed_by_user_id = actor_id
        proposal.reviewed_at = datetime.now(timezone.utc)
        proposal.review_reason = (str(reason).strip()[:2000] if reason and reason.strip() else None)
        for binding in (await self._session.execute(select(MemoryCandidateScopeProposal).where(
            MemoryCandidateScopeProposal.scope_proposal_id == proposal.id,
            MemoryCandidateScopeProposal.status == "suggested",
        ))).scalars().all():
            binding.status = "confirmed"
            exists = await self._session.scalar(select(MemoryCandidateScope.id).where(
                MemoryCandidateScope.candidate_id == binding.candidate_id,
                MemoryCandidateScope.scope_id == scope.id,
                MemoryCandidateScope.role == binding.role,
            ))
            if exists is None:
                self._session.add(MemoryCandidateScope(
                    candidate_id=binding.candidate_id, scope_id=scope.id,
                    role=binding.role, status="suggested", method="llm_suggestion",
                    confidence=binding.confidence, rationale=binding.rationale,
                ))
        snapshot = await self._session.get(DocumentMemorySnapshot, proposal.snapshot_id)
        if snapshot:
            await self._update_snapshot(snapshot)
        return proposal

    async def reject_scope_proposal(
        self, *, proposal_id: UUID, actor_id: UUID | None, reason: str,
    ) -> MemoryScopeProposal:
        if not str(reason or "").strip():
            raise ValueError("A rejection reason is required")
        proposal = await self._required_scope_proposal(proposal_id)
        if proposal.status not in {"awaiting_term", "needs_review"}:
            raise ValueError("Only an open scope proposal can be rejected")
        proposal.status = "rejected"
        proposal.rejection_reason = reason.strip()[:2000]
        proposal.reviewed_by_user_id = actor_id
        proposal.reviewed_at = datetime.now(timezone.utc)
        proposal.review_reason = reason.strip()[:2000]
        bindings = (await self._session.execute(select(MemoryCandidateScopeProposal).where(
            MemoryCandidateScopeProposal.scope_proposal_id == proposal.id,
            MemoryCandidateScopeProposal.status == "suggested",
        ))).scalars().all()
        for binding in bindings:
            binding.status = "rejected"
        snapshot = await self._session.get(DocumentMemorySnapshot, proposal.snapshot_id)
        if snapshot:
            await self._update_snapshot(snapshot)
        return proposal

    async def _required_scope_proposal(self, proposal_id: UUID) -> MemoryScopeProposal:
        snapshot_id = await self._session.scalar(select(MemoryScopeProposal.snapshot_id).where(
            MemoryScopeProposal.id == proposal_id,
        ))
        if snapshot_id is None:
            raise ValueError("Scope proposal not found")
        snapshot = await self._session.scalar(select(DocumentMemorySnapshot).where(
            DocumentMemorySnapshot.id == snapshot_id,
        ).with_for_update().execution_options(populate_existing=True))
        proposal = await self._session.scalar(select(MemoryScopeProposal).where(
            MemoryScopeProposal.id == proposal_id,
        ).with_for_update().execution_options(populate_existing=True))
        if proposal is None:
            raise ValueError("Scope proposal not found")
        if proposal.status != "approved" and (
            snapshot is None or snapshot.status == "superseded"
            or proposal.attempt_id != snapshot.active_attempt_id
        ):
            raise ValueError("Scope proposal belongs to an inactive extraction attempt")
        return proposal

    async def _approved_proposal_term_id(self, proposal: MemoryScopeProposal) -> UUID | None:
        if proposal.glossary_term_id:
            return await self._session.scalar(select(GlossaryTerm.id).where(
                GlossaryTerm.id == proposal.glossary_term_id,
                GlossaryTerm.is_active.is_(True),
            ))
        if not proposal.term_candidate_id:
            return None
        return await self._session.scalar(select(GlossaryTerm.id).join(
            MemoryExtractionCandidate,
            MemoryExtractionCandidate.id == GlossaryTerm.approved_candidate_id,
        ).where(
            MemoryExtractionCandidate.id == proposal.term_candidate_id,
            MemoryExtractionCandidate.resolution_status == "resolved",
            GlossaryTerm.is_active.is_(True),
        ))

    async def _activate_linked_scope_proposals(self, term_candidate_id: UUID) -> None:
        proposals = (await self._session.execute(select(MemoryScopeProposal).where(
            MemoryScopeProposal.term_candidate_id == term_candidate_id,
            MemoryScopeProposal.status.in_(("awaiting_term", "needs_review")),
        ).with_for_update())).scalars().all()
        term_id = await self._session.scalar(select(GlossaryTerm.id).where(
            GlossaryTerm.approved_candidate_id == term_candidate_id,
            GlossaryTerm.is_active.is_(True),
        ))
        if term_id is None:
            raise ValueError("Approved glossary term is unavailable for linked scopes")
        for proposal in proposals:
            proposal.source_term_candidate_id = term_candidate_id
            proposal.glossary_term_id = term_id
            proposal.term_candidate_id = None
            if proposal.memory_scope_id is None:
                proposal.status = "needs_review"
                continue
            binding = await self._session.get(MemoryScopeGlossaryTerm, proposal.memory_scope_id)
            if binding is None:
                self._session.add(MemoryScopeGlossaryTerm(
                    scope_id=proposal.memory_scope_id, glossary_term_id=term_id,
                ))
            elif binding.glossary_term_id != term_id:
                raise ValueError("Existing scope is already linked to a different glossary term")
            proposal.status = "approved"

    async def _require_scope_proposals_approved(self, candidate_id: UUID) -> None:
        rows = (await self._session.execute(select(
            MemoryScopeProposal.name,
            MemoryScopeProposal.status,
            MemoryScopeProposal.rejection_reason,
            MemoryCandidateScopeProposal.status,
        ).join(
            MemoryCandidateScopeProposal,
            MemoryCandidateScopeProposal.scope_proposal_id == MemoryScopeProposal.id,
        ).where(
            MemoryCandidateScopeProposal.candidate_id == candidate_id,
            MemoryCandidateScopeProposal.role == "applies_to",
            MemoryCandidateScopeProposal.status != "superseded",
            or_(MemoryCandidateScopeProposal.status == "rejected", MemoryScopeProposal.status != "approved",
                MemoryScopeProposal.memory_scope_id.is_(None)),
        ))).all()
        if rows:
            labels = [f"{name} (rejected: {reason or 'binding rejected'})"
                      if status == "rejected" or binding_status == "rejected"
                      else f"{name} ({status})"
                      for name, status, reason, binding_status in rows]
            raise ValueError("Memory is blocked by unapproved scopes: " + ", ".join(labels))
        approved = (await self._session.execute(select(MemoryScopeProposal).join(
            MemoryCandidateScopeProposal,
            MemoryCandidateScopeProposal.scope_proposal_id == MemoryScopeProposal.id,
        ).where(
            MemoryCandidateScopeProposal.candidate_id == candidate_id,
            MemoryCandidateScopeProposal.role == "applies_to",
            MemoryCandidateScopeProposal.status != "superseded",
        ))).all()
        for (proposal,) in approved:
            active_scope = await self._session.scalar(select(MemoryScope.id).where(
                MemoryScope.id == proposal.memory_scope_id,
                MemoryScope.lifecycle_status == "active",
            ))
            if active_scope is None:
                raise ValueError("Memory is blocked because its approved scope is no longer active")
            term_ready = await self._approved_proposal_term_id(proposal)
            if term_ready is None:
                raise ValueError("Memory is blocked because its scope term is no longer active")

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
        self.published_item_ids.add(item.id)
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
            MemoryExtractionCandidate.attempt_id == snapshot.active_attempt_id,
            MemoryExtractionCandidate.resolution_status.in_(("extracted", "needs_review", "conflict")),
        ).limit(1))).scalar_one_or_none()
        open_scope = await self._session.scalar(select(MemoryScopeProposal.id).where(
            MemoryScopeProposal.attempt_id == snapshot.active_attempt_id,
            MemoryScopeProposal.status.in_(("awaiting_term", "needs_review")),
        ).limit(1))
        if open_count is None and open_scope is None:
            resolved = await self._session.scalar(select(MemoryExtractionCandidate.id).where(
                MemoryExtractionCandidate.attempt_id == snapshot.active_attempt_id,
                MemoryExtractionCandidate.resolution_status == "resolved",
            ).limit(1))
            snapshot.status = "approved" if resolved else "rejected"
        else:
            snapshot.status = "awaiting_review"
        if snapshot.active_attempt_id:
            attempt = await self._session.get(DocumentMemoryExtractionAttempt, snapshot.active_attempt_id)
            if attempt:
                attempt.status = "awaiting_review" if snapshot.status == "awaiting_review" else "completed"
