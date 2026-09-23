# Agent Runtime

## Обзор

Целевой runtime построен как многослойный execution pipeline:

`ChatStreamService -> ChatTurnOrchestrator -> RuntimePipeline -> mechanical lookup -> TurnPreflight -> GraphPlanner | Synthesizer`

При `GraphPlanner` ветка продолжается через
`SqlPlanStore -> GraphOrchestrator -> AgentExecutor -> DirectOperationExecutor`
и завершается Synthesizer. Полное решение зафиксировано в
[`ADR: TurnPreflight Routing`](./ADR_TURN_PREFLIGHT_ROUTING.md).

Канонический планировщик возвращает не следующий шаг, а предложение
сохраняемой итерации: `IterationProposal -> IterationCompiler -> SqlPlanStore`.
`IterationProposal` не содержит lifecycle, trigger, goal или идентификаторы:
runtime добавляет идентификаторы и транзакционно сохраняет iteration.
`GraphOrchestrator` единолично меняет статусы задач, фиксирует
попытки, terminal invocation и различает технический failure от бизнес-результата
`unfulfillable`. Выполнение v1 последовательное; зависимости уже являются
частью контракта и готовы к будущему параллельному scheduler.

Это важно: агентный runtime больше не является одним простым tool-call loop. Он включает:
- root-level TurnPreflight, который маршрутизирует пользовательский turn,
- preflight разрешение доступных агентов/коллекций/операций,
- persisted iterative task graph with dependency and explicit-pause handling,
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

`ExecutionPreflight` выполняется только для уже выбранного агентного task. Он
не является `TurnPreflight` и не выбирает маршрут пользовательского turn.

### TurnPreflight

Root-level системная роль перед planner. После дешёвого code-only lookup
глоссария, проектов и сущностей она возвращает строгий route: `synthesis`,
`planner`, `recall` или `clarify`. Для `planner` она формирует `TaskBrief`, для
`synthesis` — `SynthesisBrief`; сама не выполняет tools, не создаёт задачи и
не пишет память.

### RuntimePipeline
Единая точка входа runtime.

