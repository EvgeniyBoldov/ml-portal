# TODO

- [ ] Реализовать batch reindex orchestration для stale документов и коллекций.
  - Источник: `docs/DOCUMENT_COLLECTION_TARGET_PLAN.md` (пункт про postponed batch reindex).
  - Ожидаемый результат: фоновый пакетный реиндекс с управляемыми батчами, ретраями, наблюдаемостью и безопасной остановкой/возобновлением.

- [ ] Разделить `model limits` и `runtime budgets` в runtime v3.
  - Проблема: сейчас часть токен-лимитов смешивает ограничения модели (`SystemLLMRole.max_tokens`) и бюджет выполнения, что дает неочевидное поведение в trace и stop-логике.
  - Ожидаемый результат: независимые контракты лимитов, прозрачные причины остановки и предсказуемый учет расходов.

- [ ] Ввести и применять ограничения LLM-модели на каждом LLM-вызове (`planner` / `synthesizer` / `agent`).
  - Вызовные лимиты: `max_output_tokens` (completion cap per call), `max_input_tokens` (prompt budget до вызова), проверка `input + output <= context_window`.
  - Поведение при превышении: управляемый `trim/summarize` входа до вызова, либо корректный fail-fast с явным error code и trace reason.

- [ ] Перевести orchestrator/agent на собственные runtime-бюджеты (entity-level) и убрать остатки legacy budget-пути.
  - Orchestrator: считать `planner_steps`, `tokens_*`, `wall_time_ms`, `retries` в своем entity-budget.
  - Agent: считать `agent_steps`, `tokens_*`, `wall_time_ms`; tool-расход учитывать в дочерних tool-entity без double-count.
  - Run: агрегировать расход по дереву entity, обеспечивать stop по run-cap при превышении.

- [ ] Ввести единый lifecycle и удаление для `tenant` / `collection` / `user` / `rbac rule`.
  - Создать/доработать GC-воркер, который уже используется для sandbox sessions, чтобы он чистил все сущности со статусом `deprecated` после TTL.
  - Внедрить статусы для tenant, collection, user, rbac rule.
  - Внедрить `hard delete` для всех этих сущностей.
  - Внедрить `soft delete` через перевод сущности в `deprecated` и последующую очистку GC.
  - Добавить на фронт форму удаления с просмотром dependency graph и чекбоксами для явного `hard delete` зависимых объектов.

- [ ] Унифицировать кнопки действий на фронте (shared action buttons).
  - Проблема: сейчас на страницах админки зоопарк реализаций (`actions`, `actionButtons`, локальные стили/варианты), из-за чего поведение и видимость кнопок (`Редактировать`, `Удалить`, `Восстановить`, `Сохранить`, `Отмена`) расходятся.
  - Ожидаемый результат: единый shared-компонент/контракт для action-кнопок в entity-страницах, одинаковый порядок, варианты, состояния loading/disabled и единая логика показа по mode/lifecycle.

- [ ] Убрать `tenant.default_agent_slug` из доменной модели и runtime-контура.
  - Проблема: дефолтный агент на уровне тенанта создает скрытую связность и неочевидный fallback при оркестрации/оверрайдах.
  - Ожидаемый результат: выбор агента управляется явными правилами (runtime policy / request context), без tenant-level default agent.

- [ ] Добавить свитч `Default tenant` в форму редактирования тенанта.
  - Требование: админ должен иметь возможность назначить текущий тенант платформенным default прямо из `TenantPage`.
  - Поведение: включение свитча переносит флаг default на выбранный тенант в рамках одной транзакции; выключение у текущего default напрямую запрещено (нужно выбрать другой тенант).
