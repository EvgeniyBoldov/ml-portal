# Ревью легаси и мёртвого кода — повторный проход

Дата: 2026-11-20 · Инструменты: pyflakes 4.1.0, vulture 2.16, tsc 5.9.3 (`--noUnusedLocals --noUnusedParameters`), knip (apps/web).

Это самостоятельное ревью по дереву **после** закоммиченных фаз очистки 1–5 (2026-11-19/20, коммиты `628f0a0 big clear`, `30e1403 fix contract` и др.; предыдущее ревью удалено). Задача — свежий срез: что из мёртвого осталось или проявилось после большой очистки.

Методика та же, что в фазах 1–5: подсчёт упоминаний идентификатора по всему репозиторию, разрешение относительных/абсолютных импортов, реестры (Celery `include`, строковая диспетчеризация mcp-роутера, ленивые `__getattr__`-карты), тест-корни и CLI-точки входа. Для vulture-кандидатов — ярусная верификация LIVE/DOC/VENDOR (детали в секции 3); пересечений `getattr`-вызовов с кандидатами нет.

## Статус исполнения (зачистка 2026-11-20, вечер)

Рекомендации секции 1–3 из секции 8 исполнены. Все изменения **не закоммичены** (73 файла в `git status`: 18 удалений, 55 правок; +243/−5402; HEAD `628f0a0`). Статусы по этапам:

| Этап | Объём | Результат |
|---|---|---|
| **Фаза A** — мёртвые модули (секц. 2) | 9 файлов | удалены целиком |
| **Фаза B** — test-only модули (секц. 2) | 5 модулей + 4 тест-файла (19 тестов) + 4 записи ленивой карты `_EXPORTS` | удалены; тесты умерших объектов вырезаны |
| **Фаза C** — vulture dead + few (секц. 3) | **70 объектов из 40 файлов**: 60 из dead-73 в сохранившихся файлах + 8 few-dead + 2 few-test-only (`build_runtime_operation_slug`, `cleanup_expired` с тест-хирургией) | AST-вырезание по манифесту `.cleanup-tmp/phaseC_worklist.json` |
| **Каскад** — вторичный vulture-проход | **19 объектов из 12 файлов** (методы 9, классы 6, функции 4), в т.ч. `PromptVersionRepository` целиком (умерли все 3 метода) и обе `sync_*_from_registry` | вырезаны после побайтовой перепроверки refcount=0 по всему репо (вердикт ревью: «мертвы функции и записи карты») |
| **Орфан-свипы импортов** | 29 + 6 в два прохода (pyflakes после вырезаний) | pyflakes 113 → **109** |
| **Ручные правки** | 4 файла | докстринг `core/exceptions.py` (убран `InUseError` из перечня), реэкспорт `InstanceDomain` в `models/__init__.py`, Example-блок `permission_service.py` (`is_instance_allowed`), импорт и слаг-тест в `test_operation_publication.py` |

**Не тронуты намеренно:** undefined-name баги секции 4 (латентные, предсуществующие — тикеты владельцам), unused locals секции 5, согласованные исключения vulture — `api/mcp/schemas.py` ×2 + `mcp/netbox/tests/test_server.py` ×2 (это единственные 4 dead в свежем прогоне), защищённые реэкспорты секции 1, весь web (бейзлайны секции 6 не менялись).

### Верификация после зачистки

- `compileall` — OK; WatchFiles в api-контейнере перезагрузился на удалениях модулей чисто, без трейсбеков.
- Свежий vulture (пайплайн r2, артефакты сброшены): dead = **ровно 4 согласованных исключения** (см. выше).
- pyflakes: 113 → **109** (−4 реальных орфан-импорта; остальные дельты — сдвиг строк предсуществующих багов секции 4, сами баги не тронуты).
- Docker pytest (`docker compose exec api pytest tests/`): **86 failed / 2097 passed / 137 skipped**. Ключевое: множество FAILED **побайтово идентично** бейзлайнам секции 7 — unit 78 = 78 (0 новых, 0 «починившихся»), integration 8 = 8.
- Дельты счётчиков объяснены удалёнными тестами умерших объектов: skipped −12 = 5 PG-gated тестов `integration/test_memory_runtime_reads.py` (параметризация 2+1+6+1+1 = 11 items) + 1 inventory-тест `test_result_workspace_sql.py`; passed −31 ≈ 19 тестов в 4 удалённых юнит-файлах + слаг-билдер + 9 параметризованных `test_memory_execution_search.py` + 3 `test_memory_phase1_regressions.py` + единичные правки параметризации.
- Контейнер тестировал актуальное дерево (tests-директория bind-mount; все 4 удалённых тест-файла в контейнере отсутствуют — проверено).
- Сквозной grep: все удалённые символы (включая `PromptVersionRepository`, `IdempotencyService`, `PromptService`, `sync_*_from_registry`, `InstanceDomain`, `InUseError` и др.) — 0 упоминаний в src/tests/mcp/scripts.

