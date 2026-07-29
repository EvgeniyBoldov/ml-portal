from __future__ import annotations

from typing import Any, Dict, Optional

from app.models.system_llm_role import SystemLLMRoleType


ExamplesV2 = Dict[str, Any]


def _planner_examples() -> ExamplesV2:
    return {
        "input": {
            "goal": "Понять, какие источники данных доступны для вопроса пользователя",
            "trigger": "initial",
            "plan": {"revision": 0, "tasks": {}, "outputs": {}},
            "available_agents": [
                {"slug": "other_answer", "description": "Отвечает на общие и non-domain вопросы без доступа к доменным системам"},
                {"slug": "viewer", "description": "Отвечает по структуре и метаданным источников"},
                {"slug": "netbox", "description": "Работает с API инвентаря инфраструктуры"},
            ],
            "completed_outputs": {},
            "needs": [],
        },
        "outputs": {
            "apply_graph": {"action": "apply_graph", "tasks": [{"task_id": "discover", "executor": "viewer", "intent": "Собрать источники", "instructions": "Собрать доступные источники"}]},
            "ask_user": {"action": "ask_user", "question": "Уточните фокус запроса."},
            "complete": {"action": "complete", "answer_brief": "Данных достаточно."},
            "fail": {"action": "fail", "failure_reason": "Нет подходящего агента."},
        },
    }


def _triage_examples() -> ExamplesV2:
    return {
        "input": {
            "user_message": "Какие у нас есть источники данных?",
            "conversation_summary": "Начало диалога.",
            "available_agents": [{"slug": "viewer"}],
            "session_state": {},
            "policies": "Не раскрывать секреты.",
        },
        "outputs": {
            "final": {
                "type": "final",
                "confidence": 0.89,
                "reason": "Вопрос можно закрыть сразу справочным ответом.",
                "answer": "Доступны документные и API-источники данных.",
            },
            "clarify": {
                "type": "clarify",
                "confidence": 0.64,
                "reason": "Нужно уточнить фокус запроса.",
                "clarify_prompt": "Уточните, по каким именно доменам нужны источники?",
            },
            "orchestrate": {
                "type": "orchestrate",
                "confidence": 0.81,
                "reason": "Нужно вызвать профильного агента для точного ответа.",
                "goal": "Собрать актуальный список источников и их назначение.",
                "agent_hint": "viewer",
            },
            "resume": {
                "type": "resume",
                "confidence": 0.76,
                "reason": "Нужно продолжить уже начатый ран.",
                "resume_run_id": "run-42",
            },
        },
    }


def _fact_extractor_examples() -> ExamplesV2:
    return {
        "input": {
            "user_message": "Покажи какие данные есть по коллекции регламентов.",
            "agent_results": [
                {"agent": "viewer", "summary": "Нашел коллекцию reglament, 7 записей.", "success": True},
            ],
            "known_facts": [{"subject": "collection_slug", "value": "reglament"}],
        },
        "outputs": {
            "default": {
                "facts": [
                    {"scope": "chat", "subject": "requested_collection", "value": "reglament", "confidence": 0.95},
                    {"scope": "chat", "subject": "collection_rows", "value": "7", "confidence": 0.88},
                    {"scope": "user", "subject": "intent", "value": "inspect_data_sources", "confidence": 0.84},
                ],
            },
        },
    }


def _summary_compactor_examples() -> ExamplesV2:
    return {
        "input": {
            "previous": {
                "goals": ["Ответить про источники данных"],
                "done": [],
                "entities": {"collection": "reglament"},
                "open_questions": [],
                "last_updated_turn": 3,
            },
            "turn_delta": {
                "user_message": "Покажи структуру коллекции регламентов.",
                "assistant_final": "Коллекция reglament содержит служебные и специфические поля.",
                "agent_results": [{"agent": "viewer", "summary": "Вернул схему полей", "success": True}],
            },
            "turn_number": 4,
        },
        "outputs": {
            "default": {
                "goals": ["Показать структуру данных коллекции reglament"],
                "done": ["Определена целевая коллекция", "Получена схема полей"],
                "entities": {"collection_slug": "reglament", "collection_type": "document"},
                "open_questions": ["Нужно ли показать примеры запросов к коллекции?"],
            },
        },
    }


def _plain_text_examples() -> ExamplesV2:
    return {
        "input": {
            "goal": "Сформировать финальный ответ пользователю.",
            "conversation_summary": "Собраны факты по доступным источникам и их назначению.",
            "runtime_facts": ["Есть document коллекция reglament", "Есть API-источник netbox"],
        },
        "outputs": {
            "default": (
                "Доступны два типа источников данных: документные коллекции и API-интеграции. "
                "Коллекция reglament используется для регламентов работ, а netbox — для инвентаря инфраструктуры."
            ),
        },
    }


def get_role_examples(role: SystemLLMRoleType | str) -> Optional[ExamplesV2]:
    normalized = role.value if isinstance(role, SystemLLMRoleType) else str(role)
    role_type = SystemLLMRoleType(normalized)

    if role_type == SystemLLMRoleType.PLANNER:
        return _planner_examples()
    if role_type == SystemLLMRoleType.TRIAGE:
        return _triage_examples()
    if role_type == SystemLLMRoleType.FACT_EXTRACTOR:
        return _fact_extractor_examples()
    if role_type == SystemLLMRoleType.SUMMARY_COMPACTOR:
        return _summary_compactor_examples()
    if role_type in (SystemLLMRoleType.SYNTHESIZER, SystemLLMRoleType.SUMMARY, SystemLLMRoleType.MEMORY):
        return _plain_text_examples()
    return None
