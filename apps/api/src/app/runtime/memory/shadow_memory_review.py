"""Conflict detection for the isolated document-memory staging area."""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Literal
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.di import get_llm_client
from app.models.document_memory_staging import (
    DocumentMemorySnapshot,
    MemoryConflictCase,
    MemoryConflictMember,
    MemoryExtractionCandidate,
)
from app.models.system_llm_role import SystemLLMRoleType
from app.models.memory_scope import MemoryCandidateScope, MemoryScope
from app.runtime.llm.structured import StructuredLLMCall
from app.runtime.memory.shadow_study_prompts import document_memory_prompt
from app.runtime.memory.shadow_memory_publication import ShadowMemoryPublicationService


class _ConflictOutput(BaseModel):
    kind: Literal["compatible_extension", "contradiction", "insufficient_evidence"]
    rationale: str = ""


class ShadowMemoryReviewService:
    """Uses deterministic narrowing before one bounded LLM comparison."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def check_snapshot(
        self,
        snapshot: DocumentMemorySnapshot,
        *,
        agent_execution_id: str | None = None,
        event_sink: Callable[[Any], Awaitable[Any]] | None = None,
    ) -> dict[str, int]:
        candidates = list((await self._session.execute(select(MemoryExtractionCandidate).where(
            MemoryExtractionCandidate.snapshot_id == snapshot.id,
            MemoryExtractionCandidate.resolution_status.in_(("extracted", "needs_review")),
        ))).scalars().all())
        counts = {"conflicts": 0, "duplicates": 0, "autoeligible": 0}
        for candidate in candidates:
            matches = list((await self._session.execute(select(MemoryExtractionCandidate).where(
                MemoryExtractionCandidate.id != candidate.id,
                MemoryExtractionCandidate.candidate_type == candidate.candidate_type,
                MemoryExtractionCandidate.normalized_subject == candidate.normalized_subject,
                or_(
                    MemoryExtractionCandidate.resolution_status == "resolved",
                    and_(MemoryExtractionCandidate.snapshot_id == snapshot.id,
                         MemoryExtractionCandidate.resolution_status == "needs_review"),
                ),
                or_(
                    MemoryExtractionCandidate.visibility_tenant_id.is_(None),
                    MemoryExtractionCandidate.visibility_tenant_id == snapshot.visibility_tenant_id,
                ),
            ).limit(12))).scalars().all())
            for existing in matches:
                if candidate.candidate_type == "term":
                    # Repeated spellings contribute aliases; they do not
                    # assert competing scoped definitions.
                    continue
                if existing.snapshot_id == snapshot.id and str(existing.id) <= str(candidate.id):
                    continue
                kind, rationale = await self._classify(
                    candidate, existing, snapshot.visibility_tenant_id,
                    agent_execution_id=agent_execution_id, event_sink=event_sink,
                )
                case = MemoryConflictCase(
                    visibility_tenant_id=snapshot.visibility_tenant_id,
                    kind=kind, rationale=rationale[:2000],
                    evidence={"candidate": str(candidate.id), "existing_candidate": str(existing.id)},
                )
                self._session.add(case)
                await self._session.flush()
                self._session.add_all((
                    MemoryConflictMember(conflict_id=case.id, candidate_id=candidate.id, role="candidate"),
                    MemoryConflictMember(conflict_id=case.id, candidate_id=existing.id, role="existing"),
                ))
                if kind == "duplicate":
                    counts["duplicates"] += 1
                    # Strict auto-approval is intentionally narrower than
                    # duplicate detection: no project binding, no promotion,
                    # byte-identical content and identical visibility.
                    if (candidate.scope_candidate == existing.scope_candidate == "global"
                            and candidate.visibility_tenant_id == existing.visibility_tenant_id):
                        await ShadowMemoryPublicationService(self._session).approve(
                            candidate_id=candidate.id, actor_id=None, reason="Exact source-backed duplicate.",
                            scope="global", automatic=True,
                        )
                        case.status = "resolved"
                        counts["autoeligible"] += 1
                elif kind in {"contradiction", "insufficient_evidence"}:
                    candidate.resolution_status = "conflict"
                    counts["conflicts"] += 1
        pending = (await self._session.execute(select(MemoryExtractionCandidate.id).where(
            MemoryExtractionCandidate.snapshot_id == snapshot.id,
            MemoryExtractionCandidate.resolution_status.in_(("needs_review", "conflict", "extracted")),
        ).limit(1))).scalar_one_or_none()
        snapshot.status = "awaiting_review" if pending is not None else "approved"
        snapshot.metrics = {**dict(snapshot.metrics or {}), "conflicts": counts}
        return counts

    async def _classify(
        self,
        candidate: MemoryExtractionCandidate,
        existing: MemoryExtractionCandidate,
        tenant_id: UUID | None,
        *,
        agent_execution_id: str | None = None,
        event_sink: Callable[[Any], Awaitable[Any]] | None = None,
    ) -> tuple[str, str]:
        candidate_scopes = await self._scope_keys(candidate.id)
        existing_scopes = await self._scope_keys(existing.id)
        if (candidate.content_text == existing.content_text
                and candidate.scope_candidate == existing.scope_candidate
                and candidate_scopes == existing_scopes):
            return "duplicate", "Exact canonical content in the same proposed scope."
        if candidate_scopes != existing_scopes:
            return "scope_override", "Same subject has different proposed applicability; review both scope sets."
        if {candidate.scope_candidate, existing.scope_candidate} == {"global", "project"}:
            return "scope_override", "Same subject has global and project-specific candidates; review applicability."
        try:
            structured = StructuredLLMCall(session=self._session, llm_client=get_llm_client())
            role_config = await structured.role_service.get_role_config(SystemLLMRoleType.DOCUMENT_MEMORY_EXTRACTOR)
            result = await structured.invoke(
                role=SystemLLMRoleType.DOCUMENT_MEMORY_EXTRACTOR,
                system_prompt=document_memory_prompt(role_config.get("extras"), stage="conflict"),
                payload={
                    "candidate": {**_candidate_payload(candidate), "scope_keys": sorted(candidate_scopes)},
                    "existing": {**_candidate_payload(existing), "scope_keys": sorted(existing_scopes)},
                },
                schema=_ConflictOutput,
                tenant_id=tenant_id,
                use_default_model=True,
                agent_execution_id=agent_execution_id,
                trace_parent_entity_type="agent_execution",
                trace_parent_entity_id=agent_execution_id,
                event_sink=event_sink,
            )
            return result.value.kind, result.value.rationale
        except Exception:
            # Failure must never silently turn an unknown contradiction into a
            # publishable fact.
            return "insufficient_evidence", "Conflict classifier unavailable; manual review required."

    async def _scope_keys(self, candidate_id: UUID) -> set[str]:
        rows = (await self._session.execute(select(MemoryScope.key).join(
            MemoryCandidateScope, MemoryCandidateScope.scope_id == MemoryScope.id,
        ).where(MemoryCandidateScope.candidate_id == candidate_id,
                MemoryCandidateScope.role == "applies_to",
                MemoryCandidateScope.status != "rejected",
                MemoryScope.lifecycle_status == "active"))).scalars().all()
        return set(rows)


def _candidate_payload(candidate: MemoryExtractionCandidate) -> dict[str, object]:
    return {
        "id": str(candidate.id), "type": candidate.candidate_type,
        "subject": candidate.subject, "content": dict(candidate.content or {}),
        "scope": candidate.scope_candidate, "evidence_section_ids": list(candidate.evidence_section_ids or []),
    }