Примечание: `docker compose ps` показывает api «unhealthy» — это артефакт пути healthcheck (`/health` → 404, `localhost:8000/health` таймаут; рабочий эндпоинт `/api/v1/healthz` → 200), с зачисткой не связано.

## Резюме

| Категория | Находок | Инструмент |
|---|---|---|
| Python: неиспользуемые импорты | 37 — практически весь осознанный остаток фаз 1–5 | pyflakes |
| Python: мёртвые модули (никто не импортирует) | **9** (+5 test-only) | резолв импортов |
| Python: мёртвые функции/классы/методы | **73** raw → **71** кандидат (−2 unittest-хука), из них 2 — mcp-зона | vulture + верификация |
| Python: few-объекты (1–2 упоминания) | 27 разобраны вручную: **12 dead / 7 test-only / 8 live** | vulture + верификация |
| Python: undefined names | 33 = **6 реальных латентных багов** + 8 имён подозрительного блока `pipeline.py` + 19 lint-only | pyflakes |
| Python: unused locals и прочее | 43 (35 locals, 2 redefinition, 3 shadowed import, 2 `global`, 1 f-string) | pyflakes |
| TypeScript/React: локальные объявления | **0** | tsc |
| TypeScript/React: knip | 2 (1 сохранённый файл + 1 unlisted dep) | knip |

Ключевое отличие от прошлого прохода: секции, закрытые фазами 1–5 (импорты, модули, vulture-массштаб, TS-файлы/экспорты/типы/дубли/зависимости), дают почти нулевой остаток. Новые находки — это (а) каскады: код, оставшийся без потребителей после удалений фаз 1–3, и (б) latent-баги, которые оголила очистка unused-импортов.

---

## 0. Уже почищено (фазы 1–5, 2026-11-19/20)

Кратко, для контекста (детали были в предыдущем ревью):

- **Импорты (фаза 1):** 242 имени в 133 файлах удалены (autoflake).
- **Мёртвые модули (фаза 2):** 36/36 удалены.
- **Vulture dead/test-only + limits/policies (фаза 3):** 391 запись манифеста исполнена (350 определений AST-скриптом, 4 файла limits/policies целиком и др.); таблицы БД `limits`/`policies` не тронуты.
- **TS locals (фаза 4):** 133 находки → 0.
- **knip (фаза 5):** 40 файлов + 254 экспорта + 252 типа + 20 дублей + 5 зависимостей удалены; фиксированная точка: файлов 1 (сохранённый `scripts/visual-review.mjs`), остальное 0.
- Валидация фаз: unit 78F/2084P/3S и integration 8F/44P/146S — байт-в-байт база HEAD, 0 регрессий.

---

## 1. Python — неиспользуемые импорты (pyflakes, 37)

Полный свежий прогон: 113 находок (`.cleanup-tmp/pyflakes_fresh.txt`); из них 37 — импорты. Разбивка показывает, что это не новый долг, а осознанный остаток, зафиксированный ещё при закрытии фаз 1–3:

| Категория | Кол-во | Статус |
|---|---|---|
| `models/__init__.py` — реэкспорты SQLAlchemy-моделей | 10 | сохранить (конвенция); исключение — `InstanceDomain`, см. секцию 3 |
| `core/errors.py` — реэкспорты обработчиков/ошибок | 9 | сохранить (конвенция, публичная поверхность `core.errors`) |
| `migrations/versions/*` — служебные импорты Alembic | 8 | не трогать (миграции исключены из кандидатов) |
| `schemas/tool_instances.py` — `CredentialCreate/Update/Response` | 3 | реэкспорт: live-ссылки есть (vulture не flagged), сохранить |
| `collection_service.py` — `InvalidSchemaError`, `RowValidationError` | 2 | защищённые реэкспорты (решение фазы 2) |
| `extractors/layout_pdf.py` — `doctr` ×2 | 2 | optional-dependency probe в try-блоке, сохранить |
| `celery_app.py:341` — `periodic_task_tracker` | 1 | side-effect импорт регистрации воркера, сохранить |
| `agents/builtins/__init__.py:58` — `template_fill` | 1 | агрегатор-реестр ботов, сохранить |
| `api/deps.py:15` — `get_llm_client` | 1 | легитимный реэкспорт (восстановлен в фазе 3, питает 3 роутера) |

**Вывод по секции: удалять нечего.** Единственный кандидат внутри этой категории — `InstanceDomain` (мёртв и как класс, и как строка реэкспорта) — учтён в секции 3.

---

## 2. Python — мёртвые модули (9 + 5 test-only)

Модульный граф по 875 модулям (`apps/api/src`, `apps/emb/src`, `apps/rerank/src`, `mcp`, `scripts`; тест-корни: `apps/api/tests` + src-вложенные `test_*.py`/`*/tests/*`). Живость вычислена BFS-фикспоинтом: правило «`__init__.py` жив, если жив хоть один реэкспортированный им модуль» применяется **внутри** итерации, а не постфактум — иначе side-effect импорты хабов (`models`, `repositories`, `adapters/impl`) ложно «умерщвляют» живые модули. Дуги: обычные импорты, относительные (level=1 с отрезанием собственного имени; от `__init__` — level-1), строковые `import_module("app.…")`, Celery `include`. Кандидат проверен grep'ом по всему репо (docs/web/mcp/infra/scripts) — ноль упоминаний у всех девяти.

| Модуль | Примечание |
|---|---|
| `apps/api/src/app/core/resilience.py` | ретраи/circuit-breaker без потребителей |
| `apps/api/src/app/runtime/memory/turn_recall.py` | — |
| `apps/api/src/app/schemas/runtime_trace.py` | — |
| `apps/api/src/app/services/agent_seed_service.py` | сиды дефолтных агентов при старте; никто не вызывает (в т.ч. `seed_all`, см. секцию 3) |
| `apps/api/src/app/services/chat_generated_file_service.py` | — |
| `apps/api/src/app/services/collection_vector_service.py` | — |
| `apps/api/src/app/services/document_text_reader.py` | — |
| `apps/api/src/app/services/runtime_capability_graph_service.py` | — |
| `apps/api/src/app/services/runtime_hitl_policy_contract_service.py` | — |

Все девять — **каскады фаз 1–3**: их последние потребители удалены в прошлых фазах (поэтому `git log` даёт им дату 2026-11-20 — правки самих фаз). В docs/web/mcp/infra/scripts не упоминаются — расхождений код/документация нет.

### Test-only модули (5) — отдельное решение

| Модуль | Примечание |
|---|---|
| `apps/api/src/app/runtime/memory/search.py` | в src импортируется только `search_contract`; остальное — тесты |
| `apps/api/src/app/services/idempotency_service.py` | + класс в few-списке, см. секцию 3 |
| `apps/api/src/app/services/inventory_sql_prompt.py` | — |
| `apps/api/src/app/services/prompt_service.py` | — |
| `apps/api/src/app/services/runtime_evaluation_harness.py` | выживший фазы 3 (тогда признан живым); сейчас потребителей в src нет |

> **Статус: исполнено (фазы A/B).** Все 9 модулей и все 5 test-only удалены целиком; вместе с test-only удалены 4 тест-файла (`test_idempotency_service`, `test_memory_search_contract`, `test_prompt_service`, `test_runtime_evaluation_harness`, 19 тестов) и 4 записи `_EXPORTS` (`IdempotencyService`, `PromptService`, `sync_tools_from_registry`, `sync_backend_releases_from_registry`). Оговорки ниже (tool_results_migrations, mcp-хендлеры, хаб-цепочки) проверены и соблюдены — ничего из «НЕ кандидат» не удалено.

### Проверено и НЕ кандидат (важные оговорки)

