"""
Протокол для operation-calls в тексте LLM ответа.

Используем JSON-блоки в тексте вместо OpenAI function calling,
чтобы не зависеть от конкретного провайдера LLM.

Формат:
```operation_call
{
    "operation": "instance.docs.collection.doc_search",
    "arguments": {
        "query": "как настроить nginx"
    }
}
```

LLM может вызвать несколько operations в одном ответе.
"""
from __future__ import annotations
import json
import re
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple
from dataclasses import dataclass

from app.agents.context import OperationCall
from app.agents.json_utils import extract_balanced_json

if TYPE_CHECKING:
    from app.agents.contracts import ResolvedOperation


OPERATION_CALL_PATTERN = re.compile(
    r'```operation_call\s*\n(.*?)\n```',
    re.DOTALL
)

# Fallback: ```json\n{"operation": ...}\n```
OPERATION_CALL_JSON_BLOCK = re.compile(
    r'```(?:json)?\s*\n(\{[^`]*?"operation"\s*:[^`]*?\})\s*\n```',
    re.DOTALL
)

def _find_operation_json_objects(content: str) -> List[str]:
    """
    Find all JSON objects containing an "operation" key in the text.
    Uses balanced-brace extraction for robustness with multiline JSON.
    """
    results = []
    idx = 0
    while idx < len(content):
        brace = content.find('{', idx)
        if brace < 0:
            break
        candidate = extract_balanced_json(content, brace)
        if candidate:
            try:
                data = json.loads(candidate)
                if isinstance(data, dict) and "operation" in data:
                    results.append(candidate)
            except (json.JSONDecodeError, ValueError):
                pass
            idx = brace + len(candidate)
        else:
            idx = brace + 1
    return results

TOOL_RESULT_TEMPLATE = """```tool_result
{result}
```"""


@dataclass
class ParsedResponse:
    """
    Результат парсинга ответа LLM.
    """
    text: str
    operation_calls: List[OperationCall]
    has_operation_calls: bool
    
    @property
    def is_final(self) -> bool:
        """Ответ финальный (без operation calls)"""
        return not self.has_operation_calls


def parse_llm_response(content: str, *, strict: bool = False) -> ParsedResponse:
    """
    Парсит ответ LLM и извлекает operation_calls.
    
    Supports multiple formats:
    1. ```operation_call\n{...}\n```  (canonical)
    2. ```json\n{"operation": ...}\n```
    3. Any JSON object with "operation" key (balanced braces)
    
    Args:
        content: Текст ответа LLM
        
    Returns:
        ParsedResponse с текстом и списком operation_calls
    """
    operation_calls: List[OperationCall] = []
    seen_operations: set = set()
    text = content
    
    # 1. Try canonical ```operation_call ... ```
    matches = OPERATION_CALL_PATTERN.findall(content)
    for match in matches:
        try:
            data = json.loads(match.strip())
            if "operation" in data and data["operation"] not in seen_operations:
                operation_calls.append(OperationCall.from_dict(data))
                seen_operations.add(data["operation"])
        except json.JSONDecodeError:
            continue
    if operation_calls:
        text = OPERATION_CALL_PATTERN.sub('', text).strip()
        return ParsedResponse(text=text, operation_calls=operation_calls, has_operation_calls=True)
    
    # 2. Try ```json ... ```
    matches = OPERATION_CALL_JSON_BLOCK.findall(content)
    for match in matches:
        try:
            data = json.loads(match.strip())
            if "operation" in data and data["operation"] not in seen_operations:
                operation_calls.append(OperationCall.from_dict(data))
                seen_operations.add(data["operation"])
        except json.JSONDecodeError:
            continue
    if operation_calls:
        text = OPERATION_CALL_JSON_BLOCK.sub('', text).strip()
        return ParsedResponse(text=text, operation_calls=operation_calls, has_operation_calls=True)
    
    # 3. Fallback: find any JSON with "operation" key using balanced braces
    if not strict:
        json_strs = _find_operation_json_objects(content)
        for js in json_strs:
            try:
                data = json.loads(js)
                if data["operation"] not in seen_operations:
                    operation_calls.append(OperationCall.from_dict(data))
                    seen_operations.add(data["operation"])
                    text = text.replace(js, '', 1)
            except (json.JSONDecodeError, KeyError):
                continue
    
    if operation_calls:
        text = text.strip()
    
    return ParsedResponse(
        text=text,
        operation_calls=operation_calls,
        has_operation_calls=len(operation_calls) > 0
    )


def format_operation_result(operation_call: OperationCall, result_content: str) -> str:
    """
    Форматирует результат выполнения tool для добавления в контекст LLM.
    """
    result_data = {
        "operation": operation_call.operation_slug,
        "call_id": operation_call.id,
        "result": result_content
    }
    return TOOL_RESULT_TEMPLATE.format(
        result=json.dumps(result_data, ensure_ascii=False, indent=2)
    )


