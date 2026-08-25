# Agent Runtime

## Обзор

Текущий runtime построен как многослойный execution pipeline:

`ChatStreamService -> ChatTurnOrchestrator -> RuntimePipeline -> PipelineAssembler -> GraphPlanner -> SqlPlanStore -> GraphOrchestrator -> AgentExecutor -> DirectOperationExecutor`

Канонический планировщик теперь возвращает не следующий шаг, а смысловую
мутацию сохраняемого графа: `PlannerGraphOutput -> PlanPatch -> SqlPlanStore`.
`PlannerGraphOutput` не содержит revision, trigger, goal или идентификаторы:
runtime добавляет CAS-ревизию из snapshot непосредственно перед транзакционным
применением `PlanPatch`.
`GraphOrchestrator` единолично меняет статусы задач, фиксирует
попытки, checkpoint и различает технический failure от бизнес-результата
`unfulfillable`. Выполнение v1 последовательное; зависимости уже являются
частью контракта и готовы к будущему параллельному scheduler.

Это важно: агентный runtime больше не является одним простым tool-call loop. Он уже включает:
- preflight разрешение доступных агентов/коллекций/операций,
- persisted planner task graph with dependency/checkpoint pause handling,
- sub-agent operation loop,
- canonical event journal and pause handling.

## Архитектурное правило

- MCP принимается как **стандарт tool contract**
- Это означает единый descriptor:
  - `name`
  - `description`
  - `inputSchema`
  - optional `outputSchema`
- Это **не означает обязательный сетевой hop**
- Локальные коллекции пока остаются **local / in-process providers**
- Если позже появится практический смысл, local collection provider можно вынести в отдельный MCP container/server без изменения planner/runtime contracts

Канонический формат runtime trace и inspector contract фиксируются в [`docs/architecture/RUNTIME_TRACE_SPEC.md`](./RUNTIME_TRACE_SPEC.md).

## Компоненты

### ToolContext
Контекст выполнения runtime и operation execution.

```python
@dataclass
class ToolContext:
    tenant_id: UUID | str
    user_id: UUID | str
    chat_id: UUID | str
    scopes: list[str]
```

### Local provider / tool adapter
Абстрактный базовый слой локального исполнения.

```python
class ToolHandler(ABC):
    slug: str  # уникальный идентификатор
    name: str
    description: str
    
    @abstractmethod
    def input_schema(self) -> dict:
        """JSON Schema для входных параметров"""
        pass
    
    @abstractmethod
    async def execute(self, ctx: ToolContext, args: dict) -> str:
        """Выполнение инструмента"""
        pass
```

### ToolRegistry
Singleton реестр локальных handlers.

Важно:
- это **technical registry**, а не source of truth runtime-модели
- runtime должен опираться на:
  - `ResolvedDataInstance`
  - `ResolvedOperation`
  - `ProviderExecutionTarget`
- для local providers registry допустим как implementation detail
- для MCP providers capability discovery идёт через `tools/list`
- historical trace/run contracts не сохраняются и не читаются.

```python
class ToolRegistry:
    _handlers: dict[str, ToolHandler]
    
    def register(self, handler: ToolHandler) -> None
    def get(self, slug: str) -> ToolHandler | None
    def list_all(self) -> list[ToolHandler]
```

### ExecutionPreflight
Каноническая pre-runtime стадия разрешения.

```python
class ExecutionPreflight:
    async def prepare(...) -> ExecutionRequest:
        # 1. Resolve active agent/version
        # 2. Resolve collections and operation availability
        # 3. Resolve permissions and credentials
        # 4. Build execution targets and available actions
        # 5. Determine execution mode
```

### RuntimePipeline
Единая точка входа runtime.

```python
class RuntimePipeline:
    async def execute(...) -> AsyncGenerator[RuntimeEvent, None]:
        # platform snapshot -> memory -> planning -> agent execution -> finalization
```

## Tool Contract

LLM-facing contract provider-agnostic и использует MCP-compatible descriptor.

Канонический блок вызова:

```
\`\`\`tool_call
{"tool": "collection.document.search", "arguments": {"collection_slug": "docs", "query": "..."}}
\`\`\`
```