- **`apps/api/src/app/tool_results_migrations/` (6 файлов)** — формально недостижим в графе, но **LIVE**: `apps/api/tool_results_alembic.ini` (`script_location = app/tool_results_migrations`) копируется в Docker-образы (`infra/docker/api/Dockerfile:19`, `Dockerfile.prod:29`); миграции гоняют integration-тесты. Не удалять.
- **mcp `handle_*`-хендлеры и unittest-хуки (`asyncSetUp`/`asyncTearDown`)** — LIVE: строковая диспетчеризация `apps/api/src/app/api/mcp/router.py:33-39`, unittest вызывает хуки фреймворком. mcp исключён из кандидатов.
- Хаб-цепочки перепроверены и живы: `collections/__init__` → glossary/crud/upload/stream/templates; `upload.py` → documents+table; `stream.py` → stream_download/events/lifecycle; `admin/collections.py` → collections_core; rag stream/lifecycle → content_access; planner жив через `assembler.py`/`pipeline.py`/`llm/structured.py`.

---

## 3. Python — неиспользуемые функции, классы, методы (vulture + верификация)

### Методика

Как в фазе 3, охват `apps/api/src, apps/emb/src, apps/rerank/src, mcp, scripts` (без tests; тесты — отдельный ярус): `vulture` 2.16 → **1993 raw** → AST-триаж декораторов (FastAPI/Celery/Pydantic/регистрации) → **957 кандидатов** → токен-индекс по всему репо с ярусами LIVE/DOC/VENDOR → верификация каждой ссылки (USE/IMPORT/DYNREF/DEF/STRING/COMMENT/TEST). Пайплайн: `.cleanup-tmp/r2/pipeline.py` (перезапуско-устойчив, токен-индекс `r2/token_index.pkl`), детали: `r2/fresh_dead_few.json`.

### Итоги

| Вердикт | Кол-во |
|---|---|
| **Dead** — 0 упоминаний где-либо (refcount 0, включая докстринги) | **73** |
| — из них unittest-хуки `mcp/netbox/tests/test_server.py` (`asyncSetUp`/`asyncTearDown`, вызываются фреймворком) | −2 → исключены |
| — из них mcp-зона: `api/mcp/schemas.py` (`MCPResource`, `ResourceContents` — зеркало протокольных типов MCP) | 2 → решение за владельцем mcp |
| **Итого кандидатов на удаление** | **71** (69 безоговорочных + 2 mcp-зона) |
| Few (1–2 упоминания) — разобраны вручную ниже | 27 |
| Live (USE/IMPORT/DYNREF или >2 ссылок) | 445 |

По типам (73): методы 40, классы 24, функции 9. Пересечений `getattr`-вызовов с кандидатами — 0.

Все 73 — **каскады фаз 1–3**: в прошлом манифесте их не было, потому что тогда были живы их потребители. Наиболее «каскадные» гнёзда: `services/file_delivery_service.py` (4 private-резолвера по storage-URI), `services/sandbox_override_resolver.py` (4), `services/prompt_service.py` (2 + 3 в few — модуль test-only, секция 2), `agents/contracts.py` (7 протокольных классов + 2 в few), `core/sse.py` (3), `repositories/*` (8).

### Полный список dead-73

Формат: `путь:строка` · тип · имя. Помечены: `[mcp]` — mcp-зона, решение за владельцем; `[unittest]` — исключено.

<details><summary>Развернуть список (73)</summary>

