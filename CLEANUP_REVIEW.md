# Ревью легаси и мёртвого кода

Дата: 2026-11-19 — 2026-11-20 · Инструменты: pyflakes 4.1.0, vulture 2.16, tsc 5.9.3 (`--noUnusedLocals --noUnusedParameters`), knip (apps/web).

Каждая находка верифицировалась: подсчёт упоминаний идентификатора по всему репозиторию, разрешение относительных/абсолютных импортов, реестров (Celery `include`, ExtractorRegistry, agents builtins) и Docker entry points. Для секций 1–2 пересечений `getattr`-вызовов с кандидатами нет; секция 3 верифицировалась отдельно — ярусная проверка LIVE/DOC/VENDOR с учётом динамических реестров (ленивые `__getattr__`-пакеты, словари диспетчеризации; детали — в методике секции 3).

## Резюме

| Категория | Находок | Инструмент |
|---|---|---|
| Python: неиспользуемые импорты | 258 в 150 файлах | pyflakes |
| Python: мёртвые модули (никто не импортирует) | 36 + mcp-оговорки | резолв импортов |
| Python: неиспользуемые функции | 57 | vulture + верификация |
| Python: неиспользуемые классы | 67 | vulture + верификация |
| Python: неиспользуемые методы | 197 | vulture + верификация |
| Python: неиспользуемые properties | 15 | vulture + верификация |
| Python: test-only код (используется только тестами) | 57 | vulture + верификация |
| TS: неиспользуемые локальные импорты/переменные | 133 в 87 файлах | tsc |
| TS: неиспользуемые файлы | 41 | knip |
| TS: неиспользуемые зависимости | 3 + 2 dev | knip |
| TS: неиспользуемые экспорты | 252 | knip |
| TS: неиспользуемые экспортируемые типы | 243 | knip |
| TS: дублирующиеся экспорты | 69 | knip |

### Статус выполнения (обновлено 2026-11-20)

- **Секция 1 (импорты) — ✅ 2026-11-19:** 242 имени в 133 файлах (autoflake); остаток — исключённые категории + защищённые реэкспорты.
- **Секция 2 (мёртвые модули) — ✅ 2026-11-19:** 36/36 удалено.
- **Секция 3 (vulture: dead 304 + test-only 56 + limits/policies 31) — ✅ 2026-11-20:** 391/391 записей манифеста исполнены (детали — статус-блок в секции 3); таблицы БД limits/policies не тронуты; валидация — 0 регрессий (unit 78F/2084P/3S, integration 8F/44P/146S — байт-в-байт база HEAD).
- **Секция 4 (tsc: 133 в 87 файлах) — ✅ 2026-11-20:** закрыта полностью; повторный прогон даёт 0 диагностик, build/vitest/lint без регрессий (детали — статус-блок в секции 4).
- **Секция 5, шаг «файлы» — ✅ 2026-11-20:** 40/41 файлов удалено, плюс 1 каскадный и 2 осиротевших CSS; `scripts/visual-review.mjs` сохранён как документированная CLI-точка входа. knip после удаления: неиспользумых файлов 1 (только сохранённый скрипт).
- **Секция 5, шаг «экспорты» — ✅ 2026-11-20:** 254 флага → 0 (два прохода + каскады; 12 мёртвых файлов удалено дополнительно, включая `auth.ts` целиком; детали — статус-блок в секции 5). knip после: файлов 1 (сохранённый скрипт), экспортов 0, типов 252, дублей 20.
- **Секция 5, шаг «типы» — ✅ 2026-11-20:** 252 флага → 0 (один проход + каскады; 10 мёртвых каталогов `shared/ui` удалено дополнительно; детали — статус-блок в секции 5). knip после: файлов 1 (сохранённый скрипт), экспортов 0, типов 0, дублей 20.
- **Секция 5, шаг «дубли» — ✅ 2026-11-20:** 20 дублей → 0 (named-канон 15, default-канон 5, алиас 1; детали — статус-блок в секции 5).
- **Секция 5, шаг «зависимости» — ✅ 2026-11-20:** удалены `prismjs`, `rehype-prism-plus`, `rehype-raw` (runtime) и `msw`, `undici-types` (dev); lock −725 строк.
- **knip после всех шагов секции 5 — полная фиксированная точка:** файлов 1 (сохранённый `scripts/visual-review.mjs`), типов 0, экспортов 0, дублей 0, зависимостей 0.

**Итоговый diff:** 137 staged `D` (50 Python + 87 TS) + 442 unstaged `M` (включая `apps/web/package.json` и `package-lock.json`) + untracked `CLEANUP_REVIEW.md`; коммит — пользователь.

Исключено из кандидатов (намеренный код, не легаси): миграции Alembic, `models/__init__.py` (регистрация SQLAlchemy-моделей), `__init__.py`-агрегаторы, декорированные функции (FastAPI/Celery/pytest-регистрации), поля Pydantic-классов, `# noqa`, реэкспорты через `__all__` и `import x as x`.

---

## 1. Python — неиспользуемые импорты (pyflakes, 258)

> **Статус (2026-11-19, после удаления 29 модулей):** свежий прогон — 277 raw; после фильтров (`# noqa` 16, `__init__.py`-реэкспорт 11, alembic 8) и проверки реального использования — **242 безопасных в 140 файлах** (список: `/tmp/opencode/unused_by_file2.json`). Три кандидата с упоминанием имени в других строках проверены вручную — все безопасны (`core/cache.py` `asyncio` — это атрибут `redis.asyncio`; `shadow_memory_publication.py` `re` — слово в строке; `scripts/index_hipporag_documents.py` `import app.models` — родитель загружается через `from app.models.rag import ...`).
>
> **ВЫПОЛНЕНО (2026-11-19):** autoflake 2.4.0 удалил импорты — 139 файлов, +103/−219 строк. Контрольный pyflakes: осталось ровно 35 находок = исключённые категории (11 `__init__.py` + 8 alembic + 16 `# noqa`), «undefined name» без изменений (42, ранее существовавшие), синтаксических ошибок 0. autoflake также удалял избыточные `pass` после докстрингов (5 файлов без находок) — эти правки откачены для сохранения объёма «только импорты»; снести `pass` можно отдельным шагом (ruff PIE790 / autoflake проход).
>
> **Правка после первого прогона тестов:** `services/collection_service.py` — восстановлены 2 импорта-реэкспорта, которые pyflakes считает неиспользуемыми, но которые импортируют тесты: `InvalidSchemaError` (из `core.exceptions`) и `RowValidationError` (из `services/collection.field_coercion`). Кросс-проверка ast-разбором всех `from app.services.collection_service import ...` по репозиторию подтвердила: других сломанных реэкспортов нет. Итог по pyflakes: 37 находок = 35 исключённых категорий + 2 осознанных реэкспорта. **Не удалять эти 2 имени в будущих проходах** (вариант на будущее: пометить реэкспорт конвенцией `import x as x` или `__all__`).
>
> **Валидация тестами (2026-11-19, docker, исходники смонтированы):** сравнение полных прогонов с нашими правками против чистого HEAD (stash-цикл):
> - unit: **78 failed / 2182 passed / 3 skipped** — в обоих случаях, множества падений идентичны (diff пуст), 0 регрессий
> - integration: **8 failed / 44 passed / 146 skipped** — в обоих случаях, множества идентичны, 0 регрессий
> - 78 unit + 8 integration падений — ранее существовавший тест-долг (в осн. `SimpleNamespace`-фикстуры без новых атрибутов модели, напр. `collection.is_remote` в `status_snapshot_service.py`), к очистке отношения не имеет.
>
> **Итоговый diff:** 36 удалённых модулей (staged) + 133 файла правок импортов (unstaged; autoflake тронул 138, из них 5 откачены как «pass-only»), 242 удалённых имени.

Файл → список неиспользуемых имён (строка):

- `apps/api/src/app/adapters/impl/minio.py`: urllib.parse.urlparse (L6), urllib.parse.urlunparse (L6)
- `apps/api/src/app/adapters/interfaces/object_storage.py`: typing.BinaryIO (L1)
- `apps/api/src/app/agents/builtins/collection_aggregate.py`: uuid (L6)
- `apps/api/src/app/agents/builtins/collection_catalog.py`: uuid (L7)
- `apps/api/src/app/agents/builtins/collection_document_get.py`: app.services.file_delivery_service.FileDeliveryService (L20), app.core.config.get_settings (L22)
- `apps/api/src/app/agents/builtins/collection_document_list.py`: typing.Optional (L11), app.services.file_delivery_service.FileDeliveryService (L22)
- `apps/api/src/app/agents/builtins/collection_text_search.py`: typing.Optional (L16)
- `apps/api/src/app/agents/builtins/template_fill.py`: app.services.file_delivery_service.FileDeliveryService (L26)
- `apps/api/src/app/agents/builtins/template_list.py`: typing.List (L8), typing.Optional (L8), app.services.file_delivery_service.FileDeliveryService (L17)
- `apps/api/src/app/agents/context.py`: asyncio (L5)
- `apps/api/src/app/agents/execution_config_resolver.py`: typing.Any (L12), typing.Dict (L12)
- `apps/api/src/app/agents/handlers/versioned_tool.py`: abc.abstractmethod (L32)
- `apps/api/src/app/agents/operation_builder.py`: app.models.discovered_tool.DiscoveredTool (L13)
- `apps/api/src/app/agents/run_context_compact.py`: typing.List (L13)
- `apps/api/src/app/agents/runtime/agent.py`: app.agents.runtime.policy.GenerationParams (L94)
- `apps/api/src/app/agents/runtime/direct.py`: app.runtime.events.RuntimeEventType (L21)
- `apps/api/src/app/agents/runtime/tools.py`: json as _json (L1338)
- `apps/api/src/app/agents/runtime_sandbox_resolver.py`: app.agents.execution_preflight.ExecutionRequest (L12)
- `apps/api/src/app/api/mcp/llm_proxy.py`: pydantic.Field (L13)
- `apps/api/src/app/api/mcp/router.py`: typing.Dict (L10), typing.Optional (L10)
- `apps/api/src/app/api/v1/routers/admin/ai_generate.py`: app.models.agent.Agent (L15)
- `apps/api/src/app/api/v1/routers/admin/rbac.py`: fastapi.HTTPException (L11)
- `apps/api/src/app/api/v1/routers/admin/system_llm_roles.py`: app.services.system_llm_role_service.SystemLLMRoleNotFoundError (L14)
- `apps/api/src/app/api/v1/routers/admin/tool_instances.py`: sqlalchemy.orm.selectinload (L14)
- `apps/api/src/app/api/v1/routers/admin/tools.py`: fastapi.HTTPException (L17)
- `apps/api/src/app/api/v1/routers/chat/messages.py`: typing.Dict (L6)
- `apps/api/src/app/api/v1/routers/collections/documents.py`: app.models.rag_ingest.RAGStatus (L262)
- `apps/api/src/app/api/v1/routers/collections/templates.py`: typing.Optional (L9)
- `apps/api/src/app/api/v1/routers/monitoring.py`: fastapi.HTTPException (L4), fastapi.status (L4), prometheus_client.core.GaugeMetricFamily (L8), prometheus_client.core.CounterMetricFamily (L8)
- `apps/api/src/app/api/v1/routers/profile.py`: app.models.tool.Tool (L22), sqlalchemy.orm.selectinload (L32)
- `apps/api/src/app/api/v1/routers/sandbox/runs.py`: app.api.deps.get_current_user_sse (L12), app.models.sandbox.SandboxBranch (L25), app.models.sandbox.SandboxOverrideSnapshot (L25), app.models.agent.Agent (L26), app.models.agent_version.AgentVersion (L27), app.models.tool.Tool (L28), app.models.tool_release.ToolRelease (L29), app.models.collection.Collection (L30), app.models.tool_instance.ToolInstance (L31)
- `apps/api/src/app/api/v1/routers/security.py`: pydantic.EmailStr (L6)
- `apps/api/src/app/celery_app.py`: app.core.logging.get_logger (L2)
- `apps/api/src/app/core/audit.py`: sqlalchemy.Integer (L10), sqlalchemy.orm.sessionmaker (L12), sqlalchemy.Index (L284)
- `apps/api/src/app/core/cache.py`: asyncio (L5), time (L8), typing.Dict (L10), typing.Union (L10)
- `apps/api/src/app/core/health.py`: app.core.resilience.resilience_manager (L9)
- `apps/api/src/app/core/http/clients.py`: typing.Any (L2), ..circuit_breaker.CircuitBreakerConfig (L4)
- `apps/api/src/app/core/idempotency.py`: fastapi.HTTPException (L5)
- `apps/api/src/app/core/metrics.py`: time (L5), typing.Optional (L7), celery.events.EventReceiver (L14)
- `apps/api/src/app/core/observability.py`: fastapi.Response (L8)
- `apps/api/src/app/core/openapi_validator.py`: typing.Optional (L4)
- `apps/api/src/app/core/pagination.py`: typing.Dict (L4), typing.Tuple (L4), uuid (L7)
- `apps/api/src/app/core/resilience.py`: typing.Any (L4), typing.Optional (L4)
- `apps/api/src/app/core/security.py`: typing.Optional (L5)
- `apps/api/src/app/core/sse.py`: typing.Dict (L4), fastapi.HTTPException (L5), fastapi.status (L5)
- `apps/api/src/app/models/chat.py`: typing.Optional (L6)
- `apps/api/src/app/models/chat_summary.py`: sqlalchemy.String (L6)
- `apps/api/src/app/models/events.py`: sqlalchemy.Column (L7), sqlalchemy.Text (L7)
- `apps/api/src/app/models/limit.py`: sqlalchemy.Boolean (L19)
- `apps/api/src/app/models/platform_settings.py`: sqlalchemy.String (L11)
- `apps/api/src/app/models/prompt.py`: sqlalchemy.Boolean (L5)
- `apps/api/src/app/models/rag.py`: typing.Optional (L6), sqlalchemy.orm.relationship (L10)
- `apps/api/src/app/models/rag_ingest.py`: datetime.datetime (L3), typing.Optional (L4), typing.Dict (L4), typing.Any (L4), typing.List (L4), sqlalchemy.CheckConstraint (L5)
- `apps/api/src/app/models/system_llm_role.py`: sqlalchemy.Integer (L12), sqlalchemy.orm.relationship (L14)
- `apps/api/src/app/models/template_analysis_status.py`: datetime.datetime (L4), typing.Optional (L5), sqlalchemy.Integer (L7)
- `apps/api/src/app/repositories/base.py`: sqlalchemy.exc.NoResultFound (L14)
- `apps/api/src/app/repositories/chats_repo.py`: typing.Tuple (L2), sqlalchemy.func (L4), sqlalchemy.cast (L4), sqlalchemy.String (L4), sqlalchemy.dialects.postgresql.JSONB (L5)
- `apps/api/src/app/repositories/documents_repo.py`: typing.Dict (L5), typing.Any (L5), sqlalchemy.asc (L7), datetime.datetime (L8), datetime.timezone (L8)
- `apps/api/src/app/repositories/fact_admin_repository.py`: collections.abc.Sequence (L4)
- `apps/api/src/app/repositories/factory.py`: app.repositories.base.AsyncTenantRepository (L11)
- `apps/api/src/app/repositories/idempotency_repo.py`: sqlalchemy.desc (L7)
- `apps/api/src/app/repositories/model_registry_repo.py`: sqlalchemy.and_ (L7), sqlalchemy.orm.selectinload (L8), app.models.model_registry.ModelStatus (L9)
- `apps/api/src/app/repositories/prompt_repository.py`: sqlalchemy.orm.selectinload (L6)
- `apps/api/src/app/repositories/rag_ingest_repos.py`: sqlalchemy.func (L8)
- `apps/api/src/app/repositories/rag_status_repo.py`: sqlalchemy.orm.selectinload (L12)
- `apps/api/src/app/repositories/tenants_repo.py`: typing.Dict (L8), typing.Any (L8)
- `apps/api/src/app/repositories/users_repo.py`: sqlalchemy.insert (L8)
- `apps/api/src/app/runtime/agent_executor.py`: app.runtime.orchestrator_contracts.TaskConfirmationRequired (L38)
- `apps/api/src/app/runtime/assembler.py`: typing.Optional (L17)
- `apps/api/src/app/runtime/contracts.py`: uuid.UUID (L16)
- `apps/api/src/app/runtime/llm/streaming.py`: uuid.UUID (L8)
- `apps/api/src/app/runtime/memory/builder.py`: app.runtime.memory.components.ConversationMemoryComponent (L18), app.runtime.memory.components.MemoryItem (L18), app.runtime.memory.components.MemorySection (L18)
- `apps/api/src/app/runtime/memory/components.py`: typing.Iterable (L10), typing.Tuple (L10)
- `apps/api/src/app/runtime/memory/decisions.py`: dataclasses.field (L4)
- `apps/api/src/app/runtime/memory/evidence_feedback.py`: app.models.memory.MemoryItemSource (L14)
- `apps/api/src/app/runtime/memory/fact_store.py`: datetime.datetime (L20), datetime.timezone (L20)
- `apps/api/src/app/runtime/memory/shadow_memory_publication.py`: re (L6)
- `apps/api/src/app/runtime/memory/shadow_memory_review.py`: app.models.document_memory_staging.DocumentMemoryExtractionAttempt (L12)
- `apps/api/src/app/runtime/memory/writer.py`: app.models.memory.FactSource (L22)
- `apps/api/src/app/runtime/orchestrator.py`: app.runtime.orchestrator_contracts.TaskOutputFulfillment (L16), app.runtime.orchestrator_contracts.TerminalKind (L16), app.runtime.memory.effective_scope.project_memory_context (L27)
- `apps/api/src/app/runtime/pipeline.py`: os (L16), app.runtime.envelope.PhasedEvent (L31), app.runtime.memory.effective_scope.ScopeSelection (L51), app.runtime.input_builders.compact_memory_tool_records (L58)
- `apps/api/src/app/runtime/plan_store.py`: typing.Iterable (L7), typing.List (L7)
- `apps/api/src/app/runtime/ports.py`: typing.List (L22), app.agents.context.ToolContext (L33)
- `apps/api/src/app/schemas/analyze.py`: typing.List (L5)
- `apps/api/src/app/schemas/auth.py`: datetime.datetime (L7)
- `apps/api/src/app/schemas/chats.py`: typing.Union (L2), datetime.date (L4)
- `apps/api/src/app/schemas/common.py`: datetime.datetime (L6)
- `apps/api/src/app/schemas/ingest_run.py`: typing.List (L4)
- `apps/api/src/app/schemas/memory.py`: typing.Optional (L3)
- `apps/api/src/app/schemas/rag.py`: app.schemas.common.EmbeddingModel (L9)
- `apps/api/src/app/schemas/rbac.py`: typing.List (L4)
- `apps/api/src/app/schemas/sandbox.py`: app.schemas.runtime_trace.RunTraceResponse (L14)
- `apps/api/src/app/services/agent_service.py`: app.models.tool_instance.ToolInstance (L30)
- `apps/api/src/app/services/chat_artifact_reference_service.py`: datetime.timedelta (L5), sqlalchemy.and_ (L8)
- `apps/api/src/app/services/chat_context_compactor.py`: app.services.chat_context_contracts.TopicScopePayload (L15)
- `apps/api/src/app/services/chat_context_reducer.py`: typing.Any (L4)
- `apps/api/src/app/services/chat_context_service.py`: typing.Optional (L3)
- `apps/api/src/app/services/chat_stream_service.py`: uuid (L13)
- `apps/api/src/app/services/chat_summary_service.py`: sqlalchemy.update (L6)
- `apps/api/src/app/services/collection/ddl.py`: sqlalchemy.text (L12), app.models.collection.FieldCategory (L15)
- `apps/api/src/app/services/collection/field_coercion.py`: typing.Optional (L10), app.core.exceptions.InvalidSchemaError (L12), app.models.collection.FieldCategory (L13)
- `apps/api/src/app/services/collection/row_service.py`: app.core.exceptions.CollectionNotFoundError (L16)
- `apps/api/src/app/services/collection/vector_lifecycle.py`: app.models.collection.FieldCategory (L10)
- `apps/api/src/app/services/collection_csv_service.py`: typing.Any (L6)
- `apps/api/src/app/services/collection_service.py`: app.core.exceptions.InvalidSchemaError (L16), app.services.collection.field_coercion.RowValidationError (L33)
- `apps/api/src/app/services/health/adapters.py`: typing.Any (L6), typing.Dict (L6), typing.Optional (L6), app.agents.runtime.rerank_client.rerank_scores (L16)
- `apps/api/src/app/services/health/engine.py`: typing.Any (L5), typing.List (L5), typing.Type (L5), sqlalchemy.orm.selectinload (L10), app.services.health.base.HealthCheckTarget (L15), app.services.health.base.BACKOFF_POLICY_10M (L15)
- `apps/api/src/app/services/health/metrics.py`: typing.Dict (L4), typing.Any (L4), datetime.datetime (L5), datetime.timezone (L5), prometheus_client.core.CounterMetricFamily (L9)
- `apps/api/src/app/services/health/tests/test_adapters.py`: datetime.datetime (L6), app.services.health.base.HealthProbeResult (L10)
- `apps/api/src/app/services/health/tests/test_engine.py`: unittest.mock.patch (L5)
- `apps/api/src/app/services/idempotency_service.py`: app.schemas.common.ProblemDetails (L12)
- `apps/api/src/app/services/ldap_user_service.py`: app.core.ldap_client.LDAPAuthResult (L19), app.models.tenant.UserTenants (L21)
- `apps/api/src/app/services/lifecycle_admin_service.py`: sqlalchemy.String (L9)
- `apps/api/src/app/services/llm_service.py`: uuid.UUID (L7), sqlalchemy.future.select (L10), app.models.model_registry.Model (L12)
- `apps/api/src/app/services/model_health_checker.py`: enum.Enum (L18)
- `apps/api/src/app/services/model_service.py`: sqlalchemy.delete as sa_delete (L11)
- `apps/api/src/app/services/permission_service.py`: app.models.rbac.RbacRule (L18)
- `apps/api/src/app/services/platform_settings_service.py`: uuid.UUID (L6)
- `apps/api/src/app/services/prompt_service.py`: re (L3)
- `apps/api/src/app/services/rag_download.py`: typing.Optional (L4), app.models.rag.RAGDocument (L11)
- `apps/api/src/app/services/rag_status_views.py`: typing.List (L6), app.models.rag.RAGDocument (L9)
- `apps/api/src/app/services/rag_upload_service.py`: json (L7)
- `apps/api/src/app/services/runtime_evaluation_harness.py`: dataclasses.field (L4)
- `apps/api/src/app/services/runtime_hitl_policy_contract_service.py`: typing.Optional (L3)
- `apps/api/src/app/services/sandbox/run_manager.py`: typing.Tuple (L4)
- `apps/api/src/app/services/sandbox/turn_lifecycle.py`: app.models.sandbox.SandboxRun (L10)
- `apps/api/src/app/services/sandbox_override_resolver.py`: app.services.sandbox_override_blueprints.AGENT_VERSION_ALL_FIELDS as _AGENT_VERSION_ALL_FIELDS (L21)
- `apps/api/src/app/services/system_llm_role_contracts.py`: app.runtime.orchestrator_contracts.IterationProposal (L12), app.runtime.memory.fact_extractor._LLMFactOutput (L13)
- `apps/api/src/app/services/system_llm_role_service.py`: app.core.exceptions.AppError as SystemLLMRoleError (L10)
- `apps/api/src/app/services/tool_catalog_sync_service.py`: typing.Optional (L12)
- `apps/api/src/app/services/tool_instance_service.py`: sqlalchemy.select (L15), app.core.exceptions.InstanceInUseError (L18)
- `apps/api/src/app/services/tool_release_service.py`: app.core.exceptions.AppError as ToolReleaseServiceError (L20)
- `apps/api/src/app/storage/paths.py`: typing.List (L4)
- `apps/api/src/app/workers/helpers.py`: typing.Tuple (L8), app.storage.paths.get_idempotency_key (L13), app.storage.paths.get_lock_key (L13)
- `apps/api/src/app/workers/tasks_collection_export.py`: uuid (L6)
- `apps/api/src/app/workers/tasks_collection_vectorize.py`: json (L13)
- `apps/api/src/app/workers/tasks_health.py`: os (L10), datetime.timedelta (L11), typing.Optional (L12), sqlalchemy.update (L478), app.models.discovered_tool.DiscoveredTool (L480)
- `apps/api/src/app/workers/tasks_health_check.py`: datetime.datetime (L9), datetime.timezone (L9)
- `apps/api/src/app/workers/tasks_hipporag_document.py`: json (L5), app.adapters.s3_client.s3_manager (L12), app.core.config.get_settings (L14), app.models.rag.RAGDocument (L16), app.models.rag_ingest.Source (L17)
- `apps/api/src/app/workers/tasks_memory.py`: os (L10), sqlalchemy.func (L17)
- `apps/api/src/app/workers/tasks_rag_ingest/dispatch.py`: app.models.rag_ingest.RAGIngestOutbox (L12)
- `apps/api/src/app/workers/tasks_rag_ingest/embed.py`: uuid (L5)
- `apps/api/src/app/workers/tasks_rag_ingest/error_utils.py`: typing.Optional (L4)
- `apps/api/src/app/workers/tasks_rag_ingest/normalize.py`: app.services.document_artifacts.get_document_artifact (L12)
- `apps/api/src/app/workers/tasks_rag_ingest/stage_results.py`: typing.Optional (L10)
- `apps/api/src/app/workers/transaction_utils.py`: typing.AsyncContextManager (L8), typing.Callable (L8), typing.Any (L8)
- `apps/emb/src/app/main.py`: typing.Union (L11), fastapi.BackgroundTasks (L16), pydantic.validator (L17), torch (L20), numpy as np (L21)
- `mcp/hipporag/server.py`: httpx (L16)
- `mcp/hipporag/test_document_operations.py`: json (L2)
- `scripts/index_hipporag_documents.py`: app.models (L7)