При этом:
- local collection tools публикуются в том же формате descriptor, что и MCP tools,
- executor уже сам решает, это in-process provider или remote MCP target,
- planner и runtime оперируют resolved tool names выбранного provider-а;
- каждый collection-scoped вызов обязательно передаёт `collection_slug`. Имя
  тулзы не кодирует instance, provider или source;
- `CollectionRuntimeResolver` — единственный резолвер target-а, а
  `CollectionToolResolver` — единственный резолвер tools этого target-а: для local
  collection он выбирает provider по `collection_type`, для SQL/API следует
  цепочке `collection -> data source -> MCP provider`. RBAC применяется после
  этого резолвинга к каждой коллекции, не к общему provider. Tools берутся как
  active discovered tools выбранного provider-а плюс platform defaults коллекции;
  список provider-specific имён в коде не используется.

## Runtime flow

```
1. `ChatStreamService` или sandbox создаёт `ToolContext`.
2. `RuntimePipeline` загружает platform snapshot и строит turn memory.
3. Planner генерирует semantic action (`apply_graph`, `ask_user`, `complete` или `fail`); runtime преобразует его в строгий `PlanPatch` с текущей revision. Каждый task содержит `executor`, `intent`, `instructions`, `depends_on` и `needs`.
4. Orchestrator выбирает одну ready task и создаёт `RuntimeTaskAttempt`.
5. Для task выполняется `ExecutionPreflight`, затем `AgentExecutor` возвращает строгий `AgentTaskResult`.
6. Технический сбой сохраняется отдельно и может быть retried; `unfulfillable` является валидным бизнес-результатом.
7. Checkpoint и outputs открывают зависимости или возобновляют логическую task новым attempt.
8. FinalizationStage формирует финальный ответ только после terminal plan; sandbox сохраняет и стримит canonical journal events, chat стримит только пользовательский transport.

### Memory lifecycle

Turn memory is assembled before planning by `MemoryBuilder`. It reads only
bounded confirmed active facts for the effective user and tenant through
`MemoryService`; the builder also assembles bounded in-turn tool, agent and
attachment sections. For sandbox runs, branch fact overlays are applied before
the immutable snapshot is handed to runtime.

The `memory` system role is not a fact writer: it selects indexes from the
already loaded facts, project catalogue and confirmed glossary, and may report
ambiguities. Glossary aliases are used by `memory.lookup` to expand terms before
project and project-memory-key matching; project rules are never injected into
the automatic turn snapshot. A failed selection falls back to an empty
optional context and does not fail the main turn.

After finalization, the chat path emits the answer and dispatches
`finalize_memory` asynchronously. That worker runs `FactExtractor`,
`FactCompactor` and `FactReconciler`; evidence is deduplicated into
`FactObservation`, active rows use supersede semantics, and only confirmed
facts are read by a later turn. Writeback failures are isolated from the user
answer. Sandbox fact overlays never persist directly to the durable `facts`
table.

### Единый journal boundary

`RuntimeEventLogger` создаётся один раз на root run и является единственным
writer в `runtime_execution_events`. Он назначает DB `event_id` и `sequence`,
после чего возвращает тот же event для SSE/tail. Planner, orchestrator, task
executor, agent runtime, tools, budgets и workers получают только scoped sink
и эмитят `RuntimeEvent`; они не создают logger, sequence, envelope stamper или
отдельный trace store.

Preflight, operation execution and agent-triggered document extraction are
also journalled semantic boundaries. Extraction is a child of `tool_call`;
independent RAG ingestion keeps its own job-status/event contract.
The canonical trace presentation hierarchy is
`run -> orchestrator -> plan_revision -> step -> agent_execution -> llm_call|tool_call|interaction|error|snapshot`.
`task` and `attempt` are persisted execution-control entities, not a competing
trace containment chain: lifecycle rows retain their plan parent and carry
explicit task/attempt references to the corresponding executor run. Until the
breaking terminology migration, emitted `planner_iteration`/`iteration` rows
are the legacy wire name for `plan_revision`.

### Progress delivery

The logger is also the only admission point for user-safe execution progress.
`RuntimeProgressStreamer` projects a bounded intent/fallback description from
the same canonical event and publishes it through the runtime tail channel.
Chat consumes only `runtime_progress` projections; deltas remain a separate
answer-content stream. `stream_logs` and `stream_progress` are independent:
chat root uses `none/false/true`, sandbox uses `full/true/true`, and agent
scopes decide detail from their own logging level.
```

