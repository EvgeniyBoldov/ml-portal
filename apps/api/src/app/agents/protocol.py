"""
Tool-call protocol for model responses.

The runtime accepts only the canonical tool-first shape:

```tool_call
{
    "tool": "instance.docs.collection.document.search",
    "arguments": {
        "query": "как настроить nginx"
    }
}
```
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from app.agents.context import ToolCall
from app.agents.json_utils import extract_balanced_json
from app.agents.runtime.prompt_contract import (
    build_prompt_input_schema,
    build_prompt_operation_description,
)
from app.services.platform_settings_defaults import PLATFORM_OPERATION_RULES_TEXT

if TYPE_CHECKING:
    from app.agents.contracts import ResolvedOperation


TOOL_CALL_PATTERN = re.compile(r"```tool_call\s*\n(.*?)\n```", re.DOTALL)
TOOL_CALL_JSON_BLOCK = re.compile(
    r'```(?:json)?\s*\n(\{[^`]*?"tool"\s*:[^`]*?\})\s*\n```',
    re.DOTALL,
)

TOOL_RESULT_TEMPLATE = """```tool_result
{result}
```"""


def _extract_tool_name(data: Dict[str, Any]) -> Optional[str]:
    value = data.get("tool")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _find_tool_json_objects(content: str) -> List[str]:
    """Find JSON objects containing a `tool` key using balanced braces."""

    results: List[str] = []
    idx = 0
    while idx < len(content):
        brace = content.find("{", idx)
        if brace < 0:
            break
        candidate = extract_balanced_json(content, brace)
        if candidate:
            try:
                data = json.loads(candidate)
                if isinstance(data, dict) and _extract_tool_name(data):
                    results.append(candidate)
            except (json.JSONDecodeError, ValueError):
                pass
            idx = brace + len(candidate)
        else:
            idx = brace + 1
    return results


@dataclass
class ParsedResponse:
    """Parsed model response with extracted tool calls."""

    text: str
    tool_calls: List[ToolCall]
    has_tool_calls: bool

    @property
    def is_final(self) -> bool:
        return not self.has_tool_calls


def parse_llm_response(content: str, *, strict: bool = False) -> ParsedResponse:
    """Parse a text model response and extract canonical tool calls."""

    tool_calls: List[ToolCall] = []
    seen_tools: set[tuple[str, str]] = set()
    text = content

    matches = TOOL_CALL_PATTERN.findall(content)
    for match in matches:
        try:
            data = json.loads(match.strip())
            tool_name = _extract_tool_name(data)
            if not tool_name:
                continue
            args_json = json.dumps(data.get("arguments", {}), sort_keys=True)
            tool_key = (tool_name, args_json)
            if tool_key in seen_tools:
                continue
            tool_calls.append(ToolCall.from_dict(data))
            seen_tools.add(tool_key)
        except json.JSONDecodeError:
            continue
    if tool_calls:
        text = TOOL_CALL_PATTERN.sub("", text).strip()
        return ParsedResponse(text=text, tool_calls=tool_calls, has_tool_calls=True)

    matches = TOOL_CALL_JSON_BLOCK.findall(content)
    for match in matches:
        try:
            data = json.loads(match.strip())
            tool_name = _extract_tool_name(data)
            if not tool_name:
                continue
            args_json = json.dumps(data.get("arguments", {}), sort_keys=True)
            tool_key = (tool_name, args_json)
            if tool_key in seen_tools:
                continue
            tool_calls.append(ToolCall.from_dict(data))
            seen_tools.add(tool_key)
        except json.JSONDecodeError:
            continue
    if tool_calls:
        text = TOOL_CALL_JSON_BLOCK.sub("", text).strip()
        return ParsedResponse(text=text, tool_calls=tool_calls, has_tool_calls=True)

    if not strict:
        for js in _find_tool_json_objects(content):
            try:
                data = json.loads(js)
                tool_name = _extract_tool_name(data)
                if not tool_name:
                    continue
                args_json = json.dumps(data.get("arguments", {}), sort_keys=True)
                tool_key = (tool_name, args_json)
                if tool_key in seen_tools:
                    continue
                tool_calls.append(ToolCall.from_dict(data))
                seen_tools.add(tool_key)
                text = text.replace(js, "", 1)
            except (json.JSONDecodeError, KeyError):
                continue

    if tool_calls:
        text = text.strip()

    return ParsedResponse(
        text=text,
        tool_calls=tool_calls,
        has_tool_calls=len(tool_calls) > 0,
    )


def format_tool_result(tool_call: ToolCall, result_content: str) -> str:
    result_data = {
        "tool": tool_call.tool_name,
        "call_id": tool_call.id,
        "result": result_content,
    }
    return TOOL_RESULT_TEMPLATE.format(
        result=json.dumps(result_data, ensure_ascii=False, indent=2),
    )


def build_tools_prompt(
    tool_schemas: List[dict],
    *,
    mandatory_rules_text: Optional[str] = None,
    prompt_labels: Optional[Dict[str, Any]] = None,
    prompt_budgets: Optional[Dict[str, Any]] = None,
) -> str:
    """Build the model-facing tool contract block."""

    if not tool_schemas:
        return ""

    tools_json = json.dumps(tool_schemas, ensure_ascii=False, indent=2)
    labels = prompt_labels if isinstance(prompt_labels, dict) else {}
    budgets = prompt_budgets if isinstance(prompt_budgets, dict) else {}
    heading = _prompt_label(labels, "operations_heading", "Доступные инструменты")
    rules_heading = _prompt_label(labels, "mandatory_rules_heading", "ОБЯЗАТЕЛЬНЫЕ ПРАВИЛА")
    call_heading = _prompt_label(
        labels,
        "operation_call_heading",
        "Чтобы вызвать инструмент, ответь блоком tool_call:",
    )
    list_heading = _prompt_label(labels, "operation_list_heading", "Список инструментов:")

    rules_max_chars = _prompt_budget(budgets, "operations_rules_max_chars")
    if (
        rules_max_chars is not None
        and isinstance(mandatory_rules_text, str)
        and len(mandatory_rules_text) > rules_max_chars
    ):
        mandatory_rules_text = mandatory_rules_text[:rules_max_chars].rstrip()

    rules_block = (
        mandatory_rules_text.strip()
        if isinstance(mandatory_rules_text, str) and mandatory_rules_text.strip()
        else PLATFORM_OPERATION_RULES_TEXT.replace("ОБЯЗАТЕЛЬНЫЕ ПРАВИЛА", rules_heading, 1)
    )

    return f"""
