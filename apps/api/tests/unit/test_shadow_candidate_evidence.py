import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api.v1.routers.admin import semantic_memory
from app.storage.paths import calculate_text_checksum


@pytest.mark.asyncio
async def test_candidate_evidence_reads_only_referenced_sections(monkeypatch) -> None:
    text = "А" * 5000 + "\n\nSLA для ПЗЭ составляет 96%."
    candidate = SimpleNamespace(snapshot_id=uuid4(), evidence_section_ids=["section-2"])
    snapshot = SimpleNamespace(document_id=uuid4(), canonical_checksum=calculate_text_checksum(text))
    document = SimpleNamespace(s3_key_processed="canonical.json", title="Описание сервиса", filename="service.txt")
    db = SimpleNamespace(get=AsyncMock(side_effect=[candidate, snapshot, document]))
    get_object = AsyncMock(return_value=json.dumps({"text": text}).encode())
    monkeypatch.setattr(semantic_memory.s3_manager, "get_object", get_object)
    monkeypatch.setattr(semantic_memory, "get_settings", lambda: SimpleNamespace(S3_BUCKET_RAG="rag"))

    result = await semantic_memory.get_shadow_candidate_evidence(uuid4(), db=db, _=SimpleNamespace())

    assert result.document_title == "Описание сервиса"
    assert [section.id for section in result.sections] == ["section-2"]
    assert result.sections[0].text == "SLA для ПЗЭ составляет 96%."
    get_object.assert_awaited_once_with("rag", "canonical.json")