## 2. Python — мёртвые модули (36)

> **ВЫПОЛНЕНО ПОЛНОСТЬЮ (2026-11-19): удалено 36 из 36** (изменения staged в git; 29 удалил пользователь, 7 доудалены после тройной перепроверки: абсолютные/относительные импорты, `from app.core import`, упоминания в конфигах — ноль ссылок).
>
> Контрольный pyflakes после финальных 7 удалений: **новых находок 0**; «undefined name» 42 → 36 (исчезли только 5×`Index` из удалённого `core/audit.py` и артефакт области прогона), «imported but unused» 37 → 36; всё, что осталось вне исключённых категорий, — строки с явным `# noqa: F401` (side-effect импорт Celery-воркера в `celery_app.py:341`, реэкспорты `core/errors.py`, optional-зависимость `doctr` в try-блоке `layout_pdf.py`) + 2 защищённых реэкспорта `collection_service.py`.
>
> **Финальная валидация (после всех 36 удалений + 242 удалённых импортов):** unit **78 failed / 2182 passed / 3 skipped** и integration **8 failed / 44 passed / 146 skipped** — полные множества падений побайтово идентичны базам HEAD (diff пуст), **0 регрессий**.

Файлы, которые не импортируются ни кодом, ни тестами, ни конфигами (Celery `include`, compose, Dockerfile), и не являются entry points. Колонка — дата последнего коммита:

| Дата последнего коммита | Файл |
|---|---|
| 2025-11-14 | `apps/api/src/app/adapters/impl/minio.py` |
| 2025-11-14 | `apps/api/src/app/adapters/interfaces/email.py` |
| 2025-11-14 | `apps/api/src/app/adapters/interfaces/object_storage.py` |
| 2025-11-14 | `apps/api/src/app/adapters/interfaces/queue.py` |
| 2025-11-14 | `apps/api/src/app/adapters/interfaces/vector_store.py` |
| 2025-11-14 | `apps/api/src/app/api/deps_authz.py` |
| 2025-11-14 | `apps/api/src/app/api/deps_idempotency.py` |
| 2025-11-14 | `apps/api/src/app/core/constants.py` |
| 2025-11-14 | `apps/api/src/app/core/jwt_keys.py` |
| 2025-11-14 | `apps/api/src/app/core/pagination.py` |
| 2025-11-14 | `apps/api/src/app/core/s3_links.py` |
| 2025-11-14 | `apps/api/src/app/schemas/auth.py` |
| 2025-11-14 | `apps/api/src/app/schemas/chat_messages.py` |
| 2025-11-14 | `apps/api/src/app/schemas/repository_schemas.py` |
| 2025-11-14 | `apps/api/src/app/workers/schemas.py` |
| 2025-12-18 | `apps/api/src/app/api/mcp/rate_limit.py` |
| 2025-12-18 | `apps/api/src/app/core/audit.py` |
| 2025-12-18 | `apps/api/src/app/core/metrics.py` |
| 2025-12-18 | `apps/api/src/app/core/observability.py` |
| 2025-12-18 | `apps/api/src/app/core/openapi_validator.py` |
| 2025-12-18 | `apps/api/src/app/core/rbac.py` |
| 2025-12-19 | `apps/api/src/app/services/rag_download.py` |
| 2026-04-16 | `apps/api/src/app/services/policy_service.py` |
| 2026-04-18 | `apps/api/src/app/services/orchestration_state.py` |
| 2026-04-19 | `apps/api/src/app/schemas/ingest_run.py` |
| 2026-04-19 | `apps/api/src/app/schemas/pagination.py` |
| 2026-04-19 | `apps/api/src/app/schemas/prompts.py` |
| 2026-05-19 | `apps/api/src/app/services/chat_summary_service.py` |
| 2026-06-05 | `apps/api/src/app/workers/tasks_health_check.py` |
| 2026-07-16 | `apps/api/src/app/core/health.py` |
| 2026-07-27 | `apps/api/src/app/runtime/stages/planner_llm_trace_emitter.py` |
| 2026-08-03 | `apps/api/src/app/agents/run_context_compact.py` |
| 2026-10-09 | `apps/api/src/app/schemas/analyze.py` |
| 2026-10-09 | `apps/api/src/app/schemas/limits.py` |
| 2026-10-09 | `apps/api/src/app/services/limit_service.py` |
| 2026-11-14 | `apps/api/src/app/agents/runtime/direct.py` |

Заметки по подтверждённым кандидатам:

- `app/workers/tasks_health_check.py` — в Celery `include` есть только `tasks_health`; модуль не подключён.
- `app/core/rbac.py` мёртв, но `models/rbac.py` и `repositories/rbac_repository.py` используются — удалять только первый.
- `app/adapters/interfaces/{email,object_storage,queue,vector_store}.py` и `app/adapters/impl/minio.py` — неиспользуемые интерфейсы/реализации из начального скелета проекта (последний коммит 2025-11).
- `app/schemas/{analyze,auth,chat_messages,ingest_run,limits,pagination,prompts,repository_schemas}.py` — схемы без потребителей.

### Оговорки: mcp-файлы исключены из списка, но требуют решения

- `mcp/hipporag/server.py` — копируется в образ, но entrypoint `worker:app`; `server.py` импортируется только unittest-файлами внутри образа. Legacy-ветка сервера — кандидат на удаление после сверки с README.
- `mcp/{adapter,atlassian,atlassian_adapter,ml_inference,netbox}/server.py` — живые entry points (`MCP_SERVER_ENTRYPOINT=server:app`).
- `mcp/sql/server.py` — закомментирован в dev-compose, но используется в prod-compose как образ `mcp-sql`.
- `mcp/hipporag/{common,document_operations,model_failures,portal}.py` — импортируются `worker.py` (flat-импорты внутри образа), живые.
- `mcp/hipporag/test_*.py` — unittest, запускаются внутри worker-образа.

---

## 3. Python — неиспользуемые функции, классы, методы, свойства (vulture + верификация)

> **ВЫПОЛНЕНО ПОЛНОСТЬЮ (2026-11-20):** все **391 запись** манифеста удалений (`.cleanup-tmp/remove_manifest.json`: dead 304 / test_only 56 / subsystem_limits_policies 31) исполнены по решениям пользователя (57 test-only — вместе с тестами; все 15 property; limits/policies — код без таблиц БД):
>
> - **dead + test-only (360 записей):** 350 определений удалены AST-скриптом `.cleanup-tmp/remove_defs.py` в 151 файле (`pass_inserted=0`, отчёт `remove_report.json`), 9 записей скипнуты как члены уже удалённых классов, `UpstreamError` (единственный miss скрипта) удалён вручную из `core/exceptions.py`.
> - **Подсистема limits/policies (31 запись):** 4 файла удалены целиком (`models/limit.py`, `models/policy.py`, `repositories/limit_repository.py`, `repositories/policy_repository.py`), 8 исключений `Limit*`/`Policy*` — из `core/exceptions.py`, реэкспорты — из `models/__init__.py`; `SandboxStepEnrichmentService` — файлом. **Таблицы `limits`/`policies` и миграции не тронуты** (решение пользователя).
> - **Зачистка тестов:** 7 тест-файлов удалены целиком (тестировали только удалённый код, вкл. eval-кейс `tests/eval/test_runtime_eval_cases.py`), 33 правлены AST-удалением обращений к удалённым именам (отчёт `remove_tests_report.json`). Коллизий нет: все 56 test-only имён в src отсутствуют; `list_tenants` удалён из сервиса, но не из роутера (живой).
> - **eval-подсистема добита:** осиротевшая фикстура `tests/eval/cases/runtime_eval_cases.json` удалена; из Makefile убраны цель `test-runtime-eval` (шаг гейта `test-backend-10-10-gate` + `.PHONY` — иначе гейт падал бы с exit 5 «no tests ran»); строка убрана из `docs/admin/RUN.md`. Выживший `services/runtime_evaluation_harness.py` чист, его unit-тест импортирует только живые имена.
> - **Два предсуществующих бага закрыты фиксом, не только удалением:** (1) `compute_schema_diff` числился мёртвым из-за пропущенного импорта в `tool_release_service.py` — метод реально достижим (роутер `admin/tools.py:368`), импорт `from app.core.schema_hash import compute_schema_diff` восстановлен, символ жив; (2) удаление test-only имён оголило реэкспорт `api/deps.py` → autoflake снёс `get_llm_client` и ломал 3 роутера (`mcp/llm_proxy.py`, `chat/chats.py`, `chat/messages.py`) — реэкспорт восстановлен с `# noqa: F401` (конвенция `core/errors.py`). Контрольный AST-свип всех 339 исчезнувших импорт-имён по 310 изменённым py-файлам (absolute + relative): других сломанных реэкспортов **0**.
> - **Валидация (docker):** collect **2362 теста / 0 ошибок**; unit **78 failed / 2084 passed / 3 skipped** — failed байт-в-байт база HEAD (78, `.cleanup-tmp/unit_failures_after.txt`), passed −98 = ровно удалённые тесты, ни один из 22 упавших файлов нами не правился/не удалялся; integration **8 failed / 44 passed / 146 skipped** — идентична базе. **0 регрессий.**
> - **Контрольный pyflakes (скоуп apps/api/src + apps/emb + mcp + scripts):** 38 unused-импортов — все из исключённых категорий + осознанные реэкспорты; diff с прогоном до фазы 3 — ровно **+1 строка** (`deps.py:15`, легитимный реэкспорт). Новых находок, требующих удаления, нет.
> - **Итоговый diff:** 50 staged `D` (36 модулей фаз 1–2 + 4 limits/policies + 1 sandbox-сервис + 7 тест-файлов + 1 eval-тест + 1 eval-фикстура) + 264 unstaged `M`. Коммит — пользователь.

### Методика

Инструменты: `vulture` 2.16 + собственная верификация (AST-триаж и токен-индекс). Пайплайн: `.cleanup-tmp/pipeline.py`, классификатор: `.cleanup-tmp/classify_few.py` (в gitignore, воспроизводятся командами из конца файла).

1. `vulture` по `apps/api/src`, `apps/api/tests`, `apps/emb`, `mcp`, `scripts` → **2333 raw-находок**.
2. AST-триаж декораторов по эмпирическому набору «живых»: FastAPI-роутеры и HTTP-глаголы (`router.*`/`app.*`, `get/post/put/patch/delete/…`, `api_route`, `on_event`), Celery (`celery_app.task`, `shared_task`), сигналы (`connect`, `listens_for`), Pydantic (`field_validator`, `model_validator`, `validator`, `field_serializer`, `computed_field`), `register_tool`, `tool_version` (реестр версий инструментов диспетчеризует по `method_name`); dunder-имена — живые. → **856 кандидатов** (412 сняты как живые по декоратору).
3. Токен-индекс по 12 582 файлам (~921k токенов) с **ярусами**:
   - **LIVE** — весь код и конфиги, включая тесты: ссылки здесь считаются использованием;
   - **DOC** — `docs/**`, `*.md`, фронтенд `.ts/.tsx/.js`: упоминания использованием не считаются (фронтенд не вызывает Python-интерналс), а фиксируются как расхождения код/документация;
   - **VENDOR** — `.long-memory-experiment/` (сторонний код эксперимента), `models_llm/` (11 ГБ скачанных моделей, ложные совпадения имён в BPE-таблицах), `templates/` (тестовые датасеты): игнор.
4. Классификация каждой LIVE-ссылки токенайзером: **USE** (вызов/обращение), **IMPORT** (после фазы 2 неиспользуемых импортов импорт = реальное использование), **DYNREF** (строка-литерал, в точности равная идентификатору: ленивые реестры `services/__init__.py::_EXPORTS`, `__getattr__`-пакеты, словарь диспетчеризации mcp-роутера — реальные динамические ссылки), **DEF** (другое определение с тем же именем), **STRING** (упоминание внутри строкового литерала/докстринга), **COMMENT**, **TEST**.

