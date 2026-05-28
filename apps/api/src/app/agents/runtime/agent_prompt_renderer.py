"""AgentPromptRenderer - render base agent prompts and synthesis prompts."""
from __future__ import annotations

from typing import Any, Dict, Optional, TYPE_CHECKING

from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.agents.execution_preflight import ExecutionRequest

logger = get_logger(__name__)

_AGENT_VERSION_PROMPT_FIELDS = (
    "identity",
    "mission",
    "scope",
    "rules",
    "tool_use_rules",
    "output_format",
    "examples",
)


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


class AgentPromptRenderer:
    @staticmethod
    def _compile_prompt_from_parts(parts: Dict[str, Any]) -> str:
        sections = []
        labels = {
            "identity": "Identity",
            "mission": "Mission",
            "scope": "Scope",
            "rules": "Rules",
            "tool_use_rules": "Tool Use Rules",
            "output_format": "Output Format",
            "examples": "Examples",
        }
        for key, label in labels.items():
            value = parts.get(key)
            if value:
                sections.append(f"# {label}\n{value}")
        return "\n\n".join(sections)

    @staticmethod
    def render_base_prompt(
        exec_request: ExecutionRequest,
        system_prompt_override: Optional[str] = None,
        sandbox_overrides: Optional[Dict[str, Any]] = None,
    ) -> str:
        if sandbox_overrides and getattr(exec_request, "agent_version", None) is not None:
            av_id = str(getattr(exec_request.agent_version, "id", "") or "")
            av_overrides_map = sandbox_overrides.get("agent_version_overrides") or {}
            av_overrides = av_overrides_map.get(av_id)
            if isinstance(av_overrides, dict):
                prompt_overrides = {
                    k: v for k, v in av_overrides.items() if k in _AGENT_VERSION_PROMPT_FIELDS
                }
                if prompt_overrides:
                    prompt_parts = {
                        field: getattr(exec_request.agent_version, field, None)
                        for field in _AGENT_VERSION_PROMPT_FIELDS
                    }
                    prompt_parts.update(prompt_overrides)
                    compiled = AgentPromptRenderer._compile_prompt_from_parts(prompt_parts)
                    if compiled:
                        logger.info(
                            "[AgentPromptRenderer] Using per-agent-version sandbox prompt override for %s",
                            av_id,
                        )
                        return compiled

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

