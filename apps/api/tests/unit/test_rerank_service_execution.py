import asyncio
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException


@pytest.fixture
def service(monkeypatch):
    monkeypatch.setitem(sys.modules, 'sentence_transformers', SimpleNamespace(CrossEncoder=object))
    path = Path(__file__).resolve().parents[3] / 'rerank/src/app/main.py'
    if not path.exists():
        path = Path('/tmp/docsearch-rerank-main.py')
    spec = importlib.util.spec_from_file_location('docsearch_rerank_service', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.MODEL_BATCH_SIZE = 1
    module.inference_gate = asyncio.Semaphore(1)
    return module


@pytest.mark.asyncio
async def test_rerank_batches_preserve_original_indices_and_keep_event_loop_responsive(service):
    import time
    observed = []
    def predict(pairs, **kwargs):
        observed.extend(pair[1] for pair in pairs)
        time.sleep(0.02)
        return [float(len(pair[1])) for pair in pairs]
    service.model = SimpleNamespace(predict=predict)
    request = SimpleNamespace(headers={}, is_disconnected=AsyncMock(return_value=False))
    task = asyncio.create_task(service.rerank(service.RerankRequest(query='q', documents=['longest', 'a', 'bbb']), request))
    await asyncio.sleep(0.005)
    assert (await service.health())['status'] == 'ok'
    assert not task.done()
    response = await task
    assert observed == ['a', 'bbb', 'longest']
    assert [item['index'] for item in response['results']] == [0, 2, 1]


@pytest.mark.asyncio
async def test_disconnected_client_stops_before_next_batch(service):
    calls = []
    service.model = SimpleNamespace(predict=lambda pairs, **kwargs: calls.append(pairs) or [0.5])
    request = SimpleNamespace(headers={}, is_disconnected=AsyncMock(side_effect=[False, False, True]))
    with pytest.raises(HTTPException) as error:
        await service.rerank(service.RerankRequest(query='q', documents=['a', 'b', 'c']), request)
    assert error.value.status_code == 499
    assert len(calls) == 1
    assert not service.inference_gate.locked()


@pytest.mark.asyncio
async def test_request_deadline_includes_inference(service):
    import time
    def predict(pairs, **kwargs):
        time.sleep(0.03)
        return [0.5]
    service.model = SimpleNamespace(predict=predict)
    request = SimpleNamespace(headers={'X-Request-Timeout-Seconds': '0.01'}, is_disconnected=AsyncMock(return_value=False))
    with pytest.raises(HTTPException) as error:
        await service.rerank(service.RerankRequest(query='q', documents=['a', 'b']), request)
    assert error.value.status_code == 504
    assert not service.inference_gate.locked()


@pytest.mark.asyncio
async def test_queue_wait_is_bounded_and_does_not_start_inference(service):
    calls = []
    service.model = SimpleNamespace(predict=lambda pairs, **kwargs: calls.append(pairs) or [0.5])
    await service.inference_gate.acquire()
    request = SimpleNamespace(headers={'X-Request-Timeout-Seconds': '0.01'}, is_disconnected=AsyncMock(return_value=False))
    try:
        with pytest.raises(HTTPException) as error:
            await service.rerank(service.RerankRequest(query='q', documents=['a']), request)
        assert error.value.status_code == 504
        assert not calls
        assert service.inference_gate.locked()
    finally:
        service.inference_gate.release()