Вердикты: **0 LIVE-ссылок** → мёртвый код; ссылки только DEF/STRING/COMMENT → мёртвый код (взаимные определения и текстовые упоминания использованием не являются); все ссылки в тестах → test-only; USE/IMPORT/DYNREF → живой (ложное срабатывание vulture).

Проверено и исключено как ложные срабатывания: 2 unittest-хука (`asyncSetUp`/`asyncTearDown`, вызываются фреймворком), 12 few-объектов с динамическими ссылками, 449 объектов с >2 LIVE-ссылками.

### Итоги

| Категория | Кол-во |
|---|---|
| Мёртвый код: 0 ссылок в LIVE-ярусе (включая тесты) | 290 |
| Мёртвый код: ссылки только на определения/в строках/комментариях | 46 |
| **Итого мёртвых кандидатов** | **336** |
| — из них вообще без упоминаний где-либо | 40 |
| — из них упоминаются только в docs/web (расхождения, см. ниже) | 296 |
| Test-only: живой код, используемый только тестами (отдельное решение) | 57 |
| Ложные срабатывания vulture (динамические ссылки/много ссылок) | 12 + 449 |

По типам (0-ссылок + только-def/string): классы 67, функции 57, методы 197, свойства 15.

Не верифицировались этим пайплайном: unused-переменные/атрибуты/модульные константы из raw-выхода vulture (низкая ценность, высокий риск); неиспользуемые импорты закрыты фазой 2 (autoflake/pyflakes).

### Списки мёртвого кода по файлам

Формат: `путь:строка` · тип · имя · пометка (`docs+` — упоминается в docs/web, см. расхождения; `тест-ссылки` — на имя ссылаются тесты, при удалении править тесты).

#### `apps/api/src/app/adapters/qdrant_client.py`

- L273 · метод · `upsert_points` · docs+
- L341 · метод · `get_collection_info` · docs+

#### `apps/api/src/app/adapters/s3_client.py`

- L271 · метод · `get_object_metadata` · docs+

#### `apps/api/src/app/agents/builtins/collection_aggregate.py`

- L427 · метод · `_build_where_clause` · docs+
- L445 · метод · `_build_having_clause` · docs+

#### `apps/api/src/app/agents/builtins/collection_search.py`

- L598 · функция · `create_collection_tool` · docs+

#### `apps/api/src/app/agents/builtins/template_fill.py`

- L75 · функция · `_fill_excel` · docs+
- L97 · функция · `_fill_word` · docs+

#### `apps/api/src/app/agents/context.py`

- L90 · метод · `has_errors` · docs+
- L98 · свойство · `total_ms` · docs+
- L186 · метод · `with_runtime_deps` · docs+
- L233 · метод · `to_message_content` · docs+

#### `apps/api/src/app/agents/contracts.py`

- L52 · класс · `NextAction`
- L72 · класс · `Observation`
- L86 · класс · `PolicyDecision` · docs+
- L120 · класс · `ToolCapability` · docs+
- L301 · класс · `HelperSummary` · docs+
- L333 · класс · `OutlineProgress` · docs+
- L339 · метод · `is_phase_completed` · docs+
- L342 · метод · `mark_phase_completed` · docs+
- L346 · метод · `add_phase_note` · docs+
- L354 · класс · `StopReason` · docs+
- L363 · класс · `RuntimePipelineRequest` · docs+
- L375 · класс · `RuntimeTriageDecision` · docs+
- L388 · класс · `RuntimeExecutionSnapshot` · docs+

#### `apps/api/src/app/agents/execution_config_resolver.py`

- L148 · метод · `resolve_direct`

#### `apps/api/src/app/agents/handlers/base.py`

- L108 · метод · `to_llm_schema` · docs+

#### `apps/api/src/app/agents/handlers/versioned_tool.py`

- L262 · метод · `to_llm_schema` · docs+
- L323 · метод · `get_by_domain` · docs+

#### `apps/api/src/app/agents/json_utils.py`

- L36 · функция · `extract_json_from_text` · docs+

#### `apps/api/src/app/agents/operation_publication.py`

- L20 · метод · `to_publication_decision` · docs+
- L555 · функция · `is_operation_allowed_for_collection_type` · docs+
- L656 · функция · `get_operation_spec` · docs+
- L660 · функция · `get_collection_capability_bindings` · docs+

#### `apps/api/src/app/agents/protocol.py`

- L89 · свойство · `is_final` · docs+
- L242 · функция · `_prompt_budget` · docs+

#### `apps/api/src/app/agents/registry.py`

- L128 · метод · `register_class` · docs+
- L167 · метод · `list_mcp_descriptors` · docs+
- L178 · метод · `list_by_domain` · docs+

#### `apps/api/src/app/agents/runtime/agent.py`

- L149 · функция · `_checkpoint_receipt` · docs+
- L182 · функция · `_is_read_operation_name` · docs+

#### `apps/api/src/app/agents/runtime/base.py`

- L95 · метод · `_build_conversation_summary` · docs+

#### `apps/api/src/app/agents/runtime/tools.py`

- L1336 · метод · `format_observation_text` · docs+
- L1371 · метод · `make_summary` · docs+

#### `apps/api/src/app/agents/runtime_graph.py`

- L54 · метод · `to_legacy_maps` · docs+

#### `apps/api/src/app/agents/tool_resolver.py`

- L81 · метод · `to_prompt_context` · docs+
- L297 · функция · `_build_description` · docs+

#### `apps/api/src/app/api/deps.py`

- L88 · функция · `get_llm_client_mock` · docs+
- L139 · функция · `get_current_user_optional` · docs+
- L181 · функция · `require_tenant` · docs+

#### `apps/api/src/app/api/mcp/schemas.py`

- L24 · класс · `JSONRPCNotification` · docs+
- L214 · класс · `ListResourcesResult` · docs+
- L220 · класс · `ReadResourceParams` · docs+
- L232 · класс · `ReadResourceResult` · docs+
- L241 · класс · `PaginatedParams` · docs+

#### `apps/api/src/app/api/v1/routers/profile.py`

- L152 · функция · `get_user_from_db` · docs+

#### `apps/api/src/app/api/v1/routers/sandbox/runs.py`

- L392 · функция · `_extract_attachment_meta_from_events` · docs+

#### `apps/api/src/app/core/cache.py`

- L100 · метод · `add_to_index` · docs+
- L112 · метод · `remove_from_index` · docs+
- L136 · метод · `invalidate_index` · docs+
- L267 · функция · `get_distributed_lock` · docs+
- L323 · функция · `cache_invalidate` · docs+

#### `apps/api/src/app/core/config.py`

- L363 · функция · `get_model_path` · docs+
- L375 · функция · `get_model_parallelism` · docs+
- L387 · функция · `is_production` · docs+

#### `apps/api/src/app/core/crypto.py`

- L125 · метод · `rotate_key` · docs+

#### `apps/api/src/app/core/exceptions.py`

- L194 · класс · `SystemLLMExecutorError` · docs+
- L298 · класс · `InstanceInUseError` · docs+
- L343 · класс · `LimitNotFoundError`
- L348 · класс · `LimitVersionNotFoundError`
- L353 · класс · `LimitAlreadyExistsError`
- L358 · класс · `LimitVersionNotEditableError`
- L365 · класс · `PolicyNotFoundError`
- L370 · класс · `PolicyVersionNotFoundError`
- L375 · класс · `PolicyAlreadyExistsError`
- L380 · класс · `PolicyVersionNotEditableError`
- L437 · класс · `UpstreamError` · docs+

#### `apps/api/src/app/core/http/clients.py`

- L13 · метод · `embed_query`
- L29 · метод · `embed_query`

#### `apps/api/src/app/core/idempotency.py`

- L14 · класс · `IdempotencyMiddleware` · docs+
- L138 · функция · `create_idempotency_key_hash` · docs+

#### `apps/api/src/app/core/middleware/__init__.py`

- L259 · класс · `TracingMiddleware` · docs+
- L277 · класс · `IdempotencyMiddleware` · docs+

#### `apps/api/src/app/core/prometheus_metrics.py`

- L261 · функция · `record_task_duration` · docs+
- L269 · функция · `record_task_started` · docs+
- L278 · функция · `record_task_finished` · docs+
- L287 · функция · `record_task_failed` · docs+
- L296 · функция · `record_outbox_backlog` · docs+
- L301 · функция · `record_sse_client_connected` · docs+
- L306 · функция · `record_sse_client_disconnected` · docs+
- L311 · функция · `record_sse_delivery_lag` · docs+
- L316 · функция · `record_model_progress` · docs+

#### `apps/api/src/app/core/sse.py`

- L95 · функция · `create_sse_stream` · docs+
- L100 · функция · `heartbeat_generator` · docs+
- L106 · функция · `progress_generator` · docs+
- L143 · функция · `validate_sse_request` · docs+
- L162 · функция · `wrap_sse_stream` · docs+
- L200 · функция · `sse_response` · docs+
- L208 · функция · `sse_error` · docs+

#### `apps/api/src/app/core/startup.py`

- L206 · функция · `seed_default_agents` · docs+

#### `apps/api/src/app/models/collection.py`

- L71 · класс · `FilterOperator` · docs+
- L276 · метод · `get_required_fields` · docs+
- L343 · метод · `get_schema_mutable_fields` · docs+
- L351 · метод · `get_mutable_fields` · docs+
- L383 · свойство · `file_fields` · docs+

#### `apps/api/src/app/models/limit.py`

- L163 · свойство · `can_deactivate`

#### `apps/api/src/app/models/memory_scope.py`

- L16 · класс · `MemoryScopeType` · docs+

#### `apps/api/src/app/models/mixins/lifecycle.py`

- L45 · свойство · `is_deprecated` · docs+

#### `apps/api/src/app/models/policy.py`

- L174 · свойство · `can_deactivate`

#### `apps/api/src/app/models/tool_instance.py`

- L42 · класс · `ConnectorSubtype` · docs+
- L188 · свойство · `is_service` · docs+
- L205 · свойство · `is_model_connector` · docs+

#### `apps/api/src/app/repositories/agent_repository.py`

- L152 · метод · `archive_published_version` · docs+

#### `apps/api/src/app/repositories/base.py`

- L466 · метод · `bulk_create` · docs+

#### `apps/api/src/app/repositories/chats_repo.py`

- L206 · метод · `update_message` · docs+
- L217 · метод · `delete_message` · docs+

#### `apps/api/src/app/repositories/credential_set_repository.py`

- L217 · метод · `get_all_for_instance` · docs+

#### `apps/api/src/app/repositories/documents_repo.py`

- L130 · метод · `get_by_document_id` · docs+
- L137 · метод · `get_by_chunk_index` · docs+

#### `apps/api/src/app/repositories/events_outbox_repo.py`

- L21 · метод · `get_pending_events` · docs+
- L49 · метод · `mark_delivered` · docs+
- L74 · метод · `get_oldest_pending_seq` · docs+
- L82 · метод · `get_backlog_count` · docs+

#### `apps/api/src/app/repositories/factory.py`

- L59 · метод · `get_rag_chunks_repository` · docs+
- L65 · метод · `get_users_repository` · docs+
- L71 · метод · `get_idempotency_repository` · docs+
- L84 · метод · `get_chunk_repository` · docs+
- L96 · метод · `get_model_registry_repository` · docs+
- L102 · метод · `get_emb_status_by_source_id` · docs+
- L112 · метод · `create_chat_message` · docs+
- L117 · метод · `create_rag_document` · docs+
- L128 · метод · `get_rag_documents` · docs+
- L140 · метод · `count_rag_documents` · docs+
- L172 · метод · `get_tenants_repository` · docs+

#### `apps/api/src/app/repositories/idempotency_repo.py`

- L39 · метод · `create_key` · docs+
- L69 · метод · `is_key_active` · docs+
- L74 · метод · `delete_expired_keys` · docs+
- L92 · метод · `get_stats` · docs+

#### `apps/api/src/app/repositories/limit_repository.py`

- L14 · класс · `LimitRepository`
- L55 · метод · `list_limits`
- L70 · метод · `get_default`
- L74 · класс · `LimitVersionRepository`
- L90 · метод · `get_by_limit_and_version`
- L102 · метод · `get_active_by_limit`
- L110 · метод · `get_latest_by_limit` · docs+
- L120 · метод · `get_all_by_limit`
- L152 · метод · `deactivate_active_version`
- L174 · метод · `has_draft`

#### `apps/api/src/app/repositories/model_registry_repo.py`

- L66 · метод · `get_by_model` · docs+
- L106 · метод · `count_tenants_using` · docs+
- L113 · метод · `get_tenants_by_model` · docs+
- L120 · метод · `get_models_by_status` · docs+
- L127 · метод · `get_global_models` · docs+
- L143 · метод · `count_total` · docs+

#### `apps/api/src/app/repositories/policy_repository.py`

- L14 · класс · `PolicyRepository`
- L67 · метод · `list_policies`
- L83 · метод · `get_default`
- L88 · класс · `PolicyVersionRepository`
- L106 · метод · `get_by_policy_and_version`
- L119 · метод · `get_active_by_policy`
- L128 · метод · `get_latest_by_policy` · docs+
- L139 · метод · `get_all_by_policy`
- L174 · метод · `deactivate_active_version`
- L199 · метод · `has_draft`

#### `apps/api/src/app/repositories/prompt_repository.py`

- L115 · метод · `get_latest_by_prompt` · docs+
- L173 · метод · `has_draft`

#### `apps/api/src/app/repositories/rag_ingest_repos.py`

- L87 · метод · `bulk_upsert` · docs+
- L123 · метод · `get_texts_for_chunk_ids` · docs+
- L232 · метод · `is_source_ready` · docs+
- L240 · метод · `ready_for_source` · docs+
- L299 · метод · `get_active_models` · docs+

#### `apps/api/src/app/repositories/rag_status_repo.py`

- L179 · метод · `get_nodes_by_status` · docs+
- L186 · метод · `update_node_status` · docs+

#### `apps/api/src/app/repositories/rbac_repository.py`

- L31 · метод · `bulk_create` · docs+
- L202 · метод · `delete_by_user` · docs+
- L209 · метод · `delete_by_tenant` · docs+

#### `apps/api/src/app/repositories/template_analysis_status_repo.py`

- L120 · метод · `get_failed_row_ids` · docs+

#### `apps/api/src/app/repositories/tenants_repo.py`

- L126 · метод · `get_tenants_by_model` · docs+

#### `apps/api/src/app/repositories/tool_release_repository.py`

- L50 · метод · `get_latest` · docs+
- L176 · метод · `list_by_domain` · docs+

#### `apps/api/src/app/repositories/tool_repository.py`

- L60 · метод · `get_by_domain` · docs+

#### `apps/api/src/app/repositories/users_repo.py`

- L80 · метод · `is_user_in_tenant` · docs+

#### `apps/api/src/app/runtime/agent_executor.py`

- L1158 · метод · `_is_url_only_response` · docs+
- L1368 · метод · `_parse_structured_response` · docs+
- L1401 · метод · `_parse_needs_from_content` · docs+

#### `apps/api/src/app/runtime/assembler.py`

- L56 · метод · `memory_writer` · docs+

#### `apps/api/src/app/runtime/budgets/ledger.py`

- L49 · метод · `can_consume` · docs+

#### `apps/api/src/app/runtime/entity_ids.py`

- L39 · функция · `memory_preparation_orchestrator_id` · docs+

#### `apps/api/src/app/runtime/error_surface.py`

- L21 · функция · `looks_internal_error_text` · docs+

#### `apps/api/src/app/runtime/memory/builder.py`

- L174 · метод · `_load_summary` · docs+

#### `apps/api/src/app/runtime/memory/components.py`

- L308 · класс · `MemoryPromptRenderer` · docs+
- L353 · класс · `ConversationMemoryComponent` · docs+

#### `apps/api/src/app/runtime/memory/dto.py`

- L57 · метод · `matches_key` · docs+

#### `apps/api/src/app/runtime/memory/fact_extractor.py`

- L221 · метод · `_to_dtos` · docs+

#### `apps/api/src/app/runtime/memory/fact_store.py`

- L200 · метод · `forget`

#### `apps/api/src/app/runtime/memory/service.py`

- L19 · класс · `MemorySubject` · docs+
- L48 · метод · `agent_context` · docs+

#### `apps/api/src/app/runtime/memory/tool_ledger.py`

- L324 · функция · `_is_read_operation` · docs+

#### `apps/api/src/app/runtime/memory/writer.py`

- L533 · функция · `_fact_to_artifact_row` · docs+

#### `apps/api/src/app/runtime/ports.py`

- L54 · класс · `PlannerPort` · docs+
- L68 · класс · `TaskFailureClassifier` · docs+

#### `apps/api/src/app/runtime/task_value_normalization.py`

- L14 · функция · `normalize_task_value` · docs+

#### `apps/api/src/app/runtime/turn_preflight.py`

- L424 · метод · `_routing_request` · docs+

#### `apps/api/src/app/schemas/agents.py`

- L180 · класс · `AgentVersionInfo` · docs+

#### `apps/api/src/app/schemas/chats.py`

- L93 · класс · `ChatCreateRequest` · docs+
- L116 · класс · `ChatListResponse` · docs+
- L124 · класс · `ChatMessageCreateRequest` · docs+
- L169 · класс · `ChatMessageListResponse` · docs+
- L177 · класс · `ChatUpdateRequest` · docs+

#### `apps/api/src/app/schemas/collections.py`

- L276 · функция · `_normalize_str_list` · docs+

#### `apps/api/src/app/schemas/collections_public.py`

- L81 · класс · `PublicCollectionListResponse` · docs+

#### `apps/api/src/app/schemas/common.py`

- L68 · класс · `QueuePriority` · docs+

#### `apps/api/src/app/schemas/document_status_graph.py`

- L8 · класс · `StatusNode` · docs+

#### `apps/api/src/app/schemas/platform_settings.py`

- L47 · класс · `PlatformSettingsCreate` · docs+

#### `apps/api/src/app/schemas/rag.py`

- L25 · класс · `RAGDocumentCreate` · docs+
- L33 · класс · `RAGDocumentUpdate` · docs+
- L43 · класс · `RAGDocumentResponse` · docs+
- L77 · класс · `RAGChunkCreate` · docs+
- L82 · класс · `RAGChunkResponse` · docs+
- L91 · класс · `EmbeddingMeta` · docs+
- L117 · класс · `IngestRunCreate` · docs+
- L121 · класс · `IngestRun` · docs+

#### `apps/api/src/app/schemas/runtime_trace.py`

- L39 · класс · `RunTraceResponse` · docs+

#### `apps/api/src/app/schemas/system_llm_roles.py`

- L129 · класс · `TriageDecision` · docs+
- L166 · класс · `HelperSummaryPayload` · docs+
- L179 · класс · `TriageInput` · docs+
- L189 · класс · `PlannerInput`
- L200 · класс · `SummaryInput` · docs+

#### `apps/api/src/app/services/agent_service.py`

- L117 · метод · `get_agent_with_versions` · docs+
- L535 · метод · `resolve_agent_for_chat` · docs+

