# TODO

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
