"""Read models for the user-facing glossary catalogue."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_memory_staging import DocumentMemorySnapshot, GlossaryTerm, MemoryExtractionCandidate
from app.models.rag import RAGDocument
from app.services.glossary_service import GlossaryService


@dataclass(frozen=True)
class GlossaryTermRecord:
    canonical_term: str
    aliases: tuple[str, ...]
    description: str
    updated_at: datetime
    source_document_id: UUID
    source_document_title: str
    source_section_ids: tuple[str, ...]


class GlossaryCatalogRepository:
    """Read published terms from the canonical, unscoped glossary."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_visible(self) -> list[GlossaryTermRecord]:
        published_ids = GlossaryService.published_terms_query().with_only_columns(GlossaryTerm.id)
        rows = (await self._session.execute(
            select(GlossaryTerm, MemoryExtractionCandidate, DocumentMemorySnapshot, RAGDocument)
            .join(MemoryExtractionCandidate, GlossaryTerm.approved_candidate_id == MemoryExtractionCandidate.id)
            .join(DocumentMemorySnapshot, MemoryExtractionCandidate.snapshot_id == DocumentMemorySnapshot.id)
            .join(RAGDocument, DocumentMemorySnapshot.document_id == RAGDocument.id)
            .where(GlossaryTerm.id.in_(published_ids))
            .order_by(GlossaryTerm.canonical_term)
        )).all()
        return [GlossaryTermRecord(
            canonical_term=term.canonical_term,
            aliases=tuple(term.aliases or ()),
            description=term.definition,
            updated_at=term.updated_at,
            source_document_id=snapshot.document_id,
            source_document_title=document.title,
            source_section_ids=tuple(candidate.evidence_section_ids or ()),
        ) for term, candidate, snapshot, document in rows]