#### `apps/api/src/app/services/chat_attachment_service.py`

- L256 · метод · `get_owned_attachments_any_chat` · docs+
- L449 · метод · `delete_chat_attachments` · docs+

#### `apps/api/src/app/services/chat_turn_service.py`

- L277 · метод · `is_in_flight` · docs+

#### `apps/api/src/app/services/collection/schema_contract_service.py`

- L210 · свойство · `document_specific_field_names` · docs+
- L214 · свойство · `sql_specific_field_names` · docs+
- L218 · свойство · `api_specific_field_names` · docs+
- L222 · свойство · `template_specific_field_names` · docs+
- L354 · метод · `ensure_api_preset_fields` · docs+

#### `apps/api/src/app/services/collection/template_contract.py`

- L757 · метод · `raise_if_invalid` · docs+

#### `apps/api/src/app/services/collection/template_layout_parser.py`

- L302 · метод · `_detect_dense_regions` · docs+
- L358 · метод · `_parse_docx` · docs+
- L523 · метод · `_parse_text` · docs+
- L663 · функция · `_split_dotted` · docs+

#### `apps/api/src/app/services/collection/template_schema_builder.py`

- L348 · метод · `_columns_from_header` · docs+
- L375 · метод · `_infer_field_type` · docs+
- L387 · метод · `_hint_description` · docs+
- L410 · метод · `_label_for_token` · docs+
- L435 · метод · `_first_table_token` · docs+
- L477 · метод · `_is_required` · docs+
- L481 · метод · `_min_rows` · docs+
- L485 · метод · `_max_rows` · docs+
- L489 · метод · `_table_description` · docs+
- L493 · метод · `_region_label` · docs+

#### `apps/api/src/app/services/collection/vector_lifecycle.py`

- L273 · метод · `cleanup_collection_creation_artifacts` · docs+

#### `apps/api/src/app/services/collection_service.py`

- L96 · метод · `_coerce_row_value` · docs+
- L139 · метод · `_resolve_primary_vector_model` · docs+
- L143 · метод · `_resolve_embedding_dimensions` · docs+
- L209 · метод · `_normalize_default_sort` · docs+
- L215 · метод · `_ensure_sql_preset_fields` · docs+
- L334 · метод · `_create_remote_collection` · docs+
- L572 · метод · `_create_tool_instance_for_collection` · docs+
- L739 · метод · `_delete_tool_instance_for_collection` · docs+

#### `apps/api/src/app/services/collection_vector_service.py`

- L56 · метод · `delete_qdrant_collection` · docs+
- L122 · метод · `update_vectorization_stats` · docs+

#### `apps/api/src/app/services/credential_scope_resolver.py`

- L33 · метод · `resolve_strategy` · docs+

#### `apps/api/src/app/services/document_source_metadata_service.py`

- L170 · метод · `set_scope_unassigned` · docs+

#### `apps/api/src/app/services/extractors/base.py`

- L20 · метод · `to_json` · docs+

#### `apps/api/src/app/services/extractors/registry.py`

- L37 · метод · `register_class` · docs+

#### `apps/api/src/app/services/file_delivery_service.py`

- L170 · метод · `get_presigned_url`

#### `apps/api/src/app/services/file_formats/registry.py`

- L105 · метод · `format_for_filename` · docs+

#### `apps/api/src/app/services/health/base.py`

- L131 · метод · `should_check` · docs+

#### `apps/api/src/app/services/hipporag_service.py`

- L143 · метод · `index_document` · docs+

#### `apps/api/src/app/services/mcp_audit_service.py`

- L216 · метод · `set_tokens` · docs+

#### `apps/api/src/app/services/model_resolver.py`

- L104 · метод · `resolve_or_default` · docs+

#### `apps/api/src/app/services/outbox_helper.py`

- L51 · функция · `emit_status_change` · docs+
- L112 · функция · `emit_deleted` · docs+

#### `apps/api/src/app/services/permission_service.py`

- L55 · свойство · `allowed_collections` · тест-ссылки
- L75 · метод · `filter_instances` · docs+
- L79 · метод · `filter_agents` · docs+
- L249 · метод · `check_instance_permission` · docs+
- L259 · метод · `check_agent_permission` · docs+

#### `apps/api/src/app/services/prompt_service.py`

- L46 · метод · `create_prompt` · docs+
- L75 · метод · `get_prompt_with_recommended` · docs+
- L96 · метод · `update_prompt` · docs+
- L190 · метод · `get_all_versions` · docs+
- L262 · метод · `update_recommended_version` · docs+
- L305 · метод · `render_version` · docs+

#### `apps/api/src/app/services/rag_event_publisher.py`

- L220 · метод · `publish_document_deleted` · docs+

#### `apps/api/src/app/services/rag_ingest_service.py`

- L198 · метод · `get_progress` · docs+
- L300 · метод · `cancel_ingest` · docs+

#### `apps/api/src/app/services/rag_status_manager.py`

- L288 · метод · `_build_stage_control` · docs+

#### `apps/api/src/app/services/rbac_service.py`

- L249 · метод · `set_platform_effect` · docs+

#### `apps/api/src/app/services/sandbox_override_resolver.py`

- L110 · метод · `get_override_field_spec` · docs+
- L198 · свойство · `has_overrides` · docs+
- L277 · метод · `resolve_blueprint_state` · docs+
- L525 · метод · `get_tenant_overrides` · docs+
- L540 · метод · `get_role_overrides` · docs+
- L550 · метод · `get_tool_release_overrides` · docs+

#### `apps/api/src/app/services/sandbox_service.py`

- L151 · метод · `touch_session` · docs+
- L472 · метод · `purge_expired` · docs+

#### `apps/api/src/app/services/sandbox_step_enrichment_service.py`

- L50 · класс · `SandboxStepEnrichmentService` · тест-ссылки
- L113 · метод · `enrich` · docs+

#### `apps/api/src/app/services/status_aggregator.py`

- L318 · функция · `is_document_stale` · docs+

#### `apps/api/src/app/services/system_llm_role_service.py`

- L134 · метод · `update_planner_role` · docs+
- L138 · метод · `update_turn_preflight_role` · docs+
- L141 · метод · `update_synthesizer_role` · docs+
- L145 · метод · `update_fact_extractor_role` · docs+
- L149 · метод · `update_fact_compactor_role` · docs+

#### `apps/api/src/app/services/tenants_service.py`

- L48 · метод · `list_tenants` · тест-ссылки

#### `apps/api/src/app/services/tool_instance_service.py`

- L70 · метод · `_infer_service_provider_kind` · docs+
- L466 · метод · `resolve_instance` · docs+
- L480 · метод · `create_local_instance` · docs+
- L580 · метод · `_perform_health_check` · docs+

#### `apps/api/src/app/services/tool_release_service.py`

- L76 · метод · `list_backend_releases` · docs+
- L85 · метод · `get_backend_release` · docs+
- L116 · метод · `list_releases` · docs+
- L154 · метод · `create_release` · docs+
- L222 · метод · `update_release` · docs+
- L261 · метод · `activate_release` · docs+
- L311 · метод · `get_schema_diff` · docs+
- L343 · метод · `archive_release` · docs+

#### `apps/api/src/app/services/tool_service.py`

- L32 · метод · `get_tool_by_slug` · docs+
- L56 · метод · `delete_tool` · docs+

#### `apps/api/src/app/storage/paths.py`

- L48 · функция · `get_embeddings_manifest_path` · docs+
- L53 · функция · `get_temp_path` · docs+

#### `apps/api/src/app/workers/helpers.py`

- L17 · функция · `generate_content_hash` · docs+
- L273 · функция · `log_step_progress` · docs+
- L297 · функция · `calculate_progress` · docs+

#### `apps/api/src/app/workers/periodic_task_tracker.py`

- L18 · функция · `_get_by_task_path` · docs+

#### `apps/api/src/app/workers/tasks_rag_ingest/stage_context.py`

- L97 · свойство · `source_id_str` · docs+

#### `apps/api/src/app/workers/tasks_rag_ingest/stage_results.py`

- L135 · класс · `DocumentMemoryResult` · docs+

#### `apps/api/src/app/workers/transaction_utils.py`

- L44 · функция · `flush_for_sse` · docs+

#### `apps/emb/src/app/main.py`

- L244 · метод · `_get_model_name` · docs+

#### `mcp/atlassian/server.py`

- L41 · функция · `_auth_scheme` · docs+

#### `mcp/hipporag/portal.py`

- L144 · метод · `_init_llm_config` · docs+

#### `mcp/hipporag/server.py`

- L61 · метод · `_init_llm_config` · docs+

### Test-only: код, используемый только тестами (отдельное решение)

Продакшн-код, на который ссылаются только тесты (включая модуль `sandbox_step_enrichment_service.py` целиком — продакшн-код никогда не вызывается, только его юнит-тесты). Удаление вместе с тестами:

- `apps/api/src/app/adapters/embeddings.py`: `list_available_models` (L436), `clear_cache` (L441)
- `apps/api/src/app/adapters/impl/llm_context.py`: `allocate_context` (L58)
- `apps/api/src/app/adapters/impl/openai_compatible_llm.py`: `_provider_detail_for_diagnostics` (L614)
- `apps/api/src/app/agents/builtins/collection_doc_search.py`: `_resolve_filtered_row_ids` (L479)
- `apps/api/src/app/agents/operation_publication.py`: `canonical_operation_identity` (L646)
- `apps/api/src/app/agents/registry.py`: `register_handler` (L89), `clear_handlers` (L105)
- `apps/api/src/app/agents/runtime/agent.py`: `_required_operation_retry_instruction` (L2502)
- `apps/api/src/app/agents/runtime/agent_prompt_renderer.py`: `build_synthesis_messages` (L112)
- `apps/api/src/app/agents/runtime/llm.py`: `_coerce_tool_choice_error_to_tool_call` (L149), `_coerce_tool_choice_error_to_native_response` (L212)
- `apps/api/src/app/agents/runtime/prompt_assembler.py`: `assemble_system_operations_prompt` (L194)
- `apps/api/src/app/runtime/entity_ids.py`: `memory_recall_orchestrator_id` (L53)
- `apps/api/src/app/runtime/llm/structured.py`: `debug_payload` (L66)
- `apps/api/src/app/runtime/memory/search_contract.py`: `MemorySearchInput` (L43)
- `apps/api/src/app/runtime/memory/service.py`: `write_extracted` (L77)
- `apps/api/src/app/runtime/memory/turn_recall.py`: `recall_with_stable_scope` (L8)
- `apps/api/src/app/runtime/orchestrator.py`: `_recall_requires_rag` (L99), `_recall_requires_tool` (L106), `_has_successful_runtime_observation` (L119), `_has_successful_rag_evidence` (L135)
- `apps/api/src/app/runtime/turn_state.py`: `add_runtime_fact` (L134)
- `apps/api/src/app/services/chat_context_contracts.py`: `TopicScopePayload` (L43)
- `apps/api/src/app/services/chat_generated_file_service.py`: `ChatGeneratedFileService` (L23), `extract_and_store` (L44)
- `apps/api/src/app/services/chat_stream_service.py`: `verify_chat_access` (L76)
- `apps/api/src/app/services/collection_linking.py`: `context_domain_for_collection` (L32)
- `apps/api/src/app/services/collection_service.py`: `_validate_fields` (L84), `_validate_admin_defined_fields` (L87), `_validate_and_prepare_row_payload` (L99), `_ensure_document_preset_fields` (L212), `_create_local_collection` (L312)
- `apps/api/src/app/services/collection_vector_service.py`: `CollectionVectorService` (L17), `create_qdrant_collection` (L28), `index_row` (L64), `search_similar` (L158)
- `apps/api/src/app/services/document_text_reader.py`: `read_text_from_bytes` (L20)
- `apps/api/src/app/services/file_delivery_service.py`: `make_storage_uri` (L70), `resolve_storage_uri` (L141)
- `apps/api/src/app/services/idempotency_service.py`: `check_or_store_response` (L51), `store_response` (L122), `cleanup_expired_keys` (L183)
- `apps/api/src/app/services/model_service.py`: `get_default_model` (L318)
- `apps/api/src/app/services/prompt_service.py`: `render_active` (L300)
- `apps/api/src/app/services/rag_event_publisher.py`: `publish_document_added` (L202)
- `apps/api/src/app/services/runtime_capability_graph_service.py`: `RuntimeCapabilityGraphService` (L18)
- `apps/api/src/app/services/runtime_evaluation_harness.py`: `default_runtime_eval_cases` (L59), `evaluate_runtime_cases` (L145), `load_eval_cases` (L152)
- `apps/api/src/app/services/runtime_hitl_policy_contract_service.py`: `RuntimeHitlPolicyContractService` (L8)
- `apps/api/src/app/services/runtime_terminal_status.py`: `normalize_run_status_for_storage` (L42), `continuation_terminal_from_event` (L72), `continuation_api_status_from_terminal` (L85)
- `apps/api/src/app/services/sandbox_step_enrichment_service.py`: `sanitize_step_payload` (L58)
- `apps/api/src/app/services/system_llm_role_contracts.py`: `get_role_output_model` (L166)
- `apps/api/src/app/workers/tasks_collection_vectorize.py`: `_needs_revectorization_for_model` (L192)

### Подсистема limits/policies — мертва целиком (особый случай)

`LimitRepository`, `LimitVersionRepository`, `LimitNotFoundError` и ещё 7 исключений (`Limit*`, `Policy*`) не имеют ни одной ссылки. Модели `Limit`/`Policy`/их репозитории держит только реэкспорт в `models/__init__.py`; API-слоя нет. При этом таблицы `limits` и `policies` создаются начальной миграцией (`7ac97d34b0aa…`, строки 149 и 213) — полное удаление подсистемы затрагивает модели, репозитории, исключения, реэкспорты и требует решения по таблицам (сохранив миграции как есть или погасив).

> **Решение (2026-11-20):** код подсистемы удалён полностью; **таблицы и миграции оставлены как есть** — при желании погасить таблицы отдельной миграцией это делается независимо от очистки кода.

### Расхождения код/документация

296 из 336 мёртвых объектов упоминаются в `docs/**`, `*.md` или на фронте. По правилам репозитория документация не держит код живым; расхождения перечислены ниже (полный список с указанием файлов-документов — в `.cleanup-tmp/vulture_verified.json`, поле `doc_refs`). Ключевые:

- `app/runtime/ports.py` → `PlannerPort` — фигурирует в архитектурных доках как canonical graph planner (упоминание в докстринге самого файла и в docs): реализации нет, порт не используется.
- `app/agents/contracts.py` → `NextAction`, `Observation`, `RuntimeTriageDecision` и др. — контракты агентского слоя из доков, код не использует.
- `app/api/mcp/schemas.py` → `JSONRPCNotification`, `ReadResourceResult`, … — неиспользуемые схемы JSON-RPC.
- `app/schemas/system_llm_roles.py` → `TriageInput`/`PlannerInput`/`SummaryInput` — упоминаются только в комментариях колонок (`comment=`) начальной миграции.

---

## 4. TypeScript/React — неиспользуемые локальные объявления (tsc, 133)

> **Статус (2026-11-20) — ✅ выполнено:** 133 находки в 87 файлах закрыты полностью. Повторный прогон `tsc -p tsconfig.json --noEmit --noUnusedLocals --noUnusedParameters` — **0 диагностик**. Итоговый diff: 87 файлов, +60/−206.
>
> **Механика правок:** неиспользуемые импорты удалялись декларацией целиком либо отдельным specifier'ом; чистые инициализаторы (`const x = [...]`, `new Set(...)`) удалялись вместе со statement'ом; инициализаторы с побочными эффектами и хуки переводились в bare-call с сохранением порядка вызова (`const x = useQueryClient()` → `useQueryClient();`, `useQuery(...)`, `useMemo(...)`, `await import('react')`); неиспользуемые параметры переименованы в `_name`; элементы деструктуризации удалялись по правилам списка (хвостовые — вместе с запятой, средние — hole, объектные паттерны с `...rest` не трогались). Удаление statement проглатывает один перевод строки, bare-call его сохраняет.
>
> **Каскад:** после удаления мёртвых констант (`glossaryColumns`, `memoryColumns`, `isCreate`, `enabledCount`, `TYPE_LABELS` и др.) их зависимости стали неиспользуемыми — дочищены повторными проходами (+9, затем +2 диагностики); ещё 4 удалены вручную (`new Set([...])` в `traceState.ts`, `asString(...).toLowerCase()` в `traceProjection.ts`, `[...new Set(...)].sort()` и `activeMemoryScopes` в `MemoryPage.tsx`).
>
> **Валидация (сравнение с baseline HEAD):**
> - `tsc --noUnusedLocals --noUnusedParameters` — exit 0, 0 диагностик (было 133);
> - `npm run build` — exit 0, ✓ 5.15s (только pre-existing chunk-ворнинги);
> - `vitest --run` — 13 failed / 411 passed / 424, байт-в-байт база HEAD (проверено `git stash` изменённых файлов);
> - `npm run lint` — `@typescript-eslint/no-unused-vars` 72 → 0, `prettier/prettier` 10373 → 10341, остальные правила без изменений; exit 1 — pre-existing;
> - `prettier --check` по 87 изменённым файлам — 64 «грязных», все входят в baseline 380; новых регрессий 0.

