# AI Engineer Guide

Гид для AI/ML инженера: как запускается выполнение, какие данные участвуют, где смотреть причины деградации и как безопасно расширять систему.

## 1. Runtime-контур (от запроса к ответу)

1. Chat request приходит с user/tenant контекстом.
2. Agent Router собирает ExecutionRequest:
   - agent profile,
   - policy limits,
   - доступные tools/instances,
   - resolved credentials и permissions.
3. Agent Runtime запускает tool-call loop.
4. LLM генерирует ответ и/или tool_call.
5. Tool handlers выполняются в контексте ToolContext.
6. Результаты возвращаются в loop до финального ответа.
7. События и метаданные исполнения пишутся в run logs.

## 2. Что именно должно быть описано в данных

## 2.1 Agent

Обязательные описания:

- назначение агента,
- целевые сценарии и нецелевые сценарии,
- список необходимых tools,
- режим partial-mode,
- связанная policy.

## 2.2 Tool

Обязательные описания:

- бизнес-смысл инструмента,
- input_schema и ограничения аргументов,
- expected output contract,
- timeout/retry ожидания,
- типичные ошибки и как их интерпретировать.

## 2.3 Collection/RAG

Обязательные описания:

- домен данных и назначение коллекции,
- schema полей и search_modes,
- качество/актуальность источника,
- правила scope/tenant доступа,
- expected latency/throughput ограничения.

## 3. Data flow: Chat + Tools + RAG

## 3.1 Chat

- хранит цепочку сообщений и runtime события,
- служит источником контекста для следующего шага модели.

## 3.2 Tool execution

- каждый tool_call — это явный шаг с аргументами и результатом,
- шаг должен быть трассируемым и воспроизводимым,
- ошибка инструмента должна быть доменно понятной, а не «Exception: something broke». 

## 3.3 RAG

- ingestion: extract -> chunk -> embed -> index,
- retrieval: фильтрация по tenant/scope -> поиск -> rerank (если включен),
- финальный ответ должен быть согласован с retrieved context.

## 4. Ограничения и guardrails

- execution ограничен policy (steps/tool calls/wall time/timeouts),
- доступ к tool instance определяется effective permissions,
- credential resolution: user -> tenant -> default,
- при недоступности required tool:
  - partial-mode off -> run unavailable,
  - partial-mode on -> degraded run с предупреждением.

## 5. Наблюдаемость и диагностика

Смотреть в первую очередь:

1. Agent runs (status, duration, step timeline).
2. Tool-level ошибки и таймауты.
3. RAG ingest статусы и failed stages.
4. Search quality (recall/precision, пустые выдачи).
5. Корреляция latency с конкретными tool instances.

Минимум для RCA:

- входной запрос,
- execution mode,
- список задействованных tools,
- лимиты policy,
- tenant/user scope,
- шаг, где произошел сбой.

## 6. Как добавлять новый tool безопасно

1. Добавить handler и input_schema.
2. Зарегистрировать tool в registry.
3. Добавить запись/seed в БД (для админки и bindings).
4. Подготовить instance config + credential strategy.
5. Добавить тесты: unit + integration на happy path и timeout/error path.
6. Обновить документацию (этот файл + architecture/AGENT_RUNTIME.md при изменении flow).

## 7. Чеклист качества перед релизом

- Есть понятное описание agent/tool/data contracts.
- Лимиты policy заданы и проверены.
- Наблюдаемость достаточна для разбора инцидента.
- Доступ к данным и агентам соответствует effective access policy (tenant = отдел; sharing между отделами только через явный PermissionSet).
- Документация обновлена синхронно с кодом.

Если поведение нельзя объяснить по логам и данным — значит система еще не готова к масштабу. И это не философия, а эксплуатация.
