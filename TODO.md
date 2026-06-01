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
