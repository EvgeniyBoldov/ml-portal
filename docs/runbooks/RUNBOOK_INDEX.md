# RUNBOOK — Полный план приведения проекта к ТЗ

Ниже — последовательность этапов. Выполнять строго по порядку (можно параллелить только отмеченные подпункты). Каждый этап завершается прогоном тестов в контейнере и коротким отчётом в PR.

## Список этапов
- **STAGE_00_RULES.md** — правила выполнения и шаблон отчёта.
- **STAGE_01_URLS.md** — контракт и заведение урлов `/api/v1`, миграция old→new.
- **STAGE_02_ROUTERS_USERS.md** — перенос users под routers и удаление контроллеров.
- **STAGE_03_ERRORS_HEALTH.md** — единый формат ошибок (Problem) и health.
- **STAGE_04_RAG.md** — RAG: ingest/search/chat, единый пайплайн.
- **STAGE_05_ANALYZE.md** — Analyze поверх retrieval (sync/SSE).
- **STAGE_06_RBAC_SEED_PAT.md** — seed суперпользователя, роли, PAT.
- **STAGE_07_CONNECTORS_MODELS.md** — коннекторы LLM/Emb/Artifact/Index и каталоги моделей.
- **STAGE_08_TESTS_CLEANUP.md** — профили тестов, чистка и отчётность.
- **STAGE_09_OBSERVABILITY.md** — health/metrics/structured logs/trace-id.
- **STAGE_10_ARTIFACTS_STORAGE.md** — ArtifactStore, версионирование, TTL/ретеншн.
- **STAGE_11_FE_CLIENT_UI.md** — генерация типобезопасного клиента и базовые страницы UI.
- **STAGE_12_CI_CD.md** — быстрый/полный профили, кэш моделей/зависимостей, артефакты.
- **STAGE_13_RELEASE_VERSIONING.md** — семвер API, deprecation, CHANGELOG, миграции.
- **STAGE_14_SECURITY_SECRETS.md** — секреты, .env, токены, доступы, минимум RBAC-правил.
- **STAGE_15_PERF_CAPACITY.md** — нагрузочное тестирование, лимиты, ретраи, профилирование.
- **STAGE_16_AUDIT_SCRIPTS.md** — аудит импортов/роутов, реестр удалений и автопроверки.

> Если в процессе откроются новые требования — правим соответствующий этап и возвращаемся к уже выполненным только через отдельный mini-stage.
