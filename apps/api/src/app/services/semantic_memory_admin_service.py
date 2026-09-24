"""Read-only administrative inspection of source-backed semantic memory."""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import exists, func, or_, select
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
from app.models.memory_scope import MemoryClaimScope, MemoryScope


@dataclass(frozen=True)
class SemanticMemoryListRow:
    item: MemoryItem
    source_count: int
    claim_count: int
    scope_keys: tuple[str, ...] = ()


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
        scope_type: str | None = None,
        scope_id: UUID | None = None,
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
            .outerjoin(MemoryClaim, (MemoryClaim.memory_item_id == MemoryItem.id) & (MemoryClaim.lifecycle_status == "active"))
            .where(MemoryItem.lifecycle_status == "active", _approved_item())
            .group_by(MemoryItem.id)
            .order_by(MemoryItem.updated_at.desc(), MemoryItem.subject, MemoryItem.id)
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
        for predicate in _scope_filters(scope_type, scope_id):
            stmt = stmt.where(predicate)
        if query and query.strip():
            pattern = f"%{query.strip()}%"
            stmt = stmt.where(or_(MemoryItem.subject.ilike(pattern), MemoryItem.content_text.ilike(pattern)))
        rows = (await self._session.execute(stmt)).all()
        scope_keys_by_item: dict[UUID, set[str]] = {}
        if rows:
            scope_rows = (await self._session.execute(select(MemoryClaim.memory_item_id, MemoryScope.key)
                .join(MemoryClaimScope, MemoryClaimScope.claim_id == MemoryClaim.id)
                .join(MemoryScope, MemoryScope.id == MemoryClaimScope.scope_id)
                .where(MemoryClaim.memory_item_id.in_([row[0].id for row in rows]),
                       MemoryClaim.approved_candidate_id.is_not(None),
                       MemoryClaim.lifecycle_status == "active"))).all()
            for item_id, key in scope_rows:
                scope_keys_by_item.setdefault(item_id, set()).add(key)
        count_stmt = select(func.count()).select_from(MemoryItem).where(MemoryItem.lifecycle_status == "active", _approved_item())
        for predicate in _item_filters(scope, state, item_type, project_id, query, scope_type, scope_id):
            count_stmt = count_stmt.where(predicate)
        total = int((await self._session.execute(count_stmt)).scalar_one())
        return SemanticMemoryPage(
            rows=tuple(SemanticMemoryListRow(item=row[0], source_count=int(row[1]), claim_count=int(row[2]),
                                             scope_keys=tuple(sorted(scope_keys_by_item.get(row[0].id, ())))) for row in rows),
            total=total,
        )

    async def get_item(self, item_id: UUID) -> SemanticMemoryDetail | None:
        item = await self._session.get(MemoryItem, item_id)
        if item is None or item.lifecycle_status != "active":
            return None
        sources = (await self._session.execute(
            select(MemoryItemSource).where(MemoryItemSource.memory_item_id == item_id)
            .order_by(MemoryItemSource.created_at.desc())
        )).scalars().all()
        claims = (await self._session.execute(
            select(MemoryClaim).where(MemoryClaim.memory_item_id == item_id, MemoryClaim.lifecycle_status == "active")
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


def _approved_item():
    return exists(select(MemoryClaim.id).join(
        MemoryExtractionCandidate, MemoryExtractionCandidate.id == MemoryClaim.approved_candidate_id,
    ).where(
        MemoryClaim.memory_item_id == MemoryItem.id,
        MemoryClaim.lifecycle_status == "active",
        MemoryExtractionCandidate.resolution_status == "resolved",
    ))


def _scope_filters(scope_type, scope_id):
    if scope_type == "global":
        yield ~exists(select(MemoryClaimScope.scope_id).join(
            MemoryClaim, MemoryClaim.id == MemoryClaimScope.claim_id,
        ).where(MemoryClaim.memory_item_id == MemoryItem.id,
                MemoryClaim.approved_candidate_id.is_not(None),
                MemoryClaim.lifecycle_status == "active"))
    elif scope_type or scope_id:
        stmt = select(MemoryClaimScope.scope_id).join(
            MemoryClaim, MemoryClaim.id == MemoryClaimScope.claim_id,
        ).join(MemoryScope, MemoryScope.id == MemoryClaimScope.scope_id).where(
            MemoryClaim.memory_item_id == MemoryItem.id,
            MemoryClaim.approved_candidate_id.is_not(None),
            MemoryClaim.lifecycle_status == "active",
            MemoryScope.lifecycle_status == "active",
        )
        if scope_type:
            stmt = stmt.where(MemoryScope.scope_type == scope_type)
        if scope_id:
            stmt = stmt.where(MemoryScope.id == scope_id)
        yield exists(stmt)


def _item_filters(scope, state, item_type, project_id, query, scope_type=None, scope_id=None):
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
    yield from _scope_filters(scope_type, scope_id)