- `src/app/providers/AuthProvider.tsx`: L17: 'logout' is declared but its value is never read
- `src/app/providers/GlobalConfirmDialog.tsx`: L4: 'React' is declared but its value is never read
- `src/domains/admin/components/AdminSidebar.tsx`: L1: 'React' is declared but its value is never read
- `src/domains/admin/components/LongMemoryTab.tsx`: L4: 'Button' is declared but its value is never read
- `src/domains/admin/components/StatCard.tsx`: L1: 'React' is declared but its value is never read
- `src/domains/admin/layouts/AdminLayout.tsx`: L1: 'React' is declared but its value is never read
- `src/domains/admin/pages/AgentPage.tsx`: L15: 'Agent' is declared but its value is never read; L16: 'AgentDetail' is declared but its value is never read; L17: 'AgentCreate' is declared but its value is never read; L18: 'AgentUpdate' is declared but its value is never read; L19: 'AgentVersion' is declared but its value is never read; L26: 'BreadcrumbItem' is declared but its value is never read
- `src/domains/admin/pages/AuditPage.tsx`: L4: 'React' is declared but its value is never read
- `src/domains/admin/pages/CollectionPage.tsx`: L6: 'useEffect' is declared but its value is never read; L397: 'isTemplateType' is declared but its value is never read
- `src/domains/admin/pages/CredentialPage.tsx`: L13: 'BreadcrumbItem' is declared but its value is never read; L16: 'Button' is declared but its value is never read
- `src/domains/admin/pages/DashboardPage.tsx`: L1: 'React' is declared but its value is never read
- `src/domains/admin/pages/MemoryPage.tsx`: L4: 'Select' is declared but its value is never read; L10: 'MemoryActionsMenu' is declared but its value is never read; L13: 'reviewColumns' is declared but its value is never read; L14: 'scopeTypeLabels' is declared but its value is never read; L23: 'glossaryColumns' is declared but its value is never read; L32: 'memoryColumns' is declared but its value is never read; L42: 'navigate' is declared but its value is never read; L51: 'setMemoryScopeType' is declared but its value is never read; L52: 'setMemoryScopeId' is declared but its value is never read; L53: 'setMemoryPage' is declared but its value is never read; L79: 'glossaryLoading' is declared but its value is never read; L79: 'glossaryError' is declared but its value is never read; L84: All destructured elements are unused; L93: 'reviewLoading' is declared but its value is never read; L93: 'reviewError' is declared but its value is never read; L117: 'selectedReviewCandidates' is declared but its value is never read; L150: 'hasActiveGlossarySelection' is declared but its value is never read; L151: 'canActivateGlossarySelection' is declared but its value is never read; L169: 'filteredGlossary' is declared but its value is never read; L175: 'memoryScopeTypes' is declared but its value is never read
- `src/domains/admin/pages/RbacListPage.tsx`: L20: 'EnrichedRule' is declared but its value is never read; L25: 'EFFECT_OPTIONS' is declared but its value is never read
- `src/domains/admin/pages/TenantPage.tsx`: L8: 'React' is declared but its value is never read; L20: 'Tenant' is declared but never used; L20: 'TenantUpdate' is declared but never used
- `src/domains/admin/pages/UserPage.test.tsx`: L55: 'React' is declared but its value is never read
- `src/domains/admin/pages/UserPage.tsx`: L22: 'User' is declared but never used
- `src/domains/admin/pages/dashboard/DashboardModels.tsx`: L1: 'React' is declared but its value is never read
- `src/domains/admin/pages/dashboard/DashboardState.tsx`: L1: 'React' is declared but its value is never read
- `src/domains/admin/pages/dashboard/DashboardTable.test.tsx`: L1: 'React' is declared but its value is never read
- `src/domains/admin/pages/dashboard/DashboardTable.tsx`: L1: 'React' is declared but its value is never read
- `src/domains/admin/pages/dashboard/DashboardTables.tsx`: L1: 'React' is declared but its value is never read
- `src/domains/admin/pages/dashboard/UsageChart.tsx`: L1: 'React' is declared but its value is never read
- `src/domains/admin/shared/rbacRuleTable.tsx`: L1: 'React' is declared but its value is never read
- `src/domains/chat/components/ChatContextPanel.tsx`: L1: 'React' is declared but its value is never read
- `src/domains/chat/components/ChatMemoryScopes.test.tsx`: L1: 'React' is declared but its value is never read
- `src/domains/chat/components/ChatMemoryScopes.tsx`: L1: 'React' is declared but its value is never read
- `src/domains/chat/components/ChatTags.tsx`: L1: 'React' is declared but its value is never read
- `src/domains/chat/components/GlobalChatStatusListener.test.tsx`: L1: 'React' is declared but its value is never read
- `src/domains/chat/components/RAGSources.tsx`: L1: 'React' is declared but its value is never read
- `src/domains/chat/contexts/ChatContext.tsx`: L1: 'React' is declared but its value is never read
- `src/domains/chat/hooks/useChatStreaming.ts`: L29: 'ChatRuntimeProgress' is declared but never used
- `src/domains/collections/pages/TemplateStatusModal.tsx`: L1: 'React' is declared but its value is never read
- `src/domains/common/pages/Forbidden.tsx`: L1: 'React' is declared but its value is never read
- `src/domains/common/pages/NotFound.tsx`: L1: 'React' is declared but its value is never read
- `src/domains/gpt/pages/ChatPage.tsx`: L1: 'React' is declared but its value is never read
- `src/domains/gpt/pages/ChatSidebar.tsx`: L1: 'React' is declared but its value is never read
- `src/domains/gpt/pages/Doc.tsx`: L1: 'React' is declared but its value is never read
- `src/domains/gpt/pages/GPTLayout.tsx`: L1: 'React' is declared but its value is never read
- `src/domains/profile/components/ProfileTenantManagement.test.tsx`: L38: 'path' is declared but its value is never read
- `src/domains/profile/pages/ProfilePage.test.tsx`: L1: 'React' is declared but its value is never read
- `src/domains/profile/pages/ProfilePage.tsx`: L5: 'React' is declared but its value is never read
- `src/domains/sandbox/components/ConfigPanel.tsx`: L107: 'TYPE_LABELS' is declared but its value is never read; L173: 'PLATFORM_LIMIT_KEYS' is declared but its value is never read; L747: 'handleAgentVersionChange' is declared but its value is never read
- `src/domains/sandbox/components/RunChat.tsx`: L17: 'Tooltip' is declared but its value is never read; L195: 'onSelectRun' is declared but its value is never read
- `src/domains/sandbox/components/SessionSidebar.tsx`: L7: 'Button' is declared but its value is never read; L59: 'session' is declared but its value is never read
- `src/domains/sandbox/components/traceInspector/TraceInspector.tsx`: L1: 'InspectorExpandableValue' is declared but its value is never read
- `src/domains/sandbox/layouts/SandboxLayout.tsx`: L5: 'React' is declared but its value is never read
- `src/domains/sandbox/pages/SandboxSessionPage.tsx`: L21: 'ConfirmWriteDialog' is declared but its value is never read
- `src/domains/sandbox/traceProjection.ts`: L1229: 'kind' is declared but its value is never read; L2911: 'runStatus' is declared but its value is never read
- `src/domains/sandbox/traceState.ts`: L40: 'isCreate' is declared but its value is never read
- `src/shared/api/hooks/useAdmin.ts`: L74: 'variables' is declared but its value is never read
- `src/shared/api/hooks/useAgents.ts`: L30: 'id' is declared but its value is never read
- `src/shared/api/hooks/usePlatformSettings.ts`: L10: 'PlatformSettings' is declared but its value is never read
- `src/shared/components/statusFlow/longMemoryFlow.test.tsx`: L1: 'React' is declared but its value is never read; L3: 'describe' is declared but its value is never read
- `src/shared/hooks/useAIGenerate.ts`: L14: 'entityType' is declared but its value is never read; L15: 'queryClient' is declared but its value is never read
- `src/shared/hooks/useRBAC.ts`: L20: 'scope' is declared but its value is never read
- `src/shared/ui/AIGenerateButton.tsx`: L4: 'React' is declared but its value is never read
- `src/shared/ui/Breadcrumbs/Breadcrumbs.tsx`: L1: 'React' is declared but its value is never read
- `src/shared/ui/CompactStatusBlock/CompactStatusBlock.tsx`: L7: 'React' is declared but its value is never read
- `src/shared/ui/ContractAwareEditor/ContractLegend.tsx`: L3: 'SchemaTreeRenderer' is declared but its value is never read; L15: 'hasSchemaShape' is declared but its value is never read
- `src/shared/ui/CredentialsPanel/CredentialsPanel.tsx`: L11: 'React' is declared but its value is never read
- `src/shared/ui/EntityField/EntityField.tsx`: L12: 'React' is declared but its value is never read
- `src/shared/ui/EntityPage/EntityPage.tsx`: L57: 'entityTypeLabel' is declared but its value is never read
- `src/shared/ui/FactsPanel/FactsPanel.tsx`: L1: 'React' is declared but its value is never read
- `src/shared/ui/FieldEditor.tsx`: L4: 'React' is declared but its value is never read
- `src/shared/ui/JSONDisplay/JSONDisplay.tsx`: L11: 'React' is declared but its value is never read
- `src/shared/ui/JSONDisplay/JSONDisplaySimple.tsx`: L6: 'React' is declared but its value is never read
- `src/shared/ui/LifecycleDeleteDialog.tsx`: L1: 'React' is declared but its value is never read
- `src/shared/ui/Modal.test.tsx`: L1: 'React' is declared but its value is never read
- `src/shared/ui/RbacRuleBlock/RbacRuleBlock.tsx`: L5: 'React' is declared but its value is never read; L67: 'isEditable' is declared but its value is never read
- `src/shared/ui/RbacRuleBlock/RbacTargetBlock.tsx`: L5: 'React' is declared but its value is never read
- `src/shared/ui/RbacRuleBlock/ResourceSelector.tsx`: L4: 'React' is declared but its value is never read
- `src/shared/ui/RbacRulesEditor/RbacRulesEditor.tsx`: L6: 'React' is declared but its value is never read
- `src/shared/ui/RbacTargetBlock/RbacTargetBlock.tsx`: L4: 'React' is declared but its value is never read; L21: 'editable' is declared but its value is never read
- `src/shared/ui/RowActions.tsx`: L5: 'React' is declared but its value is never read
- `src/shared/ui/Select/Select.tsx`: L114: 'enabledCount' is declared but its value is never read
- `src/shared/ui/Table.tsx`: L45: '_onSelectionChange' is declared but its value is never read
- `src/shared/ui/ThemeSwitch.tsx`: L38: 'showLabel' is declared but its value is never read
- `src/shared/ui/Toggle.tsx`: L4: 'React' is declared but its value is never read
- `src/shared/ui/VersionsBlock/VersionsBlock.tsx`: L7: 'React' is declared but its value is never read; L45: 'selectedVersion' is declared but its value is never read; L48: 'onSetRecommended' is declared but its value is never read
- `src/shared/ui/builders/EntityBuilder/EntityBuilder.tsx`: L7: 'ContentBlock' is declared but its value is never read; L37: 'className' is declared but its value is never read
- `src/shared/ui/fields/BadgeField.tsx`: L4: 'React' is declared but its value is never read; L21: 'editable' is declared but its value is never read; L22: 'disabled' is declared but its value is never read
- `src/shared/ui/fields/BooleanField.tsx`: L4: 'React' is declared but its value is never read
- `src/shared/ui/fields/CodeField.tsx`: L4: 'React' is declared but its value is never read
- `src/shared/ui/fields/DateField.tsx`: L4: 'React' is declared but its value is never read; L20: 'editable' is declared but its value is never read; L21: 'disabled' is declared but its value is never read
- `src/shared/ui/fields/SelectField.tsx`: L4: 'React' is declared but its value is never read
- `src/shared/ui/fields/TextField.tsx`: L4: 'React' is declared but its value is never read
- `src/shared/ui/fields/TextareaField.tsx`: L4: 'React' is declared but its value is never read

---

## 5. TypeScript/React — knip

### Неиспользуемые файлы (41) — не импортируются ниоткуда

> **Статус шага (2026-11-20) — ✅ выполнено:** удалено 40/41 файлов списка, плюс 1 каскадный (`src/domains/sandbox/components/ConfirmWriteDialog.tsx` — стал неиспользуемым после удаления мёртвого импорта в секции 4) и 2 осиротевших CSS (`ResourceSelector.module.css`, `Field.module.css` — импортировались только удалёнными компонентами). `apps/web/scripts/visual-review.mjs` **сохранён**: это CLI-точка входа документированного сценария визуального ревью (`docs/admin/RUN.md`, `.codex/agents/designer.toml`), а не мёртвый код.
>
> Повторный knip: неиспользуемых файлов — **1** (только сохранённый `visual-review.mjs`); экспортов 254, типов 245, дублей 69, зависимостей 3 + 2 dev (без изменений). Валидация: `tsc --noUnusedLocals --noUnusedParameters` — 0 диагностик; `npm run build` — exit 0, ✓ 5.26s; `vitest --run` — 13 failed / 411 passed / 424 (baseline HEAD); `npm run lint` — prettier 10373 → 10131, `no-explicit-any` 96 → 88, остальные правила не выросли; `format:check` — 357 «грязных» (baseline 380), новых 0.

- `scripts/visual-review.mjs` — **сохранён** (документированный CLI-сценарий, не импортируется кодом)
- `src/domains/admin/components/MemoryCandidateTagEditor.tsx`
- `src/domains/admin/components/MemoryReviewRelations.tsx`
- `src/domains/admin/pages/platformLimitsTooltips.ts`
- `src/domains/collections/components/CollectionDocumentStatus.tsx`
- `src/domains/gpt/pages/Doc.tsx`
- `src/entities/auth/index.ts`
- `src/shared/api/hooks/useAuth.ts`
- `src/shared/configs/commonFields.ts`
- `src/shared/hooks/useRbacRuleCreate.ts`
- `src/shared/hooks/useVersionActions.tsx`
- `src/shared/interfaces/entities/index.ts`
- `src/shared/interfaces/forms/index.ts`
- `src/shared/lib/auth.ts`
- `src/shared/lib/badgeHelpers.ts`
- `src/shared/lib/statusConfig.ts`
- `src/shared/lib/storage.ts`
- `src/shared/lib/templateSchemaSummary.ts`
- `src/shared/lib/utils.ts`
- `src/shared/schemas/admin.ts`
- `src/shared/schemas/auth.ts`
- `src/shared/schemas/index.ts`
- `src/shared/schemas/rag.ts`
- `src/shared/ui/builders/EntityBuilder/EntityBuilder.tsx`
- `src/shared/ui/builders/EntityBuilder/index.ts`
- `src/shared/ui/fields/BadgeField.tsx`
- `src/shared/ui/fields/BooleanField.tsx`
- `src/shared/ui/fields/CodeField.tsx`
- `src/shared/ui/fields/DateField.tsx`
- `src/shared/ui/fields/index.ts`
- `src/shared/ui/fields/NumberField.tsx`
- `src/shared/ui/fields/SelectField.tsx`
- `src/shared/ui/fields/TextareaField.tsx`
- `src/shared/ui/fields/TextField.tsx`
- `src/shared/ui/JSONDisplay/JSONDisplaySimple.tsx`
- `src/shared/ui/JSONDisplay/useJSONActions.tsx`
- `src/shared/ui/RbacRuleBlock/index.ts`
- `src/shared/ui/RbacRuleBlock/RbacRuleBlock.tsx`
- `src/shared/ui/RbacRuleBlock/RbacTargetBlock.tsx`
- `src/shared/ui/RbacRuleBlock/ResourceSelector.tsx`
- `src/shared/ui/RbacTargetBlock/RbacTargetBlock.tsx`

### Неиспользуемые зависимости (3)

> **Статус шага (2026-11-20) — ✅ выполнено** (вместе с devDependencies, см. ниже): `prismjs`, `rehype-prism-plus`, `rehype-raw` удалены из `apps/web/package.json` (`npm uninstall --legacy-peer-deps`); перед удалением проверено отсутствие упоминаний в `src/`, `e2e-tests/`, `scripts/`, конфигах vitest/vite. `package-lock.json` обновлён (−725 строк).

- `prismjs`
- `rehype-prism-plus`
- `rehype-raw`

### Неиспользуемые devDependencies (2)

> **Статус шага (2026-11-20) — ✅ выполнено:** `msw`, `undici-types` удалены. Проверки: `msw` не упоминается ни в `src/test/setup.ts`, ни в тестах, ни в скриптах; `undici-types` импортируется только типами `@types/node` (`fetch.d.ts`, `worker_threads.d.ts`) — резолв уходит на локальный ambient-шим `src/types/undici-types.d.ts` (он ровно для этого и существует), `tsc` остаётся чистым.

- `msw`
- `undici-types`

### Незадекларированные зависимости (1)

- `@eslint/js eslint.config.js:1:16`

### Неиспользуемые экспорты (252)

> **Статус шага (2026-11-20) — ✅ выполнено:** 254 флага knip → **0** (два прохода + каскады). Правила решений: используется только внутри файла → снять `export`; не используется нигде → удалить декларацию/назначение; re-export в barrel → удалить specifier/строку; экспортируемые типы не тронуты (отдельный шаг).
>
> **Проход 1** (снимок knip: 254 флага в 111 файлах; анализатор `.cleanup-tmp/fix_ts_exports.mjs`): 232 правки в 111 файлах — unexport 46, delete-statement 69, remove-assign 37 (мёртвые `export default`), delete-export-decl 64 (мёртвые строки barrel, осн. часть — `shared/ui/index.ts`), remove-specifier 16; skip 2 → решены вручную (см. auth.ts ниже). Анализатор резолвит ссылки через `ts.resolveModuleName` по tsconfig (paths, Bundler), различает named/default, классифицирует ссылки internal/live/cascade/ignore, разворачивает транзитивные barrel-цепочки и гонит каскады до фиксированной точки; «словесные» упоминания имени в чужих файлах без импорта — ignore; хиты в `.py`/`.md`/models_llm — note-only (правки не блокируют).
>
> **Каскады после прохода 1:** снятие экспортов обнажило неиспользуемые локалы — `.cleanup-tmp/fix_ts_locals.mjs` в 3 итерациях (20+11+1 файлов); остаток — 5 локальных type-интерфейсов без потребителей (`RbacRulesEditorProps`, `TabType`, `FieldInfo`, `VariantInfo`, `TabPanelProps`) удалены вручную. Опустевшие файлы удалены через `git rm`: `ContractAwareEditor/index.ts`, `AdminHeader.tsx` + `AdminHeader.module.css`, `ServerDataTable.tsx`, `EntityField/` (3 файла), `FieldEditor.tsx` + `.module.css`, `RowActions.tsx`, `InspectorEmpty.tsx`.
>
> **Проход 2** (свежий knip: 9 флагов в 8 файлах — каскадно всплывшие): 7 правок в 7 файлах (delete 5, remove-specifier 2). Skip 2 — `login`/`me` в `src/shared/api/auth.ts`: knip-хиты в e2e проверены вручную, оказались шумом (URL `**/auth/me`, текст теста «login form», `record.login` в чужих типах; импортов нет) → файл мёртв целиком (единственный потребитель — строка `export * from './auth'` в api barrel): удалён вместе с этой строкой.
>
> **Итог (knip, фиксированная точка):** files 1 (сохранённый `visual-review.mjs`), **exports 0**, types 245 → 252, duplicates 69 → 20 (дубли реэкспортов исчезли вместе с мёртвыми строками barrel). Валидация: `tsc` plain — 0; с `--noUnusedLocals --noUnusedParameters` — 0; `npm run build` — exit 0 (✓ 5.15s); `vitest --run` — 13 failed / 411 passed / 424 = baseline; lint: prettier 10131 → 10025, `no-explicit-any` 88 → 81, `no-restricted-imports` 40 = 40, `no-undef` 33 = 33, `exhaustive-deps` 16 → 15; `format:check` — 350 «грязных» (baseline 357), новых 0 (6 файлов, загрязнённых правками, отформатированы prettier).
>
> **Note:** `docs/frontend/PATTERNS.md`/`RULES.md` упоминают имена компонентов (`ErrorBoundary`, `ToastProvider`, `VersionsBlock`, `Popover`) — проверено: это JSX-примеры и списки без импортов из barrel; сами компоненты живы (удалены только мёртвые строки реэкспорта) → доки валидны, правки не требуются.

