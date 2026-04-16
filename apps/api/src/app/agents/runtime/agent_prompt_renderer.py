"""AgentPromptRenderer - render base agent prompts and synthesis prompts."""
from __future__ import annotations

from typing import Any, Dict, Optional, TYPE_CHECKING

from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.agents.execution_preflight import ExecutionRequest

logger = get_logger(__name__)


DEFAULT_AGENT_SYSTEM_PROMPT = (
    "Ты — полезный ассистент. Отвечай на языке пользователя. "
    "Будь точным, кратким и структурированным."
)

SYNTHESIS_INSTRUCTION = (
    "ВАЖНО: Используй ТОЛЬКО данные выше для ответа на исходный вопрос. "
    "Ссылайся на конкретные факты из данных. Если данные пустые или нерелевантные — "
    "скажи, что информация не найдена. Отвечай на языке вопроса пользователя. "
    "Не показывай служебные идентификаторы (UUID) — ссылайся на документы по названию."
)

SYNTHESIS_ASSISTANT_STUB = "Я получил следующие данные с помощью инструментов."

SYNTHESIS_USER_TEMPLATE = (
    "Вот данные, полученные из инструментов:\n\n"
    "{observation_text}\n\n"
    "{synthesis_instruction}"
)

PLANNER_SYNTHESIS_SYSTEM = (
    "Синтезируй финальный ответ из собранных фактов. "
    "Отвечай на языке пользователя. Будь структурированным и точным."
)

PLANNER_SYNTHESIS_USER_TEMPLATE = (
    "Собранные факты:\n{facts_text}\n\n"
    "Дай исчерпывающий ответ на основе этих фактов."
)


class AgentPromptRenderer:
    @staticmethod
    def render_base_prompt(
        exec_request: ExecutionRequest,
        system_prompt_override: Optional[str] = None,
        sandbox_overrides: Optional[Dict[str, Any]] = None,
    ) -> str:
        if sandbox_overrides:
            prompt_ov = sandbox_overrides.get("prompt")
            if prompt_ov:
                logger.info("[AgentPromptRenderer] Using sandbox prompt override")
                return prompt_ov

        if system_prompt_override:
            return system_prompt_override

        compiled = getattr(exec_request, "prompt", None)
        if compiled:
            return compiled

        return DEFAULT_AGENT_SYSTEM_PROMPT

    @staticmethod
    def build_synthesis_messages(
        agent_prompt: str,
        original_messages: list,
        observation_text: str,
    ) -> list:
        return [
            {"role": "system", "content": agent_prompt},
            *original_messages,
            {"role": "assistant", "content": SYNTHESIS_ASSISTANT_STUB},
            {
                "role": "user",
                "content": SYNTHESIS_USER_TEMPLATE.format(
                    observation_text=observation_text,
                    synthesis_instruction=SYNTHESIS_INSTRUCTION,
                ),
            },
        ]

    @staticmethod
    def build_planner_synthesis_messages(
        original_messages: list,
        facts_text: str,
    ) -> list:
        return [
            {"role": "system", "content": PLANNER_SYNTHESIS_SYSTEM},
            *original_messages,
            {
                "role": "user",
                "content": PLANNER_SYNTHESIS_USER_TEMPLATE.format(
                    facts_text=facts_text,
                ),
            },
        ]
