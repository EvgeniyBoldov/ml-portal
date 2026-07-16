# Agent Codebase Remediation

## Goal

Привести репозиторий к состоянию, в котором агент может безопасно исследовать и изменять код: архитектурные границы понятны, локальные правила находятся рядом с кодом, legacy подтвержден и удален только при доказанной неиспользуемости, а документация соответствует реализации.

## Acceptance criteria

- Описаны backend и frontend entrypoints, основные runtime/data flows, engines, connectors, workers, persistence и test contours.
- Для каждой архитектурной границы есть понятные правила или явно зафиксировано, почему отдельный `AGENTS.md` не нужен.
- Legacy-кандидаты имеют доказательство использования или неиспользуемости и решение по каждому.
- Неиспользуемый legacy удален без dangling imports, routes, registrations и config references.
- `AGENTS.md`, проектная документация и код не противоречат друг другу.
- Доступные backend/frontend проверки выполнены; пропуски и причины записаны ниже.

## Constraints

Первый структурный проход выполняется без чтения содержимого файлов: используются только пути, имена, расширения, git-метаданные и структура каталогов. Содержимое кода и конфигурации читается только на этапе подтверждения entrypoints, контрактов, зависимостей и legacy-кандидатов.

Legacy удаляется после проверки imports/exports, registrations, routes, configuration, Docker usage, tests and migrations. Тесты, которые проверяют удаленный контракт, актуализируются или удаляются; они не являются причиной возвращать мертвый код. Исторические миграции и реально используемые публичные контракты оцениваются отдельно, а compatibility adapters/aliases без активного потребителя удаляются.

## Research order

### 1. Backend structure

Исследовать `apps/api` первым: application entrypoint и lifecycle, API routers/dependencies, core/config/security, runtime/agents, services, repositories/models/schemas, adapters/connectors, workers, storage, migrations и tests.

Для каждого контура зафиксировать source of truth, входы/выходы, зависимости, transaction boundary, security boundary, error handling, observability и тесты.

Текущее подтвержденное состояние: приложение запускается из `app.main` через FastAPI lifespan; startup регистрирует embedding models, tool catalog/backend releases, local instances, discovered tools, seed agents и connector validation. Celery регистрирует RAG, collection, health, cleanup, LDAP и memory tasks.

### 2. Backend execution flows

Проследить HTTP flow, chat/runtime flow, tool discovery/publication/execution, RAG ingest/retrieval, MCP credential flow, sandbox snapshot/overlay и worker flow.

Текущий chat runtime: `ChatStreamService -> ChatTurnOrchestrator -> RuntimePipeline -> PipelineAssembler -> PlanningStage/AgentExecutor/FinalizationStage`. `ExecutionPreflight` разрешает agent version, permissions, data instances, credentials, operations и execution mode перед sub-agent execution.

### 3. Frontend structure

Исследовать app composition, router/providers, API client/hooks/schemas, shared UI, entities, domains, admin, runtime trace, sandbox и tests. Текущий frontend запускается из `main.tsx`, собирает providers в `AppProviders`, использует lazy React Router routes, единый `shared/api/http.ts`, `qk` и shared query client.

### 4. Local instructions

Сохранить верхнеуровневые `apps/api/AGENTS.md` и `apps/web/AGENTS.md`. Вложенный файл создавать только для самостоятельной архитектурной границы с отдельным контрактом, опасным режимом или правилами, которые нельзя корректно выразить в родительском файле.

### 5. Legacy audit and cleanup

Составить registry кандидатов с путем, ролью, evidence, replacement, риском и решением. Проверить старые editor-паттерны, `_deprecated` области, дубли entrypoints/configuration, неиспользуемые adapters/routes/services и obsolete migration artifacts. Удалять только доказанно мертвое.

### 6. Verification

Запустить targeted tests после затронутых контуров, затем backend unit/integration/migration/eval проверки, frontend type-check/lint/unit/build/e2e и финальную проверку отсутствия dangling references.

## Candidate AGENTS boundaries

Созданы только подтвержденные самостоятельные границы: backend `agents`, `runtime`, `adapters`, `workers`; frontend `domains/runtimeTrace`, `domains/sandbox`. `api`, `services`, `repositories`, `shared/api`, `shared/ui`, `domains/admin` покрываются родительскими правилами и не получили отдельный файл.

## Legacy registry