- `default` — function src/app/providers/ThemeProvider.tsx:108:16
- `useModalOpen` — src/app/store/app.store.ts:185:14
- `useDropdownOpen` — src/app/store/app.store.ts:188:14
- `useSelectedUsers` — src/app/store/app.store.ts:192:14
- `useSelectedModels` — src/app/store/app.store.ts:194:14
- `useSelectedTenants` — src/app/store/app.store.ts:196:14
- `useSidepanelOpen` — src/app/store/app.store.ts:198:14
- `useActiveTab` — src/app/store/app.store.ts:200:14
- `AdminHeader` — function src/domains/admin/components/AdminHeader.tsx:52:17
- `AdminSidebar` — src/domains/admin/components/index.ts:1:10
- `AdminHeader` — src/domains/admin/components/index.ts:2:10
- `memoryTypeLabels` — src/domains/admin/components/MemoryContentView.tsx:13:14
- `memoryStateLabels` — src/domains/admin/components/MemoryContentView.tsx:17:14
- `scopeLabels` — src/domains/admin/components/MemoryReviewTable.tsx:6:14
- `readinessLabels` — src/domains/admin/components/MemoryReviewTable.tsx:7:14
- `candidateReadiness` — src/domains/admin/components/MemoryReviewTable.tsx:13:14
- `AdminLayout` — function src/domains/admin/layouts/AdminLayout.tsx:8:17
- `AuditPage` — function src/domains/admin/pages/AuditPage.tsx:17:17
- `COLLECTION_TYPE_OPTIONS` — src/domains/admin/pages/collection/fields/blockConfigs.ts:4:14
- `STATUS_FIELDS` — src/domains/admin/pages/collection/fields/blockConfigs.ts:208:14
- `DOCUMENT_PRESET_FIELDS` — …omains/admin/pages/collection/fields/collectionFieldPresets.ts:3:14
- `TEMPLATE_PRESET_FIELDS` — …omains/admin/pages/collection/fields/collectionFieldPresets.ts:9:14
- `SQL_PRESET_FIELDS` — …mains/admin/pages/collection/fields/collectionFieldPresets.ts:19:14
- `DOCUMENT_SPECIFIC_FIELD_NAMES` — …mains/admin/pages/collection/fields/collectionFieldPresets.ts:41:14
- `TEMPLATE_SPECIFIC_FIELD_NAMES` — …mains/admin/pages/collection/fields/collectionFieldPresets.ts:42:14
- `formatSchemaPropertyType` — function src/domains/admin/pages/collection/sqlSchema.ts:1:17
- `CollectionListPage` — function src/domains/admin/pages/CollectionListPage.tsx:60:17
- `CollectionPage` — function src/domains/admin/pages/CollectionPage.tsx:209:17
- `DashboardPage` — function src/domains/admin/pages/DashboardPage.tsx:20:17
- `hasModelCharacteristic` — src/domains/admin/pages/modelPageFields.ts:3:14
- `TenantsListPage` — function src/domains/admin/pages/TenantsListPage.tsx:15:17
- `UsersListPage` — function src/domains/admin/pages/UsersListPage.tsx:14:17
- `RBAC_RESOURCE_TYPE_DISPLAY_LABELS` — src/domains/admin/shared/rbacLabels.ts:31:14
- `RBAC_RESOURCE_TYPE_ORDER` — src/domains/admin/shared/rbacLabels.ts:43:14
- `formatRbacOwnerLabel` — function src/domains/admin/shared/rbacLabels.ts:53:17
- `resolveRbacOwnerLabel` — function src/domains/admin/shared/rbacRuleTable.tsx:21:17
- `resolveRbacResourceLabel` — function src/domains/admin/shared/rbacRuleTable.tsx:25:17
- `default` — function src/domains/chat/components/ChatComposer.tsx:368:16
- `getRecentDistinctProgress` — function src/domains/chat/components/ChatRunStatus.tsx:6:17
- `ChatComposer` — src/domains/chat/components/index.ts:2:10
- `UserMessage` — src/domains/chat/components/index.ts:3:10
- `AssistantMessage` — src/domains/chat/components/index.ts:4:10
- `ChatRunStatus` — src/domains/chat/components/index.ts:5:10
- `ChatAttachments` — src/domains/chat/components/index.ts:6:10
- `ChatContextPanel` — src/domains/chat/components/index.ts:7:10
- `typeLabels` — src/domains/collections/components/CollectionPresentation.tsx:9:14
- `collectionReadiness` — function src/domains/collections/components/CollectionPresentation.tsx:25:17
- `collectionDescription` — function src/domains/collections/components/CollectionPresentation.tsx:31:17
- `collectionCount` — function src/domains/collections/components/CollectionPresentation.tsx:36:17
- `truncateTemplateIdentifier` — function src/domains/collections/pages/templateStatusPresentation.ts:63:17
- `default` — function src/domains/rag/components/StatusModalNew.tsx:594:16
- `llmMessages` — function src/domains/sandbox/callInspection.ts:139:17
- `ConfigPanel` — function src/domains/sandbox/components/ConfigPanel.tsx:295:17
- `LlmTokenUsage` — function src/domains/sandbox/components/traceInspector/CallViews.tsx:14:17
- `LlmRequestView` — src/domains/sandbox/components/traceInspector/CallViews.tsx:126:14
- `LlmResponseView` — src/domains/sandbox/components/traceInspector/CallViews.tsx:127:14
- `AgentResultViewer` — src/domains/sandbox/components/traceInspector/ResultViews.tsx:107:14
- `SynthesizerResultViewer` — src/domains/sandbox/components/traceInspector/ResultViews.tsx:108:14
- `ExtractionResultViewer` — src/domains/sandbox/components/traceInspector/viewers/index.ts:6:10
- `TokenUsageViewer` — src/domains/sandbox/components/traceInspector/viewers/index.ts:12:27
- `LlmRequestViewer` — src/domains/sandbox/components/traceInspector/viewers/index.ts:12:71
- `LlmResponseViewer` — …c/domains/sandbox/components/traceInspector/viewers/index.ts:12:116
- `ToolRequestViewer` — …c/domains/sandbox/components/traceInspector/viewers/index.ts:12:154
- `ToolResponseViewer` — …c/domains/sandbox/components/traceInspector/viewers/index.ts:12:193
- `AgentResultViewer` — src/domains/sandbox/components/traceInspector/viewers/index.ts:13:10
- `SynthesizerResultViewer` — src/domains/sandbox/components/traceInspector/viewers/index.ts:13:29
- `PlanViewer` — src/domains/sandbox/components/traceInspector/viewers/index.ts:14:27
- `useSandboxCatalog` — function src/domains/sandbox/hooks/useSandboxNavigation.ts:6:17
- `useUpdateSession` — function src/domains/sandbox/hooks/useSandboxSession.ts:36:17
- `traceResultStatusLabel` — src/domains/sandbox/traceProjection.ts:660:14
- `tabsForTarget` — function src/domains/sandbox/traceProjection.ts:721:17
- `TOKEN_SCOPES` — src/shared/api/admin.ts:1029:14
- `SCOPE_HIERARCHY` — src/shared/api/admin.ts:1045:14
- `expandScopes` — function src/shared/api/admin.ts:1056:17
- `login` — function src/shared/api/auth.ts:4:23
- `me` — function src/shared/api/auth.ts:14:23
- `logout` — function src/shared/api/auth.ts:18:23
- `useAgentDetail` — src/shared/api/hooks/index.ts:1:24
- `useUpdateModel` — function src/shared/api/hooks/useAdmin.ts:67:17
- `useModel` — function src/shared/api/hooks/useAdmin.ts:133:17
- `useCreateModel` — function src/shared/api/hooks/useAdmin.ts:142:17
- `useDeleteModel` — function src/shared/api/hooks/useAdmin.ts:153:17
- `useHealthCheckModel` — function src/shared/api/hooks/useAdmin.ts:164:17
- `useHealthCheckAllModels` — function src/shared/api/hooks/useAdmin.ts:176:17
- `useTenants` — function src/shared/api/hooks/useAdmin.ts:191:17
- `useAuditLog` — function src/shared/api/hooks/useAdmin.ts:251:17
- `useOrchestrationSettings` — function src/shared/api/hooks/usePlatformSettings.ts:38:17
- `useUpdateOrchestrationSettings` — function src/shared/api/hooks/usePlatformSettings.ts:46:17
- `useUpdateOrchestratorExecutionLimits` — function src/shared/api/hooks/usePlatformSettings.ts:177:17
- `useUpdateTurnPreflightRole` — function src/shared/api/hooks/usePlatformSettings.ts:232:17
- `useUpdatePlannerRole` — function src/shared/api/hooks/usePlatformSettings.ts:246:17
- `useUpdateSynthesizerRole` — function src/shared/api/hooks/usePlatformSettings.ts:293:17
- `useUpdateFactExtractorRole` — function src/shared/api/hooks/usePlatformSettings.ts:308:17
- `useUpdateFactCompactorRole` — function src/shared/api/hooks/usePlatformSettings.ts:323:17
- `ApiError` — src/shared/api/index.ts:14:10
- `toApiError` — src/shared/api/index.ts:14:20
- `setAuthTokens` — src/shared/api/index.ts:15:22
- `clearAuthTokens` — src/shared/api/index.ts:15:37
- `getAccessToken` — src/shared/api/index.ts:15:54
- `refreshAccessToken` — src/shared/api/index.ts:15:70
- `promptsApi` — src/shared/api/prompts.ts:96:14
- `STAGE_ORDER` — src/shared/api/types/documentStatus.ts:27:14
- `default` — function src/shared/components/statusFlow/StatusFlowDetails.tsx:189:16
- `compareFlowNodePriority` — function src/shared/components/statusFlow/statusFlowUtils.ts:89:17
- `default` — function src/shared/components/statusFlow/StatusFlowView.tsx:332:16
- `DOCUMENT_MEMORY_EXTRACTOR_INPUT_CONTRACT` — src/shared/constants/orchestratorContracts.ts:175:14
- `default` — function src/shared/hooks/useStatusConfig.ts:143:16
- `normalizeVersionStatus` — function src/shared/hooks/useVersionLifecycleActions.tsx:30:17
- `default` — function src/shared/hooks/useVersionLifecycleActions.tsx:152:16
- `getTheme` — function src/shared/lib/theme.ts:13:17
- `setTheme` — function src/shared/lib/theme.ts:27:17
- `toggleTheme` — function src/shared/lib/theme.ts:37:17
- `default` — function src/shared/ui/AdminPage/AdminPage.tsx:126:16
- `default` — src/shared/ui/AdminPage/index.ts:2:23
- `default` — function src/shared/ui/AppHeader/AppHeader.tsx:134:16
- `default` — src/shared/ui/AppHeader/index.ts:2:10
- `BaseLayout` — function src/shared/ui/BaseLayout/BaseLayout.tsx:62:17
- `SplitLayout` — function src/shared/ui/BaseLayout/BaseLayout.tsx:73:17
- `TabsLayout` — function src/shared/ui/BaseLayout/BaseLayout.tsx:87:17
- `default` — function src/shared/ui/BaseLayout/BaseLayout.tsx:113:16
- `BaseLayout` — src/shared/ui/BaseLayout/index.ts:1:10
- `SplitLayout` — src/shared/ui/BaseLayout/index.ts:1:22
- `TabsLayout` — src/shared/ui/BaseLayout/index.ts:1:35
- `default` — function src/shared/ui/Breadcrumbs/Breadcrumbs.tsx:52:16
- `default` — src/shared/ui/Breadcrumbs/index.ts:1:23
- `CompactStatusBlock` — function src/shared/ui/CompactStatusBlock/CompactStatusBlock.tsx:24:17
- `default` — function src/shared/ui/CompactStatusBlock/CompactStatusBlock.tsx:39:16
- `CompactStatusBlock` — src/shared/ui/CompactStatusBlock/index.ts:4:10
- `default` — function src/shared/ui/ContentBlock/ContentBlock.tsx:231:16
- `default` — function src/shared/ui/ContentBlock/ContentGrid.tsx:34:16
- `ContentGrid` — src/shared/ui/ContentBlock/index.ts:5:10
- `default` — function src/shared/ui/ContractAwareEditor/ContractAwareEditor.tsx:174:16
- `ContractAwareEditor` — src/shared/ui/ContractAwareEditor/index.ts:1:10
- `ContractCriteriaBlock` — function src/shared/ui/ContractCriteriaBlock/ContractCriteriaBlock.tsx:8:17
- `ContractCriteriaBlock` — src/shared/ui/ContractCriteriaBlock/index.ts:1:10
- `ContractFieldsBlock` — function src/shared/ui/ContractFieldsBlock/ContractFieldsBlock.tsx:68:17
- `ContractFieldsBlock` — src/shared/ui/ContractFieldsBlock/index.ts:1:10
- `EntityCardItem` — function src/shared/ui/EntityCard/EntityCard.tsx:49:17
- `default` — function src/shared/ui/EntityCard/EntityCard.tsx:76:16
- `EntityCardItem` — src/shared/ui/EntityCard/index.ts:1:22
- `EntityField` — function src/shared/ui/EntityField/EntityField.tsx:61:17
- `default` — function src/shared/ui/EntityField/EntityField.tsx:122:16
- `EntityField` — src/shared/ui/EntityField/index.ts:1:10
- `default` — src/shared/ui/EntityField/index.ts:1:23
- `EntityPage` — function src/shared/ui/EntityPage/EntityPage.tsx:54:17
- `default` — function src/shared/ui/EntityPage/EntityPage.tsx:156:16
- `default` — function src/shared/ui/EntityPage/EntityPageV2.tsx:307:16
- `EntityPage` — src/shared/ui/EntityPage/index.ts:1:10
- `FieldEditor` — function src/shared/ui/FieldEditor.tsx:29:17
- `default` — function src/shared/ui/FieldEditor.tsx:136:16
- `default` — function src/shared/ui/GridLayout/GridLayout.tsx:510:16
- `default` — function src/shared/ui/HealthIndicator/HealthIndicator.tsx:44:16
- `FilterIcon` — function src/shared/ui/Icon.tsx:377:17
- `DownloadIcon` — function src/shared/ui/Icon.tsx:420:17
- `RefreshIcon` — function src/shared/ui/Icon.tsx:453:17
- `ArchiveIcon` — function src/shared/ui/Icon.tsx:478:17
- `TrashIcon` — function src/shared/ui/Icon.tsx:508:17
- `ActionsButton` — src/shared/ui/index.ts:2:10
- `Card` — src/shared/ui/index.ts:7:21
- `LifecycleRestoreDialog` — src/shared/ui/index.ts:12:21
- `ErrorBoundary` — src/shared/ui/index.ts:17:21
- `MultiSelectTagPicker` — src/shared/ui/index.ts:21:21
- `MemoryScopeSelect` — src/shared/ui/index.ts:23:10
- `Popover` — src/shared/ui/index.ts:27:21
- `ServerDataTable` — src/shared/ui/index.ts:31:21
- `Table` — src/shared/ui/index.ts:32:21
- `ThemeSwitch` — src/shared/ui/index.ts:34:21
- `Toast` — src/shared/ui/index.ts:35:10
- `ToastProvider` — src/shared/ui/index.ts:35:17
- `FieldEditor` — src/shared/ui/index.ts:36:21
- `Tabs` — src/shared/ui/index.ts:37:10
- `TabPanel` — src/shared/ui/index.ts:37:16
- `BaseLayout` — src/shared/ui/index.ts:42:10
- `SplitLayout` — src/shared/ui/index.ts:42:22
- `TabsLayout` — src/shared/ui/index.ts:42:35
- `TableHeader` — src/shared/ui/index.ts:50:10
- `AppHeader` — src/shared/ui/index.ts:54:10
- `EntityPage` — src/shared/ui/index.ts:58:10
- `ContentBlock` — src/shared/ui/index.ts:64:10
- `ContentGrid` — src/shared/ui/index.ts:64:24
- `RowActions` — src/shared/ui/index.ts:68:10
- `RbacRulesEditor` — src/shared/ui/index.ts:71:10
- `RBACRulesTable` — src/shared/ui/index.ts:75:10
- `Breadcrumbs` — src/shared/ui/index.ts:84:10
- `CompactStatusBlock` — src/shared/ui/index.ts:87:10
- `EntityCardItem` — src/shared/ui/index.ts:91:22
- `MetaRow` — src/shared/ui/index.ts:95:10
- `MetaList` — src/shared/ui/index.ts:95:19
- `QuickAction` — src/shared/ui/index.ts:99:10
- `QuickActionGrid` — src/shared/ui/index.ts:99:23
- `VersionsBlock` — src/shared/ui/index.ts:103:10
- `VersionCard` — src/shared/ui/index.ts:107:10
- `PromptVersionCard` — src/shared/ui/index.ts:107:23
- `SecretField` — src/shared/ui/index.ts:117:10
- `GridLayout` — src/shared/ui/index.ts:127:10
- `EntityField` — src/shared/ui/index.ts:131:10
- `AIGenerateButton` — src/shared/ui/index.ts:135:10
- `ResponseContractCard` — src/shared/ui/index.ts:136:10
- `ContractAwareEditor` — src/shared/ui/index.ts:139:10
- `ContractFieldsBlock` — src/shared/ui/index.ts:140:10
- `ContractCriteriaBlock` — src/shared/ui/index.ts:142:10
- `InspectorDate` — function src/shared/ui/Inspector/fields/InspectorFields.tsx:40:17
- `InspectorReadonlyBlock` — function src/shared/ui/Inspector/fields/InspectorFields.tsx:47:17
- `InspectorEmpty` — src/shared/ui/Inspector/index.ts:4:10
- `InspectorDate` — src/shared/ui/Inspector/index.ts:6:10
- `InspectorReadonlyBlock` — src/shared/ui/Inspector/index.ts:6:111
- `InspectorEmpty` — function src/shared/ui/Inspector/InspectorEmpty.tsx:7:17
- `default` — function src/shared/ui/JSONDisplay/JSONDisplay.tsx:89:16
- `MetaList` — src/shared/ui/MetaRow/index.ts:1:19
- `MetaList` — function src/shared/ui/MetaRow/MetaRow.tsx:29:17
- `default` — function src/shared/ui/MetaRow/MetaRow.tsx:39:16
- `QuickAction` — src/shared/ui/QuickAction/index.ts:1:10
- `QuickActionGrid` — src/shared/ui/QuickAction/index.ts:1:23
- `QuickAction` — function src/shared/ui/QuickAction/QuickAction.tsx:17:17
- `QuickActionGrid` — function src/shared/ui/QuickAction/QuickAction.tsx:31:17
- `default` — function src/shared/ui/QuickAction/QuickAction.tsx:39:16
- `RbacRulesEditor` — src/shared/ui/RbacRulesEditor/index.ts:1:10
- `RbacRulesEditorDefault` — src/shared/ui/RbacRulesEditor/index.ts:1:38
- `RbacRulesEditor` — function src/shared/ui/RbacRulesEditor/RbacRulesEditor.tsx:30:17
- `default` — function src/shared/ui/RbacRulesEditor/RbacRulesEditor.tsx:259:16
- `RBACRulesTable` — src/shared/ui/RBACRulesTable/index.ts:1:10
- `default` — src/shared/ui/RBACRulesTable/index.ts:2:10
- `default` — function src/shared/ui/RBACRulesTable/RBACRulesTable.tsx:98:16
- `default` — function src/shared/ui/ResponseContractCard.tsx:303:16
- `RowActions` — function src/shared/ui/RowActions.tsx:32:17
- `default` — function src/shared/ui/RowActions.tsx:79:16
- `SecretField` — src/shared/ui/SecretField/index.ts:1:10
- `SecretField` — function src/shared/ui/SecretField/SecretField.tsx:32:17
- `default` — function src/shared/ui/SecretField/SecretField.tsx:142:16
- `default` — function src/shared/ui/ServerDataTable.tsx:24:25
- `SkeletonList` — function src/shared/ui/Skeleton.tsx:57:17
- `SkeletonTable` — function src/shared/ui/Skeleton.tsx:83:17
- `SkeletonCard` — function src/shared/ui/Skeleton.tsx:141:17
- `parseValue` — src/shared/ui/SmartViewer/useSmartParse.ts:83:10
- `default` — function src/shared/ui/Table.tsx:184:16
- `default` — src/shared/ui/TableHeader/index.ts:2:10
- `default` — variable src/shared/ui/TableHeader/TableHeader.tsx:89:16
- `default` — function src/shared/ui/Tabs.tsx:73:16
- `default` — function src/shared/ui/Tags/Tags.tsx:105:16
- `Toast` — function src/shared/ui/Toast.tsx:20:17
- `ToastContainer` — function src/shared/ui/Toast.tsx:151:17
- `useInfoToast` — function src/shared/ui/Toast.tsx:241:17
- `useWarningToast` — function src/shared/ui/Toast.tsx:247:17
- `Toggle` — function src/shared/ui/Toggle.tsx:16:17
- `default` — src/shared/ui/Tooltip/index.ts:1:19
- `default` — function src/shared/ui/Tooltip/Tooltip.tsx:148:16
- `VersionCard` — src/shared/ui/VersionCard/index.ts:1:10
- `PromptVersionCard` — src/shared/ui/VersionCard/index.ts:1:23
- `VersionCard` — function src/shared/ui/VersionCard/VersionCard.tsx:35:17
- `PromptVersionCard` — function src/shared/ui/VersionCard/VersionCard.tsx:125:17
- `default` — function src/shared/ui/VersionCard/VersionCard.tsx:148:16
- `default` — function src/shared/ui/VersionsBlock/VersionsBlock.tsx:106:16

