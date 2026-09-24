from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.runtime.input_builders import PlannerInputBuilder
from app.runtime.orchestrator_contracts import PlanRequest, PlannerContext
from app.runtime.turn_preflight import TurnPreflight, TurnPreflightDecision


def test_planner_payload_preserves_full_preflight_task_brief() -> None:
    request = PlanRequest(context=PlannerContext(
        goal="Обновить glossary", trigger="initial", execution_ledger={},
        task_brief={
            "goal": "Обновить glossary", "project_hints": ["network"],
            "entity_hints": ["sphere"], "direction": "apply glossary update",
            "constraints": ["verify evidence"], "expected_result": "candidate recorded",
        },
    ))
    payload = PlannerInputBuilder().build_graph_request(request)
    assert payload["task_brief"]["project_hints"] == ["network"]
    assert payload["task_brief"]["constraints"] == ["verify evidence"]


@pytest.mark.asyncio
async def test_preflight_uses_shared_db_prompt_builder() -> None:
    preflight = TurnPreflight(session=object(), llm_client=AsyncMock())
    preflight._llm.invoke = AsyncMock(return_value=SimpleNamespace(
        value=TurnPreflightDecision.model_validate({
            "route": "clarify",
            "clarification": {"question": "Какой проект имеется в виду?"},
        }),
    ))

    await preflight.decide(
        user_request="Проверь статус",
        mechanical_lookup={},
    )

    kwargs = preflight._llm.invoke.await_args.kwargs
    assert "system_prompt" not in kwargs
    assert kwargs["schema"] is TurnPreflightDecision
    assert kwargs["payload"]["user_request"] == "Проверь статус"


@pytest.mark.asyncio
async def test_preflight_receives_confirmed_facts_as_raw_context() -> None:
    preflight = TurnPreflight(session=object(), llm_client=AsyncMock())
    preflight._llm.invoke = AsyncMock(return_value=SimpleNamespace(
        value=TurnPreflightDecision.model_validate({
            "route": "planner",
            "task_brief": {
                "goal": "Показать тикеты", "project_hints": ["ABC"],
                "direction": "read current Jira tickets", "expected_result": "Список тикетов",
            },
        }),
    ))

    facts = [{"scope": "user", "kind": "fact", "subject": "jira project", "value": "ABC", "confidence": 1.0}]
    await preflight.decide(
        user_request="Какие тикеты на моём проекте?", mechanical_lookup={}, facts_context=facts,
    )

    assert preflight._llm.invoke.await_args.kwargs["payload"]["facts_context"] == facts


@pytest.mark.asyncio
async def test_preflight_bounds_only_its_routing_copy_of_a_large_user_request() -> None:
    preflight = TurnPreflight(session=object(), llm_client=AsyncMock())
    preflight._llm.invoke = AsyncMock(return_value=SimpleNamespace(
        value=TurnPreflightDecision.model_validate({
            "route": "clarify",
            "clarification": {"question": "Какой ожидается результат?"},
        }),
    ))
    user_request = "начало " + ("данные " * 2_000) + "сохрани изменения в конце"

    await preflight.decide(user_request=user_request, mechanical_lookup={})

    routing_copy = preflight._llm.invoke.await_args.kwargs["payload"]["user_request"]
    assert len(routing_copy) < len(user_request)
    assert len(routing_copy) <= TurnPreflight._MAX_ROUTING_REQUEST_CHARS + 200
    assert routing_copy.startswith("начало ")
    assert routing_copy.endswith("сохрани изменения в конце")


@pytest.mark.asyncio
async def test_preflight_routes_explicit_fact_memory_write_to_synthesis() -> None:
    preflight = TurnPreflight(session=object(), llm_client=AsyncMock())
    preflight._llm.invoke = AsyncMock(return_value=SimpleNamespace(
        value=TurnPreflightDecision.model_validate({
            "route": "planner",
            "task_brief": {
                "goal": "Сохранить факт", "direction": "store_memory",
                "expected_result": "Факт сохранён",
            },
            "memory_candidates": [{
                "scope": "tenant", "kind": "fact", "subject": "НОП",
                "value": "национальная облачная платформа",
            }],
        }),
    ))

    result = await preflight.decide(
        user_request="НОП — национальная облачная платформа. Запомни как факт.",
        mechanical_lookup={},
    )

    assert result.route == "synthesis"
    assert result.synthesis_brief is not None
    assert result.memory_candidates[0].subject == "НОП"


@pytest.mark.asyncio
async def test_preflight_does_not_claim_glossary_write_before_writeback() -> None:
    preflight = TurnPreflight(session=object(), llm_client=AsyncMock())
    preflight._llm.invoke = AsyncMock(return_value=SimpleNamespace(
        value=TurnPreflightDecision.model_validate({
            "route": "synthesis",
            "synthesis_brief": {
                "synthesis_brief": {
                    "user_question": "Добавь термин в глоссарий",
                    "planned_work": "Добавить", "purpose": "Записать",
                    "answer_requirements": "Подтвердить успех",
                },
                "answer_draft": "Термин успешно добавлен в глоссарий.",
            },
            "memory_candidates": [{
                "scope": "tenant", "kind": "glossary", "subject": "АВР",
                "value": "Автоматический ввод резерва",
            }],
        }),
    ))

    result = await preflight.decide(
        user_request="Добавь термин АВР в глоссарий", mechanical_lookup={},
    )

    assert result.route == "synthesis"
    assert result.synthesis_brief is not None
    assert "успешно" not in result.synthesis_brief.answer_draft.lower()
    assert "провер" in result.synthesis_brief.answer_draft.lower()


@pytest.mark.asyncio
async def test_empty_mechanical_lookup_cannot_ground_collection_access_answer() -> None:
    preflight = TurnPreflight(session=object(), llm_client=AsyncMock())
    preflight._llm.invoke = AsyncMock(return_value=SimpleNamespace(
        value=TurnPreflightDecision.model_validate({
            "route": "synthesis",
            "synthesis_brief": {
                "synthesis_brief": {
                    "user_question": "посмотри доступные мне коллекции",
                    "planned_work": "Проверить коллекции",
                    "purpose": "Ответить",
                    "answer_requirements": "Кратко",
                },
                "answer_draft": "Доступных коллекций нет.",
            },
        }),
    ))

    result = await preflight.decide(
        user_request="посмотри доступные мне коллекции и скажи чем я могу оперировать",
        mechanical_lookup={"projects": [], "glossary": [], "entities": []},
    )

    assert result.route == "planner"
    assert result.task_brief is not None
    assert result.task_brief.goal == "посмотри доступные мне коллекции и скажи чем я могу оперировать"
    assert result.synthesis_brief is None


def test_collection_concept_question_does_not_require_inventory() -> None:
    assert not TurnPreflight._needs_collection_inventory("Что такое коллекция документов?")
    assert TurnPreflight._needs_collection_inventory("Which collections can I access?")
