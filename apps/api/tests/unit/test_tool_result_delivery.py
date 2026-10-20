import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.agents.context import ToolCall, ToolContext, ToolResult
from app.agents.runtime import agent as agent_module
from app.agents.runtime.agent import AgentLoopState, AgentToolRuntime
from app.agents.runtime.policy import PolicyLimits
from app.agents.runtime.tools import OperationExecutionFacade


@pytest.mark.asyncio
@pytest.mark.parametrize('operation', ['memory.search', 'collection.list_documents'])
async def test_direct_result_bypasses_store_and_reaches_model_and_trace(monkeypatch, operation):
    payload = ({'groups': [{'scope_slug': 'company', 'success': True, 'items': [{'text': 'я' * 8000}]}]}
               if operation == 'memory.search' else {'documents': [{'text': 'я' * 8000}], 'count': 1})
    result = ToolResult.ok(payload, delivery='direct')
    store = Mock(save=AsyncMock(side_effect=AssertionError('Direct responses must not be stored')))
    monkeypatch.setattr(agent_module, 'ToolResultStore', lambda: store)
    runtime = AgentToolRuntime(Mock())
    runtime.tools.execute = AsyncMock(return_value=(result, []))
    runtime.tools._find_operation = Mock(side_effect=AssertionError('Direct responses need no storage resolution'))
    ctx = ToolContext(user_id=uuid4(), tenant_id=uuid4(), extra={'runtime_root_run_id': str(uuid4())})
    session = SimpleNamespace(run_id=uuid4(), record_event=AsyncMock(), finish=AsyncMock())
    outputs, messages = [], []
    events = [event async for event in runtime._execute_single_operation_call(
        operation_call=ToolCall(id='call', tool_name=operation, arguments={}),
        agent_slug='secretary', agent_execution_id='execution', llm_call_id='llm',
        ctx=ctx, available_operations=[], policy=PolicyLimits(), run_session=session,
        all_operation_outputs=outputs, all_sources=[], loop_state=AgentLoopState(),
        operation_results_for_context=messages, operation_calls_total_ref=[0],
        remaining_wall_time_ms=60000,
    )]
    store.save.assert_not_awaited()
    assert outputs[0]['success']
    assert outputs[0]['data'] == payload
    if operation == 'memory.search':
        receipt = json.loads(messages[0][1])
        assert receipt['evidence_call_id'] == 'call' and receipt['memory_updated']
        assert 'я' * 8000 not in messages[0][1]
        assert 'я' * 8000 in str(ctx.extra['task_memory_context'])
    else:
        assert json.loads(messages[0][1]) == {**payload, 'evidence_call_id': 'call'}
    trace = next(call.args[1] for call in session.record_event.await_args_list if call.args[0] == 'tool_result')
    assert trace['data'] == payload
    assert 'result_id' not in trace['data']
    tool_event = next(event for event in events if event.type.value == 'tool_result')
    assert tool_event.data['data'] == payload


def test_direct_context_is_complete_json_even_above_workspace_and_preview_limits():
    payload = {'items': [{'text': 'я' * 8000}], 'count': 1}
    rendered = OperationExecutionFacade.format_result_for_context(
        ToolResult.ok(payload, delivery='direct'), evidence_call_id='memory-call')
    assert json.loads(rendered) == {**payload, 'evidence_call_id': 'memory-call'}


@pytest.mark.asyncio
async def test_api_collection_result_keeps_source_normalization_and_storage(monkeypatch):
    from app.services.result_workspace import ResultWorkspace
    payload = {'value': [{'name': 'switch'}], 'meta': {'complete': True}}
    descriptor = {'result_id': str(uuid4()), 'sql_ref': 'result_test', 'inline_complete': False,
                  'row_count': 1, 'observed_schema': {}, 'source_complete': True}
    save = AsyncMock(return_value=(descriptor, payload))
    monkeypatch.setattr(ResultWorkspace, 'save_source', save)
    runtime = AgentToolRuntime(Mock())
    runtime.tools.execute = AsyncMock(return_value=(ToolResult.ok(payload), []))
    runtime.tools._find_operation = Mock(return_value=(SimpleNamespace(
        source='mcp', raw_tool_slug='get_objects', target=SimpleNamespace(mcp_tool_name='get_objects')), None))
    session = SimpleNamespace(run_id=uuid4(), record_event=AsyncMock(), finish=AsyncMock())
    messages = []
    events = [event async for event in runtime._execute_single_operation_call(
        operation_call=ToolCall(id='api-call', tool_name='collection.get_objects', arguments={}),
        agent_slug='reader', agent_execution_id='execution', llm_call_id='llm',
        ctx=ToolContext(user_id=uuid4(), tenant_id=uuid4(), extra={'runtime_root_run_id': str(uuid4())}),
        available_operations=[], policy=PolicyLimits(), run_session=session,
        all_operation_outputs=[], all_sources=[], loop_state=AgentLoopState(),
        operation_results_for_context=messages, operation_calls_total_ref=[0], remaining_wall_time_ms=60000,
    )]
    save.assert_awaited_once()
    assert save.await_args.kwargs['source_tool'] == 'get_objects'
    assert json.loads(messages[0][1])['_runtime_result']['delivery'] == 'stored'
    assert events[-1].data['data']['result_id'] == descriptor['result_id']


