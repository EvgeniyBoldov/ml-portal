from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.runtime.input_builders import PlannerInputBuilder
from app.runtime.budgets import BudgetExceededError, BudgetRegistry, EntityLimits, RunLimits
from app.runtime.llm.structured import StructuredLLMCall
from app.runtime.orchestrator_contracts import PlanRequest, PlannerContext
from app.runtime.turn_preflight import TurnPreflight, TurnPreflightDecision
from app.services.runtime_limits_service import ModelCallLimits


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
async def test_preflight_handoff_reaches_planner_payload_with_only_selected_materials(monkeypatch) -> None:
    """Exercise the assembled request and the planner's final LLM payload."""
    from app.runtime.memory.role_tools import RoleMemoryTools
    from app.runtime.orchestrator import GraphOrchestrator
    from app.runtime.planner.graph_planner import GraphPlanner
    from app.runtime.run_context import RunContext

    run_id, plan_id = uuid4(), uuid4()
    run_context = RunContext(
        original_request="Проверь статус этого сервера по переписке и источнику",
        goal="Проверить статус сервера alpha",
        recent_dialogue=[
            {"message_id": "selected-message", "role": "user", "content": "сервер alpha", "truncated": False},
            {"message_id": "unselected-message", "role": "assistant", "content": "Старый ответ", "truncated": False},
        ],
    )
    selected_file = run_context.add_evidence(
        "file.read", {"artifact_id": "file-1"}, {"success": True, "content": "STATUS=healthy"},
    )
    unselected_file = run_context.add_evidence(
        "file.read", {"artifact_id": "file-2"}, {"success": True, "content": "PRIVATE_UNSELECTED_CONTENT"},
    )
    history = run_context.add_evidence("chat.history.read", {}, {"messages": [
        {"message_id": "selected-message", "role": "user", "content": "сервер alpha", "truncated": False},
    ]})
    memory_search = run_context.add_evidence("memory.search", {"query": "status"}, {"groups": [
        {"scope_slug": "project.alpha", "items": [{"text": "alpha memory"}]},
        {"scope_slug": "project.beta", "items": [{"text": "beta memory"}]},
    ]})
    run_context.task_brief = {
        "goal": "Проверить статус сервера alpha",
        "project_hints": ["alpha"],
        "direction": "Проверить актуальный источник",
        "expected_result": "Подтверждённый статус",
        "constraints": ["Не опираться на старые ответы"],
        "evidence_refs": [selected_file, history, memory_search],
        "message_refs": ["selected-message"],
    }
    runtime_state = SimpleNamespace(
        run_context=run_context,
        attachment_contexts=[],
        deleted_artifact_ids=[],
    )
    ctx = SimpleNamespace(extra={"runtime_turn_state": runtime_state})

    orchestrator = object.__new__(GraphOrchestrator)
    orchestrator.store = SimpleNamespace(snapshot=AsyncMock(return_value={
        "root_run_id": str(run_id), "tasks": {}, "memory_context": [],
        "scope_context": {"keys": ["project.alpha"], "revision": 4},
    }))
    monkeypatch.setattr(
        "app.runtime.datastore_context.load_result_catalog",
        AsyncMock(return_value=([], "available")),
    )
    request = await orchestrator._planner_request(
        plan_id=plan_id,
        goal=run_context.goal,
        trigger="initial",
        available_agents=[],
        available_artifacts=[],
        planner_kwargs={"runtime_state": runtime_state, "ctx": ctx},
    )

    assert request.context.goal == run_context.goal
    assert request.context.scope_context == {"keys": ["project.alpha"], "revision": 4}
    assert request.context.task_brief["constraints"] == ["Не опираться на старые ответы"]
    assert unselected_file not in request.context.task_brief["evidence_refs"]

    planner = object.__new__(GraphPlanner)
    planner._session = object()
    planner._input_builder = PlannerInputBuilder()
    planner._llm = SimpleNamespace(
        role_service=SimpleNamespace(get_role_config=AsyncMock(return_value={})),
        _compile_role_prompt=Mock(return_value="planner prompt"),
        invoke=AsyncMock(return_value=SimpleNamespace(
            value=SimpleNamespace(
                kind="proposal", proposal=object(),
                to_runtime_proposal=lambda *, goal: {"goal": goal},
            ),
        )),
    )
    monkeypatch.setattr(RoleMemoryTools, "descriptors", AsyncMock(return_value=[]))

    result = await planner.plan(request=request, ctx=ctx, planner_iteration_trace_id="iteration-1")

    assert result == {"goal": run_context.goal}
    payload = planner._llm.invoke.await_args.kwargs["payload"]
    assert payload["goal"] == run_context.goal
    assert payload["scope_context"] == {"keys": ["project.alpha"], "revision": 4}
    assert payload["task_brief"]["constraints"] == ["Не опираться на старые ответы"]
    assert payload["run_context"]["original_request"] == run_context.original_request
    assert [item["tool"] for item in payload["run_context"]["evidence"]] == ["file.read", "memory.search"]
    assert payload["run_context"]["evidence"][0]["id"] == selected_file
    memory_groups = payload["run_context"]["evidence"][1]["data"]["groups"]
    assert [item["scope_slug"] for item in memory_groups] == ["project.alpha"]
    assert [item["message_id"] for item in payload["run_context"]["conversation_materials"]] == ["selected-message"]
    assert "PRIVATE_UNSELECTED_CONTENT" not in str(payload)
    assert "Старый ответ" not in str(payload)