### Неиспользуемые экспортируемые типы (243)

> **Статус шага (2026-11-20) — ✅ выполнено:** 252 флага knip → **0** (один проход + каскады). Правила решений: тип используется только внутри файла → снять `export`; не используется нигде → удалить декларацию; re-export в barrel → удалить specifier/строку.
>
> **Проход 1** (снимок knip: 252 флага в 77 файлах; анализатор `.cleanup-tmp/fix_ts_types.mjs` — адаптация `fix_ts_exports.mjs`: та же классификация internal/live/cascade/ignore, `ts.resolveModuleName`, разворот barrel-цепочек, фиксированная точка; якоря — InterfaceDeclaration/TypeAliasDeclaration/EnumDeclaration и ExportSpecifier, runtime-проверки чистоты не нужны): 217 правок в 77 файлах — unexport 104, delete-statement 44, remove-specifier 27, delete-export-decl 42; skip-live 1 → решён вручную (см. `User` ниже). Хиты имён в `.py`/`.md` — note-only (бэкенд не импортирует фронтовые типы).
>
> **Skip `User`** (блокирующие хиты в `.codex/agents/*.toml`): проверен вручную — это проза «User > Tenant > Default» про приоритет permissions, к TS-типу отношения не имеет; `auth.store.ts` импортирует `User`/`LoginResponse` напрямую из `@/shared/api/types`, минуя barrel → мёртвая строка `export type { User } from './types'` в api barrel удалена вручную.
>
> **Каскады после прохода 1:** (1) `remove-specifier` в группах оставил висячие запятые — `DataTable/index.ts` и `GridLayout/index.ts` переписаны вручную (diff проверен: удалены ровно флагованные имена); (2) `prompts.ts` после снятия всех 11 экспортов перестал быть модулем (TS2306) — файл содержал только локальные типы, удалён вместе со строкой `export * from './prompts'`; (3) 9 опустевших barrel `index.ts` удалены (`git rm`); (4) их компоненты лишились единственного пути к потребителю — свежий knip подтвердил 13 мёртвых файлов → 10 каталогов `shared/ui` удалены целиком с CSS-модулями: `BaseLayout`, `CompactStatusBlock`, `ContentBlock` (+`ContentGrid`), `ContractCriteriaBlock`, `ContractFieldsBlock`, `MetaRow`, `QuickAction`, `RbacRulesEditor`, `SecretField`, `VersionCard`. `RBACRulesTable` жив (прямые импорты в UserPage/PlatformSettingsPage/TenantPage) — удалён только его пустой barrel; (5) остаточные TS6196/TS6133 в живых файлах: удалены `OrchestrationSettings` (`admin.ts`), импорты `React`/`BreadcrumbItem` (`EntityPage.tsx` — реэкспорт идёт напрямую из `../Breadcrumbs`); (6) из `shared/ui/index.ts` убраны stale-секционные комментарии удалённых компонентов.
>
> **Итог (knip, фиксированная точка):** files 1 (сохранённый `visual-review.mjs`), **types 0**, exports 0, duplicates 20 (не уменьшились: цепочки типов между файлами — предмет отдельного шага «дубли»). Валидация: `tsc` plain — 0; с `--noUnusedLocals --noUnusedParameters` — 0; `npm run build` — exit 0 (✓ 5.09s); `vitest --run` — 13 failed / 411 passed / 424 = baseline; lint: prettier 10025 → 9981, `no-explicit-any` 81 → 73, `no-restricted-imports` 40 = 40, `no-undef` 33 = 33, `exhaustive-deps` 15 = 15; `format:check` — 284 «грязных» (baseline 357), новых 0 (5 файлов, загрязнённых правками, отформатированы prettier).

- `ChatStreamFinal` — interface src/domains/chat/chatStream.ts:14:18
- `ChatConfirmationItem` — interface src/domains/chat/components/ConfirmationPrompt/ConfirmationPrompt.tsx:5:18
- `RAGSource` — type src/domains/chat/components/RAGSources.tsx:7:13
- `ChatRole` — type src/domains/chat/types.ts:1:13
- `TemplateSchemaNodeKind` — type src/domains/collections/pages/templateSchemaPresentation.ts:1:13
- `TemplateDescriptionSection` — interface src/domains/collections/pages/templateStatusPresentation.ts:1:18
- `LlmOutcomeKind` — type src/domains/sandbox/callInspection.ts:4:13
- `ConfigTabItem` — interface src/domains/sandbox/components/ConfigTabs.tsx:3:18
- `RawTraceEvent` — type src/domains/sandbox/components/traceInspector/viewers/index.ts:5:32
- `SandboxRun` — interface src/domains/sandbox/hooks/useSandboxRun.ts:103:18
- `TraceCallKind` — type src/domains/sandbox/traceProjection.ts:8:13
- `TraceStageKind` — type src/domains/sandbox/traceProjection.ts:9:13
- `TraceStepKind` — type src/domains/sandbox/traceProjection.ts:10:13
- `TraceExecutorKind` — type src/domains/sandbox/traceProjection.ts:11:13
- `TraceInspectorTabId` — type src/domains/sandbox/traceProjection.ts:12:13
- `TraceInspectorTab` — interface src/domains/sandbox/traceProjection.ts:14:18
- `TraceCallInfo` — interface src/domains/sandbox/traceProjection.ts:47:18
- `TraceCallRequest` — interface src/domains/sandbox/traceProjection.ts:57:18
- `TraceToolInvocation` — interface src/domains/sandbox/traceProjection.ts:78:18
- `TraceCallResponse` — interface src/domains/sandbox/traceProjection.ts:108:18
- `TraceExtractionResult` — interface src/domains/sandbox/traceProjection.ts:127:18
- `TraceLimitRow` — interface src/domains/sandbox/traceProjection.ts:143:18
- `TraceExecutorStatisticKey` — type src/domains/sandbox/traceProjection.ts:156:13
- `TraceAccessRow` — interface src/domains/sandbox/traceProjection.ts:172:18
- `TraceResultStatus` — type src/domains/sandbox/traceProjection.ts:260:13
- `TraceAgentCompletion` — type src/domains/sandbox/traceProjection.ts:279:13
- `TraceAgentOutcome` — type src/domains/sandbox/traceProjection.ts:280:13
- `TraceAgentActionView` — interface src/domains/sandbox/traceProjection.ts:301:18
- `TraceAgentInteractionView` — interface src/domains/sandbox/traceProjection.ts:315:18
- `TraceMemoryFact` — interface src/domains/sandbox/traceProjection.ts:396:18
- `TraceMemoryDecision` — interface src/domains/sandbox/traceProjection.ts:426:18
- `TraceStageFailure` — interface src/domains/sandbox/traceProjection.ts:481:18
- `TraceTaskAttempt` — interface src/domains/sandbox/traceProjection.ts:507:18
- `TraceAttachment` — interface src/domains/sandbox/traceProjection.ts:528:18
- `OverrideEntityType` — type src/domains/sandbox/types.ts:52:13
- `SandboxCatalogToolVersion` — interface src/domains/sandbox/types.ts:218:18
- `SandboxCatalogTool` — interface src/domains/sandbox/types.ts:224:18
- `SandboxCatalogDomainGroup` — interface src/domains/sandbox/types.ts:239:18
- `SandboxCatalogAgentVersion` — interface src/domains/sandbox/types.ts:276:18
- `SandboxCatalogAgent` — interface src/domains/sandbox/types.ts:282:18
- `SandboxCatalogRouter` — interface src/domains/sandbox/types.ts:290:18
- `SandboxSelectableType` — type src/domains/sandbox/types.ts:307:13
- `RetryBackoffType` — type src/shared/api/admin.ts:53:13
- `ResponseContractFormat` — type src/shared/api/admin.ts:55:13
- `ResponseContractFailurePolicy` — interface src/shared/api/admin.ts:57:18
- `JsonResponseContract` — interface src/shared/api/admin.ts:61:18
- `PlainTextResponseContract` — interface src/shared/api/admin.ts:75:18
- `MarkdownResponseContract` — interface src/shared/api/admin.ts:89:18
- `TokenScope` — interface src/shared/api/admin.ts:198:18
- `UserToken` — interface src/shared/api/admin.ts:203:18
- `AuditFilters` — interface src/shared/api/admin.ts:261:18
- `ModelStatus` — type src/shared/api/admin.ts:313:13
- `HealthStatus` — type src/shared/api/admin.ts:314:13
- `HealthCheckRequest` — interface src/shared/api/admin.ts:405:18
- `EmbeddingUsageTenantRow` — interface src/shared/api/admin.ts:448:18
- `EmbeddingUsageCollectionRow` — interface src/shared/api/admin.ts:458:18
- `AgentType` — type src/shared/api/agents.ts:10:13
- `AgentVersionInfo` — interface src/shared/api/agents.ts:37:18
- `DataInstanceShort` — interface src/shared/api/collections.ts:58:18
- `CollectionSource` — interface src/shared/api/collections.ts:64:18
- `PublishedCollectionVersionInfo` — interface src/shared/api/collections.ts:69:18
- `CollectionCount` — interface src/shared/api/collections.ts:74:18
- `CollectionWorkspace` — interface src/shared/api/collections.ts:80:18
- `CollectionTypePreset` — interface src/shared/api/collections.ts:122:18
- `DiscoveredApiEntity` — interface src/shared/api/collections.ts:143:18
- `SchemaOperation` — interface src/shared/api/collections.ts:255:18
- `UsageSummary` — interface src/shared/api/dashboard.ts:5:18
- `DashboardProblem` — interface src/shared/api/dashboard.ts:72:18
- `McpProbeToolItem` — interface src/shared/api/discoveredTools.ts:43:18
- `ErrorEnvelope` — type src/shared/api/errors.ts:1:13
- `UseAuditParams` — interface src/shared/api/hooks/useAdmin.ts:241:18
- `User` — type src/shared/api/index.ts:19:15
- `LoginResponse` — type src/shared/api/index.ts:19:21
- `RequestOptions` — type src/shared/api/index.ts:20:15
- `AuthTokens` — type src/shared/api/index.ts:20:31
- `DependencyWillBe` — type src/shared/api/lifecycle.ts:5:13
- `PromptStatus` — type src/shared/api/prompts.ts:7:13
- `PromptType` — type src/shared/api/prompts.ts:8:13
- `PromptContainer` — interface src/shared/api/prompts.ts:10:18
- `PromptVersion` — interface src/shared/api/prompts.ts:20:18
- `PromptVersionInfo` — interface src/shared/api/prompts.ts:33:18
- `PromptListItem` — interface src/shared/api/prompts.ts:41:18
- `PromptDetail` — interface src/shared/api/prompts.ts:53:18
- `CreatePromptContainerRequest` — interface src/shared/api/prompts.ts:67:18
- `UpdatePromptContainerRequest` — interface src/shared/api/prompts.ts:74:18
- `CreatePromptVersionRequest` — interface src/shared/api/prompts.ts:79:18
- `UpdatePromptVersionRequest` — interface src/shared/api/prompts.ts:86:18
- `EnrichedOwnerInfo` — interface src/shared/api/rbac.ts:62:18
- `EnrichedResourceInfo` — interface src/shared/api/rbac.ts:70:18
- `RuntimeOperation` — interface src/shared/api/toolInstances.ts:32:18
- `LinkedDataInstanceRuntimeSummary` — interface src/shared/api/toolInstances.ts:94:18
- `Pagination` — interface src/shared/api/types.ts:4:18
- `ApiResponse` — interface src/shared/api/types.ts:20:18
- `AuthTokens` — interface src/shared/api/types.ts:91:18
- `IngestPolicyControl` — interface src/shared/api/types/documentStatus.ts:59:18
- `IngestPolicy` — interface src/shared/api/types/documentStatus.ts:68:18
- `PipelineNode` — interface src/shared/api/types/documentStatus.ts:91:18
- `EmbeddingNode` — interface src/shared/api/types/documentStatus.ts:101:18
- `FlowGraphModel` — type src/shared/components/statusFlow/index.ts:7:3
- `FlowLane` — type src/shared/components/statusFlow/index.ts:9:3
- `FlowSelection` — type src/shared/components/statusFlow/index.ts:10:3
- `FlowStatus` — type src/shared/components/statusFlow/index.ts:11:3
- `UnifiedVersionStatus` — type src/shared/hooks/useVersionLifecycleActions.tsx:4:13
- `VersionLifecycleCallbacks` — interface src/shared/hooks/useVersionLifecycleActions.tsx:6:18
- `VersionLifecycleLoadingState` — interface src/shared/hooks/useVersionLifecycleActions.tsx:15:18
- `Theme` — type src/shared/lib/theme.ts:6:13
- `AdminPageAction` — interface src/shared/ui/AdminPage/AdminPage.tsx:30:18
- `AdminPageProps` — type src/shared/ui/AdminPage/index.ts:1:26
- `AdminPageAction` — type src/shared/ui/AdminPage/index.ts:1:47
- `AlertVariant` — type src/shared/ui/Alert.tsx:4:13
- `AppHeaderProps` — type src/shared/ui/AppHeader/index.ts:1:26
- `BaseLayoutType` — type src/shared/ui/BaseLayout/BaseLayout.tsx:17:13
- `BaseLayoutProps` — interface src/shared/ui/BaseLayout/BaseLayout.tsx:19:18
- `SplitLayoutProps` — interface src/shared/ui/BaseLayout/BaseLayout.tsx:32:18
- `TabsLayoutProps` — interface src/shared/ui/BaseLayout/BaseLayout.tsx:47:18
- `BaseLayoutType` — type src/shared/ui/BaseLayout/index.ts:2:15
- `BaseLayoutProps` — type src/shared/ui/BaseLayout/index.ts:2:31
- `SplitLayoutProps` — type src/shared/ui/BaseLayout/index.ts:2:48
- `TabsLayoutProps` — type src/shared/ui/BaseLayout/index.ts:2:66
- `CompactStatusBlockProps` — interface src/shared/ui/CompactStatusBlock/CompactStatusBlock.tsx:11:18
- `CompactStatusBlockProps` — type src/shared/ui/CompactStatusBlock/index.ts:5:15
- `BlockWidth` — type src/shared/ui/ContentBlock/ContentBlock.tsx:18:13
- `FieldType` — type src/shared/ui/ContentBlock/ContentBlock.tsx:20:13
- `FieldOption` — interface src/shared/ui/ContentBlock/ContentBlock.tsx:31:18
- `FieldDefinition` — interface src/shared/ui/ContentBlock/ContentBlock.tsx:36:18
- `ContentBlockProps` — type src/shared/ui/ContentBlock/index.ts:4:29
- `FieldDefinition` — type src/shared/ui/ContentBlock/index.ts:4:53
- `FieldType` — type src/shared/ui/ContentBlock/index.ts:4:75
- `BlockWidth` — type src/shared/ui/ContentBlock/index.ts:4:91
- `ContentGridProps` — type src/shared/ui/ContentBlock/index.ts:5:28
- `ContractCriteriaBlockProps` — interface src/shared/ui/ContractCriteriaBlock/ContractCriteriaBlock.tsx:3:18
- `ContractCriteriaBlockProps` — type src/shared/ui/ContractCriteriaBlock/index.ts:2:15
- `ContractFieldsBlockProps` — interface src/shared/ui/ContractFieldsBlock/ContractFieldsBlock.tsx:3:18
- `ContractFieldsBlockProps` — type src/shared/ui/ContractFieldsBlock/index.ts:2:15
- `CredentialsPanelMode` — type src/shared/ui/CredentialsPanel/CredentialsPanel.tsx:27:13
- `CredentialsPanelProps` — type src/shared/ui/CredentialsPanel/index.ts:2:15
- `CredentialsPanelMode` — type src/shared/ui/CredentialsPanel/index.ts:2:38
- `DataTableFilterKind` — type src/shared/ui/DataTable/DataTable.tsx:39:13
- `DataTableColumnFilter` — interface src/shared/ui/DataTable/DataTable.tsx:46:18
- `DataTableProps` — type src/shared/ui/DataTable/index.ts:4:3
- `DataTableColumnFilter` — type src/shared/ui/DataTable/index.ts:5:3
- `DataTableFilterKind` — type src/shared/ui/DataTable/index.ts:6:3
- `DataTableFilterValue` — type src/shared/ui/DataTable/index.ts:7:3
- `EntityCardItemProps` — interface src/shared/ui/EntityCard/EntityCard.tsx:40:18
- `EntityCardProps` — type src/shared/ui/EntityCard/index.ts:2:15
- `EntityCardItemProps` — type src/shared/ui/EntityCard/index.ts:2:32
- `EntityFieldProps` — interface src/shared/ui/EntityField/EntityField.tsx:19:18
- `EntityFieldProps` — type src/shared/ui/EntityField/index.ts:2:15
- `EntityPageProps` — interface src/shared/ui/EntityPage/EntityPage.tsx:17:18
- `BreadcrumbItem` — type src/shared/ui/EntityPage/EntityPageV2.tsx:25:15
- `TabLayout` — type src/shared/ui/EntityPage/EntityPageV2.tsx:28:13
- `EntityPageProps` — type src/shared/ui/EntityPage/index.ts:2:15
- `EntityPageV2Props` — type src/shared/ui/EntityPage/index.ts:5:15
- `FactsPanelMode` — type src/shared/ui/FactsPanel/FactsPanel.tsx:13:13
- `BlockWidth` — type src/shared/ui/GridLayout/GridLayout.tsx:32:13
- `BlockHeight` — type src/shared/ui/GridLayout/GridLayout.tsx:33:13
- `IconVariant` — type src/shared/ui/GridLayout/GridLayout.tsx:34:13
- `FieldType` — type src/shared/ui/GridLayout/GridLayout.tsx:36:13
- `FieldOption` — interface src/shared/ui/GridLayout/GridLayout.tsx:50:18
- `GridLayoutProps` — type src/shared/ui/GridLayout/index.ts:3:3
- `BlockProps` — type src/shared/ui/GridLayout/index.ts:4:3
- `BlockWidth` — type src/shared/ui/GridLayout/index.ts:5:3
- `BlockHeight` — type src/shared/ui/GridLayout/index.ts:6:3
- `IconVariant` — type src/shared/ui/GridLayout/index.ts:7:3
- `FieldType` — type src/shared/ui/GridLayout/index.ts:9:3
- `FieldOption` — type src/shared/ui/GridLayout/index.ts:10:3
- `ActionItem` — type src/shared/ui/index.ts:3:15
- `DropdownMenuProps` — type src/shared/ui/index.ts:15:33
- `MultiSelectTagOption` — type src/shared/ui/index.ts:22:15
- `MultiSelectTagPickerProps` — type src/shared/ui/index.ts:22:37
- `SelectProps` — type src/shared/ui/index.ts:29:15
- `SelectOption` — type src/shared/ui/index.ts:29:28
- `AdminPageProps` — type src/shared/ui/index.ts:41:15
- `AdminPageAction` — type src/shared/ui/index.ts:41:31
- `BaseLayoutType` — type src/shared/ui/index.ts:43:15
- `BaseLayoutProps` — type src/shared/ui/index.ts:43:31
- `SplitLayoutProps` — type src/shared/ui/index.ts:43:48
- `TabsLayoutProps` — type src/shared/ui/index.ts:43:66
- `TableHeaderProps` — type src/shared/ui/index.ts:51:15
- `AppHeaderProps` — type src/shared/ui/index.ts:55:15
- `EntityPageProps` — type src/shared/ui/index.ts:59:15
- `EntityPageV2Props` — type src/shared/ui/index.ts:61:15
- `ContentBlockProps` — type src/shared/ui/index.ts:65:15
- `ContentGridProps` — type src/shared/ui/index.ts:65:34
- `FieldDefinition` — type src/shared/ui/index.ts:65:52
- `FieldType` — type src/shared/ui/index.ts:65:69
- `BlockWidth` — type src/shared/ui/index.ts:65:80
- `RbacPermissions` — type src/shared/ui/index.ts:72:15
- `RBACTableMode` — type src/shared/ui/index.ts:76:15
- `CompactStatusBlockProps` — type src/shared/ui/index.ts:88:15
- `EntityCardProps` — type src/shared/ui/index.ts:92:15
- `EntityCardItemProps` — type src/shared/ui/index.ts:92:32
- `MetaRowProps` — type src/shared/ui/index.ts:96:15
- `MetaListProps` — type src/shared/ui/index.ts:96:29
- `QuickActionProps` — type src/shared/ui/index.ts:100:15
- `QuickActionGridProps` — type src/shared/ui/index.ts:100:33
- `VersionInfo` — type src/shared/ui/index.ts:104:15
- `VersionsBlockProps` — type src/shared/ui/index.ts:104:28
- `VersionCardProps` — type src/shared/ui/index.ts:108:15
- `VersionCardEntityType` — type src/shared/ui/index.ts:108:33
- `PromptVersionCardProps` — type src/shared/ui/index.ts:108:56
- `JSONDisplayProps` — type src/shared/ui/index.ts:114:15
- `SecretFieldProps` — type src/shared/ui/index.ts:118:15
- `CredentialsPanelProps` — type src/shared/ui/index.ts:122:15
- `CredentialsPanelMode` — type src/shared/ui/index.ts:122:38
- `FactsPanelMode` — type src/shared/ui/index.ts:124:15
- `GridLayoutProps` — type src/shared/ui/index.ts:128:15
- `BlockProps` — type src/shared/ui/index.ts:128:32
- `GridBlockWidth` — type src/shared/ui/index.ts:128:58
- `BlockHeight` — type src/shared/ui/index.ts:128:74
- `ContractFieldsBlockProps` — type src/shared/ui/index.ts:141:15
- `ContractCriteriaBlockProps` — type src/shared/ui/index.ts:143:15
- `JSONDisplayProps` — type src/shared/ui/JSONDisplay/index.ts:2:15
- `MetaRowProps` — type src/shared/ui/MetaRow/index.ts:2:15
- `MetaListProps` — type src/shared/ui/MetaRow/index.ts:2:29
- `MetaListProps` — interface src/shared/ui/MetaRow/MetaRow.tsx:24:18
- `QuickActionProps` — type src/shared/ui/QuickAction/index.ts:2:15
- `QuickActionGridProps` — type src/shared/ui/QuickAction/index.ts:2:33
- `QuickActionProps` — interface src/shared/ui/QuickAction/QuickAction.tsx:10:18
- `QuickActionGridProps` — interface src/shared/ui/QuickAction/QuickAction.tsx:26:18
- `RbacPermissions` — type src/shared/ui/RbacRulesEditor/index.ts:2:15
- `RbacPermissions` — interface src/shared/ui/RbacRulesEditor/RbacRulesEditor.tsx:16:18
- `RBACTableMode` — type src/shared/ui/RBACRulesTable/index.ts:1:31
- `RBACTableMode` — type src/shared/ui/RBACRulesTable/RBACRulesTable.tsx:16:13
- `RowActionsProps` — interface src/shared/ui/RowActions.tsx:9:18
- `SecretFieldProps` — type src/shared/ui/SecretField/index.ts:2:15
- `SecretFieldProps` — interface src/shared/ui/SecretField/SecretField.tsx:17:18
- `SelectProps` — type src/shared/ui/Select/index.ts:2:15
- `SkeletonListProps` — interface src/shared/ui/Skeleton.tsx:50:18
- `SkeletonTableProps` — interface src/shared/ui/Skeleton.tsx:74:18
- `SkeletonCardProps` — interface src/shared/ui/Skeleton.tsx:135:18
- `ParsedNode` — type src/shared/ui/SmartViewer/index.ts:3:15
- `ParsedNodeType` — type src/shared/ui/SmartViewer/nodes/types.ts:1:13
- `TableHeaderProps` — type src/shared/ui/TableHeader/index.ts:1:28
- `ToastContainerProps` — interface src/shared/ui/Toast.tsx:146:18
- `VersionCardProps` — type src/shared/ui/VersionCard/index.ts:2:15
- `VersionCardEntityType` — type src/shared/ui/VersionCard/index.ts:2:33
- `PromptVersionCardProps` — type src/shared/ui/VersionCard/index.ts:2:56
- `VersionCardEntityType` — type src/shared/ui/VersionCard/VersionCard.tsx:16:13
- `VersionCardProps` — interface src/shared/ui/VersionCard/VersionCard.tsx:18:18
- `PromptVersionCardProps` — interface src/shared/ui/VersionCard/VersionCard.tsx:114:18
- `VersionInfo` — type src/shared/ui/VersionsBlock/index.ts:2:15
- `VersionsBlockProps` — type src/shared/ui/VersionsBlock/index.ts:2:28