def test_duplicate_direct_result_keeps_delivery_mode():
    from app.agents.runtime.tool_reuse_policy import ToolCallReusePolicy
    from app.runtime.turn_state import RuntimeTurnState
    state = RuntimeTurnState(run_id=uuid4())
    state.record_tool_call(tool='memory.search', call_id='first', arguments={'query': 'backup'},
                           agent_slug='secretary', phase_id='task')
    state.record_tool_result(call_id='first', success=True, data={'items': [{'text': 'Backup'}]},
                             result_delivery='direct')
    result, _ = ToolCallReusePolicy().maybe_reuse(operation_slug='memory.search', arguments={'query': 'backup'},
        ctx=ToolContext(user_id=uuid4(), tenant_id=uuid4(),
                        extra={'runtime_tool_ledger': state.tool_ledger, 'runtime_task_id': 'task'}))
    assert result.delivery == 'direct'
    assert result.data == {'items': [{'text': 'Backup'}]}
    assert 'stored_result' not in result.metadata


@pytest.mark.asyncio
async def test_document_listing_declares_direct_delivery(monkeypatch):
    from app.agents.builtins import collection_document_list as module
    tenant = uuid4()
    session = AsyncMock()
    session.__aenter__.return_value = session
    session.execute.side_effect = [Mock(scalar=Mock(return_value=0)), Mock(all=Mock(return_value=[]))]
    monkeypatch.setattr(module, 'get_session_factory', lambda: lambda: session)
    collection = SimpleNamespace(id=uuid4(), tenant_id=tenant, slug='reglament',
                                 collection_type='document', table_name=None, fields=[])
    monkeypatch.setattr(module, 'CollectionService', lambda _: SimpleNamespace(get_by_slug=AsyncMock(return_value=collection)))
    tool = next(cls for cls in vars(module).values() if isinstance(cls, type)
                and getattr(cls, 'tool_slug', None) == 'collection.list_documents')()
    result = await tool.v1_0_0(ToolContext(user_id=uuid4(), tenant_id=tenant, chat_id=uuid4()),
                              {'collection_slug': 'reglament', 'query': 'сетевые работы'})
    assert result.success
    assert result.delivery == 'direct'
    assert result.data == {'documents': [], 'total': 0, 'collection': 'reglament'}


@pytest.mark.asyncio
async def test_document_listing_commits_returned_file_references(monkeypatch):
    from app.agents.builtins import collection_document_list as module
    tenant, document_id, membership_id, reference_id = uuid4(), uuid4(), uuid4(), uuid4()
    session = AsyncMock()
    session.__aenter__.return_value = session
    doc = SimpleNamespace(id=document_id, filename='regulation.md', title='Regulation', status='ready',
                          size_bytes=10, size=10, content_type='text/markdown', created_at=None)
    session.execute.side_effect = [Mock(scalar=Mock(return_value=1)), Mock(all=Mock(return_value=[(doc, {})])),
        Mock(all=Mock(return_value=[SimpleNamespace(source_id=document_id, id=membership_id, collection_row_id=None)]))]
    monkeypatch.setattr(module, 'get_session_factory', lambda: lambda: session)
    collection = SimpleNamespace(id=uuid4(), tenant_id=tenant, slug='reglament', collection_type='document', table_name=None, fields=[])
    monkeypatch.setattr(module, 'CollectionService', lambda _: SimpleNamespace(get_by_slug=AsyncMock(return_value=collection)))
    register = AsyncMock(return_value=SimpleNamespace(id=reference_id))
    reference_service = Mock(return_value=SimpleNamespace(register=register))
    reference_service.manifest.return_value = {'artifact_id': str(reference_id)}
    monkeypatch.setattr(module, 'ChatArtifactReferenceService', reference_service)
    tool = next(cls for cls in vars(module).values() if isinstance(cls, type) and getattr(cls, 'tool_slug', None) == 'collection.list_documents')()
    result = await tool.v1_0_0(ToolContext(user_id=uuid4(), tenant_id=tenant, chat_id=uuid4()), {'collection_slug': 'reglament'})
    assert result.success
    assert result.data['documents'][0]['artifact_id'] == str(reference_id)
    register.assert_awaited_once()
    session.commit.assert_awaited_once()
