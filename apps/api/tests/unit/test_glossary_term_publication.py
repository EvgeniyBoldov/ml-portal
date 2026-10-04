from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.models.document_memory_staging import GlossaryTerm
from app.runtime.memory.content_contracts import normalize_memory_content
from app.runtime.memory.shadow_memory_publication import ShadowMemoryPublicationService


def test_term_requires_a_definition() -> None:
    with pytest.raises(ValueError):
        normalize_memory_content("term", {})
    assert normalize_memory_content("term", {"definition": "  Поле золотых единорогов  "}) == {
        "definition": "Поле золотых единорогов",
    }


@pytest.mark.asyncio
async def test_publishing_term_creates_one_defined_glossary_record() -> None:
    session = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: None)),
        add=Mock(),
    )
    candidate = SimpleNamespace(
        id=uuid4(),
        subject="ПЗЭ", normalized_subject="пзэ", aliases=["поле золотых единорогов"],
        content={"definition": "Поле золотых единорогов"},
    )

    await ShadowMemoryPublicationService(session)._publish_term(candidate)

    session.add.assert_called_once()
    term = session.add.call_args.args[0]
    assert isinstance(term, GlossaryTerm)
    assert term.definition == "Поле золотых единорогов"
    assert term.aliases == ["поле золотых единорогов"]


@pytest.mark.asyncio
async def test_publishing_term_does_not_replace_a_different_definition() -> None:
    existing = SimpleNamespace(definition="Другое определение", aliases=[], normalized_term="пзэ", is_active=True)
    session = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: existing)),
        add=Mock(),
    )
    candidate = SimpleNamespace(id=uuid4(), subject="ПЗЭ", normalized_subject="пзэ", aliases=[],
                                content={"definition": "Поле золотых единорогов"})

    with pytest.raises(ValueError, match="different canonical definition"):
        await ShadowMemoryPublicationService(session)._publish_term(candidate)
    assert existing.definition == "Другое определение"
    session.add.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("source_scope", ["global", "collection", "tenant", "project"])
async def test_manual_term_approval_does_not_depend_on_document_scope(source_scope) -> None:
    row = SimpleNamespace(id=uuid4(), snapshot_id=uuid4(), candidate_type="term", resolution_status="needs_review",
                          content={"definition": "Внутренняя расшифровка"}, related_entities=[], scope_candidate=None,
                          evidence_section_ids=["s1"], visibility_tenant_id=uuid4(), resolution_rationale=None)
    snapshot = SimpleNamespace(document_id=uuid4(), status="awaiting_review", created_at=datetime.now(timezone.utc))
    document = SimpleNamespace(scope=source_scope, status="ready")
    db = SimpleNamespace(get=AsyncMock(side_effect=[snapshot, document]), scalar=AsyncMock(return_value=None), add=Mock())
    service = ShadowMemoryPublicationService(db)
    service._required_candidate = AsyncMock(return_value=row)
    service._publish_term = AsyncMock()
    service._activate_linked_scope_proposals = AsyncMock()
    service._update_snapshot = AsyncMock()
    service._publish_memory = AsyncMock()

    assert await service.approve(candidate_id=row.id, actor_id=uuid4(), reason=None) is row
    service._publish_term.assert_awaited_once()
    service._publish_memory.assert_not_awaited()
    assert row.resolution_status == "resolved"
    assert row.scope_candidate is None
    assert row.visibility_tenant_id is None


@pytest.mark.asyncio
async def test_automatic_term_approval_is_forbidden() -> None:
    row = SimpleNamespace(id=uuid4(), snapshot_id=uuid4(), candidate_type="term", resolution_status="needs_review")
    db = SimpleNamespace(get=AsyncMock(return_value=SimpleNamespace()), scalar=AsyncMock(return_value=None))
    service = ShadowMemoryPublicationService(db)
    service._required_candidate = AsyncMock(return_value=row)
    with pytest.raises(ValueError, match="manual administrator approval"):
        await service.approve(candidate_id=row.id, actor_id=None, reason=None, automatic=True)
