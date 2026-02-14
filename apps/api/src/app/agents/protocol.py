"""
Протокол для tool-calls в тексте LLM ответа.

Используем JSON-блоки в тексте вместо OpenAI function calling,
чтобы не зависеть от конкретного провайдера LLM.

Формат:
```tool_call
{
    "tool": "rag.search",
    "arguments": {
        "query": "как настроить nginx"
    }
}
```

LLM может вызвать несколько tools в одном ответе.
"""
from __future__ import annotations
import re
import json
from typing import List, Optional, Tuple
from dataclasses import dataclass

from app.agents.context import ToolCall


TOOL_CALL_PATTERN = re.compile(
    r'```tool_call\s*\n(.*?)\n```',
    re.DOTALL
)

# Fallback: ```json\n{"tool": ...}\n```
TOOL_CALL_JSON_BLOCK = re.compile(
    r'```(?:json)?\s*\n(\{[^`]*?"tool"\s*:[^`]*?\})\s*\n```',
    re.DOTALL
)


def _extract_balanced_json(text: str, start: int) -> Optional[str]:
    """Extract a balanced JSON object starting from position `start` (must be '{')."""
    if start >= len(text) or text[start] != '{':
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == '\\':
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def _find_tool_json_objects(content: str) -> List[str]:
    """
    Find all JSON objects containing a "tool" key in the text.
    Uses balanced-brace extraction for robustness with multiline JSON.
    """
    results = []
    idx = 0
    while idx < len(content):
        brace = content.find('{', idx)
        if brace < 0:
            break
        candidate = _extract_balanced_json(content, brace)
        if candidate:
            try:
                data = json.loads(candidate)
                if isinstance(data, dict) and "tool" in data:
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
    tool_calls: List[ToolCall]
    has_tool_calls: bool
    
    @property
    def is_final(self) -> bool:
        """Ответ финальный (без tool calls)"""
        return not self.has_tool_calls


def parse_llm_response(content: str) -> ParsedResponse:
    """
    Парсит ответ LLM и извлекает tool_calls.
    
    Supports multiple formats:
    1. ```tool_call\n{...}\n```  (canonical)
    2. ```json\n{"tool": ...}\n```
    3. Any JSON object with "tool" key (balanced braces)
    
    Args:
        content: Текст ответа LLM
        
    Returns:
        ParsedResponse с текстом и списком tool_calls
    """
    tool_calls: List[ToolCall] = []
    seen_tools: set = set()
    text = content
    
    # 1. Try canonical ```tool_call ... ```
    matches = TOOL_CALL_PATTERN.findall(content)
    for match in matches:
        try:
            data = json.loads(match.strip())
            if "tool" in data and data["tool"] not in seen_tools:
                tool_calls.append(ToolCall.from_dict(data))
                seen_tools.add(data["tool"])
        except json.JSONDecodeError:
            continue
    if tool_calls:
        text = TOOL_CALL_PATTERN.sub('', text).strip()
        return ParsedResponse(text=text, tool_calls=tool_calls, has_tool_calls=True)
    
    # 2. Try ```json ... ```
    matches = TOOL_CALL_JSON_BLOCK.findall(content)
    for match in matches:
        try:
            data = json.loads(match.strip())
            if "tool" in data and data["tool"] not in seen_tools:
                tool_calls.append(ToolCall.from_dict(data))
                seen_tools.add(data["tool"])
        except json.JSONDecodeError:
            continue
    if tool_calls:
        text = TOOL_CALL_JSON_BLOCK.sub('', text).strip()
        return ParsedResponse(text=text, tool_calls=tool_calls, has_tool_calls=True)
    
    # 3. Fallback: find any JSON with "tool" key using balanced braces
    json_strs = _find_tool_json_objects(content)
    for js in json_strs:
        try:
            data = json.loads(js)
            if data["tool"] not in seen_tools:
                tool_calls.append(ToolCall.from_dict(data))
                seen_tools.add(data["tool"])
                text = text.replace(js, '', 1)
        except (json.JSONDecodeError, KeyError):
            continue
    
    if tool_calls:
        text = text.strip()
    
    return ParsedResponse(
        text=text,
        tool_calls=tool_calls,
        has_tool_calls=len(tool_calls) > 0
    )


def format_tool_result(tool_call: ToolCall, result_content: str) -> str:
    """
    Форматирует результат выполнения tool для добавления в контекст LLM.
    """
    result_data = {
        "tool": tool_call.tool_slug,
        "call_id": tool_call.id,
        "result": result_content
    }
    return TOOL_RESULT_TEMPLATE.format(
        result=json.dumps(result_data, ensure_ascii=False, indent=2)
    )


def build_tools_prompt(tools_schemas: List[dict]) -> str:
    """
    Генерирует инструкцию для LLM о доступных tools.
    
    Args:
        tools_schemas: Список схем tools (из handler.to_llm_schema())
        
    Returns:
        Текст инструкции для добавления в system prompt
    """
    if not tools_schemas:
        return ""
    
    tools_json = json.dumps(tools_schemas, ensure_ascii=False, indent=2)
    
    return f"""
## Available Tools

You have access to the following tools. To use a tool, respond with a tool_call block:

```tool_call
{{
    "tool": "tool_name",
    "arguments": {{
        "arg1": "value1"
    }}
}}
```

Available tools:
{tools_json}

IMPORTANT:
- You can call multiple tools in one response
- Wait for tool results before providing final answer
- If no tools are needed, respond directly without tool_call blocks
- Always use the exact tool name from the list above
"""


def build_tool_results_message(results: List[Tuple[ToolCall, str]]) -> str:
    """
    Форматирует результаты нескольких tool calls в одно сообщение.
    
    Args:
        results: Список пар (ToolCall, result_content)
        
    Returns:
        Текст сообщения с результатами
    """
    parts = []
    for tool_call, result_content in results:
        parts.append(format_tool_result(tool_call, result_content))
    
    return "\n\n".join(parts)
