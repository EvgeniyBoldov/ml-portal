import asyncio
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.agents.context import ToolContext
from app.agents.builtins import memory_search
from app.services.hipporag_service import HippoRAGService
from app.runtime.memory.search import MemorySearchService


@pytest.mark.asyncio
async def test_tool_preserves_one_group_per_chat_scope_including_empty_and_failed(monkeypatch):
    legacy = AsyncMock(side_effect=AssertionError('Legacy memory must not be queried'))
    monkeypatch.setattr(MemorySearchService, 'search', legacy)
    session = AsyncMock()
    session.__aenter__.return_value = session
    monkeypatch.setattr(memory_search, 'get_session_factory', lambda: lambda: session)
    native = AsyncMock(return_value={'backend': 'hipporag', 'groups': [
        {'scope_slug': 'company', 'status': 'completed', 'success': True, 'document_count': 1,
         'hits': [{'text': 'Prepare a backup before changes', 'score': 0.9,
                   'metadata': {'document_id': 'doc1', 'document_title': 'Regulation'}}]},
        {'scope_slug': 'dcbox', 'status': 'completed', 'success': True, 'hits': []},
        {'scope_slug': 'nims', 'status': 'failed', 'success': False, 'hits': [], 'error_code': 'memory_search_failed'},
    ]})
    monkeypatch.setattr(memory_search, 'HippoRAGService', lambda _: MagicMock(search_documents=native))
    ctx = ToolContext(tenant_id=uuid4(), user_id=uuid4(), extra={
        'memory_search_scope_keys': ['company', 'dcbox', 'nims'],
        'project_context': {'scope_context': {'keys': ['company']}},
    })
    result = await memory_search.MemorySearchTool().v1_0_0(ctx, {'query': 'backup'})
    assert result.success and result.delivery == 'direct'
    assert result.data['group_count'] == 3 and result.data['partial']
    groups = result.data['groups']
    assert [group['scope_slug'] for group in groups] == ['company', 'dcbox', 'nims']
    assert groups[0]['items'][0]['source_references'][0]['document_id'] == 'doc1'
    assert groups[1]['items'] == [] and groups[1]['success']
    assert groups[2]['items'] == [] and not groups[2]['success']
    assert 'items' not in result.data  # No combined, reranked or truncated wrapper.
    native.assert_awaited_once_with('backup', scope_keys=['company', 'dcbox', 'nims'], limit=8)
    legacy.assert_not_awaited()


@pytest.mark.asyncio
async def test_scope_queries_run_concurrently_and_keep_order_on_partial_failure():
    service = HippoRAGService(AsyncMock())
    service._models = AsyncMock(return_value={'test': True})
    entered = set()
    all_entered = asyncio.Event()

    async def call(operation, payload, **kwargs):
        entered.add(payload['scope_slug'])
        if len(entered) == 3:
            all_entered.set()
        await asyncio.wait_for(all_entered.wait(), timeout=1)
        if payload['scope_slug'] == 'dcbox':
            raise RuntimeError('private provider failure')
        return {'hits': [], 'document_count': 0}

    service._call = AsyncMock(side_effect=call)
    result = await service.search_documents('query', scope_keys=['company', 'dcbox', 'nims'], limit=3)
    assert [group['scope_slug'] for group in result['groups']] == ['company', 'dcbox', 'nims']
    assert [group['success'] for group in result['groups']] == [True, False, True]
    assert 'private provider failure' not in str(result)
    assert all(call.args[1]['top_k'] == 3 for call in service._call.await_args_list)
    service._models.assert_awaited_once()


@pytest.mark.asyncio
async def test_empty_scope_set_does_not_search_entire_corpus():
    service = HippoRAGService(AsyncMock())
    service._models = AsyncMock(side_effect=AssertionError('No scope means no search'))
    assert (await service.search_documents('query', scope_keys=[]))['groups'] == []
    service._models.assert_not_awaited()


@pytest.mark.asyncio
async def test_model_configuration_failure_still_returns_all_scope_groups():
    service = HippoRAGService(AsyncMock())
    service._models = AsyncMock(side_effect=ValueError('model unavailable'))
    result = await service.search_documents('query', scope_keys=['company', 'nims'])
    assert len(result['groups']) == 2
    assert all(not group['success'] for group in result['groups'])


def test_native_search_schema_does_not_let_model_choose_scopes():
    from app.runtime.memory.search_contract import HippoMemorySearchInput
    assert set(HippoMemorySearchInput.model_json_schema()['properties']) == {'query', 'limit'}