## {heading}

{rules_block}

    Правила выбора инструментов:
- Сначала сопоставь задачу с нужной коллекцией или системной возможностью из capability card выше.
- Перед работой с любой коллекцией сначала вызови `collection.info` для этой коллекции.
- Другие collection-bound действия не придумывай по памяти: используй только те имена и аргументы, которые вернулись в результате `collection.info`.
- Для collection-bound операций не передавай и не меняй `collection_slug`/`collection_id`, если операция явно не требует это в своей схеме.
- В поле `tool` используй имя инструмента ровно в том виде, как оно указано в списке ниже.

{call_heading}

```tool_call
{{
    "tool": "tool_name",
    "arguments": {{
        "arg1": "value1"
    }}
}}
```

Можно вызывать несколько инструментов в одном ответе. Используй имя из списка ниже без переименования и домыслов.

{list_heading}
{tools_json}
"""


def _prompt_label(labels: Dict[str, Any], key: str, default: str) -> str:
    value = labels.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return default


def _prompt_budget(budgets: Dict[str, Any], key: str) -> Optional[int]:
    def _coerce(value: Any) -> Optional[int]:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    direct = _coerce(budgets.get(key))
    if direct is not None:
        return direct
    for section in ("operations", "prompt_assembler", "capability_card", "json_schema"):
        section_value = budgets.get(section)
        if isinstance(section_value, dict):
            nested = _coerce(section_value.get(key))
            if nested is not None:
                return nested
    return None


def build_tool_results_message(results: List[Tuple[ToolCall, str]]) -> str:
    parts = []
    for tool_call, result_content in results:
        parts.append(format_tool_result(tool_call, result_content))
    return "\n\n".join(parts)


_UNSUPPORTED_SCHEMA_KEYS = frozenset(
    {"$ref", "$defs", "definitions", "allOf", "anyOf", "oneOf", "$schema", "$id"},
)


def _sanitize_tool_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in schema.items() if k not in _UNSUPPORTED_SCHEMA_KEYS}


def build_tools_payload(operations: "List[ResolvedOperation]") -> List[Dict[str, Any]]:
    """Convert resolved executable tools to OpenAI-compatible tool declarations."""

    tools: List[Dict[str, Any]] = []
    for op in operations:
        raw = build_prompt_input_schema(op)
        schema = _sanitize_tool_schema(raw)
        schema.setdefault("type", "object")
        schema.setdefault("properties", {})
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": op.operation_slug,
                    "description": build_prompt_operation_description(
                        op,
                        summary=getattr(op, "published", None),
                        max_chars=512,
                    ),
                    "parameters": schema,
                },
            }
        )
    return tools


def parse_native_tool_calls(
    response: Any,
    *,
    seen_tools: Optional[set[tuple[str, str]]] = None,
) -> Optional[ParsedResponse]:
    """Parse OpenAI-style tool_calls from a raw model response."""

    if not isinstance(response, dict):
        return None

    choices = response.get("choices") or []
    if not choices:
        return None

    message = (choices[0].get("message") or {}) if choices else {}
    raw_tool_calls = message.get("tool_calls") or []
    if not raw_tool_calls:
        return None

    if seen_tools is None:
        seen_tools = set()

    tool_calls: List[ToolCall] = []
    for item in raw_tool_calls:
        fn = (item.get("function") or {}) if isinstance(item, dict) else {}
        name = str(fn.get("name") or "").strip()
        if not name:
            continue
        raw_args = fn.get("arguments") or {}
        if isinstance(raw_args, str):
            try:
                raw_args = json.loads(raw_args)
            except json.JSONDecodeError:
                raw_args = {}
        if not isinstance(raw_args, dict):
            raw_args = {}
        args_json = json.dumps(raw_args, sort_keys=True)
        tool_key = (name, args_json)
        if tool_key in seen_tools:
            continue
        tool_calls.append(ToolCall.from_dict({"tool": name, "arguments": raw_args}))
        seen_tools.add(tool_key)

    if not tool_calls:
        return None

    text = str(message.get("content") or "").strip()
    return ParsedResponse(text=text, tool_calls=tool_calls, has_tool_calls=True)


def build_tool_result_messages(
    results: List[Tuple[ToolCall, str]],
    tool_calls_raw: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Build OpenAI-style `role=tool` messages for native tool calling."""

    id_map: Dict[str, str] = {}
    for item in tool_calls_raw:
        if isinstance(item, dict):
            fn_name = (item.get("function") or {}).get("name") or ""
            tool_call_id = str(item.get("id") or "")
            if fn_name and tool_call_id:
                id_map[fn_name] = tool_call_id

    messages: List[Dict[str, Any]] = []
    for tool_call, result_content in results:
        tool_call_id = id_map.get(tool_call.tool_name) or tool_call.id
        messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": result_content,
            }
        )
    return messages
