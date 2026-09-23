"""Read-only administrative inspection of source-backed semantic memory."""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import (
    MemoryClaim,
    MemoryItem,
    MemoryItemEvaluation,
    MemoryItemSource,
    MemoryRelation,
)
from app.models.document_memory_staging import (
    DocumentMemorySnapshot,
    GlossaryMeaning,
    MemoryCandidateProjectBinding,
    MemoryExtractionCandidate,
)


@dataclass(frozen=True)
class SemanticMemoryListRow:
    item: MemoryItem
    source_count: int
    claim_count: int


@dataclass(frozen=True)
class SemanticMemoryDetail:
    item: MemoryItem
    sources: tuple[MemoryItemSource, ...]
    claims: tuple[MemoryClaim, ...]
    relations: tuple[MemoryRelation, ...]
    evaluations: tuple[MemoryItemEvaluation, ...]


@dataclass(frozen=True)
class SemanticMemoryPage:
    rows: tuple[SemanticMemoryListRow, ...]
    total: int


@dataclass(frozen=True)
class SemanticMemoryStagingOverview:
    snapshots: dict[str, int]
    candidates: dict[str, int]
    project_bindings: dict[str, int]
    glossary_meanings: dict[str, int]
    conflicting_glossary_terms: int


class SemanticMemoryAdminService:
    """Inspection boundary; semantic memory is never edited as free text."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_items(
        self,
        *,
        scope: str | None = None,
        state: str | None = None,
        item_type: str | None = None,
        project_id: UUID | None = None,
        query: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> SemanticMemoryPage:
        stmt = (
            select(
                MemoryItem,
                func.count(func.distinct(MemoryItemSource.id)).label("source_count"),
                func.count(func.distinct(MemoryClaim.id)).label("claim_count"),
            )
            .outerjoin(MemoryItemSource, MemoryItemSource.memory_item_id == MemoryItem.id)
            .outerjoin(MemoryClaim, MemoryClaim.memory_item_id == MemoryItem.id)
            .group_by(MemoryItem.id)
            .order_by(MemoryItem.updated_at.desc(), MemoryItem.subject)
            .limit(max(1, min(limit, 200)))
            .offset(max(0, offset))
        )
        if scope == "scoped":
            stmt = stmt.where(MemoryItem.scope_signature != "legacy")
        elif scope == "company":
            stmt = stmt.where(MemoryItem.scope == "company", MemoryItem.scope_signature == "legacy")
        elif scope:
            stmt = stmt.where(MemoryItem.scope == scope)
        if state:
            stmt = stmt.where(MemoryItem.state == state)
        if item_type:
            stmt = stmt.where(MemoryItem.item_type == item_type)
        if project_id:
            stmt = stmt.where(MemoryItem.project_id == project_id)
        if query and query.strip():
            pattern = f"%{query.strip()}%"
            stmt = stmt.where(or_(MemoryItem.subject.ilike(pattern), MemoryItem.content_text.ilike(pattern)))
        rows = (await self._session.execute(stmt)).all()
        count_stmt = select(func.count()).select_from(MemoryItem)
        for predicate in _item_filters(scope, state, item_type, project_id, query):
            count_stmt = count_stmt.where(predicate)
        total = int((await self._session.execute(count_stmt)).scalar_one())
        return SemanticMemoryPage(
            rows=tuple(SemanticMemoryListRow(item=row[0], source_count=int(row[1]), claim_count=int(row[2])) for row in rows),
            total=total,
        )

    async def get_item(self, item_id: UUID) -> SemanticMemoryDetail | None:
        item = await self._session.get(MemoryItem, item_id)
        if item is None:
            return None
        sources = (await self._session.execute(
            select(MemoryItemSource).where(MemoryItemSource.memory_item_id == item_id)
            .order_by(MemoryItemSource.created_at.desc())
        )).scalars().all()
        claims = (await self._session.execute(
            select(MemoryClaim).where(MemoryClaim.memory_item_id == item_id)
            .order_by(MemoryClaim.updated_at.desc())
        )).scalars().all()
        relations = (await self._session.execute(
            select(MemoryRelation).where(MemoryRelation.memory_item_id == item_id)
            .order_by(MemoryRelation.relation_type, MemoryRelation.target_type, MemoryRelation.target_id)
        )).scalars().all()
        evaluations = (await self._session.execute(
            select(MemoryItemEvaluation).where(MemoryItemEvaluation.memory_item_id == item_id)
            .order_by(MemoryItemEvaluation.created_at.desc())
        )).scalars().all()
        return SemanticMemoryDetail(
            item=item, sources=tuple(sources), claims=tuple(claims),
            relations=tuple(relations), evaluations=tuple(evaluations),
        )

    async def staging_overview(self) -> SemanticMemoryStagingOverview:
        """Expose P0 migration health without switching any user read path."""
        snapshots = await self._count_by(DocumentMemorySnapshot.status)
        candidates = await self._count_by(MemoryExtractionCandidate.resolution_status)
        project_bindings = await self._count_by(
            MemoryCandidateProjectBinding.role, MemoryCandidateProjectBinding.status,
        )
        meanings = await self._count_by(GlossaryMeaning.resolution_status)
        conflicts = (await self._session.execute(
            select(func.count()).select_from(
                select(GlossaryMeaning.term_id)
                .where(GlossaryMeaning.resolution_status == "resolved")
                .group_by(GlossaryMeaning.term_id)
                .having(func.count(func.distinct(GlossaryMeaning.definition)) > 1)
                .subquery()
            )
        )).scalar_one()
        return SemanticMemoryStagingOverview(
            snapshots=snapshots,
            candidates=candidates,
            project_bindings=project_bindings,
            glossary_meanings=meanings,
            conflicting_glossary_terms=int(conflicts),
        )

    async def _count_by(self, *columns) -> dict[str, int]:
        rows = (await self._session.execute(
            select(*columns, func.count()).group_by(*columns)
        )).all()
        return {
            ":".join(str(value) for value in row[:-1]): int(row[-1])
            for row in rows
        }


def _item_filters(scope, state, item_type, project_id, query):
    if scope == "scoped":
        yield MemoryItem.scope_signature != "legacy"
    elif scope == "company":
        yield MemoryItem.scope == "company"
        yield MemoryItem.scope_signature == "legacy"
    elif scope:
        yield MemoryItem.scope == scope
    if state:
        yield MemoryItem.state == state
    if item_type:
        yield MemoryItem.item_type == item_type
    if project_id:
        yield MemoryItem.project_id == project_id
    if query and query.strip():
        pattern = f"%{query.strip()}%"
        yield or_(MemoryItem.subject.ilike(pattern), MemoryItem.content_text.ilike(pattern))
