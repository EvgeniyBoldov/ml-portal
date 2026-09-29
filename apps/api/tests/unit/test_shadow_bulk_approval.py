from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api.v1.routers.admin import semantic_memory


def _result(rows):
    return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: rows))


@pytest.mark.asyncio
async def test_bulk_approval_publishes_only_defined_terms_without_conflicts(monkeypatch) -> None:
    defined_id, conflicted_id, memory_id = uuid4(), uuid4(), uuid4()
    rows = [
        SimpleNamespace(id=defined_id, candidate_type="term", resolution_status="extracted",
                        normalized_subject="пзэ", content={"definition": "Поле золотых единорогов"}),
        SimpleNamespace(id=conflicted_id, candidate_type="term", resolution_status="conflict",
                        normalized_subject="sla", content={"definition": "Уровень доступности сервиса"}),
        SimpleNamespace(id=memory_id, candidate_type="rule", resolution_status="extracted",
                        normalized_subject="sla пзэ", content={"statement": "SLA для ПЗЭ составляет 96%"}),
    ]
    db = SimpleNamespace(execute=AsyncMock(side_effect=[
        _result(rows), _result([conflicted_id]), _result([]),
    ]), commit=AsyncMock(), rollback=AsyncMock())
    publisher = SimpleNamespace(approve=AsyncMock())
    monkeypatch.setattr(semantic_memory, "ShadowMemoryPublicationService", lambda _: publisher)

    result = await semantic_memory.bulk_approve_shadow_terms(
        semantic_memory.ShadowCandidateBulkRequest(ids=[defined_id, conflicted_id, memory_id]),
        db=db, user=SimpleNamespace(id=str(uuid4())),
    )

    assert result.approved_ids == [defined_id]
    assert result.review_ids == [conflicted_id, memory_id]
    publisher.approve.assert_awaited_once()
    assert publisher.approve.await_args.kwargs["candidate_id"] == defined_id
    db.commit.assert_awaited_once()
