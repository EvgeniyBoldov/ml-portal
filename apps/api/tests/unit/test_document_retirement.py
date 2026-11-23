"""Unit tests for document memory retirement (app/runtime/memory/document_retirement.py)."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from sqlalchemy import Delete, Select, Update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_memory_staging import GlossaryTerm
from app.models.knowledge_entity import KnowledgeEntity, KnowledgeEntitySource
from app.models.memory import MemoryClaim, MemoryItem, MemoryItemSource, MemoryRelation
from app.runtime.memory.document_retirement import retire_document_memory


class FakeResult:
    def __init__(self, *, scalars: list | None = None, rows: list | None = None) -> None:
        self._scalars = scalars if scalars is not None else []
        self._rows = rows if rows is not None else []

    def scalars(self):
        return MagicMock(all=MagicMock(return_value=self._scalars))

    def all(self):
        return self._rows


def make_item(state: str = "active") -> MagicMock:
    item = MagicMock(spec=MemoryItem)
    item.id = uuid4()
    item.state = state
    return item


def make_claim(*, confidence: float, content: str, content_text: str | None = None) -> MagicMock:
    claim = MagicMock(spec=MemoryClaim)
    claim.confidence = confidence
    claim.content = {"text": content}
    claim.content_text = content_text if content_text is not None else content
    claim.extraction_confidence = confidence - 0.1
    claim.project_resolution_confidence = confidence - 0.2
    claim.source_trust = 0.5
    claim.updated_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return claim


class RetirementScript:
    """Scripted fake session replaying the retirement flow against in-memory state."""

    def __init__(
        self,
        *,
        source_item_ids: list,
        claim_item_ids: list,
        entity_remaining: dict,
        claims_by_item: dict,
        items: list,
        entities: list,
    ) -> None:
        self.source_item_ids = source_item_ids
        self.claim_item_ids = claim_item_ids
        self.entity_remaining = entity_remaining  # entity_id -> remaining source id | None
        self.claims_by_item = claims_by_item  # item_id -> active claims after retirement
        self.items = {item.id: item for item in items}
        self.entities = {entity.id: entity for entity in entities}
        self.executed: list = []
        self.flushed = False

        self.execute = AsyncMock(side_effect=self._execute)
        self.get = AsyncMock(side_effect=self._get)
        self.scalar = AsyncMock(side_effect=self._scalar)
        self.flush = AsyncMock(side_effect=self._mark_flushed)

    def _mark_flushed(self) -> None:
        self.flushed = True

    async def _get(self, entity_cls, pk):
        if entity_cls is MemoryItem:
            return self.items.get(pk)
        if entity_cls is KnowledgeEntity:
            return self.entities.get(pk)
        return None

    async def _scalar(self, stmt):
        assert isinstance(stmt, Select)
        entity = stmt.column_descriptions[0]["entity"]
        if entity is KnowledgeEntitySource:
            # Compiled where-clause carries the entity id being probed.
            params = stmt.compile().params
            entity_id = params.get("entity_id_1")
            return self.entity_remaining.get(entity_id)
        raise AssertionError(f"unexpected scalar select: {entity}")

    async def _execute(self, stmt):
        self.executed.append(stmt)

        if isinstance(stmt, (Update, Delete)):
            return FakeResult()

        assert isinstance(stmt, Select), f"unexpected statement: {stmt}"
        entity = stmt.column_descriptions[0]["entity"]
        name = stmt.column_descriptions[0]["name"]

        if entity is MemoryItemSource and name == "memory_item_id":
            return FakeResult(scalars=list(self.source_item_ids))
        if entity is MemoryClaim and name == "memory_item_id":
            return FakeResult(scalars=list(self.claim_item_ids))
        if entity is KnowledgeEntitySource and name == "entity_id":
            return FakeResult(scalars=list(self.entity_remaining.keys()))
        if entity is MemoryClaim and name == "MemoryClaim":
            params = stmt.compile().params
            item_id = params.get("memory_item_id_1")
            return FakeResult(scalars=self.claims_by_item.get(item_id, []))
        if entity is MemoryItem and name == "id":
            return FakeResult(rows=[(item.id, item.state) for item in self.items.values()])

        raise AssertionError(f"unexpected select: {entity}.{name}")


def build_scenario() -> tuple[RetirementScript, dict]:
    document_id = uuid4()

    item_orphan = make_item()  # loses all evidence -> stale
    item_conflict = make_item()  # diverging claims survive -> uncertain
    item_winner = make_item()  # single surviving claim wins -> active

    winner_claim = make_claim(confidence=0.9, content="Итоговое значение")
    loser_claim = make_claim(confidence=0.4, content="Конфликтующее значение")
    surviving_claim = make_claim(confidence=0.8, content="Стабильное значение")

    entity_dropped = MagicMock(spec=KnowledgeEntity)
    entity_dropped.id = uuid4()
    entity_dropped.is_active = True

    entity_kept = MagicMock(spec=KnowledgeEntity)
    entity_kept.id = uuid4()
    entity_kept.is_active = True

    script = RetirementScript(
        source_item_ids=[item_orphan.id, item_conflict.id],
        claim_item_ids=[item_conflict.id, item_winner.id],
        entity_remaining={entity_dropped.id: None, entity_kept.id: uuid4()},
        claims_by_item={
            item_conflict.id: [winner_claim, loser_claim],
            item_winner.id: [surviving_claim],
        },
        items=[item_orphan, item_conflict, item_winner],
        entities=[entity_dropped, entity_kept],
    )
    mocks = {
        "item_orphan": item_orphan,
        "item_conflict": item_conflict,
        "item_winner": item_winner,
        "winner_claim": winner_claim,
        "surviving_claim": surviving_claim,
        "entity_dropped": entity_dropped,
        "entity_kept": entity_kept,
    }
    return script, mocks


class TestRetireDocumentMemory:
    async def test_returns_final_state_per_item(self):
        script, mocks = build_scenario()

        result = await retire_document_memory(script, document_id=uuid4())

        assert result == {
            mocks["item_orphan"].id: "stale",
            mocks["item_conflict"].id: "uncertain",
            mocks["item_winner"].id: "active",
        }

    async def test_item_without_claims_becomes_stale(self):
        script, mocks = build_scenario()
        item = mocks["item_orphan"]

        await retire_document_memory(script, document_id=uuid4())

        assert item.state == "stale"

    async def test_diverging_claims_mark_item_uncertain_with_best_claim_content(self):
        script, mocks = build_scenario()
        item = mocks["item_conflict"]
        claim = mocks["winner_claim"]

        await retire_document_memory(script, document_id=uuid4())

        assert item.state == "uncertain"
        assert item.content == claim.content
        assert item.content_text == claim.content_text
        assert item.confidence == claim.confidence
        assert item.extraction_confidence == claim.extraction_confidence
        assert item.source_trust == claim.source_trust
        assert item.last_verified_at is not None

    async def test_single_surviving_claim_keeps_item_active(self):
        script, mocks = build_scenario()
        item = mocks["item_winner"]
        claim = mocks["surviving_claim"]

        await retire_document_memory(script, document_id=uuid4())

        assert item.state == "active"
        assert item.content == claim.content

    async def test_entity_without_remaining_sources_deactivated(self):
        script, mocks = build_scenario()

        await retire_document_memory(script, document_id=uuid4())

        assert mocks["entity_dropped"].is_active is False
        assert mocks["entity_kept"].is_active is True

    async def test_expected_mutations_are_issued(self):
        script, _ = build_scenario()

        await retire_document_memory(script, document_id=uuid4())

        tables = {}
        for stmt in script.executed:
            if isinstance(stmt, (Update, Delete)):
                tables.setdefault((stmt.__visit_name__, stmt.table.name), []).append(stmt)

        # Glossary terms approved from this document are deactivated, not deleted.
        glossary_update = tables[("update", GlossaryTerm.__tablename__)][0]
        assert glossary_update.compile().params["is_active"] is False

        # Active claims turn stale instead of being destroyed.
        claim_update = tables[("update", MemoryClaim.__tablename__)][0]
        assert claim_update.compile().params["state"] == "stale"

        # Raw links and relations are removed.
        assert ("delete", MemoryItemSource.__tablename__) in tables
        assert ("delete", MemoryRelation.__tablename__) in tables
        assert ("delete", KnowledgeEntitySource.__tablename__) in tables

        assert script.flushed is True
