from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.models.model_registry import ModelType
from app.services.model_service import ModelService


@pytest.mark.parametrize("data", [
    {"type": "llm_chat"},
    {"type": "embedding", "enabled": False},
    {"type": "embedding", "status": "unavailable"},
])
def test_long_memory_rejects_unusable_encoders(data):
    with pytest.raises(ValueError):
        ModelService._validate_long_memory_encoder(data)


@pytest.mark.asyncio
async def test_switch_selects_one_encoder_and_durably_queues_rebuild(monkeypatch):
    from app.repositories.long_memory_config_repository import LongMemoryConfigRepository
    session = AsyncMock()
    model = SimpleNamespace(id=uuid4(), alias="encoder", type=ModelType.EMBEDDING,
        provider="local", connector="local_emb_http", base_url="http://encoder",
        instance_id=None, extra_config={}, enabled=True, status="available",
        default_for_type=False, use_for_long_memory=False)
    service = ModelService(session)
    service.get_by_id = AsyncMock(return_value=model)
    monkeypatch.setattr(service, "_enqueue_embedding_status_reconcile", lambda *args: None)
    select = AsyncMock()
    request = AsyncMock()
    monkeypatch.setattr(LongMemoryConfigRepository, "select_encoder", select)
    monkeypatch.setattr(LongMemoryConfigRepository, "request_reindex", request)
    await service.update_model(model.id, {"use_for_long_memory": True})
    assert model.use_for_long_memory is True
    assert model.default_for_type is False
    select.assert_awaited_once()
    request.assert_awaited_once_with(model.id)
    session.commit.assert_not_awaited()
    await service.update_model(model.id, {"use_for_long_memory": True})
    assert request.await_count == 1


@pytest.mark.asyncio
async def test_default_embedding_change_does_not_select_long_memory(monkeypatch):
    from app.repositories.long_memory_config_repository import LongMemoryConfigRepository
    session = AsyncMock()
    model = SimpleNamespace(id=uuid4(), alias="encoder", type=ModelType.EMBEDDING,
        provider="local", connector="local_emb_http", base_url="http://encoder",
        instance_id=None, extra_config={}, enabled=True, status="available",
        default_for_type=False, use_for_long_memory=False)
    service = ModelService(session)
    service.get_by_id = AsyncMock(return_value=model)
    service._unset_default_for_type = AsyncMock()
    monkeypatch.setattr(service, "_enqueue_embedding_status_reconcile", lambda *args: None)
    request = AsyncMock()
    monkeypatch.setattr(LongMemoryConfigRepository, "request_reindex", request)
    await service.update_model(model.id, {"default_for_type": True})
    request.assert_not_awaited()
    assert model.use_for_long_memory is False


def test_dispatch_happens_after_outer_commit_and_never_after_rollback(monkeypatch):
    from unittest.mock import Mock
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.workers.tasks_hipporag_document import reconcile_long_memory_reindex

    dispatch = Mock()
    monkeypatch.setattr(reconcile_long_memory_reindex, "delay", dispatch)
    with Session(create_engine("sqlite://")) as session:
        session.begin()
        session.info["long_memory_reindex"] = True
        with session.begin_nested():
            pass
        dispatch.assert_not_called()
        session.commit()
        dispatch.assert_called_once()
        session.begin()
        session.info["long_memory_reindex"] = True
        session.rollback()
        session.begin()
        session.commit()
        dispatch.assert_called_once()


@pytest.mark.asyncio
async def test_health_manifest_changes_do_not_rebuild_long_memory(monkeypatch):
    from app.repositories.long_memory_config_repository import LongMemoryConfigRepository
    session = AsyncMock()
    model = SimpleNamespace(id=uuid4(), alias="encoder", type=ModelType.EMBEDDING,
        provider="local", provider_model_name="bge-m3", connector="local_emb_http", base_url="http://encoder",
        instance_id=None, extra_config={}, enabled=True, status="available", model_version="v1",
        embedding_dimensions=1024, max_input_tokens=8192, vector_normalized=True,
        default_for_type=False, use_for_long_memory=True)
    service = ModelService(session)
    service.get_by_id = AsyncMock(return_value=model)
    monkeypatch.setattr(service, "_enqueue_embedding_status_reconcile", lambda *args: None)
    request = AsyncMock()
    monkeypatch.setattr(LongMemoryConfigRepository, "request_reindex", request)
    await service.update_model(model.id, {"extra_config": {"manifest": {"_health": {"latency_ms": 32}}}})
    request.assert_not_awaited()
    await service.update_model(model.id, {"embedding_dimensions": 384})
    request.assert_awaited_once_with(model.id)
