# TODO

## Runtime trace — закрыть разрывы контрактов, найденные в production run `e1cf84e2-117b-4b98-af6d-e5dc52355c0f`

### Исполнение, доказательства и результаты

- Запретить расхождение между результатом операции и заявлением модели: поля наподобие `memory_updated`, `status` и `source` должны выводиться runtime из подтверждённых receipts операций, а не приниматься из текста ответа агента. В данном run три вызова `project_memory.mark` были отклонены, но агент вернул `memory_updated: true`.
- Передавать агенту непридуманный opaque `evidence_ref` успешного evidence-producing вызова и разрешать `project_memory.mark` только с таким ref. Не требовать от модели угадывать или переносить journal/tool-call id между native tool calling и runtime journal.
- При отклонении операции фиксировать typed failure result и не продолжать одинаковые семантически некорректные retries. Для `evidence_must_reference_successful_current_run_tool` нужен детерминированный repair path либо терминальный безопасный результат.
- Зафиксировать typed contract dependency outputs: фактический ответ, статус, evidence и artifacts передаются разными полями. Не подменять ожидаемый `srk_definition` ссылкой на artifact, когда потребителю нужен текстовый подтверждённый факт.
- Запретить planner-у выдумывать `project_key` (`default` в run), когда ключа нет в `memory_context.type=project`. В таком случае planner обязан выбрать определённый общий источник или запросить одно уточнение.
- Убрать глобальное правило «агент обязан вызвать tool перед ответом». Задача, получившая подтверждённый typed dependency result, должна завершаться без лишнего tool call; в run это породило ненужный `project_memory.read` с выдуманным ключом `SRK_definition`.
- Уточнить capability boundary `tech_fact_manager`: его фактические операции и доступные источники должны задаваться runtime-whitelist, а не только длинным prompt/capability snapshot со всеми системными операциями.
- Исправить memory selector: нерелевантные персональные факты не должны попадать в контекст и trace фактического вопроса об аббревиатуре.

### Семантика журнала и progress

- Развести terminal events: пользовательский `final` создаётся ровно один раз на сущности `run`; промежуточный ответ исполнителя логируется как отдельный `agent_result`/`task_result`, а не как второй `final`.
- Не сохранять два равнозначных `llm_response` для одного завершённого ответа (`running` и `completed` с одинаковым content). Потоковые дельты остаются transport-only, журнал хранит осмысленные state transitions и терминальный результат.
- Ограничить размер snapshot/payload и заменить огромные capability/prompt dumps на typed summary, hash, counts и при необходимости защищённую диагностическую ссылку. Редакция происходит до persistence и до stream.
- Оставить progress трансляцией агентных ответов, но формировать её из отдельного bounded `progress_summary`/user-safe outcome, а не из произвольного `summary` или raw результата. В частности, не транслировать в progress JSON, аргументы tools, evidence ids, промпты и внутренние причины протокольных retries.
- Разделить статусные формулировки для planner, memory preparation и других orchestrator roles: «Запускаю планирование» не должно отображаться для каждого orchestrator start.

### Фронтенд: что журналируем и как показываем

- Зафиксировать явную матрицу `event_type -> entity -> typed payload -> Viewer/tab -> visibility`. Inspector не должен извлекать доменную семантику из свободного JSON или последовательности событий.
- Оставить текущую модель: trace projector один раз строит дерево только по `entity_type/entity_id/parent_*`, а Viewer получает готовую presentation model; RAW — отдельная read-only диагностическая вкладка.
- В обычных inspector tabs показывать только человекочитаемые request/result/status/duration/usage/evidence/RBAC/limits. Идентификаторы, timestamps, raw prompt/messages и технические payloads — только в ограниченном RAW/diagnostic surface.
- Для tool viewer показывать реальный outcome receipt и provenance evidence; для task/agent viewer — typed result, состояние mark/write и причины отказа. Не отображать оптимистичные утверждения модели как факт выполнения.
- Проецировать citations финального ответа из подтверждённой evidence chain успешного retrieval, а не терять их между agent result, task result и synthesis.
- Протестировать replay/live convergence: тот же canonical journal должен давать идентичное дерево и inspector state при SSE-стриме, reconnect и последующем REST replay.

## Runtime trace terminology — rename iteration to PlanRevision

- Сохранить текущую runtime-структуру на первом этапе, но в следующем breaking-изменении переименовать сущность и поля `iteration`/`planner_iteration` в `PlanRevision`.
- Зафиксировать семантику: planner decision создаёт или изменяет PlanRevision, а executor runs выполняют задачи этой версии плана.
- Не смешивать номер версии плана с визуальным этапом или параллельной волной исполнения.

## Chat stream — публичная проекция оркестратора

- Разобрать контракт `POST /chats/{chat_id}/messages`: сейчас в один SSE-поток смешаны ответ, tool request/response и диагностические решения планера.
- Оставить в chat SSE только пользовательский ответ, интеракции (`confirmation_required`, `waiting_input`, `stop`), безопасные ошибки и компактные статусы работы оркестратора.
- Убрать из chat SSE LLM-вызовы, аргументы и результаты tools, внутренние идентификаторы исполнителей и подробные события планера; эти данные доступны только в журнале ранса и sandbox stream.
- Зафиксировать отдельный публичный typed SSE contract и удалить legacy-поля/маппинг из chat transport.