```python
class RuntimePipeline:
    async def execute(...) -> AsyncGenerator[RuntimeEvent, None]:
        # lookup -> TurnPreflight -> planning or synthesis -> writeback
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
1. `ChatStreamService` или sandbox создаёт `ToolContext`; runtime выполняет bounded mechanical lookup glossary/project/entity candidates.
2. `TurnPreflight` возвращает `synthesis`, `planner`, `recall` или `clarify` и соответствующий строгий brief/request.
3. `synthesis` передаёт `SynthesisBrief` напрямую Synthesizer без persisted plan и агентских задач. `recall` читает только запрошенный scoped context и вызывает TurnPreflight повторно.
4. `planner` передаёт `TaskBrief` в GraphPlanner. Planner сам использует canonical memory tools и генерирует полную неизменяемую iteration proposal только для агентской работы.
5. Terminal является свойством iteration, а не task. `planner` создаёт следующую iteration; `synthesis` запрашивает финальную сборку ответа. Run становится `completed` только после успешного synthesis.
6. Store возвращает typed scheduler decision. Orchestrator только исполняет его: создаёт attempt, вызывает агента, применяет один атомарный result либо вызывает planner/synthesizer.
7. Planner получает полный структурный ledger всех задач и попыток и выбирает продолжение, принятие partial outputs, исключение части объёма или сообщение ограничения пользователю.
8. Synthesis получает `SynthesisBrief`, successful reports всех iteration, явно принятые partial outputs, verified artifacts/sources и актуальные user-visible limitations. Сырые agent/tool journal и технические ошибки не передаются.

Оркестратор поддерживает явные task-статусы `pending`, `running`,
`waiting_retry`, `waiting_confirmation`, `needs_dependency`, `blocked`,
`completed`, `unfulfillable`, `failed` и `cancelled`.
`ready` вычисляется по зависимостям и не является отдельным источником истины.
Retry переводит задачу обратно в исполнение только после `next_retry_at`;
задача с неуспешной зависимостью получает `blocked`. Synthesis запускается
после достижения конечного статуса всеми агентными задачами и получает
отдельную bounded-проекцию `limitations` с безопасными причинами
неуспешных ветвей.

### Memory lifecycle

Memory is not an unconditional pre-planner prompt stage. Mechanical lookup
provides only bounded candidate aliases/projects/entities to TurnPreflight.
For `recall`, runtime reads the requested scoped context before a second
TurnPreflight decision. For `planner`, planner obtains project rules, processes
and facts on demand through canonical memory operations; it does not receive a
preassembled project-memory dump. Sandbox overlays remain scoped to the
immutable run snapshot.

TurnPreflight can attach evidence-backed memory candidates, but the role is not
a writer and cannot turn them into durable facts.

After terminal synthesis, the chat path emits the answer and dispatches
`finalize_memory` asynchronously. That worker runs `FactExtractor`,
`FactCompactor` and `FactReconciler` for user/tenant dialogue facts; project
knowledge is not written through this path. Document-derived Semantic Memory
uses the separate source-backed extraction and review flow described in
[`MEMORY.md`](MEMORY.md). Writeback failures are isolated from the user answer.
Sandbox fact overlays never persist directly to the durable `facts` table.

### Единый journal boundary

`RuntimeEventLogger` создаётся один раз на root run и является единственным
writer в `runtime_execution_events`. Он назначает DB `event_id` и `sequence`,
после чего возвращает тот же event для SSE/tail. Planner, orchestrator, task
executor, agent runtime, tools, budgets и workers получают только scoped sink
и эмитят `RuntimeEvent`; они не создают logger, sequence, envelope stamper или
отдельный trace store.

TurnPreflight, agent execution preflight, operation execution and
agent-triggered document extraction are also journalled semantic boundaries.
Extraction is a child of `tool_call`; independent RAG ingestion keeps its own
job-status/event contract.
The canonical trace presentation hierarchy is
`run -> turn_preflight -> llm_call`, затем либо `synthesis_run`, либо
`memory_recall -> turn_preflight`, либо `planner orchestrator -> planner_iteration`.
Агентская ветка сохраняет
`planner_iteration -> step -> agent_execution -> llm_call|tool_call|interaction|error|snapshot`.
`task` and `attempt` are persisted execution-control entities, not a competing
trace containment chain: lifecycle rows retain their plan parent and carry
explicit task/attempt references to the corresponding executor run.
`planner_iteration` events describe planner calls; они не являются отдельной
моделью плана или ревизией.

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
- Runtime приостанавливает адресную задачу со статусом `waiting_confirmation`
  либо root TurnPreflight с `waiting_input`.
- Confirmation pause сохраняется с fingerprint операции и возобновляет тот же
  runtime run и ту же задачу.
- Уточнение TurnPreflight не является paused plan: оно сохраняет root
  continuation context без plan/task, а ответ пользователя повторно проходит
  mechanical lookup и TurnPreflight в том же root run.

Перед подтверждённым повторным запуском исполнитель получает исходный task
request и проверенный fingerprint операции.

### Контракт paused_action / paused_context
- Backend сохраняет confirmation state через
  `RuntimeHitlProtocolService.build_paused_from_stop`; TurnPreflight сохраняет
  отдельный root clarification context.
- Resume endpoint читает соответствующий continuation context, не создавая
  plan для clarification.
- Pipeline не должен затирать эти данные при паузе.

### Resume endpoints
- **Chat**: `POST /chats/runs/{id}/resume` → SSE-стрим (не JSON).
- **Sandbox**: `POST /sandbox/sessions/{sid}/runs/{rid}/resume` → SSE-стрим, тот же `RuntimePipeline`, тот же run_id (не создавать новый).
- Sandbox resume продолжает тот же sandbox run id; chat continuation не создаёт root journal run.
- Оба endpoint принимают `{ "action": "confirm" | "cancel" }` для адресной
  confirmation pause или `{ "answer": "..." }` для TurnPreflight
  clarification. Ответ clarification не создаёт новый root run.
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

## Semantic Memory retrieval

`memory.search` is the bounded system operation for document-derived project
and company knowledge and confirmed glossary terms. It applies runtime ACL and
returns typed, source-aware results. TurnPreflight uses a separate mechanical
lookup for candidate aliases/projects/entities; it does not call `memory.search`
itself. Planner and agents may call `memory.search` when they need durable
knowledge. Project memory is source-backed and is not written by conversational
`FactExtractor` writeback. See [`MEMORY.md`](MEMORY.md) for extraction,
publication and UI contracts.

## Runtime Evaluation Harness

Для baseline-проверки качества runtime добавлен каркас evaluation harness:
- `app/services/runtime_evaluation_harness.py`
- кейсы задают required/forbidden operations и ожидаемые event-типы (`final`,
  `confirmation_required`, `error`)
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
- `turn_preflight_start` — `inputs.user_request`, bounded mechanical lookup, `system_prompt`, `limits`, `meta.role=turn_preflight`
- planner `orchestrator_start` — `inputs.goal`, `system_prompt`, `limits`, `rbac`, `meta.role=planner`
- `planner_iteration_start` — `inputs.goal`, `inputs.iteration_intent`, `limits`, `meta.attempt`, `meta.available_agents`
- `agent_start` — `inputs.goal`, `inputs.agent_input`, `system_prompt`, `limits`, `rbac`, `meta.role`, `meta.agent_slug`
- `synthesis_start` — `inputs.synthesis_task`, `inputs.completed_task_count`, `system_prompt`, `limits`, `meta.role=synthesizer`
- memory `orchestrator_start` — `inputs.user_request`, `limits`, `meta.role=memory`, `meta.components`
- memory component `agent_start` — `inputs.user_request`, `system_prompt`, `limits`, `meta.role`, `meta.agent_slug`

### Логирование prompt
- При `logging_level=full` писать полный `system_prompt`
- При `brief` писать только `system_prompt_hash`
