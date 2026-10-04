from datetime import datetime, timezone
from uuid import uuid4
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.repositories.glossary_catalog_repository import GlossaryCatalogRepository, GlossaryTermRecord
from app.services.glossary_catalog_service import (
    GlossaryCatalogTerm,
    GlossaryCatalogService,
)

SOURCE_DOCUMENT_ID = uuid4()


class _Repository:
    async def list_visible(self):
        return [
            GlossaryTermRecord(
                canonical_term="evpn",
                aliases=("EVPN", "Ethernet VPN"),
                description="Ethernet Virtual Private Network",
                updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                source_document_id=SOURCE_DOCUMENT_ID,
                source_document_title="Словарь компании",
                source_section_ids=("section-1",),
            )
        ]


@pytest.mark.asyncio
async def test_glossary_catalog_service_returns_safe_entry_projection() -> None:
    repository = _Repository()
    service = GlossaryCatalogService(session=object())  # type: ignore[arg-type]
    service._repository = repository  # type: ignore[assignment]
    entries = await service.list_entries()

    assert entries == [
        GlossaryCatalogTerm(
            canonical_term="evpn",
            aliases=("EVPN", "Ethernet VPN"),
            description="Ethernet Virtual Private Network",
            updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            source_document_id=SOURCE_DOCUMENT_ID,
            source_document_title="Словарь компании",
            source_section_ids=("section-1",),
        )
    ]


@pytest.mark.asyncio
async def test_glossary_catalog_reads_canonical_defined_terms() -> None:
    term = SimpleNamespace(canonical_term="ПЗЭ", aliases=["поле золотых единорогов"],
                           definition="Поле золотых единорогов", updated_at=datetime.now(timezone.utc))
    candidate = SimpleNamespace(evidence_section_ids=["section-1"])
    snapshot = SimpleNamespace(document_id=uuid4())
    document = SimpleNamespace(title="Словарь компании")
    session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(all=lambda: [(term, candidate, snapshot, document)])))

    result = await GlossaryCatalogRepository(session).list_visible()

    assert len(result) == 1
    assert result[0].description == term.definition
    assert result[0].source_document_id == snapshot.document_id
    query = str(session.execute.call_args.args[0])
    assert "glossary_terms" in query
    assert "glossary_terms.is_active" in query
    assert "btrim(glossary_terms.definition)" in query


def test_approved_term_catalog_has_no_document_scope_or_revision_filter() -> None:
    from app.services.glossary_service import GlossaryService
    query = str(GlossaryService.published_terms_query())
    assert "memory_extraction_candidates" not in query
    assert "glossary_terms.is_active" in query
    assert "ragdocuments" not in query
    assert "document_memory_snapshots" not in query


@pytest.mark.asyncio
async def test_term_extraction_keeps_terms_for_review_without_access_scope_input() -> None:
    from unittest.mock import Mock
    from app.runtime.memory.shadow_document_study import ShadowDocumentStudyService, ShadowStudyItem
    from app.models.document_memory_staging import MemoryExtractionCandidate

    empty = SimpleNamespace(scalar_one_or_none=lambda: None, scalars=lambda: SimpleNamespace(all=lambda: []))
    db = SimpleNamespace(execute=AsyncMock(return_value=empty), add=Mock(), flush=AsyncMock())
    service = ShadowDocumentStudyService(db)
    service.ledger = AsyncMock(return_value=[])
    service._add_project_bindings = AsyncMock()
    service._add_scope_bindings = AsyncMock()
    service._persist_scope_proposals = AsyncMock()
    service._persist_term_links = AsyncMock()
    item = ShadowStudyItem(candidate_type="term", subject="Окно работ", content={"definition": "Период согласованных работ"},
                           aliases=["ОР"], evidence_section_ids=["s1"], team_keys=["ops"], project_keys=["alpha"])
    counts = await service.persist_batch(snapshot=SimpleNamespace(id=uuid4(), visibility_tenant_id=uuid4()),
        items=[item], section_ids={"s1"}, projects_by_key={})
    assert counts["created"] == 1 and counts["rejected"] == 0
    row = db.add.call_args.args[0]
    assert isinstance(row, MemoryExtractionCandidate)
    assert row.candidate_type == "term" and row.scope_candidate is None
    assert row.resolution_status == "extracted"
    assert row.evidence_section_ids == ["s1"]
    assert row.aliases == ["ОР"]
    assert row.visibility_tenant_id is None