```
apps/api/src/app/agents/builtins/collection_search.py:114 · method · build_schema_for_collection
apps/api/src/app/agents/contracts.py:12 · class · ActionType
apps/api/src/app/agents/contracts.py:29 · class · OperationActionPayload
apps/api/src/app/agents/contracts.py:34 · class · AgentActionPayload
apps/api/src/app/agents/contracts.py:43 · class · ActionMeta
apps/api/src/app/agents/contracts.py:52 · class · ObservationStatus
apps/api/src/app/agents/contracts.py:58 · class · ObservationError
apps/api/src/app/agents/contracts.py:64 · class · PolicyDecisionType
apps/api/src/app/agents/registry.py:124 · method · get_for_agent
apps/api/src/app/agents/runtime/llm.py:157 · method · _failed_generation_to_native_tool_call
apps/api/src/app/agents/runtime/llm.py:194 · method · _extract_failed_generation_json
apps/api/src/app/api/deps.py:159 · function · get_tenant_id
apps/api/src/app/api/mcp/schemas.py:199 · class · MCPResource  [mcp]
apps/api/src/app/api/mcp/schemas.py:207 · class · ResourceContents  [mcp]
apps/api/src/app/core/cache.py:85 · method · delete_pattern
apps/api/src/app/core/cache.py:101 · method · get_index_keys
apps/api/src/app/core/cache.py:114 · class · DistributedLock
apps/api/src/app/core/exceptions.py:187 · class · AgentRuntimeError
apps/api/src/app/core/exceptions.py:380 · class · ConnectorError
apps/api/src/app/core/prometheus_metrics.py:23 · method · dec
apps/api/src/app/core/sse.py:49 · method · SSEStream
apps/api/src/app/core/sse.py:96 · function · _data_to_sse_generator
apps/api/src/app/core/sse.py:111 · function · _sse_generator
apps/api/src/app/repositories/agent_repository.py:38 · method · get_by_slug_with_versions
apps/api/src/app/repositories/chats_repo.py:196 · method · get_message_by_id
apps/api/src/app/repositories/documents_repo.py:23 · method · create_document
apps/api/src/app/repositories/documents_repo.py:32 · method · get_user_documents
apps/api/src/app/repositories/documents_repo.py:59 · method · count_user_documents
apps/api/src/app/repositories/factory.py:64 · method · get_emb_status_repository
apps/api/src/app/repositories/idempotency_repo.py:29 · method · _hash_request
apps/api/src/app/repositories/idempotency_repo.py:40 · method · get_key
apps/api/src/app/repositories/prompt_repository.py:116 · method · get_all_by_prompt
apps/api/src/app/repositories/sandbox_repository.py:161 · method · delete_expired
apps/api/src/app/runtime/agent_executor.py:1383 · method · _extract_needs_from_dict
apps/api/src/app/runtime/memory/builder.py:213 · function · _apply_branch_summary_overrides
apps/api/src/app/runtime/memory/tool_ledger.py:38 · function · document_search_evidence_document_ids
apps/api/src/app/runtime/orchestrator.py:84 · function · _memory_recalls
apps/api/src/app/runtime/turn_state.py:130 · method · _normalize_fact
apps/api/src/app/schemas/chats.py:93 · class · ChatResponse
apps/api/src/app/schemas/chats.py:108 · class · ChatMessageResponse
apps/api/src/app/schemas/collections.py:272 · function · _normalize_text
apps/api/src/app/schemas/rag.py:11 · class · RAGDocumentBase
apps/api/src/app/schemas/rag.py:24 · class · RAGChunkBase
apps/api/src/app/schemas/rag.py:34 · class · IngestRunBase
apps/api/src/app/schemas/runtime_trace.py:34 · class · TraceIterationResponse  (модуль целиком мёртв, секция 2)
apps/api/src/app/services/agent_seed_service.py:305 · method · seed_all  (модуль мёртв, секция 2)
apps/api/src/app/services/chat_attachment_service.py:257 · method · list_owned_attachments_for_chat
apps/api/src/app/services/chat_generated_file_service.py:8 · class · GeneratedFileItem  (модуль мёртв)
apps/api/src/app/services/chat_generated_file_service.py:15 · class · GeneratedFileResult  (модуль мёртв)
apps/api/src/app/services/collection/template_schema_builder.py:355 · method · _token_for_placeholder
apps/api/src/app/services/collection/template_schema_builder.py:381 · method · _segment_param
apps/api/src/app/services/collection/template_schema_builder.py:391 · method · _normalize_field_key
apps/api/src/app/services/collection/vector_lifecycle.py:190 · method · resolve_primary_vector_model
apps/api/src/app/services/collection/vector_lifecycle.py:211 · method · resolve_embedding_dimensions
apps/api/src/app/services/file_delivery_service.py:70 · method · parse_storage_uri
apps/api/src/app/services/file_delivery_service.py:160 · method · _resolve_chat_attachment_by_storage
apps/api/src/app/services/file_delivery_service.py:238 · method · _resolve_rag_document_by_storage
apps/api/src/app/services/file_delivery_service.py:307 · method · _resolve_collection_export_by_storage
apps/api/src/app/services/file_delivery_service.py:388 · method · _resolve_template_upload_by_storage
apps/api/src/app/services/hipporag_service.py:144 · method · index_documents
apps/api/src/app/services/prompt_service.py:55 · method · get_prompt_by_id  (модуль test-only)
apps/api/src/app/services/prompt_service.py:130 · method · get_active_version  (модуль test-only)
apps/api/src/app/services/runtime_capability_graph_service.py:8 · class · CollectionGraphInfo  (модуль мёртв)
apps/api/src/app/services/runtime_evaluation_harness.py:319 · function · _to_str_list  (модуль test-only)
apps/api/src/app/services/runtime_evaluation_harness.py:334 · function · _to_optional_text  (модуль test-only)
apps/api/src/app/services/runtime_terminal_status.py:17 · class · ContinuationTerminalStatus
apps/api/src/app/services/runtime_terminal_status.py:23 · class · ContinuationApiStatus
apps/api/src/app/services/sandbox_override_resolver.py:134 · method · get_blueprint
apps/api/src/app/services/sandbox_override_resolver.py:175 · method · _nested_get
apps/api/src/app/services/sandbox_override_resolver.py:237 · method · resolve_field_state
apps/api/src/app/services/tool_instance_service.py:509 · method · delete_local_instance
mcp/netbox/tests/test_server.py:48 · method · asyncSetUp  [unittest — исключено]
mcp/netbox/tests/test_server.py:51 · method · asyncTearDown  [unittest — исключено]
```

