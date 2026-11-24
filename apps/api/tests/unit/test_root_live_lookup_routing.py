from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.runtime.pipeline import _policy_disposition
from app.runtime.root_route_policy import RootRoutePolicy
from app.runtime.turn_preflight import Clarification, TurnPreflight, TurnPreflightDecision


JQL_LOOKUP = 'найди задачи, которые соответствуют jql запросу: text ~ "192.0.2.4/25"'
COMBINED_LOOKUP = 'расскажи про адрес 192.0.2.4/25 из dcbox и в каких задачах из jira он встречается'


@pytest.mark.asyncio
@pytest.mark.parametrize(('request_text', 'rule_id', 'required_sources'), [
    (JQL_LOOKUP, 'live_jira_jql_lookup', ('Jira', 'JQL')),
    ('Выполни JQL:\n```jql\nproject = TEST AND text ~ "two  spaces"\n```',
     'live_jira_jql_lookup', ('Jira', 'JQL')),
    (COMBINED_LOOKUP, 'live_dcbox_jira_lookup', ('DCBox', 'Jira')),
    ('Покажи адрес 192.0.2.4 из DCBox и найди задачи по JQL: project = TEST',
     'live_dcbox_jira_lookup', ('DCBox', 'Jira')),
    ('Look up `192.0.2.4/25` in DCBox and find matching Jira issues.',
     'live_dcbox_jira_lookup', ('DCBox', 'Jira')),
])
async def test_explicit_live_lookup_reaches_planner_without_model(
    request_text: str, rule_id: str, required_sources: tuple[str, ...],
) -> None:
    recommendation = RootRoutePolicy.evaluate(request_text, [], recommendation_id='route-policy')
    preflight = TurnPreflight(session=object(), llm_client=AsyncMock())
    preflight._llm.invoke = AsyncMock()

    decision = await preflight.decide(
        user_request=request_text, mechanical_lookup={}, routing_recommendation=recommendation,
    )

    assert recommendation.rule_id == rule_id
    assert recommendation.source_agent_hint is None
    assert decision.route == 'planner'
    assert decision.task_brief is not None
    assert decision.task_brief.goal == request_text
    assert all(source in decision.task_brief.direction for source in required_sources)
    assert decision._proposed_route is None
    assert decision._reroute_reason == rule_id
    assert _policy_disposition(recommendation, decision.route) == 'accepted'
    preflight._llm.invoke.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(('request_text', 'effective_goal', 'continuation'), [
    ('Объясни JQL запрос: text ~ "192.0.2.4/25"', None, None),
    ('Покажи пример JQL запроса: text ~ "192.0.2.4/25"', None, None),
    ('Найди задачи из предыдущего ответа по JQL: project = TEST', None, None),
    ('Покажи задачи по JQL: project = TEST из старой выгрузки', None, None),
    ('Найди только в памяти задачи по JQL: project = TEST', None, None),
    ('Покажи, не выполняя запрос, задачи по JQL: project = TEST', None, None),
    ('Покажи фразу «найди задачи по JQL: project = TEST»', None, None),
    ('Покажи фразу:\n```\nнайди задачи по JQL: project = TEST\n```', None, None),
    (f'{COMBINED_LOOKUP}, без обращения к источникам', None, None),
    (f'«{JQL_LOOKUP}»', None, None),
    (f'> {COMBINED_LOOKUP}', None, None),
    ('Расскажи о процессе поиска адресов из DCBox и в задачах Jira.', None, None),
    ('Расскажи про адрес 192.0.2.4 из DCBox и объясни, как искать задачи в Jira.', None, None),
    ('Расскажи про адрес 192.0.2.4 из DCBox: «в каких задачах Jira он встречается»', None, None),
    ('А теперь выполни предыдущий JQL', None, None),
    ('И в Jira посмотри', COMBINED_LOOKUP, None),
    (JQL_LOOKUP, JQL_LOOKUP, {'mode': 'resume'}),
])
async def test_context_dependent_requests_still_use_model(
    request_text: str, effective_goal: str | None, continuation: dict[str, object] | None,
) -> None:
    recommendation = RootRoutePolicy.evaluate(
        request_text, [], recommendation_id='route-policy',
        effective_goal=effective_goal, continuation=continuation,
    )
    preflight = TurnPreflight(session=object(), llm_client=AsyncMock())
    preflight._llm.invoke = AsyncMock(return_value=SimpleNamespace(value=TurnPreflightDecision(
        route='clarify', clarification=Clarification(question='Какие данные нужны?', routing_reason='Проверить источник'),
    )))

    await preflight.decide(
        user_request=request_text, mechanical_lookup={}, routing_recommendation=recommendation,
        continuation=continuation,
    )

    preflight._llm.invoke.assert_awaited_once()
