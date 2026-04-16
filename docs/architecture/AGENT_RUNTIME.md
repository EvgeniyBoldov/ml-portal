# Agent Runtime

## Обзор

Текущий runtime построен как многослойный execution pipeline:

`ChatStreamService -> ChatTurnOrchestrator -> RuntimePipeline -> ExecutionPreflight -> PlannerRuntime -> AgentToolRuntime -> DirectOperationExecutor`

Это важно: агентный runtime больше не является одним простым tool-call loop. Он уже включает:
- triage,
- preflight разрешение доступных агентов/коллекций/операций,
- planner loop,
- sub-agent operation loop,
- trace/logging and pause handling.

## Архитектурное правило

- MCP принимается как **стандарт operation contract**
- Это означает единый descriptor:
  - `name`
  - `description`
  - `inputSchema`
  - optional `outputSchema`
- Это **не означает обязательный сетевой hop**
- Локальные коллекции пока остаются **local / in-process providers**
- Если позже появится практический смысл, local collection provider можно вынести в отдельный MCP container/server без изменения planner/runtime contracts

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

### Local provider / operation adapter
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
        # triage -> preflight -> outline -> planner dispatch
```

## Operation Contract

LLM-facing contract provider-agnostic и использует MCP-compatible descriptor.

Канонический блок вызова:

```
\`\`\`operation_call
{"operation": "instance.docs.search", "arguments": {"query": "..."}}
\`\`\`
```

При этом:
- local collection operations публикуются в том же формате descriptor, что и MCP tools,
- executor уже сам решает, это in-process provider или remote MCP target,
- planner и runtime оперируют canonical operations, а не raw tool names провайдера.

## Runtime flow

```
1. `ChatStreamService` или sandbox создаёт `ToolContext`.
2. `RuntimePipeline` делает triage: `final | clarify | orchestrate`.
3. Для `orchestrate` path выполняется `ExecutionPreflight`.
4. Preflight собирает `ExecutionRequest` с доступными агентами, коллекциями, операциями и execution targets.
5. `PlannerRuntime` выбирает следующий шаг.
6. Если нужен sub-agent, `AgentToolRuntime` выполняет operation loop.
7. `DirectOperationExecutor` dispatch-ит local/MCP execution.
8. Runtime стримит события и пишет trace/run steps.
```

## Execution Modes

| Mode | Описание | Условие |
|------|----------|---------|
| `full` | Все операции доступны | Все required operations available |
| `partial` | Часть операций недоступна | supports_partial_mode=true |
| `unavailable` | Агент недоступен | Required operation unavailable, partial=false |

## Policy Limits

Ограничения из Policy модели:

| Параметр | Описание |
|----------|----------|
| `max_steps` | Максимум итераций loop |
| `max_tool_calls_total` | Максимум operation calls |
| `max_wall_time_ms` | Таймаут выполнения |
| `tool_timeout_ms` | Таймаут одной операции |
| `max_retries` | Повторы при ошибке |
| `streaming_enabled` | Разрешить стриминг |
| `citations_required` | Требовать цитаты |

## Collection resolution

Runtime уже должен мыслить не "любой collection одинаковый", а resolver-ами по типу коллекции.

Текущие resolver categories:
- local table collection,
- local document collection,
- remote SQL collection stub.

Минимальные retrieval profiles:
- `table.hybrid` — фильтры/поиск + semantic fallback по retrieval fields,
- `document.semantic` — семантический поиск по документным фрагментам,
- `remote.sql.catalog` — каталог таблиц/схем и планирование SQL-доступа.

Правило:
- новый тип коллекции должен приводить к явному новому resolver path,
- semantics/publication/runtime prompt assembly не должны угадывать representation неявно.

## Pause / resume

Текущее поведение:
- runtime может остановиться на `waiting_input` или `waiting_confirmation`,
- pause state сохраняется в `agent_run` и `chat_turn`,
- continuation сейчас идет как новый chat turn в том же чате.

Это рабочий production path, но это еще не mid-run checkpoint resume.

Текущее усиление контракта continuation:
- при `POST /api/v1/chats/runs/{run_id}/resume` формируется `resume_checkpoint`,
- source run переводится в статус `resumed`,
- checkpoint сохраняется в `agent_runs.context_snapshot.resume_checkpoint`,
- continuation run получает lineage через `context_snapshot.continuation_meta`.

## Retrieval Surfaces

Публичные retrieval operations (видны planner/LLM):
- `collection.document.search`
- `collection.table.search`

Внутренние builtin handler slugs (runtime implementation detail):
- `collection.doc_search` -> публикуется как `collection.document.search`
- `collection.search` -> публикуется как `collection.table.search`
- `collection.text_search` -> внутренний runtime handler (не публикуется planner/LLM напрямую)

Правило:
- в prompts, planner и inspect surfaces используем только canonical operation names,
- raw builtin slugs остаются внутренним адаптерным слоем.

## Runtime Evaluation Harness

Для baseline-проверки качества runtime добавлен каркас evaluation harness:
- `app/services/runtime_evaluation_harness.py`
- кейсы задают required/forbidden operations и ожидаемые event-типы (`final`, `waiting_input`, `error`)
- результат вычисляет score и диагностические notes

Назначение:
- прогон эталонных сценариев chat/document/sql/tool-path на уровне trace/event контракта,
- быстрый регрессионный фильтр до полноценного deterministic replay/trace-pack.

Для trace-pack добавлен admin export endpoint:
- `GET /api/v1/admin/agent-runs/{run_id}/trace-pack`
- включает: `context_snapshot`, `operations`, `prompt_surfaces`, `tool_io`, `errors`, `timeline`
- используется как стабильный вход для воспроизводимого анализа и будущего replay runner.

Budget policy visibility:
- planner и agent runtime публикуют status stage `budget_policy` в event stream,
- в trace steps пишется `budget_policy` (и `budget_limit_exceeded` при срабатывании лимита),
- `AgentToolRuntime` блокирует исполнение при достижении `max_tool_calls_total`.

Runtime control-plane endpoints:
- `GET /api/v1/admin/agent-runs/capability-graph?tenant_id=...&user_id=...&agent_slug=...`
  - возвращает граф `agent -> operation -> data_instance/provider/collection`,
  - показывает `missing.tools|collections|credentials` из resolve-прохода,
  - используется как explainability surface для preflight/inspector UI.
- `GET /api/v1/admin/agent-runs/hitl-policy?tenant_id=...&user_id=...`
  - возвращает явный HITL-contract:
    - global gates (`forbid_destructive`, `require_confirmation_*`, `max_iters`),
    - condition-level правила (`require_input`, `require_confirmation`, `block`),
    - operation-level effective decision для каждой runtime operation,
    - pause/resume contract (`waiting_input|waiting_confirmation`, resume endpoint/payload).

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

1. Создать local provider handler / adapter
2. Экспортировать MCP-compatible descriptor:
   - `name`
   - `description`
   - `inputSchema`
   - optional `outputSchema`
3. Подключить provider к домену data instance
4. Убедиться, что `OperationRouter` публикует `ResolvedOperation`
5. Не делать agent bindings source of truth для runtime

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
- naming событий пока частично legacy (`tool_call`, `tool_result`),
- целевое направление: `operation_call`, `operation_result`,
- sandbox inspector и traces уже должны опираться на canonical payloads, а не на raw UUID-only surfaces.
