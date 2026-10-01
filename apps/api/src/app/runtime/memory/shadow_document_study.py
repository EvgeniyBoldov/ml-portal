"""LLM agents and deterministic persistence for shadow document study."""
from __future__ import annotations

import json
import hashlib
import re
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Literal, Sequence
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http.clients import LLMClientProtocol
from app.models.document_memory_staging import (
    DocumentMemoryExtractionAttempt,
    DocumentMemorySnapshot,
    GlossaryTerm,
    MemoryCandidateProjectBinding,
    MemoryCandidateScopeProposal,
    MemoryExtractionCandidate,
    MemoryScopeProposal,
)
from app.models.memory_scope import (
    DocumentMemoryScope, MemoryCandidateScope, MemoryScope,
    MemoryScopeGlossaryTerm,
)
from app.models.project import Project
from app.models.system_llm_role import SystemLLMRoleType
from app.runtime.llm.structured import StructuredLLMCall
from app.runtime.memory.shadow_study_prompts import (
    document_memory_prompt,
)
from app.runtime.memory.content_contracts import normalize_memory_content
from app.services.glossary_service import GlossaryService


# Keep each structured request below providers' token-per-minute limits. The
# ledger and scope catalogs grow with every section, so two sections can push
# otherwise valid documents over the request budget.
SHADOW_STUDY_BATCH_SIZE = 1
MAX_LEDGER_ITEMS = 60
MAX_GLOSSARY_ITEMS = 80


class ShadowScreeningOutput(BaseModel):
    decision: Literal["study", "skip", "needs_review"]
    reason: str = Field(default="", max_length=600)
    document_kind: str = Field(default="unknown", max_length=80)


class ShadowScopeProposal(BaseModel):
    scope_type: Literal["product", "project", "team"]
    name: str = Field(min_length=1, max_length=255)
    aliases: list[str] = Field(default_factory=list, max_length=20)
    term_subject: str = Field(min_length=1, max_length=200)
    role: Literal["applies_to", "mentions"] = "applies_to"
    rationale: str = Field(default="", max_length=600)


class ShadowStudyItem(BaseModel):
    operation: Literal["new", "extend_existing"] = "new"
    existing_candidate_id: UUID | None = None
    candidate_type: Literal["term", "description", "relationship", "rule", "constraint", "procedure", "decision"]
    scope_type: Literal["product", "project", "team"] | None = None
    subject: str = Field(min_length=1, max_length=200)
    content: dict[str, Any] = Field(default_factory=dict)
    scope_candidate: Literal["global", "project", "multi_project", "scoped", "unknown"] = "unknown"
    project_keys: list[str] = Field(default_factory=list, max_length=20)
    scope_keys: list[str] = Field(default_factory=list, max_length=20)
    mentioned_scope_keys: list[str] = Field(default_factory=list, max_length=20)
    unmatched_scope_names: list[str] = Field(default_factory=list, max_length=8)
    scope_proposals: list[ShadowScopeProposal] = Field(default_factory=list, max_length=12)
    scope_rationale: str = Field(default="", max_length=600)
    evidence_section_ids: list[str] = Field(default_factory=list, max_length=8)
    aliases: list[str] = Field(default_factory=list, max_length=20)
    extraction_confidence: float = Field(default=0.7, ge=0.0, le=1.0)


class ShadowStudyOutput(BaseModel):
    items: list[ShadowStudyItem] = Field(default_factory=list, max_length=24)