@pytest.mark.asyncio
async def test_preflight_does_not_replay_file_content_from_resume_checkpoint(monkeypatch) -> None:
    from app.runtime.interaction import InteractionQuestion, InteractionRequester, RuntimeInteraction
    from app.runtime.memory.role_tools import RoleMemoryTools

    preflight = TurnPreflight(session=object(), llm_client=AsyncMock())
    preflight._llm.invoke = AsyncMock(return_value=SimpleNamespace(value=TurnPreflightDecision.model_validate({
        "route": "planner", "task_brief": {
            "goal": "Проверь файл", "direction": "Проверить источник", "expected_result": "Отчёт",
        },
    })))
    interaction = RuntimeInteraction.create(
        InteractionQuestion(question="Какой формат?"),
        InteractionRequester(stage="turn_preflight", entity_id="preflight"),
        checkpoint={"memory_tool_results": [{
            "tool": "file.read", "arguments": {"artifact_id": "revoked"},
            "result": {"success": True, "content": "секретное содержимое"},
        }, {
            "tool": "memory.search", "arguments": {"query": "keep"},
            "result": {"success": True, "items": []},
        }]},
    )
    monkeypatch.setattr(RoleMemoryTools, "descriptors", AsyncMock(return_value=[]))
    await preflight.decide(
        user_request="Проверь файл", mechanical_lookup={},
        continuation={"paused_context": {"interaction": interaction.model_dump(mode="json")}},
    )
    results = preflight._llm.invoke.await_args.kwargs["payload"]["memory_tool_results"]
    assert [item["tool"] for item in results] == ["memory.search"]