| Candidate | Evidence | Replacement | Decision |
|---|---|---|---|
| Frontend `*EditorPage` / `*.old*` | Current router uses `*Page` replacements; files are absent from current tree | `EntityPageV2`/current entity pages | No deletion: candidates already absent; remove stale references only if they are non-contract comments |
| Backend `_deprecated` paths | No current tracked `_deprecated` directory found; historical paths only in git history | Current `api/v1/routers` layout | No deletion |
| Backend chat package patch-point shim | `messages.py` resolved symbols from `chat.__init__`; only stale tests consumed it | Direct symbols in `messages.py` and direct test patching | Removed; tests now patch the owning module |
| Backend `ToolInstanceService.InstanceType` | Repository-wide search found only the alias declaration | `InstancePlacement` | Removed as unused alias |
| Backend `PermissionService` PermissionSet compatibility | `RbacRuleRepository` has no `get_all_for_context`; only stale tests injected it | Flat `RbacRule` resolution | Removed legacy branch, alias and legacy-only tests |
| Backend `RuntimeRbacResolver` legacy kwargs | No caller passed compatibility kwargs; only `**_legacy_kwargs` remained | Explicit RBAC arguments | Removed unused catch-all kwargs |
| Backend `AgentService.route_agent` | Repository-wide call graph found only the declaration; planner-driven routing is canonical | `RuntimePipeline`/planner and `AgentResolver` | Removed dead auto-routing stub |
| Backend `services/text_extractor.py` | Only lazy export remained; no runtime/test caller | `services.extractors.ExtractorRegistry` | Removed wrapper and lazy export after repository-wide call-graph check |
| Backend flat runtime budget tracker | `RunBudgetLedger`, `BudgetLimitsResolver` and `SubBudgetLedger` had no production construction; only stale tests and `agent.py` compatibility branches consumed them | `BudgetRegistry`/`BudgetResolver` with per-entity limits | Removed tracker, flat schemas, resolver, compatibility branches and stale tests; current runtime tests use the registry path |
| Backend compatibility/fallback branches | Some are active, others require per-symbol review | Current canonical resolver/runtime path | Remove unused aliases/adapters; retain only active data/migration compatibility |
| Historical migrations with `legacy` in filename | Alembic history artifacts | Later schema revisions | Keep; migration history is immutable |

## Architecture findings

- Backend has one current runtime entrypoint in `app.runtime.RuntimePipeline`; legacy triage wording in `AGENT_RUNTIME.md` was corrected.
- `PipelineAssembler` is the wiring boundary for memory, planner, agent executor and synthesizer; stages are per-turn.
- Tool execution is resolved through `ExecutionPreflight`/`OperationRouter`, then validated and dispatched by operation execution facade.
- Connector implementations are behind adapter interfaces, with model/credential resolution and lifecycle owned by core/services.
- Workers use Celery task registration and bridge into async services through per-event-loop session handling and `worker_transaction`.
- Frontend has one router/provider composition, one HTTP client, centralized query keys, shared UI, and shared runtime trace/sandbox contracts.
- Trace tree heuristic fallback is read compatibility for historical/pre-canonical events, not a permitted new backend emit path.
- Triage role/model/contract compatibility remains in the repository for migration and historical/admin compatibility; it is not a current pipeline stage.
- Tests are not treated as an authority for removed APIs: stale tests are migrated to current contracts or removed with the dead surface.

## Documentation drift

- Corrected `docs/architecture/AGENT_RUNTIME.md` to describe the current pipeline without triage and with `PipelineAssembler`, planning, agent execution and finalization stages.
- Added scoped instructions for agent operation contracts, runtime pipeline, adapters, workers, frontend trace and sandbox.
- Existing `apps/api/AGENTS.md` and `apps/web/AGENTS.md` remain the broad rules; no contradictory local rule was introduced.
- Removed the chat router package patch-point shim and the unused `ChatStreamService.agent_service` test fixture surface; no production alias was added for stale tests.
- Runtime trace legacy normalization/heuristic paths are active read compatibility for historical event payloads and remain isolated from new event emission.
- Removed `services/text_extractor.py` and its unused lazy export after proving that runtime, workers and tests use `ExtractorRegistry` directly.

## Verification log