class ShadowDocumentStudyAgent:
    """Hard-coded prompting over the standard structured LLM transport."""

    def __init__(self, *, session: AsyncSession, llm_client: LLMClientProtocol) -> None:
        self._structured = StructuredLLMCall(session=session, llm_client=llm_client)

    async def _prompt(self, stage: Literal["screening", "study"]) -> str:
        config = await self._structured.role_service.get_role_config(SystemLLMRoleType.DOCUMENT_MEMORY_EXTRACTOR)
        return document_memory_prompt(config.get("extras"), stage=stage)

    async def screen(
        self,
        *,
        document: dict[str, Any],
        sample_sections: Sequence[dict[str, Any]],
        tenant_id: UUID,
        agent_execution_id: str | None = None,
        event_sink: Callable[[Any], Awaitable[Any]] | None = None,
    ) -> ShadowScreeningOutput:
        result = await self._structured.invoke(
            role=SystemLLMRoleType.DOCUMENT_MEMORY_EXTRACTOR,
            system_prompt=await self._prompt("screening"),
            payload={"document": document, "sample_sections": list(sample_sections)},
            schema=ShadowScreeningOutput,
            tenant_id=tenant_id,
            use_default_model=True,
            agent_execution_id=agent_execution_id,
            trace_parent_entity_type="agent_execution",
            trace_parent_entity_id=agent_execution_id,
            event_sink=event_sink,
        )
        return result.value

    async def study(
        self,
        *,
        document: dict[str, Any],
        sections: Sequence[dict[str, Any]],
        candidate_ledger: Sequence[dict[str, Any]],
        glossary: Sequence[dict[str, Any]],
        projects: Sequence[dict[str, Any]],
        scopes: Sequence[dict[str, Any]] = (),
        correction_feedback: Sequence[dict[str, Any]] = (),
        tenant_id: UUID,
        agent_execution_id: str | None = None,
        event_sink: Callable[[Any], Awaitable[Any]] | None = None,
    ) -> ShadowStudyOutput:
        result = await self._structured.invoke(
            role=SystemLLMRoleType.DOCUMENT_MEMORY_EXTRACTOR,
            system_prompt=await self._prompt("study"),
            payload={
                "document": document,
                "sections": list(sections),
                "candidate_ledger": list(candidate_ledger),
                "glossary": list(glossary),
                "project_catalog": list(projects),
                "scope_catalog": list(scopes),
                "correction_feedback": list(correction_feedback),
            },
            schema=ShadowStudyOutput,
            tenant_id=tenant_id,
            use_default_model=True,
            agent_execution_id=agent_execution_id,
            trace_parent_entity_type="agent_execution",
            trace_parent_entity_id=agent_execution_id,
            event_sink=event_sink,
        )
        return result.value


