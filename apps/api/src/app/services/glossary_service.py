"""Scope-free approved terminology. Document references provide provenance, not applicability."""
from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_memory_staging import DocumentMemorySnapshot, GlossaryTerm, MemoryExtractionCandidate


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
    def published_terms_query(*, require_active: bool = True) -> Select[tuple[GlossaryTerm]]:
        # A GlossaryTerm is created only by the administrator's approval path.
        # Its source reference is audit metadata, not a publication condition.
        query = select(GlossaryTerm).where(func.btrim(GlossaryTerm.definition) != "")
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
        ).outerjoin(
            MemoryExtractionCandidate, GlossaryTerm.approved_candidate_id == MemoryExtractionCandidate.id,
        ).outerjoin(
            DocumentMemorySnapshot, MemoryExtractionCandidate.snapshot_id == DocumentMemorySnapshot.id,
        ).order_by(GlossaryTerm.canonical_term)
        if limit is not None:
            stmt = stmt.limit(limit)
        rows = await self._session.execute(stmt)
        return [{"id": term.id, "term": term.canonical_term,
                 "definition": term.definition,
                 "source_references": [{
                     "document_id": str(snapshot.document_id), "section_id": section_id,
                 } for section_id in list(candidate.evidence_section_ids or [])[:3]] if candidate is not None and snapshot is not None else [],
                 "aliases": list(term.aliases or [])} for term, candidate, snapshot in rows.all()]
