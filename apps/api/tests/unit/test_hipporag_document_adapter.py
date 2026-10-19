"""Worker document polling keeps its capability until terminal progress."""
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest

from app.services import hipporag_service as module


@pytest.mark.asyncio
async def test_document_adapter_reports_progress_and_releases_capability(monkeypatch):
    redis = SimpleNamespace(set=AsyncMock(), delete=AsyncMock(), aclose=AsyncMock())
    monkeypatch.setattr(module.Redis, 'from_url', lambda *args, **kwargs: redis)
    monkeypatch.setattr(module.asyncio, 'sleep', AsyncMock())
    calls = []
    records = iter([
        {'operation_id': 'operation', 'status': 'queued'},
        {'operation_id': 'operation', 'status': 'running', 'steps': {'extract': {'status': 'processing'}}},
        {'operation_id': 'operation', 'status': 'completed', 'result': {'status': 'indexed'}},
    ])
    def handle(request):
        calls.append(request.method)
        return httpx.Response(202 if request.method == 'POST' else 200, json=next(records))
    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    monkeypatch.setattr(module.httpx, 'AsyncClient', lambda **kwargs: client)
    service = module.HippoRAGService(None)
    service._models = AsyncMock(return_value={})
    progress = AsyncMock()
    result = await service.document_operation(operation_id=uuid4(), document_id=uuid4(), generation=1,
        action='add', document={'content': 'Source'}, on_progress=progress)
    assert result['status'] == 'completed'
    assert calls == ['POST', 'GET', 'GET']
    assert [call.args[0]['status'] for call in progress.await_args_list] == ['queued', 'running', 'completed']
    redis.delete.assert_awaited_once()
    redis.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_document_info_does_not_require_working_models(monkeypatch):
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request:
        httpx.Response(200, json={'availability': 'absent'})))
    monkeypatch.setattr(module.httpx, 'AsyncClient', lambda **kwargs: client)
    service = module.HippoRAGService(None)
    service._models = AsyncMock(side_effect=AssertionError('status must not resolve models'))
    assert (await service.document_info(uuid4()))['availability'] == 'absent'
    service._models.assert_not_awaited()
