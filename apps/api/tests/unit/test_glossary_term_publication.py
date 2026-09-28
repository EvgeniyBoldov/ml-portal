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
