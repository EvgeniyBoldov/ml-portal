"""Unit coverage for the non-blocking document-memory extraction branch."""
from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.runtime.llm.structured import StructuredCallResult
from app.runtime.memory.document_memory import (
    DocumentMemoryExtractor,
    _DocumentMemoryCandidate,
    _DocumentMemoryOutput,
    _procedure_content,
    _related_entities,
    split_canonical_sections,
)
from app.workers.tasks_rag_ingest.document_memory import is_memory_trusted_source


def _llm_result(value):
    return StructuredCallResult(
        value=value, trace_id=None, raw_response="", duration_ms=1, model="test",
        request_messages=[], request_params={},
    )


def test_split_canonical_sections_preserves_original_offsets() -> None:
    text = "  First paragraph.\n\nSecond paragraph.\n\nThird paragraph."

    sections = split_canonical_sections(text, max_chars=35)

    assert [section["id"] for section in sections] == ["section-1", "section-2"]
    assert sections[0]["text"] == "First paragraph.\n\nSecond paragraph."
    assert text[sections[0]["start_offset"]:sections[0]["end_offset"]] == "First paragraph.\n\nSecond paragraph."
    assert text[sections[1]["start_offset"]:sections[1]["end_offset"]] == "Third paragraph."


def test_memory_trust_defaults_to_corporate_rag_and_can_be_disabled() -> None:
    assert is_memory_trusted_source({}, document_scope="global") is True
    assert is_memory_trusted_source({"memory": {"trusted": False}}, document_scope="global") is False


def test_local_document_memory_requires_explicit_trust() -> None:
    assert is_memory_trusted_source({}, document_scope="local") is False
    assert is_memory_trusted_source({"memory": {"enabled": True}}, document_scope="local") is True


def test_related_entities_accept_only_typed_bounded_edges() -> None:
    assert _related_entities([
        {"target_type": "service", "target_id": "switching", "relation_type": "uses"},
        {"target_type": "bad type", "target_id": "x", "relation_type": "uses"},
    ]) == [("service", "switching", "uses")]


def test_incomplete_procedure_is_not_published() -> None:
    assert _procedure_content({"steps": ["change VLAN"]}) is None


@pytest.mark.asyncio
async def test_extractor_keeps_only_evidenced_allowed_items() -> None:
    extractor = DocumentMemoryExtractor(session=AsyncMock(), llm_client=AsyncMock())
    extractor._structured.invoke = AsyncMock(return_value=_llm_result(_DocumentMemoryOutput(items=[
        _DocumentMemoryCandidate(
            item_type="procedure", subject=" Switch VLAN change ",
            content={
                "goal": "Change VLAN", "applicability_conditions": [], "required_approvals": [],
                "prechecks": ["Verify access"],
                "steps": [{"instruction": "Create backup", "expected_result": "Backup exists", "confirmation_required": True}],
                "verification": ["Ping succeeds"],
                "rollback": {"mode": "steps", "steps": ["Restore backup"], "reason": None},
                "exceptions": [],
            }, project_key="network",
            project_confidence=0.95, evidence_section_ids=["section-1"],
        ),
        _DocumentMemoryCandidate(
            item_type="procedure", subject="unsupported",
            content={"steps": ["x"]}, project_key="network",
            project_confidence=0.95, evidence_section_ids=["missing"],
        ),
        _DocumentMemoryCandidate(
            item_type="invented", subject="bad", evidence_section_ids=["section-1"],
        ),
    ])))

    items = await extractor.extract(
        document={"title": "Switch changes"},
        sections=[{"id": "section-1", "text": "Create a backup."}],
        projects=[{"key": "network", "name": "Network"}],
        tenant_id=uuid4(),
    )

    assert len(items) == 1
    assert items[0].subject == "switch vlan change"
    assert items[0].evidence_section_ids == ("section-1",)


@pytest.mark.asyncio
async def test_extractor_keeps_unscoped_document_knowledge_at_company_scope() -> None:
    extractor = DocumentMemoryExtractor(session=AsyncMock(), llm_client=AsyncMock())
    extractor._structured.invoke = AsyncMock(return_value=_llm_result(_DocumentMemoryOutput(items=[
        _DocumentMemoryCandidate(
            item_type="rule", subject="change approval", content={
                "statement": "Approval is required", "effect": "require", "conditions": [],
                "required_approvals": ["Change owner"], "required_checks": [], "exceptions": [], "consequences": [],
            },
            evidence_section_ids=["section-1"],
        ),
    ])))

    items = await extractor.extract(
        document={"title": "Change policy"}, sections=[{"id": "section-1", "text": "Approval is required."}],
        projects=[], tenant_id=uuid4(),
    )

    assert len(items) == 1
    assert items[0].scope == "company"


@pytest.mark.asyncio
async def test_extractor_error_propagates_so_previous_memory_is_not_retired() -> None:
    extractor = DocumentMemoryExtractor(session=AsyncMock(), llm_client=AsyncMock())
    extractor._structured.invoke = AsyncMock(side_effect=RuntimeError("LLM unavailable"))

    with pytest.raises(RuntimeError, match="LLM unavailable"):
        await extractor.extract(
            document={"title": "Switch changes"},
            sections=[{"id": "section-1", "text": "Create a backup."}],
            projects=[], tenant_id=uuid4(),
        )
