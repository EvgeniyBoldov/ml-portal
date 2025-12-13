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
    
    Args:
        content: Текст ответа LLM
        
    Returns:
        ParsedResponse с текстом и списком tool_calls
    """
    tool_calls: List[ToolCall] = []
    
    matches = TOOL_CALL_PATTERN.findall(content)
    
    for match in matches:
        try:
            data = json.loads(match.strip())
            if "tool" in data:
                tool_call = ToolCall.from_dict(data)
                tool_calls.append(tool_call)
        except json.JSONDecodeError:
            continue
    
    text = TOOL_CALL_PATTERN.sub('', content).strip()
    
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
