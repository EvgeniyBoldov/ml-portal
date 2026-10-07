"""Backend-owned instructions for every agent task's terminal declaration."""
from __future__ import annotations

import json
from typing import Any

from app.runtime.orchestrator_contracts import TaskRequest, task_completion_json_schema
from app.runtime.task_value_normalization import TASK_COMPLETION_RULES


def output_slot_example(task: TaskRequest, key: str) -> dict[str, Any]:
    """Show transport structure, without inventing a task value or a receipt."""
    spec = next((item for item in task.expected_outputs if item.key == key), None)
    fulfillment = spec.fulfillment.value if spec else "task_result"
    if fulfillment == "artifact":
        return {"kind": "artifact", "refs": ["<artifact_ref из результата операции>"]}
    if fulfillment == "verified_receipt":
        return {"kind": "evidence", "refs": ["<result_ref успешного вызова>"]}
    return {"kind": "value", "value": "<значение по schema этого output>"}


def build_task_completion_prompt(task: TaskRequest) -> str:
    example = {
        "completion": "fulfilled",
        "report": "<краткое описание выполненной работы>",
        "outputs": {item.key: output_slot_example(task, item.key) for item in task.expected_outputs},
        "needs": [],
        "coverage": [],
    }
    expected = [item.model_dump(mode="json", by_alias=True) for item in task.expected_outputs]
    return "\n\n".join([
        "# RUNTIME TASK COMPLETION DECLARATION — ОБЯЗАТЕЛЬНЫЙ КОНТРАКТ",
        "Ты исполняешь задачу агента. Итог читает backend. Этот контракт обязателен для всех агентов "
        "и имеет приоритет над Output Format и Examples версии агента. Пока нужна работа, вызывай "
        "доступные инструменты обычным способом. Вызов инструмента не является итоговым ответом.",
        "Когда заканчиваешь задачу, верни ровно один JSON-объект. Без Markdown, ограждений кода "
        "и текста до или после JSON. report — непустая строка с кратким описанием результата.",
        "outputs — объект с ключами ТОЛЬКО из expected_outputs ниже. Не переименовывай ключи. "
        "schema каждого output описывает содержимое value, а НЕ весь слот. Каждый output "
        "обязательно оберни в один из следующих слотов:\n"
        '- task_result: {"kind":"value","value":<значение по schema>}. '
        'Неверно: "device":{"hostname":"..."}. '
        'Верно: "device":{"kind":"value","value":{"hostname":"..."}}. '
        "Все поля результата помещаются внутрь value; kind находится рядом с value.\n"
        '- verified_receipt: {"kind":"evidence","refs":["<result_ref>"]}. '
        "Ссылайся только на успешные вызовы требуемых receipt_operations.\n"
        '- artifact: {"kind":"artifact","refs":["<artifact_ref>"]}. '
        "Файл должен реально создаваться операцией runtime. Не выдумывай refs.",
        "completion выбирается так:\n"
        "- fulfilled: все required outputs представлены и подтверждены; needs=[]; limitation не добавляй.\n"
        "- needs: нужен внешний ввод или зависимость. needs обязан быть непустым. Каждый элемент "
        "содержит ref, key и description; schema описывает требуемый ввод. limitation не добавляй.\n"
        "- unfulfillable: задачу выполнить невозможно. Добавь limitation с code, message "
        'и action="none" (либо другим разрешённым schema действием); needs=[]. '
        "Сохрани уже полученные корректные outputs. Не объявляй успех при недостающих required outputs.",
        "Доказательства и полнота: используй реальные наблюдаемые результаты, не достраивай "
        "обрезанные preview. Если есть сохранённый результат с inline_complete=false, каждый "
        "непустой массив в outputs требует coverage. Прочитай нужные данные через result.analyze. "
        "Элемент coverage содержит output_key, output_path (путь к массиву внутри value; "
        'для массива в корне value — ""), result_id и непустой query_call_ids. '
        "Для массива из SQL укажи result_id сохранённого SQL-результата и call_id выполненного "
        "SQL-запроса. Не выдумывай ID и не подставляй ID исходного API-вызова вместо SQL call_id. "
        "Без таких массивов coverage=[]. require_complete_source требует подтверждённой полноты источника.",
        "Структурный пример для текущей задачи (замени строки в угловых скобках реальными "
        "значениями по schema; добавь coverage, если требуется):\n"
        + json.dumps(example, ensure_ascii=False, indent=2),
        "Expected outputs (including required/schema): " + json.dumps(expected, ensure_ascii=False),
        TASK_COMPLETION_RULES,
        "freshness_policy=" + task.freshness_policy.value + ". При require_retrieval нужен "
        "успешный retrieval-вызов в этой задаче. Для verified_receipt нужны успешные вызовы "
        "каждой операции из receipt_operations. Backend сам проверяет evidence и artifacts.",
        "Перед отправкой проверь: ключи outputs совпадают с expected_outputs; каждый слот "
        "имеет kind; данные лежат внутри value либо refs; типы и обязательные поля соответствуют "
        "schema; refs и coverage подтверждены выполненными операциями. После ошибки валидации "
        "исправь указанную структуру, сохрани остальные данные и верни весь JSON. Повтор внешнего "
        "действия допустим только если действительно недостаёт доказательств.",
        "Полная JSON Schema результата, сгенерированная backend из Pydantic:\n"
        + json.dumps(task_completion_json_schema(task), ensure_ascii=False),
    ])
