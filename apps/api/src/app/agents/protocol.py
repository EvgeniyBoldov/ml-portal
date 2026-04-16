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
from typing import List, Tuple
from dataclasses import dataclass

from app.agents.context import OperationCall
from app.agents.json_utils import extract_balanced_json


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

You have access to the following operations. To use an operation, respond with an operation_call block:

```operation_call
{{
    "operation": "operation_name",
    "arguments": {{
        "arg1": "value1"
    }}
}}
```

Available operations:
{operations_json}

IMPORTANT:
- You can call multiple operations in one response
- Wait for operation results before providing final answer
- If no operations are needed, respond directly without operation_call blocks
- Always use the exact operation name from the list above
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