</details>

### Few-вердикты (27 объектов с 1–2 упоминаниями)

**Dead — 12** (упоминания только в собственном докстринге/дереве исключений/ленивой карте или определении-тёзке):

| Объект | Единственные «упоминания» |
|---|---|
| `core/exceptions.py:138 InUseError` | перечисление в докстринге модуля (`exceptions.py:17`) |
| `services/permission_service.py:42 is_instance_allowed` | пример в докстринге модуля (`permission_service.py:143`) |
| `models/prompt.py:175 can_activate` (property) | — |
| `models/tool_release.py:200 can_activate` (property) | — |
| `agents/contracts.py:282 ExecutionOutline` | определение-тёзка в другом файле; реальный потребитель — только `ExecutionOutlinePhase` |
| `schemas/system_llm_roles.py:142 ExecutionOutline` | то же |
| `models/tool_instance.py:48 InstanceDomain` | неиспользуемый реэкспорт `models/__init__.py:20` (секция 1) |
| `services/agent_service.py:270 get_version_by_number` | все 5 вызовов в `admin/agents.py` используют `get_version_by_number_and_agent_id` (:281) |
| `services/prompt_service.py:122 get_version_by_number` | вызовов нет ни в src, ни в tests |
| `services/agent_seed_service.py:299 AgentSeedService` + `:305 seed_all` | докстринг собственного модуля (модуль мёртв, секция 2) |
| `services/__init__.py:23 sync_tools_from_registry` — запись ленивой карты `_EXPORTS` | только ключ и строка-цель карты; вызовов нет |
| `services/__init__.py:24 sync_backend_releases_from_registry` — то же | то же |

Нюанс по двум последним: мертвы **функции и записи карты**; сами модули `tool_catalog_sync_service.py`/`tool_backend_release_sync_service.py` живут (имена-строки в карте — дуга живости) и других vulture-флагов не имеют.

**Test-only — 7** (живой код, используемый только тестами; отдельное решение): `agents/operation_publication.py:627 build_runtime_operation_slug`, `services/idempotency_service.py:13 IdempotencyService` + `:19 _compute_request_hash`, `services/prompt_service.py:12 PromptService` + `:34 _render_text`, `services/runtime_evaluation_harness.py:57 evaluate_runtime_case`, `services/sandbox_service.py:467 cleanup_expired`.

**Live — 8** (ложные срабатывания): `runtime/entity_ids.py:18 runtime_plan_id` (динамические ссылки), `services/tool_release_service.py:105 get_release`, mcp-хендлеры `handle_{initialize,tools_list,tools_call,prompts_list,prompts_get,ping}` ×6 (строковая диспетчеризация `api/mcp/router.py:33-39`).