@pytest.mark.asyncio
async def test_preflight_llm_call_limit_stops_followup_decision(monkeypatch) -> None:
    from app.runtime.memory.role_tools import RoleMemoryTools

    client = AsyncMock()
    client.chat = AsyncMock(return_value={"choices": [{"message": {"content": (
        '{"route":"tool_call","tool_call":{"tool":"memory.search","arguments":{"query":"test"}}}'
    )}}]})
    preflight = TurnPreflight(session=AsyncMock(), llm_client=client)
    preflight._llm.role_service.get_role_config = AsyncMock(return_value={
        "role_type": "turn_preflight", "model": "test-model", "identity": "test",
    })
    preflight._llm.limits_service.resolve_model = AsyncMock(return_value=ModelCallLimits(
        request_timeout_s=1, max_retries=0,
    ))
    monkeypatch.setattr(RoleMemoryTools, "descriptors", AsyncMock(return_value=[{
        "tool": "memory.search", "description": "search", "input_schema": {},
    }]))
    monkeypatch.setattr(RoleMemoryTools, "execute", AsyncMock(return_value={"success": True, "items": []}))
    registry = BudgetRegistry(run_limits=RunLimits())
    registry.register(entity_type="orchestrator", entity_id="preflight", parent_entity_id="run",
                      role="turn_preflight", limits=EntityLimits(llm_calls=1))

    with pytest.raises(BudgetExceededError, match="llm_calls"):
        await preflight.decide(
            user_request="Найди данные", mechanical_lookup={},
            budget_registry=registry, budget_entity_id="preflight",
        )

    assert client.chat.await_count == 1
    assert registry.get("preflight").own["llm_calls"] == 1


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
    event_sink = AsyncMock()
    await preflight.decide(
        user_request="Какие тикеты на моём проекте?", mechanical_lookup={}, facts_context=facts,
        event_sink=event_sink, trace_parent_entity_id="preflight-1",
    )

    assert preflight._llm.invoke.await_args.kwargs["payload"]["facts_context"] == facts
    snapshot = event_sink.await_args.args[0]
    assert snapshot.data["stage"] == "memory_context_used"
    assert snapshot.data["entity_type"] == "orchestrator"
    assert snapshot.data["entity_id"] == "preflight-1"
    assert snapshot.data["memory_context"][0] == facts[0]



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
async def test_preflight_routes_glossary_write_to_document_study() -> None:
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
        }),
    ))

    result = await preflight.decide(
        user_request="Добавь термин АВР в глоссарий", mechanical_lookup={},
    )

    assert result.route == "synthesis"
    assert result.synthesis_brief is not None
    assert result.memory_candidates == []
    assert "документ" in result.synthesis_brief.answer_draft.lower()


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


@pytest.mark.asyncio
async def test_invalid_user_memory_scope_hands_original_request_to_planner(monkeypatch) -> None:
    from app.runtime import turn_preflight

    preflight = TurnPreflight(session=object(), llm_client=AsyncMock())
    preflight._llm.invoke = AsyncMock(return_value=SimpleNamespace(
        value=TurnPreflightDecision.model_validate({
            "route": "planner", "scope_selection": {"keys": ["user"]},
            "task_brief": {
                "goal": "покажи задачи в проекте NIMS которые на мне", "project_hints": ["NIMS"],
                "scope_keys": ["user"], "direction": "Найти мои задачи", "expected_result": "Список задач",
            },
        }),
    ))
    monkeypatch.setattr(turn_preflight, "resolve_memory_scopes", AsyncMock(side_effect=ValueError("Unknown memory scope: user")))
    result = await preflight.decide(
        user_request="покажи задачи в проекте NIMS которые на мне", mechanical_lookup={},
        project_context={"effective_scope_keys": ["team.ops"]},
    )
    assert result.route == "planner"
    assert result.clarification is None
    assert result.task_brief.project_hints == ["NIMS"]
    assert result.task_brief.scope_keys == []
    assert result.scope_selection.keys == []
    assert result.scope_selection.mode == "inherit"


@pytest.mark.asyncio
async def test_unjustified_preflight_clarification_is_deferred_to_planner() -> None:
    preflight = TurnPreflight(session=object(), llm_client=AsyncMock())
    preflight._llm.invoke = AsyncMock(return_value=SimpleNamespace(
        value=TurnPreflightDecision.model_validate({
            "route": "clarify", "clarification": {"question": "Какой скоуп?"},
        }),
    ))
    result = await preflight.decide(user_request="Проверь статус проекта NIMS", mechanical_lookup={})
    assert result.route == "planner"
    assert result.task_brief.goal == "Проверь статус проекта NIMS"
    assert "Какой скоуп?" in " ".join(result.task_brief.constraints)


@pytest.mark.asyncio
async def test_direct_answer_clarification_can_remain_in_preflight() -> None:
    preflight = TurnPreflight(session=object(), llm_client=AsyncMock())
    preflight._llm.invoke = AsyncMock(return_value=SimpleNamespace(
        value=TurnPreflightDecision.model_validate({
            "route": "clarify", "clarification": {
                "question": "Какой из двух текстов сократить?",
                "direct_answer_reason": "Оба текста уже во входе; после выбора нужно только сократить текст без поиска и действий.",
            },
        }),
    ))
    result = await preflight.decide(user_request="Сократи этот текст", mechanical_lookup={})
    assert result.route == "clarify"
