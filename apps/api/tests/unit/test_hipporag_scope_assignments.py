from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services.hipporag_service import HippoRAGService


@pytest.mark.asyncio
async def test_reindex_preserves_default_scopes_and_explicitly_unassigned_documents(monkeypatch):
    company_document = uuid4()
    scoped_document = uuid4()
    unassigned_document = uuid4()
    session = AsyncMock()
    session.execute.return_value = SimpleNamespace(all=lambda: [
        (company_document, None, {}),
        (scoped_document, "platform", {"memory": {}}),
        (unassigned_document, None, {"memory": {"scope_unassigned": True}}),
    ])
    service = HippoRAGService(session)
    reindex = AsyncMock(return_value={"status": "completed"})
    monkeypatch.setattr(service, "_call", reindex)

    result = await service.reindex_embeddings()

    assert result == {"status": "completed"}
    assert reindex.await_args.args == ("corpus/reindex", {
        "scope_assignments": {
            str(company_document): ["company"],
            str(scoped_document): ["platform"],
            str(unassigned_document): [],
        },
    })
