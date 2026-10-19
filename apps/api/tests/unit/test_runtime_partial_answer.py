import asyncio
import json
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.runtime.events import RuntimeEvent, RuntimeEventType
from app.runtime.partial_answer import limitation_message, partial_context, stream_partial_answer
from app.runtime.turn_state import RuntimeTurnState


def fixture():
    run = uuid4()
    state = RuntimeTurnState(run_id=run)
    plan = {'root_run_id': str(run), 'goal': 'Как провести сетевые работы?', 'iterations': [],
            'tasks': {}, 'memory_context': []}
    return state, plan


def test_partial_context_preserves_evidence_and_hides_internal_failures():
    state, plan = fixture()
    plan['last_failure'] = {'code': 'planner_checkpoint_failed', 'message': 'task must explain its scope selection'}
    plan['tasks'] = {
        'done': {'status': 'completed', 'result': {'outputs': {'rule': 'Согласовать окно работ'}, 'answer': 'Найдены требования'}},
        'blocked': {'status': 'failed', 'result': {'description': 'Traceback: secret internal exception',
                                                'limitation': {'code': 'missing_credentials', 'message': 'secret=bad'}}},
    }
    state.tool_ledger.register_call(operation='memory.search', call_id='memory', arguments={}, iteration=1, agent_slug='secretary', phase_id=None)
    state.tool_ledger.register_result(call_id='memory', success=True, data={'items': [{'text': 'Сделать резервную копию'}]}, result_delivery='direct')
    context = partial_context(plan=plan, state=state, failure_code='planner_checkpoint_failed')
    rendered = json.dumps(context, ensure_ascii=False)
    assert 'Согласовать окно работ' in rendered
    assert 'Сделать резервную копию' not in rendered
    assert context['memory_context'] == []
    assert 'учётные данные' in rendered
    assert 'Traceback' not in rendered
    assert 'scope selection' not in rendered
    assert 'secret=bad' not in rendered
    assert plan['iterations'] == []


@pytest.mark.parametrize('code,expected', [('iteration_limit_exceeded', 'лимит'),
    ('agent_wall_time_exceeded', 'времени'), ('operation_timeout', 'времени'),
    ('missing_credentials', 'учётные'), ('access_denied', 'прав доступа')])
def test_user_limitation_categories(code, expected):
    assert expected in limitation_message(code)


@pytest.mark.asyncio
async def test_synthesizer_uses_separate_budget_and_completed_evidence():
    state, plan = fixture()
    class Synth:
        async def stream(self, **kwargs):
            assert kwargs['budget_registry'] is not expired
            assert kwargs['synthesis_context']['execution_summary']['partial']
            kwargs['runtime_state'].final_answer = 'Частичный ответ'
            yield RuntimeEvent.final('Частичный ответ', run_id=str(state.run_id))
    expired = object()
    events = [event async for event in stream_partial_answer(synthesizer=Synth(), plan=plan,
        runtime_state=state, failure_code='iteration_limit_exceeded', planner_kwargs={'budget_registry': expired})]
    assert events[-1].type == RuntimeEventType.FINAL
    assert state.final_answer.startswith('Частичный ответ')
    assert 'лимит' in state.final_answer
    assert events[-1].data['content'] == state.final_answer
    assert state.final_error is None


@pytest.mark.asyncio
async def test_failed_finalizer_returns_safe_answer_without_partial_stream_or_error():
    state, plan = fixture()
    class Synth:
        async def stream(self, **kwargs):
            yield RuntimeEvent.delta('Internal traceback')
            raise RuntimeError('token=private exception')
    events = [event async for event in stream_partial_answer(synthesizer=Synth(), plan=plan,
        runtime_state=state, failure_code='operation_timeout', planner_kwargs={})]
    assert [event.type for event in events] == [RuntimeEventType.FINAL]
    assert 'времени' in state.final_answer
    assert 'private' not in state.final_answer


@pytest.mark.asyncio
async def test_cancellation_does_not_trigger_fallback():
    state, plan = fixture()
    class Synth:
        async def stream(self, **kwargs):
            raise asyncio.CancelledError()
            yield
    with pytest.raises(asyncio.CancelledError):
        _ = [event async for event in stream_partial_answer(synthesizer=Synth(), plan=plan,
            runtime_state=state, failure_code='planner_execution_failed', planner_kwargs={})]
    assert state.final_answer is None