## Execution Modes

| Mode | Описание | Условие |
|------|----------|---------|
| `full` | Все инструменты доступны | All required tools available |
| `partial` | Часть инструментов недоступна | supports_partial_mode=true |
| `unavailable` | Агент недоступен | Required tool unavailable, partial=false |

## Policy Gates и Execution Limits

Ограничения исполнения теперь задаются через `execution_limits` (а не через platform caps).
Policy gates остаются отдельным runtime enforcement-слоем.

| Параметр | Описание |
|----------|----------|
| `max_steps` | Максимум итераций loop |
| `max_tool_calls_total` | Максимум tool calls |
| `max_wall_time_ms` | Таймаут выполнения |
| `tool_timeout_ms` | Таймаут одного вызова инструмента |
| `max_retries` | Повторы при ошибке |
| `streaming_enabled` | Разрешить стриминг |
| `citations_required` | Требовать цитаты |

Источник значений лимитов:
- `platform` scope — базовые лимиты по умолчанию;
- `orchestrator_role` scope — лимиты системных ролей (`planner`, `synthesizer`, `fact_extractor`, `fact_compactor`);
- `agent` scope — лимиты конкретного агента.

`ExecutionLimitsService.resolve` применяет эту иерархию к каждому полю:
entity scope → `platform/global` → code fallback. Поэтому effective profile не
может быть пустым даже при неполной или ещё не мигрированной БД. Sandbox
override применяется последним и не может обнулить значение. Agent execution
snapshot хранит также источник каждого resolved поля (`entity`, `platform`,
`sandbox`, `code`).

`llm_timeout_s` задаёт ожидание одного LLM-вызова. Значение в более узком
scope замещает platform default; для системных ролей при отсутствии лимита
используется их role timeout.

LLM transport uses the single OpenAI-compatible SDK adapter for vLLM,
LiteLLM and compatible providers. Callers resolve the effective entity limit
before the call and pass it to the adapter as the per-request SDK timeout;
cached clients do not freeze a role timeout. SDK retries are disabled: runtime
is the sole owner of semantic retry, budget accounting and `protocol_retry`.
Provider failures are normalized into safe stable codes (timeout, connection,
authentication, rate limit, context/request limit, tool/structured-output
capability and upstream failure) before they reach runtime stages.

Policy gates (`require_confirmation_*`, `forbid_*`) применяются в `PolicyEngine` перед выполнением действия.
`require_backup_before_write` сейчас хранится как конфиг-флаг, но в enforcement-решениях runtime не участвует.

## Collection resolution

Runtime мыслит коллекцией как semantic/data scope, а не как именем
provider-инстанса. Публичный вызов всегда содержит `collection_slug`; UUID
коллекции не является LLM-facing аргументом. Runtime после валидации slug
разрешает конкретную коллекцию, проверяет effective access и создаёт
target-specific execution binding.

`CollectionRuntimeResolver` — единственная точка выбора runtime target:

- local `table`, `document` и `template` выбирают общий in-process provider по
  `collection_type`;
- remote `sql` и `api` проходят цепочку
  `collection -> data_instance -> access_via/provider`;
- RBAC и readiness применяются к каждой разрешённой коллекции и её target, а
  не к общему provider-инстансу.

Минимальные retrieval profiles:
- `table.hybrid` — фильтры/поиск + semantic fallback по retrieval fields,
- `document.semantic` — семантический поиск по документным фрагментам,
- `remote.sql.catalog` — каталог таблиц/схем и планирование SQL-доступа;
- `remote.api` — operations, которые реально отдал выбранный API provider
  через discovery, за MCP-compatible descriptor.

Правило:
- новый тип коллекции должен приводить к явному новому resolver path,
- semantics/publication/runtime prompt assembly не должны угадывать representation неявно.

## Pause / resume

