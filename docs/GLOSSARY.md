# Глоссарий

## Сущности

### Agent (Агент)
AI-ассистент с набором инструментов, промптом и политикой. Выполняет задачи через tool-call loop.

### Tenant (Тенант)
Департамент или организационная единица. Изолированное пространство с пользователями, настройками и данными.

### User (Пользователь)
Учётная запись с ролью и привязкой к тенанту.

### Prompt (Промпт)
Текстовая инструкция для LLM. Имеет версии и статусы (draft/active/archived).

### Baseline Prompt
Системный промпт с ограничениями. Мержится с основным промптом агента.

### Tool (Инструмент)
Функция, которую агент может вызвать: RAG-поиск, Jira, NetBox и др.

### Tool Instance (Инстанс инструмента)
Конкретное подключение к инструменту с настройками и credentials.

### Tool Group (Группа инструментов)
Категория инструментов: collection, http, builtin.

### Collection (Коллекция)
Структурированные данные с SQL и векторным поиском. Автоматически создаёт Tool Instance.

### Policy (Политика)
Ограничения выполнения агента: лимиты шагов, токенов, времени.

### Permission Set (Набор прав)
Права доступа к инструментам и агентам. Scope: default/tenant/user.

### Credential Set (Набор credentials)
Зашифрованные учётные данные для Tool Instance. Scope: default/tenant/user.

## Процессы

### RAG Pipeline
Загрузка → Извлечение текста → Чанкинг → Эмбеддинг → Индексация в Qdrant.

### Tool-call Loop
Цикл выполнения агента: LLM → Tool call → Result → LLM → ...

### Credential Resolution
Поиск credentials по приоритету: User > Tenant > Default.

### Permission Resolution
Проверка прав по приоритету: User > Tenant > Default.

## Статусы

### Document Status
- `pending` — ожидает обработки
- `processing` — в процессе
- `ready` — готов к поиску
- `failed` — ошибка обработки
- `archived` — архивирован

### Prompt Status
- `draft` — черновик
- `active` — активная версия
- `archived` — архивная версия

### Permission Value
- `allowed` — разрешено
- `denied` — запрещено
- `undefined` — наследуется от родительского scope

## System LLM Roles (Роли оркестрации)

### Planner
Роль планирования выполнения: выбирает между `call_agent`, `clarify`, `direct_answer`, `final`, `abort`. Имеет JSON-контракт ответа.

### Synthesizer
Роль сборки финального ответа пользователю. Имеет plain-text контракт с критериями.

### Fact Extractor
Роль извлечения атомарных фактов из диалога. Имеет JSON-контракт ответа (`facts[]`).

### Summary Compactor
Роль обновления структурного summary диалога (`goals`, `done`, `entities`, `open_questions`).

### Triage
Роль первичной классификации запроса: `final` / `clarify` / `orchestrate`.

## Контракты

### Response Contract
Контракт ответа системной роли. Типы:
- `json` — структурированный ответ со схемой (Planner, Fact Extractor)
- `plain_text` — критерии качества ответа (Synthesizer)
- `markdown` — reserved для future use

### format_locked
Флаг неизменяемости контракта. Все built-in роли имеют `format_locked: true`.

## Трейсы и диагностика

### RunTrace
Семантический трейс выполнения агента: фазы, итерации, события, артефакты.

### SemanticEvent
Нормализованное событие рантайма с категорией (`llm`, `operation`, `budget`, `decision`, `error`).

### Trace Artifact
Артефакт трейса: `prompt`, `llm_request`, `llm_response`, `validation`, `budget`, `operation_input/output`, `error`.

### Execution Trace
Полная цепочка выполнения агента для диагностики AI Engineer'ом.

## Роли доступа

### reader
Только просмотр данных.

### editor
Просмотр и редактирование данных.

### admin
Полный доступ к системе.

### tenant_admin
Администратор департамента.
