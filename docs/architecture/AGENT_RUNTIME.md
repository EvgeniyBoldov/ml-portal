# Agent Runtime

## Обзор

Agent Runtime — движок выполнения AI-агентов через tool-call loop.

## Компоненты

### ToolContext
Контекст выполнения инструмента.

```python
@dataclass
class ToolContext:
    tenant_id: UUID
    user_id: UUID
    chat_id: UUID
    scopes: list[str]  # доступные scope для credentials
```

### ToolHandler
Абстрактный базовый класс для инструментов.

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
Singleton реестр зарегистрированных handlers.

```python
class ToolRegistry:
    _handlers: dict[str, ToolHandler]
    
    def register(self, handler: ToolHandler) -> None
    def get(self, slug: str) -> ToolHandler | None
    def list_all(self) -> list[ToolHandler]
```

### AgentRouter
Pre-runtime маршрутизатор.

```python
class AgentRouter:
    async def route(
        self,
        agent_slug: str,
        user_id: UUID,
        tenant_id: UUID,
        request_text: str
    ) -> ExecutionRequest:
        # 1. Load agent
        # 2. Resolve permissions
        # 3. Resolve tools + instances + credentials
        # 4. Check prerequisites
        # 5. Determine execution mode
        # 6. Create ExecutionRequest
        # 7. Log routing decision
```

### AgentRuntime
Основной движок выполнения.

```python
class AgentRuntime:
    async def run(
        self,
        request: ExecutionRequest,
        on_event: Callable[[RuntimeEvent], None]
    ) -> None:
        # Tool-call loop
```

## Tool-Call Protocol

Используется JSON-блок в ответе LLM (provider-agnostic):

```
\`\`\`tool_call
{"tool": "rag.search", "arguments": {"query": "..."}}
\`\`\`
```

## Flow выполнения

```
┌─────────────────────────────────────────────────────────────┐
│                      Agent Runtime Flow                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. ChatStreamService создаёт ToolContext                   │
│     └─► tenant_id, user_id, chat_id, scopes                │
│                                                             │
│  2. AgentRouter.route() создаёт ExecutionRequest           │
│     └─► agent, tools, credentials, mode                    │
│                                                             │
│  3. AgentRuntime.run() запускает loop                      │
│     │                                                       │
│     ├─► Build system prompt (base + baseline merge)        │
│     │                                                       │
│     ├─► If no tools → stream directly                      │
│     │                                                       │
│     └─► If tools → loop:                                   │
│         │                                                   │
│         ├─► LLM call (non-streaming)                       │
│         ├─► Parse tool_calls                               │
│         ├─► Execute tools                                  │
│         ├─► Append results to context                      │
│         └─► Repeat until done or limit                     │
│                                                             │
│  4. Stream final response via SSE                          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Execution Modes

| Mode | Описание | Условие |
|------|----------|---------|
| `full` | Все инструменты доступны | Все required tools available |
| `partial` | Часть инструментов недоступна | supports_partial_mode=true |
| `unavailable` | Агент недоступен | Required tool unavailable, partial=false |

## Policy Limits

Ограничения из Policy модели:

| Параметр | Описание |
|----------|----------|
| `max_steps` | Максимум итераций loop |
| `max_tool_calls_total` | Максимум вызовов инструментов |
| `max_wall_time_ms` | Таймаут выполнения |
| `tool_timeout_ms` | Таймаут одного инструмента |
| `max_retries` | Повторы при ошибке |
| `streaming_enabled` | Разрешить стриминг |
| `citations_required` | Требовать цитаты |

## Builtin Tools

### rag.search
Поиск по базе знаний.

```python
class RagSearchHandler(ToolHandler):
    slug = "rag.search"
    
    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "default": 5}
            },
            "required": ["query"]
        }
    
    async def execute(self, ctx, args):
        results = await rag_search_service.search(
            tenant_id=ctx.tenant_id,
            query=args["query"],
            limit=args.get("limit", 5)
        )
        return format_results(results)
```

## Добавление нового инструмента

1. Создать handler в `agents/builtins/`
2. Наследовать от `ToolHandler`
3. Реализовать `input_schema()` и `execute()`
4. Зарегистрировать в `agents/builtins/__init__.py`
5. Добавить миграцию для seed в БД
6. Добавить slug в bindings агента

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