class ShadowDocumentStudyService:
    """State machine and persistence boundary for a single document snapshot."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create_snapshot(self, *, document_id: UUID, checksum: str, visibility_tenant_id: UUID | None) -> DocumentMemorySnapshot:
        old_snapshots = select(DocumentMemorySnapshot.id).where(
            DocumentMemorySnapshot.document_id == document_id,
            DocumentMemorySnapshot.canonical_checksum != checksum,
        )
        old_candidates = select(MemoryExtractionCandidate.id).where(
            MemoryExtractionCandidate.snapshot_id.in_(old_snapshots),
        )
        await self._session.execute(update(GlossaryTerm).where(
            GlossaryTerm.approved_candidate_id.in_(old_candidates),
        ).values(is_active=False))
        await self._session.execute(update(DocumentMemorySnapshot).where(
            DocumentMemorySnapshot.id.in_(old_snapshots),
            DocumentMemorySnapshot.status != "superseded",
        ).values(status="superseded"))
        row = (await self._session.execute(select(DocumentMemorySnapshot).where(
            DocumentMemorySnapshot.document_id == document_id,
            DocumentMemorySnapshot.canonical_checksum == checksum,
        ))).scalar_one_or_none()
        if row is None:
            row = DocumentMemorySnapshot(
                document_id=document_id, canonical_checksum=checksum, visibility_tenant_id=visibility_tenant_id, status="queued",
                metrics={"next_section": 0, "shadow_study": True},
            )
            self._session.add(row)
            await self._session.flush()
        elif row.status == "backfilled":
            row.status = "queued"
            row.metrics = {**dict(row.metrics or {}), "next_section": 0, "shadow_study": True, "reused_backfill": True}
        return row

    async def ensure_active_attempt(self, snapshot: DocumentMemorySnapshot) -> DocumentMemoryExtractionAttempt:
        attempt = await self._session.get(DocumentMemoryExtractionAttempt, snapshot.active_attempt_id) if snapshot.active_attempt_id else None
        if attempt is None:
            attempt = DocumentMemoryExtractionAttempt(snapshot_id=snapshot.id, attempt_number=1)
            self._session.add(attempt)
            await self._session.flush()
            snapshot.active_attempt_id = attempt.id
        return attempt

    async def lock_active_attempt(self, snapshot_id: UUID) -> tuple[DocumentMemorySnapshot, DocumentMemoryExtractionAttempt]:
        # Serialize mutations of a document attempt, including provider failure
        # paths. Refresh the identity map before reading the guard fields.
        snapshot = await self._session.scalar(select(DocumentMemorySnapshot).where(
            DocumentMemorySnapshot.id == snapshot_id,
        ).with_for_update().execution_options(populate_existing=True))
        if snapshot is None:
            raise ValueError("Shadow study snapshot not found")
        attempt = await self.ensure_active_attempt(snapshot)
        await self._session.refresh(attempt, with_for_update=True)
        return snapshot, attempt

    async def ledger(self, snapshot_id: UUID, attempt_id: UUID | None = None) -> list[dict[str, Any]]:
        rows = (await self._session.execute(select(MemoryExtractionCandidate).where(
            MemoryExtractionCandidate.snapshot_id == snapshot_id,
            MemoryExtractionCandidate.attempt_id == attempt_id if attempt_id else MemoryExtractionCandidate.attempt_id.is_(None),
            MemoryExtractionCandidate.resolution_status.not_in(("rejected", "stale")),
        ).order_by(MemoryExtractionCandidate.ordinal.desc()).limit(MAX_LEDGER_ITEMS))).scalars().all()
        scope_rows = (await self._session.execute(select(
            MemoryCandidateScope.candidate_id, MemoryScope.key, MemoryCandidateScope.role,
        ).join(MemoryScope, MemoryScope.id == MemoryCandidateScope.scope_id).where(
            MemoryCandidateScope.candidate_id.in_([row.id for row in rows]),
            MemoryCandidateScope.status != "rejected",
            MemoryScope.lifecycle_status == "active",
        ))).all() if rows else []
        scopes_by_candidate: dict[UUID, dict[str, list[str]]] = {}
        for candidate_id, key, role in scope_rows:
            scopes_by_candidate.setdefault(candidate_id, {"applies_to": [], "mentions": []})[role].append(key)
        proposal_rows = (await self._session.execute(select(
            MemoryCandidateScopeProposal.candidate_id, MemoryCandidateScopeProposal.role,
            MemoryScopeProposal.id, MemoryScopeProposal.scope_type, MemoryScopeProposal.name,
            MemoryScopeProposal.status,
            MemoryScopeProposal.term_candidate_id, MemoryScopeProposal.glossary_term_id,
            func.coalesce(MemoryExtractionCandidate.subject, GlossaryTerm.canonical_term),
        ).join(
            MemoryScopeProposal, MemoryScopeProposal.id == MemoryCandidateScopeProposal.scope_proposal_id,
        ).outerjoin(
            MemoryExtractionCandidate, MemoryExtractionCandidate.id == MemoryScopeProposal.term_candidate_id,
        ).outerjoin(
            GlossaryTerm, GlossaryTerm.id == MemoryScopeProposal.glossary_term_id,
        ).where(
            MemoryCandidateScopeProposal.candidate_id.in_([row.id for row in rows]),
            MemoryCandidateScopeProposal.status.in_(("suggested", "confirmed")),
            MemoryScopeProposal.status.in_(("awaiting_term", "needs_review", "approved")),
        ))).all() if rows else []
        proposals_by_candidate: dict[UUID, list[dict[str, str]]] = {}
        for candidate_id, role, proposal_id, scope_type, name, status, term_candidate_id, glossary_id, term_subject in proposal_rows:
            proposals_by_candidate.setdefault(candidate_id, []).append({
                "id": str(proposal_id), "type": scope_type, "name": name,
                "role": role, "status": status,
                "term_subject": term_subject or "",
                "term_candidate_id": str(term_candidate_id) if term_candidate_id else "",
                "glossary_term_id": str(glossary_id) if glossary_id else "",
            })
        return [{
            "id": str(row.id), "type": row.candidate_type, "subject": row.subject,
            "content": dict(row.content or {}), "scope_candidate": row.scope_candidate,
            "scope_keys": scopes_by_candidate.get(row.id, {}).get("applies_to", []),
            "mentioned_scope_keys": scopes_by_candidate.get(row.id, {}).get("mentions", []),
            "unmatched_scope_names": list(row.unmatched_scope_names or []),
            "scope_rationale": row.resolution_rationale,
            "evidence_section_ids": list(row.evidence_section_ids or []),
            "scope_proposals": proposals_by_candidate.get(row.id, []),
        } for row in reversed(rows)]

    async def reextraction_feedback(self, snapshot_id: UUID, attempt_id: UUID | None = None) -> list[dict[str, Any]]:
        candidates = (await self._session.scalars(select(MemoryExtractionCandidate).where(
            MemoryExtractionCandidate.snapshot_id == snapshot_id,
            MemoryExtractionCandidate.attempt_id == attempt_id,
            MemoryExtractionCandidate.resolution_status == "rejected",
        ).order_by(MemoryExtractionCandidate.updated_at.desc()).limit(30))).all()
        scopes = (await self._session.scalars(select(MemoryScopeProposal).where(
            MemoryScopeProposal.snapshot_id == snapshot_id,
            MemoryScopeProposal.attempt_id == attempt_id,
            MemoryScopeProposal.status == "rejected",
        ).order_by(MemoryScopeProposal.updated_at.desc()).limit(10))).all()
        return [{"kind": row.candidate_type, "candidate_id": str(row.id),
                 "attempt_id": str(row.attempt_id), "subject": row.subject,
                 "content_text": row.content_text[:4000],
                 "evidence_section_ids": list(row.evidence_section_ids or [])[:8],
                 "reason": str(row.resolution_rationale or "")[:2000]} for row in candidates] + [
                {"kind": "scope", "proposal_id": str(row.id), "attempt_id": str(row.attempt_id),
                 "scope_type": row.scope_type, "subject": row.name,
                 "reason": str(row.rejection_reason or "")[:2000],
                 "evidence_section_ids": list(row.evidence_section_ids or [])[:8]} for row in scopes]

    async def glossary_context(self) -> list[dict[str, Any]]:
        rows = (await self._session.execute(GlossaryService.published_terms_query()
            .order_by(GlossaryTerm.canonical_term)
            .limit(MAX_GLOSSARY_ITEMS))).scalars().all()
        return [{"term": term.canonical_term, "definition": term.definition,
                 "aliases": list(term.aliases or [])} for term in rows]

    async def project_catalog(self) -> tuple[dict[str, Project], list[dict[str, Any]]]:
        rows = list((await self._session.execute(select(Project).where(
            Project.is_active.is_(True),
        ).order_by(Project.name))).scalars().all())
        return (
            {project.key.strip().lower(): project for project in rows},
            [{"key": project.key, "name": project.name, "aliases": list(project.aliases or [])} for project in rows],
        )

    async def scope_catalog(self) -> tuple[dict[str, MemoryScope], list[dict[str, Any]]]:
        rows = list((await self._session.execute(select(MemoryScope).where(
            MemoryScope.lifecycle_status == "active",
        ).order_by(
            MemoryScope.scope_type, MemoryScope.key,
        ))).scalars().all())
        linked_terms = dict((await self._session.execute(select(
            MemoryScopeGlossaryTerm.scope_id,
            GlossaryTerm.canonical_term,
        ).join(
            GlossaryTerm, GlossaryTerm.id == MemoryScopeGlossaryTerm.glossary_term_id,
        ).where(
            GlossaryTerm.is_active.is_(True),
            MemoryScopeGlossaryTerm.scope_id.in_([scope.id for scope in rows]),
        ))).all()) if rows else {}
        return (
            {scope.key: scope for scope in rows},
            [{"key": scope.key, "type": scope.scope_type, "name": scope.name,
              "aliases": list(scope.aliases or []), "is_all": scope.is_all,
              "glossary_term": linked_terms.get(scope.id)} for scope in rows],
        )

    async def document_scope_hints(self, document_id: UUID) -> list[dict[str, Any]]:
        """Read the current upload hints from typed document bindings."""
        rows = (await self._session.execute(select(MemoryScope).join(
            DocumentMemoryScope, DocumentMemoryScope.scope_id == MemoryScope.id,
        ).where(
            DocumentMemoryScope.document_id == document_id,
            MemoryScope.lifecycle_status == "active",
        ).order_by(MemoryScope.scope_type, MemoryScope.key))).scalars().all()
        return [{"key": scope.key, "type": scope.scope_type, "name": scope.name,
                 "aliases": list(scope.aliases or []), "is_all": scope.is_all} for scope in rows]

    async def persist_batch(
        self,
        *,
        snapshot: DocumentMemorySnapshot,
        attempt: DocumentMemoryExtractionAttempt | None = None,
        items: Sequence[ShadowStudyItem],
        document_scope: str,
        section_ids: set[str],
        projects_by_key: dict[str, Project],
        scopes_by_key: dict[str, MemoryScope] | None = None,
    ) -> dict[str, int]:
        known = {UUID(item["id"]): item for item in await self.ledger(snapshot.id, attempt.id if attempt else None)}
        maximum = (await self._session.execute(select(func.max(MemoryExtractionCandidate.ordinal)).where(
            MemoryExtractionCandidate.snapshot_id == snapshot.id,
        ))).scalar_one_or_none()
        next_ordinal = int(maximum if maximum is not None else -1) + 1
        counts = {"created": 0, "extended": 0, "rejected": 0, "invalid_content": 0}
        ordered_items = sorted(items, key=lambda item: item.candidate_type != "term")
        term_candidate_ids = {
            row.normalized_subject: row.id
            for row in (await self._session.execute(select(MemoryExtractionCandidate).where(
                MemoryExtractionCandidate.snapshot_id == snapshot.id,
                MemoryExtractionCandidate.candidate_type == "term",
                (MemoryExtractionCandidate.attempt_id == (attempt.id if attempt else None)) |
                (MemoryExtractionCandidate.resolution_status == "resolved"),
            ))).scalars().all()
        }
        for item in ordered_items:
            if item.candidate_type == "term":
                if document_scope != "global":
                    counts["rejected"] += 1
                    continue
                item = item.model_copy(update={"scope_candidate": "unknown", "project_keys": [],
                                               "scope_keys": [], "mentioned_scope_keys": [], "unmatched_scope_names": []})
            evidence = list(dict.fromkeys(value for value in item.evidence_section_ids if value in section_ids))
            if not evidence:
                counts["rejected"] += 1
                continue
            applies, mentions, unmatched, proposed_scope = _scope_proposal(item, scopes_by_key or {}, projects_by_key)
            content = dict(item.content or {})
            try:
                content = normalize_memory_content(item.candidate_type, content)
            except ValueError:
                if item.candidate_type == "term":
                    counts["rejected"] += 1
                    continue
                # Keep source-backed memory proposals visible for human review.
                counts["invalid_content"] += 1
            if item.operation == "extend_existing":
                if item.existing_candidate_id not in known:
                    counts["rejected"] += 1
                    continue
                row = await self._session.get(MemoryExtractionCandidate, item.existing_candidate_id)
                if row is None or row.candidate_type != item.candidate_type or row.normalized_subject != _normalized(item.subject):
                    counts["rejected"] += 1
                    continue
                if item.candidate_type == "term":
                    existing_definition = str((row.content or {}).get("definition") or "").strip()
                    incoming_definition = str(content["definition"])
                    if existing_definition and " ".join(existing_definition.split()).casefold() != incoming_definition.casefold():
                        counts["rejected"] += 1
                        continue
                    if not existing_definition:
                        row.content = content
                        row.content_text = json.dumps(content, ensure_ascii=False, sort_keys=True)
                row.evidence_section_ids = list(dict.fromkeys([*(row.evidence_section_ids or []), *evidence]))
                row.aliases = _unique([*(row.aliases or []), *item.aliases])
                if row.candidate_type != "term":
                    row.unmatched_scope_names = _unique([*(row.unmatched_scope_names or []), *unmatched])[:8]
                    has_existing_applies = (await self._session.execute(select(MemoryCandidateScope.id).where(
                        MemoryCandidateScope.candidate_id == row.id,
                        MemoryCandidateScope.role == "applies_to",
                        MemoryCandidateScope.status != "rejected",
                    ).limit(1))).scalar_one_or_none() is not None
                    if row.scope_candidate in (None, "unknown") and proposed_scope != "unknown":
                        if proposed_scope != "global" or not has_existing_applies:
                            row.scope_candidate = proposed_scope
                    elif row.scope_candidate == "global" and (item.scope_keys or item.project_keys):
                        row.scope_candidate = "unknown"
                    elif proposed_scope not in ("unknown", row.scope_candidate):
                        row.scope_candidate = "unknown"
                    elif proposed_scope == "unknown" and (item.scope_keys or item.project_keys):
                        row.scope_candidate = "unknown"
                    if item.scope_rationale and not row.resolution_rationale:
                        row.resolution_rationale = item.scope_rationale
                    await self._add_project_bindings(row.id, item, applies, proposed_scope, projects_by_key)
                    await self._add_scope_bindings(row.id, applies, mentions, scopes_by_key or {}, item)
                else:
                    term_candidate_ids[row.normalized_subject] = row.id
                await self._persist_scope_proposals(
                    snapshot=snapshot, item=item, candidate=row,
                    term_candidate_ids=term_candidate_ids, section_ids=evidence,
                )
                counts["extended"] += 1
                continue
            subject = _normalized(item.subject)
            if not subject:
                counts["rejected"] += 1
                continue
            row = MemoryExtractionCandidate(
                snapshot_id=snapshot.id, ordinal=next_ordinal, candidate_type=item.candidate_type,
                attempt_id=attempt.id if attempt else None,
                visibility_tenant_id=snapshot.visibility_tenant_id,
                subject=item.subject.strip()[:200], normalized_subject=subject,
                content=content, content_text=json.dumps(content, ensure_ascii=False, sort_keys=True),
                evidence_section_ids=evidence, aliases=_unique(item.aliases),
                unmatched_scope_names=unmatched,
                extraction_confidence=item.extraction_confidence,
                scope_candidate=None if item.candidate_type == "term" else proposed_scope,
                resolution_status="extracted", resolution_method="llm_suggestion",
                resolution_rationale=item.scope_rationale or None,
            )
            next_ordinal += 1
            self._session.add(row)
            await self._session.flush()
            await self._add_project_bindings(row.id, item, applies, proposed_scope, projects_by_key)
            await self._add_scope_bindings(row.id, applies, mentions, scopes_by_key or {}, item)
            if row.candidate_type == "term":
                term_candidate_ids[subject] = row.id
            await self._persist_scope_proposals(
                snapshot=snapshot, item=item, candidate=row,
                term_candidate_ids=term_candidate_ids, section_ids=evidence,
            )
            counts["created"] += 1
        return counts

    async def _persist_scope_proposals(
        self, *, snapshot: DocumentMemorySnapshot, item: ShadowStudyItem,
        candidate: MemoryExtractionCandidate, term_candidate_ids: dict[str, UUID],
        section_ids: list[str],
    ) -> None:
        proposals = list(item.scope_proposals)
        if candidate.candidate_type != "term":
            for key in _unique([*item.scope_keys, *(f"project.{key}" for key in item.project_keys)]):
                known_scope = await self._session.scalar(select(MemoryScope.id).where(
                    MemoryScope.key == key.casefold(), MemoryScope.lifecycle_status == "active",
                ))
                if known_scope is None:
                    references = list(candidate.unresolved_scope_references or [])
                    reference = {"key": key.casefold(), "reason": "unknown_scope_key"}
                    if reference not in references:
                        candidate.unresolved_scope_references = [*references, reference]
                    candidate.scope_candidate = "unknown"
        if candidate.candidate_type == "term" and item.scope_type:
            proposals.append(ShadowScopeProposal(
                scope_type=item.scope_type, name=candidate.subject,
                aliases=list(candidate.aliases or []), term_subject=candidate.subject,
                role="applies_to", rationale=item.scope_rationale,
            ))
        for proposal in proposals:
            term_key = _normalized(proposal.term_subject)
            term_candidate_id = term_candidate_ids.get(term_key)
            glossary_term_id = await self._session.scalar(select(GlossaryTerm.id).where(
                GlossaryTerm.normalized_term == term_key,
                GlossaryTerm.is_active.is_(True),
            ))
            if glossary_term_id is not None and term_candidate_id is not None:
                term_status = await self._session.scalar(select(MemoryExtractionCandidate.resolution_status).where(
                    MemoryExtractionCandidate.id == term_candidate_id,
                ))
                if term_status == "resolved":
                    term_candidate_id = None
                else:
                    glossary_term_id = None
            if term_candidate_id is None and glossary_term_id is None:
                candidate.unmatched_scope_names = _unique([
                    *(candidate.unmatched_scope_names or []), proposal.name,
                ])[:8]
                self._unresolved_scope(candidate, proposal, reason="missing_term")
                continue
            if (candidate.candidate_type != "term" and proposal.role == "applies_to"
                    and not candidate.unresolved_scope_references):
                candidate.scope_candidate = "scoped"
            normalized_key = _normalized(proposal.name)
            active_scopes = (await self._session.scalars(select(MemoryScope).where(
                MemoryScope.scope_type == proposal.scope_type,
                MemoryScope.lifecycle_status == "active",
            ))).all()
            proposed_forms = {normalized_key, *(_normalized(alias) for alias in proposal.aliases)}
            matching_scopes = [scope for scope in active_scopes if proposed_forms.intersection({
                _normalized(scope.key.removeprefix(f"{scope.scope_type}.")),
                _normalized(scope.name),
                *(_normalized(alias) for alias in scope.aliases or []),
            })]
            # Alias collisions are real ambiguity; never bind to whichever row
            # happened to be returned first by the database.
            existing_scope = matching_scopes[0] if len(matching_scopes) == 1 else None
            if len(matching_scopes) > 1:
                candidate.unmatched_scope_names = _unique([
                    *(candidate.unmatched_scope_names or []), proposal.name,
                ])[:8]
                self._unresolved_scope(candidate, proposal, reason="ambiguous_scope",
                                       alternatives=[scope.key for scope in matching_scopes])
                continue
            if existing_scope is not None:
                if candidate.candidate_type == "term":
                    proposal_row = await self._session.scalar(select(MemoryScopeProposal).where(
                        MemoryScopeProposal.scope_type == proposal.scope_type,
                        MemoryScopeProposal.normalized_key == normalized_key,
                        MemoryScopeProposal.term_candidate_id == term_candidate_id,
                        MemoryScopeProposal.attempt_id == (candidate.attempt_id),
                        MemoryScopeProposal.visibility_tenant_id == snapshot.visibility_tenant_id,
                    ))
                    if proposal_row is None:
                        proposal_row = MemoryScopeProposal(
                            snapshot_id=snapshot.id,
                            attempt_id=candidate.attempt_id,
                            visibility_tenant_id=snapshot.visibility_tenant_id,
                            scope_type=proposal.scope_type,
                            proposed_key=existing_scope.key,
                            normalized_key=normalized_key,
                            name=existing_scope.name,
                            aliases=list(dict.fromkeys([*(existing_scope.aliases or []), *proposal.aliases])),
                            term_candidate_id=term_candidate_id,
                            source_term_candidate_id=term_candidate_ids.get(term_key),
                            glossary_term_id=glossary_term_id,
                            memory_scope_id=existing_scope.id,
                            evidence_section_ids=section_ids,
                            rationale=proposal.rationale or item.scope_rationale,
                            status="needs_review" if glossary_term_id else "awaiting_term",
                        )
                        self._session.add(proposal_row)
                    continue
                binding_id = await self._session.scalar(select(MemoryCandidateScope.id).where(
                    MemoryCandidateScope.candidate_id == candidate.id,
                    MemoryCandidateScope.scope_id == existing_scope.id,
                    MemoryCandidateScope.role == proposal.role,
                ))
                if binding_id is None:
                    self._session.add(MemoryCandidateScope(
                        candidate_id=candidate.id, scope_id=existing_scope.id,
                        role=proposal.role, status="suggested", method="unique_alias",
                        confidence=item.extraction_confidence,
                        rationale=proposal.rationale or item.scope_rationale,
                    ))
                continue
            proposal_row = await self._session.scalar(select(MemoryScopeProposal).where(
                MemoryScopeProposal.scope_type == proposal.scope_type,
                MemoryScopeProposal.normalized_key == normalized_key,
                MemoryScopeProposal.status.in_(("awaiting_term", "needs_review")),
                MemoryScopeProposal.visibility_tenant_id == snapshot.visibility_tenant_id,
                MemoryScopeProposal.attempt_id == candidate.attempt_id,
                MemoryScopeProposal.term_candidate_id == term_candidate_id,
                MemoryScopeProposal.glossary_term_id == glossary_term_id,
            ))
            if proposal_row is None:
                proposal_row = MemoryScopeProposal(
                    snapshot_id=snapshot.id,
                    attempt_id=candidate.attempt_id,
                    visibility_tenant_id=snapshot.visibility_tenant_id,
                    scope_type=proposal.scope_type,
                    proposed_key=_scope_key(proposal.scope_type, proposal.name),
                    normalized_key=normalized_key,
                    name=proposal.name.strip(),
                    aliases=_unique(proposal.aliases),
                    term_candidate_id=term_candidate_id,
                    source_term_candidate_id=term_candidate_ids.get(term_key),
                    glossary_term_id=glossary_term_id,
                    evidence_section_ids=section_ids,
                    rationale=proposal.rationale or item.scope_rationale,
                    status="needs_review" if glossary_term_id else "awaiting_term",
                )
                self._session.add(proposal_row)
                await self._session.flush()
            if candidate.candidate_type == "term":
                continue
            binding_id = await self._session.scalar(select(MemoryCandidateScopeProposal.id).where(
                MemoryCandidateScopeProposal.candidate_id == candidate.id,
                MemoryCandidateScopeProposal.scope_proposal_id == proposal_row.id,
                MemoryCandidateScopeProposal.role == proposal.role,
            ))
            if binding_id is None:
                self._session.add(MemoryCandidateScopeProposal(
                    candidate_id=candidate.id, scope_proposal_id=proposal_row.id,
                    role=proposal.role, status="suggested",
                    confidence=item.extraction_confidence,
                    rationale=proposal.rationale or item.scope_rationale,
                ))

    @staticmethod
    def _unresolved_scope(candidate: MemoryExtractionCandidate, proposal: ShadowScopeProposal,
                          *, reason: str, alternatives: list[str] = ()) -> None:
        if candidate.candidate_type == "term" or proposal.role != "applies_to":
            return
        reference = {"type": proposal.scope_type, "name": proposal.name,
                     "term_subject": proposal.term_subject, "reason": reason,
                     "alternatives": list(alternatives)}
        existing = list(getattr(candidate, "unresolved_scope_references", None) or [])
        if reference not in existing:
            candidate.unresolved_scope_references = [*existing, reference]
        candidate.scope_candidate = "unknown"

    async def _add_project_bindings(self, candidate_id: UUID, item: ShadowStudyItem, applies: list[str],
                                    proposed_scope: str, projects_by_key: dict[str, Project]) -> None:
        project_keys = {value.strip().lower() for value in item.project_keys if value.strip()}
        if proposed_scope == "project":
            project_keys.update(key.removeprefix("project.") for key in applies if key.startswith("project."))
        existing = set((await self._session.execute(select(MemoryCandidateProjectBinding.project_id).where(
            MemoryCandidateProjectBinding.candidate_id == candidate_id,
        ))).scalars().all())
        for key in project_keys:
            project = projects_by_key.get(key)
            if project is not None and project.id not in existing:
                self._session.add(MemoryCandidateProjectBinding(
                    candidate_id=candidate_id, project_id=project.id, role="applies_to", status="suggested",
                    method="llm_suggestion", confidence=item.extraction_confidence,
                ))

    async def _add_scope_bindings(self, candidate_id: UUID, applies: list[str], mentions: list[str],
                                  scopes_by_key: dict[str, MemoryScope], item: ShadowStudyItem) -> None:
        existing = set((await self._session.execute(select(MemoryCandidateScope.scope_id, MemoryCandidateScope.role).where(
            MemoryCandidateScope.candidate_id == candidate_id,
        ))).all())
        for role, keys in (("applies_to", applies), ("mentions", mentions)):
            for key in keys:
                scope = scopes_by_key[key]
                if (scope.id, role) in existing:
                    continue
                self._session.add(MemoryCandidateScope(
                    candidate_id=candidate_id, scope_id=scope.id, role=role, status="suggested",
                    method="llm_suggestion", confidence=item.extraction_confidence,
                    rationale=item.scope_rationale or None,
                ))

    async def finalize(self, snapshot: DocumentMemorySnapshot,
                       attempt: DocumentMemoryExtractionAttempt | None = None) -> dict[str, int]:
        candidates = list((await self._session.execute(select(MemoryExtractionCandidate).where(
            MemoryExtractionCandidate.snapshot_id == snapshot.id,
            MemoryExtractionCandidate.attempt_id == attempt.id if attempt else MemoryExtractionCandidate.attempt_id.is_(None),
            MemoryExtractionCandidate.resolution_status == "extracted",
        ))).scalars().all())
        for candidate in candidates:
            candidate.resolution_status = "needs_review"
        snapshot.status = "conflict_checking"
        snapshot.metrics = {**dict(snapshot.metrics or {}), "candidates": len(candidates), "ready_at": datetime.now(timezone.utc).isoformat()}
        return {"candidates": len(candidates)}


def _normalized(value: str) -> str:
    return " ".join(str(value or "").strip().casefold().split())[:200]


def _scope_key(scope_type: str, name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", _normalized(name)).strip("-")
    if not slug:
        slug = "item-" + hashlib.sha256(_normalized(name).encode("utf-8")).hexdigest()[:12]
    return f"{scope_type}.{slug}"[:180]


def _scope_proposal(
    item: ShadowStudyItem,
    scopes_by_key: dict[str, MemoryScope],
    projects_by_key: dict[str, Project],
) -> tuple[list[str], list[str], list[str], str]:
    if item.candidate_type == "term":
        return [], [], [], "unknown"
    raw_applies = _unique([*item.scope_keys, *(f"project.{key}" for key in item.project_keys)])
    raw_mentions = _unique(item.mentioned_scope_keys)
    applies = [key for key in (raw.casefold() for raw in raw_applies) if key in scopes_by_key]
    mentions = [key for key in (raw.casefold() for raw in raw_mentions)
                if key in scopes_by_key and key not in applies]
    missing_applies = [raw for raw in raw_applies if raw.casefold() not in scopes_by_key]
    missing_mentions = [raw for raw in raw_mentions if raw.casefold() not in scopes_by_key]
    unmatched = _unique([*item.unmatched_scope_names, *missing_applies, *missing_mentions])[:8]
    proposed_scope = item.scope_candidate
    if proposed_scope == "global" and raw_applies:
        proposed_scope = "unknown"
    elif proposed_scope == "scoped" and (not applies or missing_applies):
        proposed_scope = "unknown"
    elif proposed_scope == "project":
        project_scope_keys = [key for key in applies if scopes_by_key[key].scope_type == "project"]
        if (missing_applies or len(applies) != 1 or len(project_scope_keys) != 1 or
                project_scope_keys[0].removeprefix("project.") not in projects_by_key):
            proposed_scope = "unknown"
    return applies, mentions, unmatched, proposed_scope


def _unique(values: Sequence[object]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = " ".join(str(raw or "").strip().split())[:255]
        normalized = value.casefold()
        if value and normalized not in seen:
            seen.add(normalized)
            result.append(value)
    return result
