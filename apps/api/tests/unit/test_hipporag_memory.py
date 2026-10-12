from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.runtime.memory import retrieval
from app.services.hipporag_service import HippoRAGService


@pytest.mark.asyncio
async def test_graph_receives_only_acl_and_scope_resolved_claims(monkeypatch):
    eligible, visible, secret = uuid4(), uuid4(), uuid4()
    projected = [{"id": eligible, "selected_claim_id": str(visible), "content_text": "Public backup rule"}]
    recall = NS(_session=object(), _accessible_semantic_items=AsyncMock(return_value=projected), _lexical_ids=AsyncMock())
    search = AsyncMock(return_value=[eligible])
    monkeypatch.setattr(retrieval, "get_settings", lambda: NS(MEMORY_SEARCH_BACKEND="hipporag"))
    monkeypatch.setattr(retrieval, "HippoRAGService", lambda _: NS(search_ids=search))
    read_args = {"project_ids": [], "tenant_id": uuid4(), "user_id": uuid4(),
                 "collection_ids": [uuid4()], "context_scope_keys": ["team.ops", "project.all"]}
    assert await retrieval.retrieve_memory_ids(recall, "backup", eligible_ids=[eligible], read_args=read_args) == [eligible]
    recall._accessible_semantic_items.assert_awaited_once_with(semantic_ids=[eligible], **read_args)
    assert search.await_args.kwargs["items"] == projected
    assert str(secret) not in str(search.await_args)
    recall._lexical_ids.assert_not_awaited()


@pytest.mark.asyncio
async def test_empty_authorized_corpus_never_calls_worker(monkeypatch):
    worker = Mock()
    monkeypatch.setattr(retrieval, "HippoRAGService", worker)
    assert await retrieval.retrieve_memory_ids(None, "secret", eligible_ids=[], read_args={}) == []
    worker.assert_not_called()


@pytest.mark.asyncio
async def test_graph_failure_is_not_hidden_by_legacy_fallback(monkeypatch):
    recall = NS(_session=object(), _accessible_semantic_items=AsyncMock(return_value=[{}]), _lexical_ids=AsyncMock())
    monkeypatch.setattr(retrieval, "get_settings", lambda: NS(MEMORY_SEARCH_BACKEND="hipporag"))
    monkeypatch.setattr(retrieval, "HippoRAGService", lambda _: NS(search_ids=AsyncMock(side_effect=RuntimeError("offline"))))
    with pytest.raises(RuntimeError, match="offline"):
        await retrieval.retrieve_memory_ids(recall, "query", eligible_ids=[uuid4()], read_args={})
    recall._lexical_ids.assert_not_awaited()


@pytest.mark.asyncio
async def test_hit_provenance_expands_duplicate_passages_and_rejects_foreign_ids():
    first, second, foreign = uuid4(), uuid4(), uuid4()
    items = [{"id": item, "selected_claim_id": str(uuid4()), "subject": "Backup", "content_text": "Make a backup"}
             for item in (first, second)]
    service = HippoRAGService(None)
    service._call = AsyncMock(return_value={"hits": [{"metadata": {"source_refs": [
        {"memory_item_id": str(first)}, {"memory_item_id": str(second)}, {"memory_item_id": str(foreign)}]}}]})
    assert await service.search_ids("backup", items=items) == [first, second]
    assert len(service._call.await_args.args[1]["documents"]) == 2


@pytest.mark.asyncio
async def test_model_capability_is_revoked_even_when_worker_fails(monkeypatch):
    import app.services.hipporag_service as module
    redis = NS(set=AsyncMock(), delete=AsyncMock(), aclose=AsyncMock())
    monkeypatch.setattr(module, "Redis", NS(from_url=lambda *args, **kwargs: redis))
    client = NS(post=AsyncMock(side_effect=RuntimeError("offline")))
    context = AsyncMock()
    context.__aenter__.return_value = client
    monkeypatch.setattr(module.httpx, "AsyncClient", lambda **_: context)
    service = HippoRAGService(None)
    service._models = AsyncMock(return_value={"llm_alias": "default"})
    with pytest.raises(RuntimeError, match="offline"):
        await service._call("extract", {"documents": []})
    assert redis.set.await_args.args[0] == redis.delete.await_args.args[0]
    assert "token" not in redis.set.await_args.args[1]