def build_operations_prompt(operation_schemas: List[dict]) -> str:
    """
    Генерирует инструкцию для LLM о доступных operations.
    
    Args:
        operation_schemas: Список схем operations
        
    Returns:
        Текст инструкции для добавления в system prompt
    """
    if not operation_schemas:
        return ""
    
    operations_json = json.dumps(operation_schemas, ensure_ascii=False, indent=2)
    
    return f"""
## Available Operations

MANDATORY RULES — follow these without exception:
1. If the user asks for REAL DATA (records, values, counts, status, config) — you MUST call an operation first. Never answer from prior knowledge about actual data.
2. EXCEPTION: if the user asks only about what data sources, collections, or operations are available (meta-question about capabilities) — you MAY answer directly using the capability card above without calling any operation.
3. Only after you receive operation results may you compose and deliver the final answer for data questions.
4. Never make up or assume actual data values — collect them via operations.

To call an operation, respond with an operation_call block:

```operation_call
{{
    "operation": "operation_name",
    "arguments": {{
        "arg1": "value1"
    }}
}}
```

You may call multiple operations in one response. Always use the exact operation name from the list below.

Available operations:
{operations_json}
"""


def build_operation_results_message(results: List[Tuple[OperationCall, str]]) -> str:
    """
    Форматирует результаты нескольких operation calls в одно сообщение.
    
    Args:
        results: Список пар (OperationCall, result_content)
        
    Returns:
        Текст сообщения с результатами
    """
    parts = []
    for operation_call, result_content in results:
        parts.append(format_operation_result(operation_call, result_content))
    
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Native function calling (OpenAI tool_calls API)
# ---------------------------------------------------------------------------

_UNSUPPORTED_SCHEMA_KEYS = frozenset({
    "$ref", "$defs", "definitions", "allOf", "anyOf", "oneOf", "$schema", "$id",
})


def _sanitize_tool_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Strip JSON Schema keys that OpenAI-compatible providers reject.

    OpenAI function calling supports a flat subset of JSON Schema. Keys like
    ``$ref``, ``allOf``, ``$defs`` etc. cause provider-level validation errors.
    We do a shallow strip — nested ``properties`` values are left intact because
    providers generally accept simple nested objects.
    """
    return {k: v for k, v in schema.items() if k not in _UNSUPPORTED_SCHEMA_KEYS}


def build_tools_payload(
    operations: "List[ResolvedOperation]",
) -> List[Dict[str, Any]]:
    """Convert ResolvedOperation list → OpenAI-compatible tools array.

    Each tool gets:
    - ``name``: operation_slug (the identifier the model will echo back).
    - ``description``: human-readable purpose fed to the model.
    - ``parameters``: sanitized input_schema (unsupported keys stripped).

    The model will return tool_calls[].function.{name, arguments} which
    ``parse_native_tool_calls`` then converts to OperationCall objects.
    """
    tools: List[Dict[str, Any]] = []
    for op in operations:
        raw = dict(op.input_schema) if op.input_schema else {}
        schema = _sanitize_tool_schema(raw)
        schema.setdefault("type", "object")
        schema.setdefault("properties", {})
        tool: Dict[str, Any] = {
            "type": "function",
            "function": {
                "name": op.operation_slug,
                "description": (op.description or op.name or op.operation_slug)[:512],
                "parameters": schema,
            },
        }
        tools.append(tool)
    return tools


def parse_native_tool_calls(
    response: Any,
    *,
    seen_operations: Optional[set] = None,
) -> Optional["ParsedResponse"]:
    """Parse OpenAI-style tool_calls from a raw LLM response dict.

    Returns ``None`` when the response contains no tool_calls (caller should
    fall back to text-based ``parse_llm_response``).

    Deduplicates by operation_slug using the same ``seen_operations`` set as
    the text parser so the two paths can be combined without double-calls.
    """
    if not isinstance(response, dict):
        return None

    choices = response.get("choices") or []
    if not choices:
        return None

    message = (choices[0].get("message") or {}) if choices else {}
    tool_calls = message.get("tool_calls") or []
    if not tool_calls:
        return None

    if seen_operations is None:
        seen_operations = set()

    operation_calls: List[OperationCall] = []
    for tc in tool_calls:
        fn = (tc.get("function") or {}) if isinstance(tc, dict) else {}
        name = str(fn.get("name") or "").strip()
        if not name or name in seen_operations:
            continue
        raw_args = fn.get("arguments") or {}
        if isinstance(raw_args, str):
            try:
                raw_args = json.loads(raw_args)
            except json.JSONDecodeError:
                raw_args = {}
        if not isinstance(raw_args, dict):
            raw_args = {}
        operation_calls.append(
            OperationCall.from_dict({"operation": name, "arguments": raw_args})
        )
        seen_operations.add(name)

    if not operation_calls:
        return None

    text = str(message.get("content") or "").strip()
    return ParsedResponse(text=text, operation_calls=operation_calls, has_operation_calls=True)


def build_tool_result_messages(
    results: List[Tuple[OperationCall, str]],
    tool_calls_raw: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Build OpenAI-style tool result messages for native tool calling path.

    Returns a list of ``{"role": "tool", "tool_call_id": ..., "content": ...}``
    messages that follow the assistant message that contained tool_calls.
    Falls back to ``call_id`` from OperationCall when the raw tool_calls list
    does not have a matching entry.
    """
    id_map: Dict[str, str] = {}
    for tc in tool_calls_raw:
        if isinstance(tc, dict):
            fn_name = (tc.get("function") or {}).get("name") or ""
            tc_id = str(tc.get("id") or "")
            if fn_name and tc_id:
                id_map[fn_name] = tc_id

    messages: List[Dict[str, Any]] = []
    for operation_call, result_content in results:
        tc_id = id_map.get(operation_call.operation_slug) or operation_call.id
        messages.append(
            {
                "role": "tool",
                "tool_call_id": tc_id,
                "content": result_content,
            }
        )
    return messages