### Каноническое поведение
- Runtime может остановиться на `waiting_input` или `waiting_confirmation`.
- Pause state сохраняется в transport state и canonical checkpoint/plan state.
- Continuation всегда переиспользует исходный runtime run и тот же
  `RuntimePipeline`; это не новый пользовательский запрос и не новый root run.

Перед повторным запуском исполнителя строится неизменяемый `resume_checkpoint`.
Он хранит исходную цель отдельно от пользовательского ввода, поэтому ответ на
уточнение не может стать новым `goal`.

### Контракт paused_action / paused_context
- Backend должен сохранять полный paused-state через `RuntimeHitlProtocolService.build_paused_from_stop`.
- Resume endpoint должен читать `run.paused_action` / `run.paused_context` для восстановления контекста.
- Pipeline не должен затирать эти данные при паузе.

### Resume endpoints
- **Chat**: `POST /chats/runs/{id}/resume` → SSE-стрим (не JSON).
- **Sandbox**: `POST /sandbox/sessions/{sid}/runs/{rid}/resume` → SSE-стрим, тот же `RuntimePipeline`, тот же run_id (не создавать новый).
- Sandbox resume продолжает тот же sandbox run id; chat continuation не создаёт root journal run.
- Оба endpoint принимают один payload: `{ "action": "input" | "confirm" | "cancel", "input"?: string }`.
  Для `waiting_input` допустимы `input` (непустое поле `input`) и `cancel`;
  для `waiting_confirmation` — `confirm` и `cancel`.
- Подтверждение выполняется только signed confirmation token, выпущенным из
  сохранённого pause state; raw fingerprints и отдельный confirm endpoint не
  являются transport contract.

## Retrieval Surfaces

Публичные collection operations (видны planner/LLM):
- `collection.info`
- `collection.document.search`
- `collection.document.list`
- `collection.document.get`
- `collection.table.search`
- `collection.template.list`
- `collection.template.search`
- `collection.template.get_schema`
- `collection.template.fill`

Внутренние builtin handler slugs (runtime implementation detail):
- `collection.doc_search` -> публикуется как `collection.document.search`
- `collection.search` -> публикуется как `collection.table.search`
- template handlers уже используют canonical `collection.template.*` slugs;
  их provider/instance binding остаётся внутренним.
- `collection.text_search` -> внутренний runtime handler (не публикуется planner/LLM напрямую)

Правило:
- в prompts, planner и inspect surfaces используем только canonical tool names,
- raw builtin slugs остаются внутренним адаптерным слоем.

## Project Memory Candidate Flow

`memory.lookup` is a global system operation which accepts multiple suspicious
terms, resolves confirmed glossary aliases, resolves matching project catalogue
entries, and returns bounded project-memory keys without values. `memory.read`
returns confirmed compact facts only for exact project keys and selected keys.
`memory.mark` never writes the database: it accepts only the runtime
`evidence_call_id` exposed by a successful tool result from the current turn and
stores bounded candidates in `RuntimeTurnState`. After Synthesizer
has returned the user answer, the normal asynchronous memory worker combines
those candidates with extracted user/tenant facts and sends project candidates
through the FactCompactor LLM before `FactReconciler` persists them.

The same writeback worker handles user and tenant candidates extracted from the
turn. `memory.mark` only places bounded evidence-backed candidates in
the current `RuntimeTurnState`; it is never a direct database write. Manual
admin fact edits use the separate admin fact service and are not treated as
LLM-extracted evidence.

## Runtime Evaluation Harness

Для baseline-проверки качества runtime добавлен каркас evaluation harness:
- `app/services/runtime_evaluation_harness.py`
- кейсы задают required/forbidden operations и ожидаемые event-типы (`final`, `waiting_input`, `error`)
- результат вычисляет score и диагностические notes

Назначение:
- прогон эталонных сценариев chat/document/sql/tool-path на уровне trace/event контракта,
- быстрый регрессионный фильтр до полноценной deterministic runtime evaluation.

Для admin inspection читается `runtime_execution_events` по самостоятельному
executor `run_id` или sandbox root `run_id`. Отдельных legacy read contracts
нет.

Budget policy visibility:
- planner и agent runtime публикуют status stage `budget_policy` в event stream,
- в trace steps пишется `budget_policy` (и `budget_limit_exceeded` при срабатывании лимита),
- `AgentToolRuntime` блокирует исполнение при достижении `max_tool_calls_total`.

