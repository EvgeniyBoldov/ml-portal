"""AgentPromptRenderer - render base agent prompts and synthesis prompts."""
from __future__ import annotations

import re
from typing import Any, Dict, Optional, TYPE_CHECKING

from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.agents.execution_preflight import ExecutionRequest

logger = get_logger(__name__)

_LOCAL_TABLE_PATTERN = re.compile(r"\bcoll_[0-9a-f]{8}_[a-z0-9_]+\b", re.IGNORECASE)
_HARDCODED_SQL_RULE_PATTERNS = (
    re.compile(r"(?im)^.*обязательно используй таблиц[ауы].*(?:\n|$)"),
    re.compile(r"(?im)^.*must use table.*(?:\n|$)"),
    re.compile(r"(?im)^.*поля таблицы:.*(?:\n|$)"),
    re.compile(r"(?im)^.*значения status:.*(?:\n|$)"),
    re.compile(r"(?im)^.*значения priority:.*(?:\n|$)"),
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

PLANNER_SYNTHESIS_SYSTEM = (
    "Синтезируй финальный ответ из собранных фактов. "
    "Отвечай на языке пользователя. Будь точным и лаконичным. "
    "ЗАПРЕЩЕНО: заголовки (##, ###), жирный текст (**bold**), "
    "блоки кода (```) для обычных текстовых данных. "
    "Используй список только при трёх и более пунктах."
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
            if _has_sql_runtime_collections(exec_request):
                return _compose_sql_runtime_prompt(compiled, exec_request)
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


def _has_sql_runtime_collections(exec_request: "ExecutionRequest") -> bool:
    for item in getattr(exec_request, "resolved_data_instances", []) or []:
        collection_type = str(getattr(item, "collection_type", "") or "").strip().lower()
        domain = str(getattr(item, "domain", "") or "").strip().lower()
        if collection_type == "sql" or domain == "collection.sql":
            return True
    return False


def _compose_sql_runtime_prompt(base_prompt: str, exec_request: "ExecutionRequest") -> str:
    sanitized = _LOCAL_TABLE_PATTERN.sub("runtime_discovered_table", base_prompt or "")
    for pattern in _HARDCODED_SQL_RULE_PATTERNS:
        sanitized = pattern.sub("", sanitized)
    sanitized = re.sub(r"\n{3,}", "\n\n", sanitized).strip()
    guidance = _build_sql_runtime_guidance(exec_request)
    if not guidance:
        return sanitized
    return f"{sanitized}\n\n{guidance}"


def _build_sql_runtime_guidance(exec_request: "ExecutionRequest") -> str:
    sql_collections: list[tuple[str, list[str]]] = []
    for item in getattr(exec_request, "resolved_data_instances", []) or []:
        collection_type = str(getattr(item, "collection_type", "") or "").strip().lower()
        domain = str(getattr(item, "domain", "") or "").strip().lower()
        if collection_type != "sql" and domain != "collection.sql":
            continue
        collection_slug = str(
            getattr(item, "collection_slug", None) or getattr(item, "slug", None) or "sql_collection"
        ).strip()
        tables = [str(v).strip() for v in (getattr(item, "remote_tables", None) or []) if str(v).strip()]
        sql_collections.append((collection_slug, tables))

    if not sql_collections:
        return ""

    lines = [
        "## SQL Runtime Override",
        "Use runtime-discovered SQL tables only. Ignore any static table names in earlier text.",
        "Before executing analytical SQL, verify actual table names via `collection.sql.search_objects` or `collection.sql.catalog_inspect`.",
        "Never assume `coll_*` names are present in remote DB.",
    ]
    for slug, tables in sql_collections:
        if tables:
            preview = ", ".join(f"`{name}`" for name in tables[:8])
            if len(tables) > 8:
                preview += f", +{len(tables) - 8} more"
            lines.append(f"- Collection `{slug}` discovered tables: {preview}")
        else:
            lines.append(f"- Collection `{slug}` discovered tables: unknown (run search_objects first)")
    return "\n".join(lines)

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