| Check | Result | Notes |
|---|---|---|
| Structural inventory | Completed | First pass used paths/names only; backend-first map then confirmed in code |
| Backend targeted tests | Passed | Updated prompt, runtime, collection, chat resume, orchestrator and collection provisioning tests; chat group `25 passed`; migration/connector group `13 passed` |
| Backend unit suite | Blocked by native process crash | `1082` items collected; run reached 39%, then Python/asyncpg segfaulted in `test_iteration_id_parent_links_correctly`; the test passes in isolation |
| Frontend type-check | Passed in Docker | Host dependencies are absent; Docker `tsc --noEmit` passed |
| Frontend unit tests | Passed | `21` files, `104` tests; rerun after sandbox legacy branch removal |
| Frontend build | Passed | Vite production build completed; existing large-chunk warnings remain |
| Frontend lint | Environment failure | ESLint could not load `/app/node_modules/json-schema-traverse/index.js`; no lint result |
| Legacy reference scan | Completed | Removed unused chat shim and sandbox unknown-argument branch; retained only active historical read compatibility and exposed extraction surface |

## Backend functional blocks

| Block | Responsibility | Canonical boundary | Main drift/legacy signal |
|---|---|---|---|
| API and dependencies | HTTP routing, auth context, request validation, SSE/error mapping | `api -> services` | Some routers still construct providers directly; review before adding new paths |
| Core/platform | config, DB/session lifecycle, security, RBAC, cache, health, observability | `core` owns cross-cutting infrastructure | Startup performs several independent commits; ownership is explicit but not centralized |
| Agents and tools | agent resolution, preflight, permissions, credentials, typed operation handlers | `agents -> services/adapters`, builtin registry | Persisted deprecated/lifecycle vocabulary and historical aliases need active-consumer review |
| Runtime | planner, pipeline assembly, stages, budgets, memory, trace events | `RuntimePipeline` and `PipelineAssembler` | Historical triage names remain only in compatibility/data paths |
| Domain services | chat, collections, RAG, sandbox, credentials, tool instances | service owns business orchestration | Several large services and compatibility entrypoints require decomposition, not new facades |
| Persistence | repositories, models, schemas, transaction-local CRUD/query | repositories use `flush()`, outer boundary commits | Direct session usage in services/workers needs per-flow review |
| Adapters/connectors | LLM, embeddings, vector store, object storage, queue, email | interface/protocol -> provider implementation | Embedding factory crosses into DB/credentials; Qdrant retains `_legacy_search` |
| Workers | Celery entry, async bridge, ingest/cleanup/health jobs | worker session/transaction boundary | Direct worker commits are allowed only at explicit task boundary |
| Migrations | schema evolution and mandatory system defaults | Alembic revision chain | Historical revisions contain broad data mutation/backfills beyond the new rule |

## Migration review

The current history contains data-changing revisions including `0002` default admin/tenant seed, `0011` planner/triage role replacement, `0014` collection backfill, `0016` execution parameter move, `0017` membership backfill and `0025`/`0026` tenant detachment updates. These revisions are historical and must not be rewritten.

The new rule is recorded in `apps/api/src/app/migrations/AGENTS.md`: migrations are schema-only, except for idempotent defaults required for mandatory system components such as planner/orchestrator. User, tenant, chat, collection, credential and other working data must be changed by application code or a separately reviewed backfill process.

## Connector and transaction review

Connector instances are normalized and validated in `services/tool_instance`; provider calls belong behind adapter interfaces and implementations. Repositories and connector services use `flush()` but do not own the final commit. API unit-of-work dependencies, startup tasks and worker task transactions are the current commit owners.

Observed drift to review:

- `adapters/embeddings.py` contains model DB lookup, credential resolution and provider construction in one factory, including legacy sync fallback. This crosses the adapter/service boundary and should be split before further provider growth.
- `adapters/impl/qdrant.py` retains `_legacy_search`; it is an active 404 fallback covered by current tests, so it must remain isolated and must not become a new connector contract.
- Provider implementations are not uniformly expressed through the declared protocols: LLM implementations expose extra methods and embeddings are partly factory-driven. New connector work must not add another parallel contract.
- Worker modules and startup tasks call `commit()` directly. This is allowed only at their explicit transaction boundary and must not be copied into adapters, repositories or domain helper methods.

## Future review queue

| Priority | Review item | Evidence to collect | Rule for decision |
|---|---|---|---|
| P0 | Remove/replace adapter DB and credential lookup | imports and tests for `EmbeddingServiceFactory` fallbacks | adapter receives resolved config; service/startup owns persistence and credentials |
| P0 | Audit migration data mutations | revision-by-revision classification and production revision state | keep history, prohibit new user/tenant backfills in Alembic |
| P1 | Revisit Qdrant `_legacy_search` | provider endpoint migration and runtime test coverage | remove only after the 404 fallback is no longer needed |
| P1 | Audit commit ownership in workers/startup | task/service call graph and rollback behavior | one explicit owner per transaction, no nested commits |
| P2 | Purge generated `__pycache__` from source tree | tracked files and ignore rules | generated artifacts never belong in source directories |

