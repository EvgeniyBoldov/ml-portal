"""Conflict detection for the isolated document-memory staging area."""
from __future__ import annotations

from typing import Literal
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
from app.runtime.llm.structured import StructuredLLMCall
from app.runtime.memory.shadow_study_prompts import SHADOW_MEMORY_CONFLICT_PROMPT
from app.runtime.memory.shadow_memory_publication import ShadowMemoryPublicationService


class _ConflictOutput(BaseModel):
    kind: Literal["compatible_extension", "contradiction", "insufficient_evidence"]
    rationale: str = ""


class ShadowMemoryReviewService:
    """Uses deterministic narrowing before one bounded LLM comparison."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def check_snapshot(self, snapshot: DocumentMemorySnapshot) -> dict[str, int]:
        candidates = list((await self._session.execute(select(MemoryExtractionCandidate).where(
            MemoryExtractionCandidate.snapshot_id == snapshot.id,
            MemoryExtractionCandidate.resolution_status == "needs_review",
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
                if existing.snapshot_id == snapshot.id and str(existing.id) <= str(candidate.id):
                    continue
                kind, rationale = await self._classify(candidate, existing, snapshot.visibility_tenant_id)
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
    ) -> tuple[str, str]:
        if candidate.content_text == existing.content_text and candidate.scope_candidate == existing.scope_candidate:
            return "duplicate", "Exact canonical content in the same proposed scope."
        if {candidate.scope_candidate, existing.scope_candidate} == {"global", "project"}:
            return "scope_override", "Same subject has global and project-specific candidates; review applicability."
        try:
            result = await StructuredLLMCall(session=self._session, llm_client=get_llm_client()).invoke(
                role=SystemLLMRoleType.DOCUMENT_MEMORY_EXTRACTOR,
                system_prompt=SHADOW_MEMORY_CONFLICT_PROMPT,
                payload={
                    "candidate": _candidate_payload(candidate),
                    "existing": _candidate_payload(existing),
                },
                schema=_ConflictOutput,
                tenant_id=tenant_id,
                use_default_model=True,
            )
            return result.value.kind, result.value.rationale
        except Exception:
            # Failure must never silently turn an unknown contradiction into a
            # publishable fact.
            return "insufficient_evidence", "Conflict classifier unavailable; manual review required."


def _candidate_payload(candidate: MemoryExtractionCandidate) -> dict[str, object]:
    return {
        "id": str(candidate.id), "type": candidate.candidate_type,
        "subject": candidate.subject, "content": dict(candidate.content or {}),
        "scope": candidate.scope_candidate, "evidence_section_ids": list(candidate.evidence_section_ids or []),
    }