@pytest.mark.asyncio
async def test_finalizer_has_bounded_timeout(monkeypatch):
    import app.runtime.partial_answer as module
    monkeypatch.setattr(module, 'get_settings', lambda: SimpleNamespace(RUNTIME_FINALIZATION_TIMEOUT_SECONDS=0.01))
    state, plan = fixture()
    class Synth:
        async def stream(self, **kwargs):
            await asyncio.sleep(1)
            yield RuntimeEvent.delta('late')
    events = [event async for event in stream_partial_answer(synthesizer=Synth(), plan=plan,
        runtime_state=state, failure_code='iteration_limit_exceeded', planner_kwargs={})]
    assert events[-1].type == RuntimeEventType.FINAL
    assert 'лимит' in state.final_answer


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['planner', 'iterations', 'tasks'])
async def test_planning_stage_finalizes_failed_execution_and_keeps_plan_diagnostics(failure):
    from app.agents.context import ToolContext
    from app.runtime.contracts import PipelineRequest
    from app.runtime.orchestrator import GraphOrchestrator
    from app.runtime.orchestrator_contracts import IterationProposal, PlannedTask, TerminalKind
    from app.runtime.stages.graph_planning_stage import GraphPlanningStage, GraphPlanningOutcomeKind
    from tests.unit.test_graph_orchestrator_iteration_grouping import AsyncMemoryStore, Executor
    class Store(AsyncMemoryStore):
        async def get_by_run(self, run):
            return SimpleNamespace(id=self.plan['id'], goal='goal', status='draft')
    class Planner:
        async def plan(self, **kwargs):
            if failure == 'planner':
                raise RuntimeError('planner internal traceback')
            tasks = [PlannedTask(task_id='work', executor='research', intent='inspect', instructions='inspect')]
            if failure == 'tasks':
                tasks.append(PlannedTask(task_id='second', executor='research', intent='inspect', instructions='inspect'))
            return IterationProposal(tasks=tasks, terminal=TerminalKind.PLANNER)
    class Synth:
        async def stream(self, **kwargs):
            assert kwargs['synthesis_context']['execution_summary']['partial']
            kwargs['runtime_state'].final_answer = 'Полезный частичный ответ'
            yield RuntimeEvent.final('Полезный частичный ответ', run_id=str(kwargs['run_id']))
    store = Store()
    state = RuntimeTurnState(run_id=UUID(store.plan['root_run_id']), goal='goal')
    orchestrator = GraphOrchestrator(store=store, planner=Planner(), executor=Executor(), synthesizer=Synth())
    stage = GraphPlanningStage(orchestrator=orchestrator, store=store, max_steps=1)
    user, tenant = uuid4(), uuid4()
    events = [event async for event in stage.run(runtime_state=state,
        request=PipelineRequest(request_text='goal', user_id=str(user), tenant_id=str(tenant)),
        ctx=ToolContext(user_id=user, tenant_id=tenant), user_id=user, tenant_id=tenant,
        available_agents=[{'slug': 'research'}], platform_config={},
        runtime_limits={'task_attempts': 1} if failure == 'tasks' else {})]
    assert stage.outcome.kind == GraphPlanningOutcomeKind.COMPLETED
    assert state.final_answer.startswith('Полезный частичный ответ')
    snapshot = await store.snapshot(store.plan['id'])
    assert snapshot['status'] == 'failed'
    assert snapshot['last_failure']
    assert snapshot['last_failure']['code'] == {
        'planner': 'initial_planning_failed', 'iterations': 'iteration_limit_exceeded',
        'tasks': 'task_execution_limit_exceeded',
    }[failure]
    assert any(event.event.type == RuntimeEventType.FINAL for event in events)
    assert not any(event.event.type == RuntimeEventType.ERROR for event in events)


@pytest.mark.asyncio
async def test_credentials_notice_survives_failed_synthesis():
    state, plan = fixture()
    state.execution_limitations.append({'code': 'missing_credentials', 'message': 'Missing credentials'})
    class Synth:
        async def stream(self, **kwargs):
            raise RuntimeError('internal provider failure')
            yield
    events = [event async for event in stream_partial_answer(synthesizer=Synth(), plan=plan,
        runtime_state=state, failure_code='planner_checkpoint_failed', planner_kwargs={})]
    assert 'учётные данные' in state.final_answer
    assert 'internal' not in state.final_answer
    assert events[-1].data['content'] == state.final_answer


@pytest.mark.asyncio
async def test_agent_preflight_keeps_missing_credentials_as_user_limitation():
    from unittest.mock import AsyncMock
    from app.agents.context import ToolContext
    from app.agents.contracts import MissingRequirements
    from app.agents.execution_preflight import ExecutionMode
    from app.runtime.agent_executor import AgentExecutor
    from app.runtime.orchestrator_contracts import TaskRequest
    state, _ = fixture()
    executor = AgentExecutor(session=AsyncMock(), llm_client=AsyncMock())
    executor._prepare_sub_agent_request = AsyncMock(return_value=SimpleNamespace(
        mode=ExecutionMode.UNAVAILABLE, missing_requirements=MissingRequirements(credentials=['source'])))
    user, tenant = uuid4(), uuid4()
    ctx = ToolContext(user_id=user, tenant_id=tenant)
    _ = [event async for event in executor.execute(
        task=TaskRequest(task_id='read', executor='secretary', intent='read', instructions='Read source'),
        runtime_state=state, messages=[], ctx=ctx, user_id=user, tenant_id=tenant)]
    assert state.execution_limitations[0]['code'] == 'missing_credentials'
    assert ctx.extra['agent_execution_result'].limitation.code == 'missing_credentials'