## Test source of truth

Production code and current documented contracts are authoritative. Tests must be updated or deleted when they assert removed APIs, old signatures, legacy fallback behavior or obsolete architecture. A test is retained only when it protects a current behavior, migration invariant or explicitly documented historical read-compatibility path.

## Frontend functional blocks

| Block | Responsibility | Canonical boundary | Main drift/legacy signal |
|---|---|---|---|
| App shell | bootstrap, providers, auth, theme, query client, error boundary | `main.tsx -> AppProviders -> router` | Provider order is centralized; new global state must not bypass it |
| Routing | lazy user/admin/sandbox route composition and guards | `router.tsx`, `AdminGuard`, `GPTGate` | Route file is a large registry; new routes must follow current lazy/guard pattern |
| Shared API | HTTP client, auth refresh, typed endpoint modules, query keys, SSE | `shared/api/http.ts`, `keys.ts` | `shared/api` contains deprecated fields/provider aliases that need consumer-based cleanup |
| User domains | chat/GPT, profile, collections, RAG and common pages | domain pages + shared API/UI | Domain boundaries are feature-based but some API hooks remain broadly shared |
| Admin domain | entities, versions, models, instances, tools, RBAC, credentials, settings | `EntityPageV2` + `Tab` + typed API | Old editor/tab patterns remain in repository and must not be copied |
| Runtime trace | event normalization, entity tree, budgets, artifacts, presentation | canonical trace entity tree | Explicit legacy assembler/field aliases are active historical-read fallback |
| Sandbox | run/session UI, branch overlays, inspector and chat | shared runtime/snapshot contract | keep the canonical `parentRunId` contract; historical payload normalization belongs at the boundary |
| Shared UI/lib | reusable components, tokens, forms, status/error/RBAC helpers | `shared/ui`, `shared/lib` | `DataTable` exposes legacy aliases; shared surface is large and needs API ownership review |

## Frontend legacy and drift

| Candidate | Evidence | Decision |
|---|---|---|
| `runtimeTrace/containerAssembler.ts` and legacy tree path | Imported by `buildEntityTree.ts` for events without canonical lifecycle parent links | Keep as read-only historical compatibility; no new emitter may depend on it; remove after event history migration is complete |
| `runtimeTrace/treeBudget.ts` legacy exports and `LegacyBudgetMetric` | Used by normalization and historical budget snapshot conversion | Keep only at read boundary; no new code may emit legacy budget shape |
| `sandbox/hooks/useSandboxRun.ts` legacy argument | Only caller passed `string | null`; `unknown` branch had no active consumer | Removed; hook now accepts the canonical `parentRunId?: string | null` type |
| `shared/ui/DataTable` legacy aliases | Only `SandboxListPage` used `title`/`idField`; all other columns already used canonical props | Removed aliases and migrated `SandboxListPage` to `label`/`keyField` |
| `shared/api/admin.ts` provider/deprecated fields | Types expose `provider` as deprecated and list APIs expose `include_deprecated` | Keep while backend lifecycle contract exposes them; UI must not introduce new deprecated flows |
| `shared/ui/themes/*` compatibility font aliases | Token comments only; no separate behavior | Low-risk cleanup after token consumers are checked |

The presence of `legacy`, `fallback` or `deprecated` is not alone proof of dead code. For frontend removal, first prove no route, hook, API module, test or historical-read path consumes the surface. Tests that only preserve removed UI/API shapes must be updated or removed.

## Frontend test review

Current unit tests cover shared UI, chat, runtime trace, sandbox selectors and normalization helpers. The source of truth is the current typed API/runtime contract, not fixtures copied from old backend payloads. Runtime trace fallback tests are valid only when they explicitly document historical read compatibility; tests for removed editor pages, old query keys or legacy component props should be deleted after call-site migration.

## Frontend future review queue

| Priority | Review item | Evidence to collect | Rule for decision |
|---|---|---|---|
| P1 | Split/retire runtime trace historical assembler | backend event history and `buildEntityTree` fallback coverage | retain only if historical payloads are still supported |
| P1 | Audit shared API deprecated fields | backend response schemas and UI usage | keep read compatibility only; remove write/UI paths for deprecated fields |
| P2 | Review shared UI ownership and large components | dependency graph and component size | move domain-specific behavior out of shared UI |