> **Статус: исполнено (фаза C + каскад).** Вырезано 70 объектов из 40 файлов (60 dead-73 в сохранившихся файлах + few-dead-8 + few-test-only `build_runtime_operation_slug`/`cleanup_expired`); 9 объектов dead-73 умерли вместе с модулями фаз A/B; 2 unittest-хука и 2 mcp-объекта оставлены (согласованные исключения). Каскадный проход дал ещё 19 объектов из 12 файлов (`PromptVersionRepository` целиком, обе `sync_*_from_registry` и др.). Свежий vulture: dead = ровно 4 исключения. Строки в списках выше — на момент ревью, после вырезаний устарели.

---

## 4. Python — undefined names: реальные латентные баги (6) + подозрительный блок

pyflakes дал 33 undefined names. Классификация: **19 lint-only** (аннотации под `from __future__ import annotations` — `agent_executor`, `orchestrator`, `tasks_memory`, `operation_router` ×8; цитатные SQLAlchemy-аннотации в `models/agent`, `models/agent_version`, `models/collection`, `sandbox_override_resolver`, `execution_preflight`; `ldap_client Server/Connection`; `tasks_memory:985 exc` — замыкание вызывается внутри того же `except`, runtime OK) — трогать не нужно. Остальное:

### Явные баги (упадут NameError при достижении пути)

| Место | Имя | Что происходит |
|---|---|---|
| `api/v1/routers/admin/tool_instances.py:245` | `is_mcp_service_instance` | вызов без импорта |
| `api/v1/routers/admin/tool_instances.py:395` | `ToolInstanceNotFoundError` | except по несуществующему имени — `except` сам упадёт |
| `api/v1/routers/rag/download.py:58` | `s3_manager` | обращение к неопределённой переменной |
| `api/v1/routers/sandbox/runs.py:708` | `UploadValidationError` | except по несуществующему имени |
| `runtime/orchestrator.py:1285` | `logger` | единственное использование в модуле, определения нет |
| `runtime/plan_store.py:107` | `ResultObservation` | реальный вызов `ResultObservation.model_validate(...)` без импорта |

### Подозрительный блок — отдать владельцам runtime (не удалять без них)

- **`runtime/pipeline.py:2086–2123`** (хвост `_finalize_memory`, начатой на :1753): используют `session_factory` (:2086, :2123), `select` (:2088), `start_event` (:2107, :2109), `terminal_orchestrator_id` (:2114, :2117) — ни одно имя не определено и не импортировано в этой области видимости. Блок пишет `MemoryFinalizeOutbox`, ждёт персистентности ассистента и эмитит `orchestrator_end` — выглядит как перенесённый/недописанный фрагмент, где эти имена были параметрами или локальными переменными другой функции. При выполнении пути — NameError.
- **`runtime/pipeline.py:522`** (внутри `RuntimePipeline.execute`, начатой на :419): `RuntimeErrorCode` не импортирована — обработчик wall-time budget (`AGENT_WALL_TIME_EXCEEDED`) упадёт NameError вместо emission ошибки бюджета.

**Происхождение:** `git log -S` показывает, что все баги предсуществующие — внесены коммитами декабря 2025 – июня 2026 (`9db6f0a`, `c1659ae`, `ac33f9a`, `4c85eb7`), **не** регрессии фаз 1–5. Очистка unused-импортов их только оголила (раньше имена приезжали транзитивными импортами в некоторых случаях). Рекомендация: завести тикеты владельцам модулей; фикс — точечные импорты/передача параметров, не легаси-чистка.

---

## 5. Python — unused locals и прочий шум (43)

Низкий приоритет, удаление безопасно, но ценность невелика:

- **35 unused locals** — `runtime/pipeline.py:573`, `runtime/plan_store.py` ×3, `runtime/agent_executor.py:556`, `runtime/memory/fact_compactor.py:210`, `agents/runtime/agent.py` ×3, `agents/runtime/prompt_assembler.py:206`, `agents/protocol.py:186`, `agents/runtime/result_workspace_tools.py:268`, `agents/builtins/{template_list ×2, collection_document_list, collection_document_get}`, `adapters/s3_client.py:315`, `core/sse.py:118`, `core/resilience.py:91` (модуль мёртв, секция 2), `api/v1/routers/*` ×7 (health, collections ×4, admin/platform_settings, rag/stream, sandbox/runs), `services/*` ×8 (collection_csv, tool_result_store, collection/ ×6), `migrations/versions/0150` ×1.
- **2 redefinition:** `workers/tasks_collection_vectorize.py:248` (`CollectionService`), `api/v1/routers/rag/stream.py:18` (`AsyncSession`).
- **3 shadowed import:** `services/sandbox_override_resolver.py:102,296,343` — `field` из line 16 затеняется loop-переменной.
- **2 `global` unused:** `core/db.py:42` — `global _engine`/`_session_factory` без присваивания в области.
- **1 f-string без плейсхолдеров:** `services/prompt_service.py:59` (модуль test-only).