Runtime control-plane reads plan state and canonical event journal directly;
Legacy control-plane endpoints удалены.

Structured answer contract (backend):
- assistant messages now persist `meta.answer_contract = answer_blocks.v1`,
- `meta.answer_blocks` includes normalized blocks:
  - `bigstring` (full answer text),
  - `code` (with `language`),
  - `table` (columns + rows),
  - `file` (name/url/content_type/size),
  - `citations` (source list).
- source implementation: `app/services/structured_answer_service.py`.
- grounding metadata:
  - `meta.grounding.score`
  - `meta.grounding.mode` (`none|weak|medium|strong`)
  - `meta.grounding.citations_count`

## Добавление новой локальной операции

1. Создать local provider handler / adapter или зарегистрировать remote MCP
   capability
2. Экспортировать MCP-compatible descriptor:
   - `name`
   - `description`
   - `inputSchema`
   - optional `outputSchema`
3. Подключить provider к collection resolver path; для remote source задать
   реляционную цепочку `data_instance -> access_via/provider`
4. Убедиться, что `OperationRouter` публикует один canonical
   `ResolvedOperation`, а target-specific binding остаётся внутренним
5. Включить `collection_slug` в input schema каждой collection-bound operation
6. Не делать agent bindings source of truth для runtime

## RuntimeEvent

События для стриминга:

```python
class RuntimeEvent:
    @staticmethod
    def delta(content: str) -> dict

    @staticmethod
    def tool_call(tool: str, args: dict) -> dict

    @staticmethod
    def tool_result(tool: str, result: str) -> dict

    @staticmethod
    def status(message: str) -> dict

    @staticmethod
    def done() -> dict

    @staticmethod
    def error(message: str) -> dict
```

Примечание:
- new runtime emits only canonical `tool_request` / `tool_result` journal events;
- transport aliases do not create persisted compatibility events.

## Context Snapshot Contract

Все lifecycle `*_start` события могут нести `context_snapshot` для фиксации состояния на момент старта сущности:

```python
context_snapshot: {
  inputs?: {
    user_request?: string
    goal?: string
    agent_input?: unknown
    planner_hint?: string
    iteration_intent?: string
  }
  system_prompt?: string
  system_prompt_hash?: string
  limits?: {
    planner_steps?: number
    agent_steps?: number
    tool_calls?: number
    tokens_in?: number
    tokens_out?: number
    tokens_total?: number
    retries?: number
    wall_time_ms?: number
  }
  rbac?: {
    candidates?: string[]
    allowed?: string[]
    denied?: string[]
    denied_by_rbac?: string[]
    denied_by_capability?: string[]
    reason?: Record<string, string>
  }
  meta?: {
    role?: string
    model?: string
    agent_slug?: string
    version_label?: string
    explicit_agent_slug?: string
    available_operations?: string[]
    available_agents?: string[]
    components?: string[]
    attempt?: number
    max_attempts?: number
    memory_digest?: {
      facts?: number
      summary_chars?: number
    }
  }
}
```

### События с snapshot
- `run_start` — `inputs.user_request`, `limits`, `meta.agent_slug`, `meta.model`
- planner `orchestrator_start` — `inputs.goal`, `system_prompt`, `limits`, `rbac`, `meta.role=planner`
- `planner_iteration_start` — `inputs.goal`, `inputs.iteration_intent`, `limits`, `meta.attempt`, `meta.available_agents`
- `agent_start` — `inputs.goal`, `inputs.agent_input`, `system_prompt`, `limits`, `rbac`, `meta.role`, `meta.agent_slug`
- `synthesis_start` — `inputs.goal`, `inputs.planner_hint`, `system_prompt`, `limits`, `meta.role=synthesizer`
- memory `orchestrator_start` — `inputs.user_request`, `limits`, `meta.role=memory`, `meta.components`
- memory component `agent_start` — `inputs.user_request`, `system_prompt`, `limits`, `meta.role`, `meta.agent_slug`

### Логирование prompt
- При `logging_level=full` писать полный `system_prompt`
- При `brief` писать только `system_prompt_hash`
