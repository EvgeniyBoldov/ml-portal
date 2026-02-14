# Tool Developer Guide (Backend)

Практический гайд для разработчика, который добавляет новый server tool в Agent Runtime.

## 1. Что такое tool в текущей архитектуре

Tool — это backend-исполняемый capability, который:

- регистрируется в runtime registry,
- вызывается из tool-call loop,
- исполняется с `ToolContext` (tenant/user/chat/scopes),
- возвращает структурированный `ToolResult`.

Базовые контракты:

- `ToolContext` и `ToolResult`: `apps/api/src/app/agents/context.py`
- `ToolHandler` base: `apps/api/src/app/agents/handlers/base.py`
- Versioned registry bridge: `apps/api/src/app/agents/registry.py`

## 2. Где должны лежать файлы

Для нового встроенного инструмента (`builtin`) используем такой набор:

1. **Tool implementation**
   - `apps/api/src/app/agents/builtins/<tool_slug_module>.py`

2. **Регистрация builtin при старте**
   - добавить импорт в `apps/api/src/app/agents/builtins/__init__.py` (`register_builtins`)

3. **(Опционально) Сервис/адаптер бизнес-логики**
   - сервисы: `apps/api/src/app/services/*`
   - внешние адаптеры: `apps/api/src/app/adapters/*`

4. **Тесты**
   - unit/integration в `apps/api/tests/` (по принятой структуре проекта)

5. **Документация**
   - обновить `docs/architecture/AGENT_RUNTIME.md` (если меняется flow/контракт)
   - обновить этот гайд или `TOOL_DEVELOPER_RULES.md` при изменении стандартов

## 3. Минимальный flow добавления нового tool

1. Создать файл `builtins/<tool>.py` с `VersionedTool` и первой версией (`@tool_version`).
2. Определить `tool_slug`, `tool_group`, `name`, `description`.
3. Описать `input_schema` и `output_schema`.
4. Реализовать async-метод версии (например, `v1_0_0`).
5. Подключить `ToolLogger` через `ctx.tool_logger("tool.slug")`.
6. Зарегистрировать import в `builtins/__init__.py`.
7. Проверить, что инструмент попадает в `ToolRegistry` и синхронизируется в БД через startup sync.
8. Добавить тесты (happy path + validation error + runtime error).
9. Обновить документацию.

## 4. Обязательная структура tool-файла

Рекомендуемый скелет:

```python
from __future__ import annotations
from typing import Any, Dict, ClassVar

from app.agents.handlers.versioned_tool import VersionedTool, tool_version, register_tool
from app.agents.context import ToolContext, ToolResult

_INPUT_SCHEMA_V1 = {...}
_OUTPUT_SCHEMA_V1 = {...}

@register_tool
class MyTool(VersionedTool):
    tool_slug: ClassVar[str] = "my.tool"
    tool_group: ClassVar[str] = "my-group"
    name: ClassVar[str] = "My Tool"
    description: ClassVar[str] = "What the tool does"

    @tool_version(
        version="1.0.0",
        input_schema=_INPUT_SCHEMA_V1,
        output_schema=_OUTPUT_SCHEMA_V1,
        description="Initial version",
    )
    async def v1_0_0(self, ctx: ToolContext, args: Dict[str, Any]) -> ToolResult:
        log = ctx.tool_logger("my.tool")
        ...
        return ToolResult.ok(data={...}, logs=log.entries_dict())
```

## 5. Какие данные должны быть обязательно

## 5.1 Metadata

- `tool_slug` — стабильный уникальный идентификатор
- `tool_group` — доменная группа (rag, collection, dcbox, ...)
- `name`, `description` — понятные человеку

## 5.2 Contract

- `input_schema` — JSON schema с `type/properties/required`
- `output_schema` — JSON schema результата
- версия (`version`) в semver-формате

## 5.3 Runtime behavior

- асинхронное выполнение
- валидация аргументов
- корректная обработка ошибок через `ToolResult.fail(...)`
- structured tool logs в `metadata.logs`

## 6. Что должно быть в execute обязательно

- Создание `ToolLogger`
- Валидация критичных аргументов
- Явный вызов доменного сервиса/адаптера
- Нормализация результата в JSON-safe структуру
- Возврат:
  - `ToolResult.ok(data=..., logs=...)` при успехе
  - `ToolResult.fail("...", logs=...)` при ошибке

## 7. Multi-tenant и безопасность

Внутри tool нельзя игнорировать контекст:

- использовать `ctx.tenant_id` для tenant-фильтрации,
- учитывать `ctx.user_id` и scopes,
- не логировать секреты/токены,
- не возвращать чувствительные данные в `data`.

## 8. Версионирование

При несовместимом изменении контракта:

- добавляем новую версию (`v1_1_0`, `v2_0_0`),
- старую не ломаем мгновенно,
- фиксируем изменения в описании версии.

## 9. Чек перед merge

- Tool зарегистрирован и виден в реестре.
- Startup sync корректно создает/обновляет запись в БД.
- Тесты покрывают happy/error cases.
- Логи структурированы, секреты не утекли.
- Документация обновлена в одном PR.