@pytest.mark.asyncio
async def test_expired_callback_capability_is_rejected(monkeypatch):
    from app.api.v1.routers import internal_hipporag as gateway
    monkeypatch.setattr(gateway, "get_redis", lambda: NS(get=AsyncMock(return_value=None)))
    with pytest.raises(HTTPException) as error:
        await gateway.capability("Bearer expired")
    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_qwen_settings_use_sdk_extra_body_and_trusted_stage_cap(monkeypatch):
    from app.api.v1.routers import internal_hipporag as gateway
    client = NS(chat=AsyncMock(return_value={"content": "json"}))
    monkeypatch.setattr(gateway, "get_llm_client", lambda: client)
    await gateway.chat(gateway.ChatRequest(messages=[{"role": "user", "content": "query"}], max_tokens=768),
                       {"llm_alias": "system.default", "qwen": True})
    kwargs = client.chat.await_args.kwargs
    assert "chat_template_kwargs" not in kwargs["params"]
    assert kwargs["params"]["extra_body"]["chat_template_kwargs"]["enable_thinking"] is False
    assert kwargs["options"].output_token_cap == 768


def test_legacy_extractor_cannot_be_run_by_old_automatic_messages(monkeypatch):
    from app.workers import tasks_shadow_document_memory as tasks
    run = Mock()
    monkeypatch.setattr(tasks, "_study_document", run)
    result = tasks.shadow_study_rag_document.run({"source_id": str(uuid4())}, str(uuid4()))
    assert result["status"] == "disabled"
    run.assert_not_called()


def test_compatibility_task_indexes_native_corpus_and_legacy_is_disabled(monkeypatch):
    from app.workers import tasks_shadow_document_memory as tasks
    from app.workers import tasks_hipporag_document as native
    run = Mock(return_value={"status": "indexed"})
    monkeypatch.setattr(native.index_hipporag_document, "run", run)
    tasks.hipporag_study_rag_document.run({}, "tenant")
    run.assert_called_once_with({}, "tenant", None)
    assert tasks.shadow_study_rag_document.run({}, "tenant", "manual")["status"] == "disabled"
    assert tasks.study_shadow_document_sections.run("snapshot", "tenant")["status"] == "disabled"
    assert tasks.finalize_shadow_document_study.run("snapshot", "tenant")["status"] == "disabled"


def test_native_projection_schema_requires_canonical_rule_content():
    from app.runtime.memory.hipporag_document_study import HippoStudyOutput
    with pytest.raises(ValidationError):
        HippoStudyOutput.model_validate({"items": [{"candidate_type": "rule", "subject": "Backup"}]})
    valid = HippoStudyOutput.model_validate({"items": [{"candidate_type": "rule", "subject": "Backup",
        "content": {"statement": "Create backup", "effect": "require", "conditions": ["before server replacement"]}}]})
    assert valid.items[0].content.conditions == ["before server replacement"]


@pytest.mark.asyncio
@pytest.mark.parametrize("allowed,member,status", [(False, True, 403), (True, False, 404)])
async def test_manual_action_checks_permission_and_exact_document_membership(monkeypatch, allowed, member, status):
    from app.api.v1.routers.collections import documents
    from app.runtime.memory import read_policy
    from app.workers import tasks_shadow_document_memory as tasks
    collection_id, document_id = uuid4(), uuid4()
    monkeypatch.setattr(documents, "_resolve_collection", AsyncMock(return_value=NS(tenant_id=uuid4())))
    monkeypatch.setattr(read_policy, "allowed_source_collections", AsyncMock(return_value=[collection_id] if allowed else []))
    monkeypatch.setattr(documents, "_resolve_document_membership", AsyncMock(return_value=NS(in_collection=member)))
    dispatch = Mock()
    monkeypatch.setattr(tasks.shadow_study_rag_document, "delay", dispatch)
    with pytest.raises(HTTPException) as error:
        await documents.extract_legacy_document_memory(collection_id, document_id, AsyncMock(), NS(id=str(uuid4())))
    assert error.value.status_code == status
    dispatch.assert_not_called()
