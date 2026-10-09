"""Backend-owned universal protocol for agent task responses."""
from __future__ import annotations

import json
from typing import Any
from app.runtime.orchestrator_contracts import TaskRequest, task_completion_json_schema


def output_slot_example(task: TaskRequest, key: str) -> dict[str, Any]:
    """Legacy callers may inspect old task specifications."""
    return {"kind": "value", "value": "<observed data>"}


def build_task_completion_prompt(task: TaskRequest) -> str:
    return "\n\n".join([
        "# RUNTIME TASK COMPLETION DECLARATION — ОБЯЗАТЕЛЬНЫЙ ПРОТОКОЛ",
        "Верни один JSON-объект. completion: fulfilled, needs или unfulfillable. "
        "Ты самостоятельно оцениваешь выполнение задачи. answer — необязательный текст; "
        "structured_response — любые фактически полученные JSON-данные; needs — зависимости "
        "с ref, key, description. Для completion=needs нужен непустой needs; для остальных needs=[].",
        "Схемы входа и результата — рекомендации. Сохрани реальные значения, включая null и пустые "
        "списки. Если данные отличаются от схемы, передай их и при необходимости объясни в answer. "
        "Не выдумывай данные. Пока нужна работа, используй доступные инструменты. "
        "Preview не заменяет полные данные: проверяй схему через result.describe, "
        "читай записи через result.read, выполняй SQL-анализ через result.sql, если он доступен.",
        "Файлы и источники прикладывает runtime из выполненных операций. Не возвращай artifact-слоты, "
        "coverage или идентификаторы доказательств. Если требуется файл, создай его доступной операцией.",
        "Requested presentation (schema is advisory): " + json.dumps(_presentation_hint(task), ensure_ascii=False, separators=(",", ":")),
        "JSON Schema протокола из Pydantic:\n" + json.dumps(_prompt_schema(task_completion_json_schema(task)), ensure_ascii=False, separators=(",", ":")),
    ])


def _presentation_hint(task: TaskRequest) -> dict[str, Any]:
    presentation = task.response_spec.model_dump(mode="json", by_alias=True)
    seen_schemas = [presentation.get("schema", {})]
    hints = []
    for output in task.expected_outputs:
        hint: dict[str, Any] = {"key": output.key, "description": output.description}
        schema = output.json_schema
        if schema and schema not in seen_schemas:
            hint["schema"] = schema
            seen_schemas.append(schema)
        hints.append(hint)
    if hints:
        presentation["data_hints"] = hints
    return presentation


def _prompt_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Omit annotation prose while retaining the generated validation contract."""
    result = {key: value for key, value in schema.items() if key not in {"title", "description"}}
    for key in ("properties", "$defs"):
        if isinstance(result.get(key), dict):
            result[key] = {name: _prompt_schema(child) for name, child in result[key].items()}
    for key in ("anyOf", "oneOf", "allOf"):
        if isinstance(result.get(key), list):
            result[key] = [_prompt_schema(child) for child in result[key]]
    if isinstance(result.get("items"), dict):
        result["items"] = _prompt_schema(result["items"])
    return result