## Credentials — platform level dedup

- Разобраться с дублированием credential записей на одном owner-уровне (platform/user/tenant) для одного `instance_id`.
- Добавить защиту на уровне БД (partial unique index для `is_active=true`) и безопасную дедуп-миграцию.
- Уточнить policy резолва при наличии исторических дублей (детерминированный выбор newest/updated).

## Периодические задачи — активный scheduler (отложено)

- Перевести scheduler на динамическое управление из UI (без релиза кода).
- Внедрить `celery-redbeat` для persistent beat schedule в Redis.
- Добавить в БД поля override расписания (`schedule_override`, `schedule_source`, `next_run_at`).
- Сделать sync слой PG -> RedBeat:
  - при старте beat,
  - при изменении настроек задачи,
  - периодический self-heal.
- Расширить API/UI:
  - редактирование interval/crontab,
  - preview ближайших запусков,
  - reset к default расписанию.
- Добавить ограничения безопасности для критичных задач (нельзя выключить/опасные интервалы).
- Добавить аудит изменений расписания и операторов.

## Развитие планера — частые темы пользователя как факты

- У нас уже есть факты уровня чата, пользователя и тенанта.
- Если пользователь часто задаёт вопросы по направлению (например, сеть / технические), складывать это как факт уровня user/tenant.
- Цель: «думающий модуль» (пред-планер) использует эти факты для переформулировки цели и лучшего понимания контекста запроса.
- Связано с `PLAN_AGENT_NEEDS_CONTRACT.md` (раздел «Думающий модуль» вне MVP-скоупа).

## Runtime memory — remaining lifecycle work

- Durable user/tenant/project facts, bounded read path, fact extraction,
  compaction, reconciliation and asynchronous writeback уже реализованы;
  канонический контракт описан в `docs/architecture/RUNTIME_MEMORY.md`.
- Не добавлять отдельный durable chat-memory store: conversation summary
  остаётся compatibility storage до отдельного обоснованного RFC, а active
  runtime memory использует facts и in-turn sections.
- Доработать authoring и RAG extraction для user/tenant/project memory через
  существующий `FactExtractor -> FactCompactor -> FactReconciler` flow; не
  делать extractor прямым writer-ом active memory.
- Добавить project-memory lifecycle: source refresh, retention/cleanup,
  устаревание правил и controlled removal.
- Реализовать conflict detection и review/merge workflow для противоречащих
  project/process rules; только approved revision становится active.

## Lifecycle отмена удаления с зависимостями

- Проработать единый механизм отмены удаления для `agent`, `collection`, `tenant`, `user` и связанных сущностей.
- Учитывать зависимости до удаления: показать, что будет `cascade_deleted`, `migrated`, `set_null`, `blocker`, и какие сущности реально затронутся.
- Сделать отмену не просто восстановлением статуса, а управляемым обратным действием, если soft/hard delete уже затронул дочерние сущности, RBAC, коллекции, привязки и другие зависимости.
- Зафиксировать контракт для UI: сначала dependency preview, потом подтверждение soft/hard delete, потом отдельный restore/reverse flow с понятным отчетом.
- Связано с `apps/api/src/app/api/v1/routers/admin/lifecycle.py`, `apps/api/src/app/services/lifecycle_admin_service.py`, `apps/web/src/shared/ui/LifecycleDeleteDialog.tsx`.

## Файлы-артефакты без чата

- Пересмотреть текущую модель, где `file.generate` и `template.fill` пишут через chat attachment storage и требуют `chat_id` в tool context.
- Разделить два сценария:
  - sandbox/чатовые артефакты, которые действительно привязаны к чату и показываются в чате как результаты выполнения;
  - автономные файлы-артефакты, которые можно создавать и читать без привязки к chat row.
- Если автономный режим делать отдельно, определить единый canonical storage contract для `file.read` / `file.analyze` / `file.generate` и не тащить chat-сущность в путь хранения.
- Если оставлять chat-based хранение, явно развести sandbox upload chat и обычный chat, чтобы файловые артефакты не порождали видимые чаты и не смешивались с пользовательским chat list.
- Связано с `apps/api/src/app/agents/builtins/file_generate.py`, `apps/api/src/app/agents/builtins/file_read.py`, `apps/api/src/app/agents/builtins/template_fill.py`, `apps/api/src/app/services/chat_attachment_service.py`, `apps/api/src/app/api/v1/routers/sandbox/runs.py`.

## Runtime agent result summary — пересмотреть `summary_preview`

- Позже разобраться, нужен ли вообще отдельный `summary_preview` и лимит в 800 символов.
- Проверить, не смешивает ли текущая конструкция внутренний результат задачи, bounded summary и пользовательский ответ.
- Определить отдельный контракт для task/result summary и убрать лимит либо заменить его на осмысленное bounded-представление, если оно действительно нужно.
