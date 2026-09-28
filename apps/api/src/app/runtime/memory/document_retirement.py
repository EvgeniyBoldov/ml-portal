"""Withdraw document evidence from published semantic memory."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_entity import KnowledgeEntity, KnowledgeEntitySource
from app.models.document_memory_staging import DocumentMemorySnapshot, GlossaryTerm, MemoryExtractionCandidate
from app.models.memory import MemoryClaim, MemoryItem, MemoryItemSource, MemoryRelation


async def retire_document_memory(session: AsyncSession, *, document_id: UUID) -> dict[UUID, str]:
    source_candidate_ids = select(MemoryExtractionCandidate.id).join(
        DocumentMemorySnapshot, MemoryExtractionCandidate.snapshot_id == DocumentMemorySnapshot.id,
    ).where(DocumentMemorySnapshot.document_id == document_id)
    await session.execute(update(GlossaryTerm).where(
        GlossaryTerm.approved_candidate_id.in_(source_candidate_ids),
    ).values(is_active=False))
    item_ids = set((await session.execute(select(MemoryItemSource.memory_item_id).where(
        MemoryItemSource.document_id == document_id,
    ))).scalars().all())
    item_ids.update((await session.execute(select(MemoryClaim.memory_item_id).where(
        MemoryClaim.document_id == document_id, MemoryClaim.state == "active",
    ))).scalars().all())
    await session.execute(update(MemoryClaim).where(
        MemoryClaim.document_id == document_id, MemoryClaim.state == "active",
    ).values(state="stale"))
    await session.execute(delete(MemoryItemSource).where(MemoryItemSource.document_id == document_id))
    await session.execute(delete(MemoryRelation).where(MemoryRelation.document_id == document_id))
    await _retire_entity_sources(session, document_id)
    for item_id in item_ids:
        await _consolidate_item(session, item_id)
    await session.flush()
    rows = (await session.execute(select(MemoryItem.id, MemoryItem.state).where(
        MemoryItem.id.in_(item_ids),
    ))).all() if item_ids else []
    return {item_id: state for item_id, state in rows}


async def _retire_entity_sources(session: AsyncSession, document_id: UUID) -> None:
    entity_ids = set((await session.execute(select(KnowledgeEntitySource.entity_id).where(
        KnowledgeEntitySource.document_id == document_id,
    ))).scalars().all())
    await session.execute(delete(KnowledgeEntitySource).where(KnowledgeEntitySource.document_id == document_id))
    for entity_id in entity_ids:
        entity = await session.get(KnowledgeEntity, entity_id)
        if entity is not None:
            remaining = await session.scalar(select(KnowledgeEntitySource.id).where(
                KnowledgeEntitySource.entity_id == entity_id,
            ).limit(1))
            entity.is_active = remaining is not None


async def _consolidate_item(session: AsyncSession, item_id: UUID) -> None:
    item = await session.get(MemoryItem, item_id)
    if item is None:
        return
    claims = list((await session.execute(select(MemoryClaim).where(
        MemoryClaim.memory_item_id == item_id, MemoryClaim.state == "active",
    ).order_by(MemoryClaim.confidence.desc(), MemoryClaim.updated_at.desc()))).scalars().all())
    if not claims:
        item.state = "stale"
        return
    winner = claims[0]
    item.content = winner.content
    item.content_text = winner.content_text
    item.confidence = winner.confidence
    item.extraction_confidence = winner.extraction_confidence
    item.project_resolution_confidence = winner.project_resolution_confidence
    item.source_trust = winner.source_trust
    item.last_verified_at = datetime.now(timezone.utc)
    item.state = "active" if len({claim.content_text for claim in claims}) == 1 else "uncertain"
