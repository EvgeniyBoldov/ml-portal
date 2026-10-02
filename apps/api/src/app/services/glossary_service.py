"""Published company definitions backed by approved global documents."""
from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.document_memory_staging import DocumentMemorySnapshot, GlossaryTerm, MemoryExtractionCandidate
from app.models.rag import RAGDocument


def matched_glossary_forms(text: str, forms: Iterable[str]) -> list[str]:
    normalized = text.casefold()
    values = {str(form).strip().casefold() for form in forms if str(form).strip()}
    return [form for form in sorted(values) if re.search(rf"(?<!\w){re.escape(form)}(?!\w)", normalized)]


def matching_glossary_terms(
    text: str, terms: list[dict[str, object]], *, limit: int = 24,
) -> list[dict[str, object]]:
    return [term for term in terms if matched_glossary_forms(
        text, [str(term.get("term") or ""), *(str(alias) for alias in term.get("aliases") or [])],
    )][:limit]


def ambiguous_glossary_aliases(text: str, terms: list[dict[str, object]]) -> list[str]:
    matched = [form for term in terms for form in matched_glossary_forms(
        text, [str(term.get("term") or ""), *(str(alias) for alias in term.get("aliases") or [])],
    )]
    return sorted(form for form, count in Counter(matched).items() if count > 1)


class GlossaryService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def published_terms_query(*, require_active: bool = True):
        newer = aliased(DocumentMemorySnapshot)
        query = select(GlossaryTerm).join(
            MemoryExtractionCandidate, GlossaryTerm.approved_candidate_id == MemoryExtractionCandidate.id,
        ).join(
            DocumentMemorySnapshot, MemoryExtractionCandidate.snapshot_id == DocumentMemorySnapshot.id,
        ).join(
            RAGDocument, DocumentMemorySnapshot.document_id == RAGDocument.id,
        ).where(
            func.btrim(GlossaryTerm.definition) != "",
            MemoryExtractionCandidate.resolution_status == "resolved",
            MemoryExtractionCandidate.candidate_type == "term",
            or_(MemoryExtractionCandidate.attempt_id == DocumentMemorySnapshot.active_attempt_id,
                and_(MemoryExtractionCandidate.attempt_id.is_(None), DocumentMemorySnapshot.active_attempt_id.is_(None))),
            func.jsonb_array_length(MemoryExtractionCandidate.evidence_section_ids) > 0,
            DocumentMemorySnapshot.status.notin_(("superseded", "failed", "rejected")),
            ~exists(select(newer.id).where(
                newer.document_id == DocumentMemorySnapshot.document_id,
                newer.created_at > DocumentMemorySnapshot.created_at,
            )),
            RAGDocument.scope == "global",
            RAGDocument.status != "archived",
        )
        return query.where(GlossaryTerm.is_active.is_(True)) if require_active else query

    async def list_terms(self) -> list[dict[str, object]]:
        rows = await self._session.execute(select(GlossaryTerm).order_by(GlossaryTerm.canonical_term))
        terms = rows.scalars().all()
        return [{
            "id": term.id,
            "canonical_term": term.canonical_term,
            "normalized_term": term.normalized_term,
            "aliases": list(term.aliases or []),
            "is_active": term.is_active,
            "definition": term.definition,
            "approved_candidate_id": term.approved_candidate_id,
            "created_at": term.created_at,
            "updated_at": term.updated_at,
        } for term in terms]

    async def list_confirmed_terms(self, *, limit: int | None = None) -> list[dict[str, object]]:
        """Return approved lexical identities and their canonical definitions."""
        stmt = self.published_terms_query().with_only_columns(
            GlossaryTerm, MemoryExtractionCandidate, DocumentMemorySnapshot,
        ).order_by(GlossaryTerm.canonical_term)
        if limit is not None:
            stmt = stmt.limit(limit)
        rows = await self._session.execute(stmt)
        return [{"id": term.id, "term": term.canonical_term,
                 "definition": term.definition,
                 "source_references": [{
                     "document_id": str(snapshot.document_id), "section_id": section_id,
                 } for section_id in list(candidate.evidence_section_ids or [])[:3]],
                 "aliases": list(term.aliases or [])} for term, candidate, snapshot in rows.all()]