---

## 6. TypeScript/React

- **tsc** (`--noUnusedLocals --noUnusedParameters`): **0 диагностик** — фаза 4 держится.
- **knip:** 2 находки —
  - `scripts/visual-review.mjs` — неиспользуемый файл: **сохранён намеренно** (документированная CLI-точка входа, решение фазы 5);
  - `eslint.config.js` — unlisted `@eslint/js`: добавить в `devDependencies` (или в ignore knip), иначе свежий `npm ci` без транзитивного заноса может сломать lint.

Бейзлайны web (для контроля после будущих правок): vitest 13F/411P (424), lint: prettier 9990 / any 73 / restricted-imports 40 / no-undef 33 / exhaustive-deps 15, format:check 284.

---

## 7. Бейзлайны backend (docker)

- unit: **78 failed / 2084 passed / 3 skipped**
- integration: **8 failed / 44 passed / 146 skipped**

Полномножества падений идентичны базе HEAD фаз 1–5 — при следующих удалениях контролировать побайтово.

> **Контроль после зачистки 2026-11-20 (сводный прогон `pytest tests/`):** 86 failed / 2097 passed / 137 skipped. Множества FAILED побайтово идентичны этим бейзлайнам: unit 78 = 78, integration 8 = 8 — 0 новых, 0 починившихся. Дельты passed −31 / skipped −12 — только удалённые тесты умерших объектов (расшифровка в «Статусе исполнения» наверху). Эти сводные числа — новая база для следующих проходов.

---

## 8. Рекомендации по порядку очистки

1. ✅ **Исполнено (фаза A).** Мёртвые модули (секция 2, 9 шт.) удалены целиком; pyflakes погасил `resilience.py:91` из секции 5, `make test`-контроль в docker пройден.
2. ✅ **Исполнено (фаза B).** Test-only модули и few test-only удалены вместе с тестами (5 модулей + 4 тест-файла + записи `_EXPORTS`; `build_runtime_operation_slug`/`cleanup_expired` — в фазе C с тест-хирургией).
3. ✅ **Исполнено (фазы C + каскад).** Vulture dead-71 вырезаны по манифесту, кроме согласованных исключений `api/mcp/schemas.py` ×2 (за владельцем mcp); few-dead-12 — вместе с каскадами (`_EXPORTS`-записи, `InstanceDomain` + строка реэкспорта). Каскад добавил ещё 19 объектов.
4. ⬜ **Undefined-name баги (секция 4)** — не легаси: завести тикеты владельцам (`runtime` — блок `pipeline.py:2086–2123` и `:522`; admin/rag/sandbox-роутеры; `plan_store`). Фикс точечный, до любых следующих удалений в этих файлах.
5. ⬜/опционально **Импорты (секция 1) и TS (секция 6)** — ничего делать не нужно; опционально внести `@eslint/js` в devDependencies.
6. ⬜ **Unused locals (секция 5)** — по желанию, последним, отдельным механическим коммитом.

## Как воспроизвести

```bash
# Python
python3 -m pyflakes apps/api/src apps/emb/src apps/rerank/src mcp scripts
python3 -m vulture apps/api/src apps/emb/src apps/rerank/src mcp scripts --min-confidence 60
# Секция 3: vulture-пайплайн r2 (токен-индекс кэшируется в r2/token_index.pkl)
python3 .cleanup-tmp/r2/pipeline.py
# Секция 2: модульный граф (BFS-фикспоинт с __init__-живостью)
python3 .cleanup-tmp/r2/module_graph.py   # → r2/module_graph.json
# TypeScript (из apps/web)
npx tsc -p tsconfig.json --noEmit --noUnusedLocals --noUnusedParameters
npx knip --no-exit-code
```

Скрипты лежат в `.cleanup-tmp/` (в `.gitignore`). Python-тесты — только в docker (`make test` не использовать из-за `--maxfail=10`); npm — с `--legacy-peer-deps`.
