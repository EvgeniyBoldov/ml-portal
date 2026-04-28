# Tool Developer Rules (Mandatory)

Обязательные правила для любого нового backend tool.

## 1) Базовые требования

1. Только `async` реализация.
2. Полная типизация (`type hints`) в публичных сигнатурах.
3. Никаких хардкодов secret/ключей/endpoint credentials.
4. Никакого обхода effective access policy. Tenant — отдел/рабочая область
   локальной компании, а не hard SaaS boundary.

## 2) Где и как создавать tool

1. Новый builtin tool — только в `apps/api/src/app/agents/builtins/*.py`.
2. Обязательная регистрация через `@register_tool`.
3. Обязательное подключение модуля в `builtins/__init__.py`.
4. Используем `VersionedTool` + `@tool_version`.

## 3) Обязательные поля tool-класса

У каждого инструмента должны быть:

- `tool_slug`
- `tool_group`
- `name`
- `description`
- `input_schema`
- `output_schema`
- минимум одна версия (`1.0.0`)

## 4) Контракты и валидация

1. `input_schema` должен описывать required поля.
2. Все аргументы валидируются до выполнения тяжелой логики (JSON Schema, typed errors).
3. `output_schema` должен соответствовать реально возвращаемой структуре.
4. Breaking changes — только новой версией инструмента.

## 5) Выполнение и ошибки

1. Всегда использовать `ctx.tool_logger("tool.slug")`.
2. Успех возвращаем только через `ToolResult.ok(...)`.
3. Ошибки возвращаем через `ToolResult.fail(...)` с безопасным сообщением.
4. Исключения не должны «вылетать» наружу сырыми traceback-строками в user-facing контент.

## 6) Доступы, tenant, data safety

1. Всегда учитывать effective access policy при data access; `ctx.tenant_id`
   сам по себе не запрещает разрешенный sharing между отделами.
2. Если нужны user-bound ограничения — учитывать `ctx.user_id`/scopes.
3. Нельзя возвращать или логировать креды/секреты.
4. Любые внешние вызовы должны идти через существующие сервисы/адаптеры.
5. Для MCP-integration: broker-first credential flow является default; raw credential fallback допускается только explicit local/dev режимом.

## 7) Логирование (обязательно)

Минимум логируем:

- начало выполнения tool,
- ключевые этапы,
- итог (success/fail),
- latency/объем результата (без секретов).

Формат — structured entries через `ToolLogger`.

Дополнительно:
- Любой trace/log/admin payload должен проходить через runtime redaction policy
  (`token/password/api_key/access_token/authorization/cookie/db_dsn/database_url`).

## 8) Тесты (обязательно)

Для нового tool обязательны:

1. Unit test: happy path.
2. Unit test: invalid args.
3. Unit test: error path (сервис падает/таймаут/внешняя ошибка).
4. При критичном tool — integration test через runtime flow.

## 9) Документация (обязательно)

В одном PR с кодом должны быть:

1. Обновление `AGENT_RUNTIME.md` (если меняется контракт/flow).
2. Обновление `TOOL_DEVELOPER_GUIDE.md`/этого файла при изменении стандартов.
3. Краткое описание use case и ограничений нового tool.

## 10) Merge checklist

- [ ] Tool зарегистрирован и обнаруживается реестром.
- [ ] Startup sync не ломается.
- [ ] Контракт версии валиден.
- [ ] Нет утечки tenant/secret данных.
- [ ] Тесты добавлены и проходят.
- [ ] Документация обновлена.