### Дублирующиеся экспорты (69)

> **Статус шага (2026-11-20) — ✅ выполнено:** к началу шага после «файлов»/«экспортов»/«типов» осталось 20 дублей (изначальные 69 в основном были в удалённых к тому моменту файлах); после шага — **0**. Все 20 — паттерн «именованный + default одного символа», канонический выбирался по фактическому использованию; правки — `.cleanup-tmp/fix_ts_duplicates.mjs` (asserted line-matcher) + 3 правки вручную (ошибка алиаса `@shared` у ProfilePage).
>
> Решения:
> - **named-канонический (15):** `collectionsApi` (6 named-потребителей vs 2 default; RbacListPage/RbacRulePage переведены на named), 11 страниц, где router использует `.then(m => ({ default: m.X }))`, а тесты — named (DiscoveredToolViewPage, DiscoveredToolsPage, OrchestrationPage, RbacRulePage, AgentListPage, AgentPage, AgentVersionPage, CollectionVersionPage, InstancePage, RbacListPage, PlatformSettingsPage) → удалена строка `export default X;`; `Skeleton` (barrel переведён на `export { Skeleton }`) и `Select` (мини-barrel `Select/index.ts` → `export { Select }`; 4 default-импортёра — CredentialsPanel, CollectionPresentation, CollectionDataPage, ProfilePage — переведены на named).
> - **default-канонический (5):** InstancesListPage, ModelPage, TenantPage, UserPage (router — plain `lazy(() => import(...))`) и TemplateStatusModal (единственный прод-потребитель импортирует default) → снят `export` с декларации, 5 тест-импортов переведены на default.
> - **Алиас (1):** `ToolResponseView = ToolResponse` (CallViews.tsx) → алиас-константа удалена, TraceInspector переведён на `ToolResponse` (3 тест-файла уже использовали его).
>
> Примечание: стиль router остался смешанным (plain lazy для default-страниц и `.then(m => …)` для named) — это предшествующее состояние, не предмет шага.
> Валидация: `tsc` plain/с флагами — 0; knip — duplicates 0; `npm run build` — exit 0; `vitest --run` — 13F/411P/424 = baseline; lint: prettier 9990 ≤ 10025, остальные = baseline; `format:check` — 284 «грязных», новых 0 (AgentListPage.tsx и Skeleton.tsx отформатированы prettier).

Символ экспортируется и как именованный, и как default (или дублируется через index) — консолидировать:

- `ThemeProvider|default src/app/providers/ThemeProvider.tsx`
- `AdminLayout|default src/domains/admin/layouts/AdminLayout.tsx`
- `AgentListPage|default src/domains/admin/pages/AgentListPage.tsx`
- `AgentPage|default src/domains/admin/pages/AgentPage.tsx`
- `AgentVersionPage|default src/domains/admin/pages/AgentVersionPage.tsx`
- `AuditPage|default src/domains/admin/pages/AuditPage.tsx`
- `CollectionListPage|default src/domains/admin/pages/CollectionListPage.tsx`
- `CollectionPage|default src/domains/admin/pages/CollectionPage.tsx`
- `CollectionVersionPage|default src/domains/admin/pages/CollectionVersionPage.tsx`
- `DashboardPage|default src/domains/admin/pages/DashboardPage.tsx`
- `DiscoveredToolsPage|default src/domains/admin/pages/DiscoveredToolsPage.tsx`
- `DiscoveredToolViewPage|default src/domains/admin/pages/DiscoveredToolViewPage.tsx`
- `InstancePage|default src/domains/admin/pages/InstancePage.tsx`
- `InstancesListPage|default src/domains/admin/pages/InstancesListPage.tsx`
- `ModelPage|default src/domains/admin/pages/ModelPage.tsx`
- `OrchestrationPage|default src/domains/admin/pages/OrchestrationPage.tsx`
- `PlatformSettingsPage|default src/domains/admin/pages/PlatformSettingsPage.tsx`
- `RbacListPage|default src/domains/admin/pages/RbacListPage.tsx`
- `RbacRulePage|default src/domains/admin/pages/RbacRulePage.tsx`
- `TenantPage|default src/domains/admin/pages/TenantPage.tsx`
- `TenantsListPage|default src/domains/admin/pages/TenantsListPage.tsx`
- `UserPage|default src/domains/admin/pages/UserPage.tsx`
- `UsersListPage|default src/domains/admin/pages/UsersListPage.tsx`
- `ChatComposer|default src/domains/chat/components/ChatComposer.tsx`
- `TemplateStatusModal|default src/domains/collections/pages/TemplateStatusModal.tsx`
- `StatusModalNew|default src/domains/rag/components/StatusModalNew.tsx`
- `ConfigPanel|default src/domains/sandbox/components/ConfigPanel.tsx`
- `LlmRequestSnapshotView|LlmRequestView src/domains/sandbox/components/traceInspector/CallViews.tsx`
- `LlmResponseSnapshotView|LlmResponseView src/domains/sandbox/components/traceInspector/CallViews.tsx`
- `ToolResponse|ToolResponseView src/domains/sandbox/components/traceInspector/CallViews.tsx`
- `ExecutorResultView|AgentResultViewer|SynthesizerResultView… …/domains/sandbox/components/traceInspector/ResultViews.tsx`
- `collectionsApi|default src/shared/api/collections.ts`
- `StatusFlowDetails|default src/shared/components/statusFlow/StatusFlowDetails.tsx`
- `StatusFlowView|default src/shared/components/statusFlow/StatusFlowView.tsx`
- `useStatusConfig|default src/shared/hooks/useStatusConfig.ts`
- `useVersionLifecycleActions|default src/shared/hooks/useVersionLifecycleActions.tsx`
- `AdminPage|default src/shared/ui/AdminPage/AdminPage.tsx`
- `AppHeader|default src/shared/ui/AppHeader/AppHeader.tsx`
- `BaseLayout|default src/shared/ui/BaseLayout/BaseLayout.tsx`
- `Breadcrumbs|default src/shared/ui/Breadcrumbs/Breadcrumbs.tsx`
- `CompactStatusBlock|default src/shared/ui/CompactStatusBlock/CompactStatusBlock.tsx`
- `ContentBlock|default src/shared/ui/ContentBlock/ContentBlock.tsx`
- `ContentGrid|default src/shared/ui/ContentBlock/ContentGrid.tsx`
- `ContractAwareEditor|default src/shared/ui/ContractAwareEditor/ContractAwareEditor.tsx`
- `EntityCard|default src/shared/ui/EntityCard/EntityCard.tsx`
- `EntityField|default src/shared/ui/EntityField/EntityField.tsx`
- `EntityPage|default src/shared/ui/EntityPage/EntityPage.tsx`
- `EntityPageV2|default src/shared/ui/EntityPage/EntityPageV2.tsx`
- `FieldEditor|default src/shared/ui/FieldEditor.tsx`
- `GridLayout|default src/shared/ui/GridLayout/GridLayout.tsx`
- `HealthIndicator|default src/shared/ui/HealthIndicator/HealthIndicator.tsx`
- `JSONDisplay|default src/shared/ui/JSONDisplay/JSONDisplay.tsx`
- `MetaRow|default src/shared/ui/MetaRow/MetaRow.tsx`
- `QuickAction|default src/shared/ui/QuickAction/QuickAction.tsx`
- `RbacRulesEditor|default src/shared/ui/RbacRulesEditor/RbacRulesEditor.tsx`
- `RBACRulesTable|default src/shared/ui/RBACRulesTable/RBACRulesTable.tsx`
- `ResponseContractCard|default src/shared/ui/ResponseContractCard.tsx`
- `RowActions|default src/shared/ui/RowActions.tsx`
- `SecretField|default src/shared/ui/SecretField/SecretField.tsx`
- `Select|default src/shared/ui/Select/Select.tsx`
- `Skeleton|default src/shared/ui/Skeleton.tsx`
- `Table|default src/shared/ui/Table.tsx`
- `TableHeader|default src/shared/ui/TableHeader/TableHeader.tsx`
- `Tabs|default src/shared/ui/Tabs.tsx`
- `Tags|default src/shared/ui/Tags/Tags.tsx`
- `Toggle|default src/shared/ui/Toggle.tsx`
- `Tooltip|default src/shared/ui/Tooltip/Tooltip.tsx`
- `VersionCard|default src/shared/ui/VersionCard/VersionCard.tsx`
- `VersionsBlock|default src/shared/ui/VersionsBlock/VersionsBlock.tsx`

---

## 6. Рекомендации по порядку очистки

1. **Безопасно и механически**: удалить неиспользуемые импорты Python (секция 1) и TS (секция 4) — ✅ выполнено (2026-11-19 / 2026-11-20); проверка: `make test` + `npm run build`.
2. **Мёртвые модули Python** (секция 2): удалять по одному с прогоном `make test`; `adapters/interfaces/*` и `schemas/*` — самые старые (2025-11), вероятно скелет проекта.
3. **Зависимости** (`prismjs`, `rehype-prism-plus`, `rehype-raw`, dev: `msw`, `undici-types`): ✅ выполнено 2026-11-20 — пакеты удалены из `apps/web/package.json`, lock обновлён, пересборка/тесты/lint/format = baseline (детали — статус-блоки секции 5).
4. **Неиспользуемые файлы TS** (секция 5): ✅ выполнено 2026-11-20 — 40/41 + каскады (детали — статус-блок секции 5); сохранён только `scripts/visual-review.mjs`.
5. **Функции/классы/методы/свойства Python** (секция 3): ✅ выполнено 2026-11-20 — решения по test-only (57 → удалить с тестами), свойствам (15 → удалить) и limits/policies (код → удалить, таблицы оставить) приняты и исполнены; пары «интерфейс + реализация» удалялись вместе (например, `embed_query` в `EmbClientProtocol`/`HTTPEmbClient`); правки тестов по пометкам «тест-ссылки» включены в зачистку.
6. **Отдельно решить**: `mcp/hipporag/server.py` (дублирует worker-ветку; его мёртвый `_init_llm_config` — в списках секции 3). `app/workers/tasks_health_check.py` удалён в фазе 2.

## Как воспроизвести

```bash
# Python
python3 -m pyflakes apps/api/src apps/emb/src apps/rerank/src mcp scripts
python3 -m vulture apps/api/src apps/emb/src apps/rerank/src mcp scripts --min-confidence 60
# Фаза 3 (секция 3): vulture + верификация; скрипты в .cleanup-tmp (в .gitignore)
python3 .cleanup-tmp/pipeline.py      # vulture → AST-триаж → токен-индекс → ярусная верификация
python3 .cleanup-tmp/classify_few.py  # классификация few-ссылок (tokenize, DYNREF)
python3 .cleanup-tmp/finalize3.py     # агрегация итогов и маркдаун секции 3
# TypeScript (из apps/web)
npx tsc -p tsconfig.json --noEmit --noUnusedLocals --noUnusedParameters
npx knip --no-exit-code
# Секция 4: fixer по диагностикам tsc (dry-run по умолчанию, --apply для записи)
node .cleanup-tmp/fix_ts_locals.mjs [--apply]
```

