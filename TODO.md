# Frontend & Backend Review TODO

Аудит выполнен по правилам из `docs/frontend/RULES.md` и `docs/frontend/PATTERNS.md`.

## P0 — критично (архитектурные нарушения)

- [ ] Убрать hardcoded query keys в SSE cache update и перейти полностью на `qk.*`.
  - `apps/web/src/app/providers/applyRagEvents.ts`:
    - `['rag', 'list']` @ `invalidateQueries`, `setQueriesData`
    - `['rag', 'detail']` @ `setQueriesData`, `removeQueries`

- [ ] Убрать hardcoded query keys в hooks/pages и использовать query key factory.
  - `apps/web/src/shared/api/hooks/useAdmin.ts`
    - `['admin', 'email-settings']`
    - fallback keys `['admin', 'users', 'undefined']`, `['admin', 'models', 'undefined']`, `['admin', 'tenants', 'undefined']`
  - `apps/web/src/domains/profile/pages/ProfilePage.tsx`
    - `['profile']`, `['profile', 'tokens']`
  - `apps/web/src/domains/admin/pages/CreateCollectionPage.tsx`
    - `['admin', 'tenants']`
  - `apps/web/src/domains/admin/pages/ViewCollectionPage.tsx`
    - `['admin', 'tenants']`

## P1 — высокий приоритет (style/accessibility/maintainability)

- [ ] Убрать inline styles из админских страниц и вынести в `.module.css`.
  - `apps/web/src/domains/admin/pages/AuditPage.tsx` (множественные inline styles)
  - `apps/web/src/domains/admin/pages/CreateCollectionPage.tsx` (`div style={{ display: 'flex', ... }}`)
  - `apps/web/src/domains/admin/pages/ViewCollectionPage.tsx` (inline styles в ячейках таблицы)
  - `apps/web/src/app/router.tsx` (`withSuspense` fallback с inline padding)

- [ ] Привести типизацию к strict-правилам (убрать `any` в новом/активно изменяемом коде).
  - `apps/web/src/domains/admin/pages/AgentEditorPage.tsx` (`any` в mutation payload/error handlers)
  - `apps/web/src/domains/admin/pages/ModelEditorPage.tsx` (`err: any`, `value: any`, и т.д.)

## P2 — средний приоритет (legacy/структура)

- [ ] Сократить крупные компоненты > 250 строк через extraction в subcomponents/hooks.
  - `apps/web/src/domains/profile/pages/ProfilePage.tsx` (~419 строк)
  - `apps/web/src/domains/admin/pages/ModelEditorPage.tsx` (~481 строк)
  - `apps/web/src/domains/admin/pages/AgentEditorPage.tsx` (~295 строк)

- [ ] Закрыть legacy naming debt по `*EditorPage.tsx`.
  - Переименовать/мигрировать:
    - `apps/web/src/domains/admin/pages/AgentEditorPage.tsx`
    - `apps/web/src/domains/admin/pages/ModelEditorPage.tsx`
  - Целевой формат: `<Entity>Page.tsx` + EntityPageV2/Tab как единый контракт.

## Дополнительно (после основных фиксов)

- [ ] Унифицировать admin CRUD/query hooks: все query keys и invalidation только через `qk`.
- [ ] Добавить lint rule на запрет inline styles (кроме явно динамических случаев).
- [ ] Добавить lint/test guard на запрет queryKey массивов вне `keys.ts`.

---

## Backend Review TODO

Аудит выполнен по правилам из `docs/backend/RULES.md` и `docs/backend/PATTERNS.md`.

## P0 — критично (архитектурные/контрактные нарушения)

- [ ] Убрать ручной `commit()` в роутерах, где используется `Depends(db_uow)` (двойное управление транзакцией).
  - `apps/api/src/app/api/v1/routers/collections/upload.py` (`await session.commit()` в `upload_csv` и `delete_collection_rows`)

- [ ] Убрать rollback из repository layer и оставить управление транзакцией на API/`db_uow`/worker transaction.
  - `apps/api/src/app/repositories/base.py` (`session.rollback()` в generic repository методах)

- [ ] Убрать fallback на raw string query key/fallback-подход в tool/rbac scope logic и заменить на enum/константы для scope/status.
  - `apps/api/src/app/repositories/base.py` (`'local'/'global'` в `_build_scope_filter`)
  - `apps/api/src/app/adapters/qdrant_client.py` (`if scope == 'local' / 'global'`)

## P1 — высокий приоритет (quality/observability/security)

- [ ] Привести логирование к структурированному формату событий (не только message string).
  - `apps/api/src/app/core/logging.py` (текущий `format="%(message)s"`)
  - `apps/api/src/app/services/rbac_service.py` (строковые f-string логи без event-полей)
  - `apps/api/src/app/services/credential_service.py` (ошибки/операции логируются без стабильного event-контракта)

- [ ] Убрать хардкод дефолтных execution limit значений в runtime и вынести в config/enum слой.
  - `apps/api/src/app/agents/runtime.py` (`PolicyLimits` default constants)

## P2 — средний приоритет (maintainability/consistency)

- [ ] **RBAC: Улучшить сводную таблицу правил** - текущая таблица в RbacListPage показывает все правила без иерархии. Нужно сделать:
  - Фильтрацию по владельцу (пользователь/тенант/платформа)
  - Группировку правил по владельцам
  - Улучшенный UI для просмотра иерархии правил
  - Возможность быстрых переходов к правилам конкретного владельца

- [ ] Привести единый стиль domain errors: выделить общий иерархический набор ошибок для сервисов, где сейчас используются ad-hoc `Exception`.
  - `apps/api/src/app/services/rbac_service.py`
  - `apps/api/src/app/services/credential_service.py`

- [ ] Добавить/усилить regression tests на transactional boundaries (rollback/commit orchestration) после очистки repository layer.
  - целевые контуры: CRUD generic repos + API маршруты на `db_uow`

## Frontend Architecture: Progressive Loading & Sandbox

### P1 — высокий приоритет (архитектурное улучшение)

- [ ] **Реализовать Progressive Loading + Role-based Splitting** - разделить загрузку по ролям и доменам для оптимизации initial bundle.
  - **Phase 1: Анализ и подготовка**
    - [ ] Проанализировать текущую архитектуру роутинга и lazy loading
    - [ ] Создать sandbox домен (layouts, pages, components)
    - [ ] Создать SandboxGuard для role-based доступа
  - **Phase 2: Перенос функциональности**
    - [ ] Перенести AgentRouterPage в sandbox домен
    - [ ] Добавить sandbox роуты в основной router.tsx
    - [ ] Добавить навигацию в песочницу из AdminLayout
  - **Phase 3: Очистка и оптимизация**
    - [ ] Удалить Agent Router из админки (страница, роут, сайдбар, кнопки)
    - [ ] Настроить code splitting для domain chunks (admin, sandbox, gpt)
    - [ ] Добавить preloading для sandbox при наведении на кнопку
  - **Phase 4: Тестирование и финализация**
    - [ ] Протестировать progressive loading и кэширование
  - **Ожидаемый результат**: Initial load ~2.3MB, Admin +2.5MB, Sandbox +1.8MB, Total cached ~6.6MB

### P2 — средний приоритет (опциональные улучшения)

- [ ] Добавить feature flags для условной загрузки sandbox модуля
- [ ] Реализовать micro-frontend подход при дальнейшем росте бандла
- [ ] Добавить метрики загрузки и performance monitoring
