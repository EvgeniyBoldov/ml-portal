# Agent Runtime Architecture

## Оглавление

1. [Введение](#введение)
2. [Общая схема](#общая-схема)
3. [Компоненты системы](#компоненты-системы)
4. [Полный цикл обработки запроса](#полный-цикл-обработки-запроса)
5. [Модели данных](#модели-данных)
6. [Tool-Call Protocol](#tool-call-protocol)
7. [RAG Search](#rag-search)
8. [Логирование и Agent Runs](#логирование-и-agent-runs)
9. [Примеры JSON](#примеры-json)
10. [Troubleshooting](#troubleshooting)

---

## Введение

**Agent Runtime** — это ядро системы, которое позволяет LLM (Large Language Model) использовать внешние инструменты (tools) для выполнения задач. 

### Зачем это нужно?

LLM сама по себе не может:
- Искать в базе знаний (RAG)
- Делать запросы к внешним API
- Выполнять вычисления
- Получать актуальные данные

Agent Runtime решает эту проблему через **tool-call loop** — цикл, в котором:
1. LLM анализирует запрос пользователя
2. Решает, какой инструмент вызвать
3. Получает результат инструмента
4. Формирует финальный ответ

### Ключевые термины

| Термин | Описание |
|--------|----------|
| **Agent** | Профиль, объединяющий System Prompt + Tools + Config |
| **Prompt** | Шаблон системного промпта (Jinja2) |
| **Tool** | Инструмент, который агент может вызвать |
| **Tool Handler** | Python-класс, реализующий логику tool |
| **Agent Run** | Запись о выполнении агента (для отладки) |
| **Agent Run Step** | Отдельный шаг внутри run |

---

## Общая схема

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              FRONTEND (React)                               │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  ChatComposer → POST /chats/{id}/messages → SSE Stream             │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           API LAYER (FastAPI)                               │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  chat.py: send_message_stream()                                     │    │
│  │  - Валидация запроса                                                │    │
│  │  - Создание ChatStreamService                                       │    │
│  │  - SSE streaming response                                           │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        SERVICE LAYER                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  ChatStreamService                                                  │    │
│  │  - Idempotency check                                                │    │
│  │  - Save user message                                                │    │
│  │  - Load AgentProfile                                                │    │
│  │  - Create ToolContext                                               │    │
│  │  - Delegate to AgentRuntime                                         │    │
│  │  - Save assistant message                                           │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         AGENT RUNTIME                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  AgentRuntime.run()                                                 │    │
│  │  ┌───────────────────────────────────────────────────────────────┐  │    │
│  │  │  TOOL-CALL LOOP (max 10 iterations)                          │  │    │
│  │  │                                                               │  │    │
│  │  │  1. Build system prompt + tools instructions                 │  │    │
│  │  │  2. Call LLM (non-streaming)                                 │  │    │
│  │  │  3. Parse response for tool_calls                            │  │    │
│  │  │  4. If tool_calls found:                                     │  │    │
│  │  │     - Execute each tool                                      │  │    │
│  │  │     - Add results to context                                 │  │    │
│  │  │     - Go to step 2                                           │  │    │
│  │  │  5. If no tool_calls (final answer):                         │  │    │
│  │  │     - Stream response to client                              │  │    │
│  │  └───────────────────────────────────────────────────────────────┘  │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    ▼                 ▼                 ▼
            ┌─────────────┐   ┌─────────────┐   ┌─────────────┐
            │ rag.search  │   │ future.tool │   │ future.tool │
            │   (RAG)     │   │   (Jira?)   │   │  (NetBox?)  │
            └─────────────┘   └─────────────┘   └─────────────┘
```

---

## Компоненты системы

### 1. Agent (Агент)

**Файл:** `apps/api/src/app/models/agent.py`

Агент — это профиль, который определяет поведение AI-ассистента.

```python
class Agent:
    slug: str              # Уникальный идентификатор ("chat-rag", "chat-simple")
    name: str              # Человекочитаемое имя
    system_prompt_slug: str # Ссылка на промпт
    tools: List[str]       # Список доступных tools ["rag.search"]
    generation_config: Dict # Настройки LLM {"temperature": 0.7}
    enable_logging: bool   # Включить логирование в agent_runs
```

**Пример из БД:**
```json
{
  "slug": "chat-rag",
  "name": "RAG Chat Agent",
  "system_prompt_slug": "agent.rag.system",
  "tools": ["rag.search"],
  "generation_config": {"temperature": 0.3},
  "enable_logging": true
}
```

### 2. Prompt (Промпт)

**Файл:** `apps/api/src/app/models/prompt.py`

Промпт — это шаблон системного сообщения для LLM.

```python
class Prompt:
    slug: str              # "agent.rag.system"
    name: str              # "RAG Agent System Prompt"
    template: str          # Текст промпта (Jinja2)
    input_variables: List  # Переменные для подстановки
    version: int           # Версионирование
```

**Пример промпта для RAG агента:**
```
Ты — AI-ассистент с доступом к базе знаний компании.

## Твоя задача
Отвечать на вопросы пользователя, используя инструмент поиска по базе знаний.

## Правила работы
1. Используй rag.search для поиска информации перед ответом
2. НЕ вызывай инструменты повторно если ты уже получил результаты
3. При цитировании указывай источник (документ и страницу)
4. Отвечай на русском языке
```

### 3. Tool Handler

**Файл:** `apps/api/src/app/agents/handlers/base.py`

Tool Handler — это Python-класс, реализующий конкретный инструмент.

```python
class ToolHandler(ABC):
    slug: str              # "rag.search"
    name: str              # "Knowledge Base Search"
    description: str       # Описание для LLM
    input_schema: Dict     # JSON Schema аргументов
    
    async def execute(self, ctx: ToolContext, args: Dict) -> ToolResult:
        # Логика выполнения
        pass
```

### 4. Tool Registry

**Файл:** `apps/api/src/app/agents/registry.py`

Singleton-реестр всех доступных tools.

```python
# Регистрация
ToolRegistry.register(RagSearchTool())

# Получение
handler = ToolRegistry.get("rag.search")

# Получение для агента
handlers = ToolRegistry.get_for_agent(["rag.search", "jira.create"])
```

### 5. Agent Runtime

**Файл:** `apps/api/src/app/agents/runtime.py`

Ядро выполнения агентов с tool-call loop.

```python
class AgentRuntime:
    DEFAULT_MAX_STEPS = 10  # Максимум итераций цикла
    
    async def run(
        self,
        profile: AgentProfile,  # Агент + промпт + tools
        messages: List[Dict],   # История сообщений
        ctx: ToolContext,       # Контекст (tenant, user, chat)
        model: Optional[str],   # Override модели
    ) -> AsyncGenerator[RuntimeEvent, None]:
        # Yields события: thinking, tool_call, tool_result, delta, final
```

---

## Полный цикл обработки запроса

### Шаг 1: Пользователь отправляет сообщение

**Frontend → API**

```http
POST /api/v1/chats/550e8400-e29b-41d4-a716-446655440000/messages
Content-Type: application/json
Authorization: Bearer <token>

{
  "content": "Как настроить VLAN на Cisco?",
  "use_rag": true,
  "agent_slug": "chat-rag"
}
```

### Шаг 2: API создаёт ChatStreamService

**Файл:** `apps/api/src/app/api/v1/routers/chat.py`

```python
service = ChatStreamService(
    session=session,
    redis=redis,
    llm_client=llm,
    chats_repo=chats_repo,
    messages_repo=messages_repo
)
```

### Шаг 3: ChatStreamService обрабатывает запрос

**Файл:** `apps/api/src/app/services/chat_stream_service.py`

```
1. Check idempotency (Redis)
2. Verify chat access
3. Save user message to DB
4. Load AgentProfile (agent + prompt + tools)
5. Load chat context (last 20 messages)
6. Create ToolContext
7. Run AgentRuntime
8. Save assistant message to DB
9. Store idempotency result
```

### Шаг 4: AgentService загружает профиль

**Файл:** `apps/api/src/app/services/agent_service.py`

```python
profile = await agent_service.get_agent_profile(
    agent_slug="chat-rag",
    use_rag=True
)

# Результат:
AgentProfile(
    agent=<Agent chat-rag>,
    system_prompt=<Prompt agent.rag.system>,
    tools=["rag.search"],
    generation_config={"temperature": 0.3}
)
```

### Шаг 5: AgentRuntime выполняет tool-call loop

**Файл:** `apps/api/src/app/agents/runtime.py`

```
┌─────────────────────────────────────────────────────────────┐
│  ITERATION 1                                                │
├─────────────────────────────────────────────────────────────┤
│  1. Build system prompt:                                    │
│     - Base prompt from agent.rag.system                     │
│     - + Tools instructions (build_tools_prompt)             │
│                                                             │
│  2. Send to LLM (non-streaming):                            │
│     messages = [                                            │
│       {"role": "system", "content": "<system prompt>"},     │
│       {"role": "user", "content": "Как настроить VLAN?"}    │
│     ]                                                       │
│                                                             │
│  3. LLM Response:                                           │
│     "Сейчас поищу информацию в базе знаний.                │
│                                                             │
│     ```tool_call                                            │
│     {                                                       │
│       "tool": "rag.search",                                 │
│       "arguments": {"query": "настройка VLAN Cisco"}        │
│     }                                                       │
│     ```"                                                    │
│                                                             │
│  4. Parse tool_calls → found 1 call                         │
│                                                             │
│  5. Execute rag.search:                                     │
│     - Search in Qdrant                                      │
│     - Return top-5 chunks                                   │
│                                                             │
│  6. Add to context:                                         │
│     messages.append({"role": "assistant", "content": ...})  │
│     messages.append({"role": "user", "content":             │
│       "```tool_result\n{...results...}\n```"})              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  ITERATION 2                                                │
├─────────────────────────────────────────────────────────────┤
│  1. Send to LLM with updated context                        │
│                                                             │
│  2. LLM Response (no tool_calls = FINAL):                   │
│     "На основе найденной информации, для настройки VLAN    │
│      на Cisco выполните следующие шаги:                     │
│      1. Войдите в режим конфигурации...                     │
│      2. Создайте VLAN командой..."                          │
│                                                             │
│  3. Parse → no tool_calls → stream final response           │
└─────────────────────────────────────────────────────────────┘
```

### Шаг 6: SSE Events отправляются клиенту

```
event: user_message
data: {"message_id": "abc-123"}

event: status
data: {"stage": "loading_agent"}

event: status
data: {"stage": "thinking_step_1"}

event: tool_call
data: {"tool": "rag.search", "arguments": {"query": "настройка VLAN Cisco"}}

event: tool_result
data: {"tool": "rag.search", "success": true, "data": {"hits": [...]}}

event: status
data: {"stage": "generating_answer"}

event: delta
data: На основе

event: delta
data:  найденной информации

event: delta
data: , для настройки VLAN...

event: final
data: {"message_id": "def-456", "sources": [...]}

data: [DONE]
```

---

## Модели данных

### Agent Run (Запись о выполнении)

**Таблица:** `agent_runs`

```sql
CREATE TABLE agent_runs (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    chat_id UUID,
    user_id UUID,
    agent_slug VARCHAR(255) NOT NULL,
    status VARCHAR(50) NOT NULL,  -- running, completed, failed
    total_steps INT DEFAULT 0,
    total_tool_calls INT DEFAULT 0,
    tokens_in INT,
    tokens_out INT,
    duration_ms INT,
    error TEXT,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ
);
```

### Agent Run Step (Шаг выполнения)

**Таблица:** `agent_run_steps`

```sql
CREATE TABLE agent_run_steps (
    id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES agent_runs(id),
    step_number INT NOT NULL,
    step_type VARCHAR(50) NOT NULL,  -- llm_request, tool_call, tool_result, final_response
    data JSONB NOT NULL,
    tokens_in INT,
    tokens_out INT,
    duration_ms INT,
    created_at TIMESTAMPTZ NOT NULL
);
```

---

## Tool-Call Protocol

### Формат вызова tool (от LLM)

LLM возвращает tool_call в виде JSON-блока в тексте:

```markdown
Сейчас поищу информацию в базе знаний.

```tool_call
{
    "tool": "rag.search",
    "arguments": {
        "query": "настройка VLAN Cisco",
        "k": 5
    }
}
```
```

### Формат результата tool (для LLM)

Результат добавляется в контекст как user message:

```markdown
```tool_result
{
    "tool": "rag.search",
    "call_id": "abc-123",
    "result": {
        "hits": [
            {
                "text": "Для создания VLAN используйте команду...",
                "source_id": "doc-001",
                "page": 15,
                "score": 0.89
            }
        ],
        "total": 5
    }
}
```
```

### Парсинг tool_calls

**Файл:** `apps/api/src/app/agents/protocol.py`

```python
TOOL_CALL_PATTERN = re.compile(
    r'```tool_call\s*\n(.*?)\n```',
    re.DOTALL
)

def parse_llm_response(content: str) -> ParsedResponse:
    matches = TOOL_CALL_PATTERN.findall(content)
    tool_calls = []
    for match in matches:
        data = json.loads(match.strip())
        tool_calls.append(ToolCall.from_dict(data))
    return ParsedResponse(
        text=content,
        tool_calls=tool_calls,
        has_tool_calls=len(tool_calls) > 0
    )
```

---

## RAG Search

### Как работает rag.search

**Файл:** `apps/api/src/app/agents/builtins/rag_search.py`

```
User Query: "Как настроить VLAN на Cisco?"
                    │
                    ▼
┌─────────────────────────────────────────────────────────────┐
│  1. EMBEDDING                                               │
│     - Преобразуем query в вектор через embedding model     │
│     - Модель: embed.local.minilm (384 dimensions)          │
└─────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────┐
│  2. VECTOR SEARCH (Qdrant)                                  │
│     - Collection: {tenant_id}__embed.local.minilm           │
│     - Top-K: 20 candidates (для reranking)                  │
│     - Cosine similarity                                     │
└─────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────┐
│  3. RERANKING (optional)                                    │
│     - Cross-encoder model                                   │
│     - Переранжирует candidates по релевантности            │
│     - Возвращает top-5                                      │
└─────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────┐
│  4. RESULT                                                  │
│     {                                                       │
│       "hits": [                                             │
│         {"text": "...", "source_id": "...", "score": 0.89}  │
│       ],                                                    │
│       "total": 5                                            │
│     }                                                       │
└─────────────────────────────────────────────────────────────┘
```

### Input Schema для rag.search

```json
{
  "type": "object",
  "properties": {
    "query": {
      "type": "string",
      "description": "The search query to find relevant documents"
    },
    "k": {
      "type": "integer",
      "description": "Number of results to return (default: 5, max: 20)",
      "default": 5
    },
    "scope": {
      "type": "string",
      "enum": ["tenant", "global", "all"],
      "default": "tenant"
    }
  },
  "required": ["query"]
}
```

---

## Логирование и Agent Runs

### Где смотреть логи

1. **Админка → Agent Runs** — список всех выполнений агентов
2. **Docker logs** — `docker compose logs api -f`

### Структура Agent Run в админке

```
┌─────────────────────────────────────────────────────────────┐
│  Agent Run: abc-123-def                                     │
│  Agent: chat-rag                                            │
│  Status: completed                                          │
│  Duration: 2.3s                                             │
│  Steps: 4                                                   │
│  Tool Calls: 1                                              │
├─────────────────────────────────────────────────────────────┤
│  STEPS:                                                     │
│                                                             │
│  #0 llm_request                                             │
│     {                                                       │
│       "step": 1,                                            │
│       "model": "llama-3.1-8b-instant",                      │
│       "messages_count": 2                                   │
│     }                                                       │
│                                                             │
│  #1 tool_call                                               │
│     {                                                       │
│       "tool_slug": "rag.search",                            │
│       "call_id": "xyz-789",                                 │
│       "arguments": {"query": "настройка VLAN Cisco"}        │
│     }                                                       │
│                                                             │
│  #2 tool_result                                             │
│     {                                                       │
│       "tool_slug": "rag.search",                            │
│       "success": true,                                      │
│       "result": {"hits": [...], "total": 5}                 │
│     }                                                       │
│                                                             │
│  #3 final_response                                          │
│     {                                                       │
│       "step": 2,                                            │
│       "has_sources": true                                   │
│     }                                                       │
└─────────────────────────────────────────────────────────────┘
```

### Включение/выключение логирования

В настройках агента (Админка → Agents):

```json
{
  "enable_logging": true
}
```

---

## Примеры JSON

### Полный запрос/ответ

**Request:**
```json
{
  "content": "Как настроить VLAN на Cisco?",
  "use_rag": true,
  "agent_slug": "chat-rag"
}
```

**SSE Events:**
```
event: user_message
data: {"message_id": "550e8400-e29b-41d4-a716-446655440001"}

event: status
data: {"stage": "loading_agent"}

event: status
data: {"stage": "loading_context"}

event: status
data: {"stage": "agent_running"}

event: status
data: {"stage": "thinking_step_1"}

event: tool_call
data: {"tool": "rag.search", "call_id": "call-001", "arguments": {"query": "настройка VLAN Cisco", "k": 5}}

event: tool_result
data: {"tool": "rag.search", "call_id": "call-001", "success": true, "data": {"hits": [{"text": "Для создания VLAN...", "source_id": "doc-001", "page": 15, "score": 0.89}], "total": 5}}

event: status
data: {"stage": "generating_answer"}

event: delta
data: На основе найденной информации

event: delta
data: , для настройки VLAN на Cisco

event: delta
data:  выполните следующие шаги:

event: delta
data: 

event: delta
data: 1. Войдите в режим конфигурации

event: final
data: {"message_id": "550e8400-e29b-41d4-a716-446655440002", "sources": [{"source_id": "doc-001", "text": "Для создания VLAN...", "page": 15, "score": 0.89}]}

data: [DONE]
```

### Agent Run в БД

```json
{
  "id": "run-001",
  "agent_slug": "chat-rag",
  "status": "completed",
  "total_steps": 4,
  "total_tool_calls": 1,
  "duration_ms": 2300,
  "started_at": "2026-01-17T12:00:00Z",
  "finished_at": "2026-01-17T12:00:02.300Z"
}
```

### Agent Run Steps

```json
[
  {
    "step_number": 0,
    "step_type": "llm_request",
    "data": {
      "step": 1,
      "model": "llama-3.1-8b-instant",
      "messages_count": 2
    }
  },
  {
    "step_number": 1,
    "step_type": "tool_call",
    "data": {
      "tool_slug": "rag.search",
      "call_id": "call-001",
      "arguments": {"query": "настройка VLAN Cisco", "k": 5}
    }
  },
  {
    "step_number": 2,
    "step_type": "tool_result",
    "data": {
      "tool_slug": "rag.search",
      "call_id": "call-001",
      "success": true,
      "result": {"hits": [...], "total": 5}
    }
  },
  {
    "step_number": 3,
    "step_type": "final_response",
    "data": {
      "step": 2,
      "has_sources": true
    }
  }
]
```

---

## Troubleshooting

### Проблема: LLM возвращает tool_call даже после получения результатов

**Причина:** Промпт не содержит явных инструкций о том, когда НЕ вызывать tools.

**Решение:** Обновить промпт агента (миграция 0035):
```
## Правила работы
1. НЕ вызывай инструменты повторно если ты уже получил результаты
2. После получения результатов tool_call — сразу формулируй финальный ответ
```

### Проблема: Agent Run не создаётся

**Причина:** `enable_logging: false` в настройках агента.

**Решение:** Включить логирование в Админка → Agents → Edit.

### Проблема: Tool not found in registry

**Причина:** Tool не зарегистрирован в `builtins/__init__.py`.

**Решение:**
```python
# apps/api/src/app/agents/builtins/__init__.py
def register_builtins() -> None:
    from app.agents.builtins.rag_search import RagSearchTool
    from app.agents.builtins.my_new_tool import MyNewTool  # Добавить
    
    ToolRegistry.register(RagSearchTool())
    ToolRegistry.register(MyNewTool())  # Добавить
```

### Проблема: Maximum steps reached

**Причина:** LLM зациклился на вызовах tools (>10 итераций).

**Решение:** 
1. Проверить промпт — добавить инструкции о завершении
2. Увеличить `max_steps` в AgentRuntime (не рекомендуется)

---

## Добавление нового Tool

### 1. Создать Handler

```python
# apps/api/src/app/agents/builtins/my_tool.py
from app.agents.handlers.base import ToolHandler
from app.agents.context import ToolContext, ToolResult

class MyTool(ToolHandler):
    slug = "my.tool"
    name = "My Custom Tool"
    description = "Does something useful"
    
    input_schema = {
        "type": "object",
        "properties": {
            "param1": {"type": "string", "description": "First parameter"}
        },
        "required": ["param1"]
    }
    
    async def execute(self, ctx: ToolContext, args: dict) -> ToolResult:
        result = do_something(args["param1"])
        return ToolResult.ok({"result": result})
```

### 2. Зарегистрировать

```python
# apps/api/src/app/agents/builtins/__init__.py
from app.agents.builtins.my_tool import MyTool
ToolRegistry.register(MyTool())
```

### 3. Добавить в агента

```sql
UPDATE agents 
SET tools = tools || '["my.tool"]'::jsonb 
WHERE slug = 'chat-rag';
```

### 4. Обновить промпт (если нужно)

Добавить инструкции по использованию нового tool в system prompt.

---

## Файловая структура

```
apps/api/src/app/
├── agents/
│   ├── __init__.py          # Экспорты
│   ├── context.py            # ToolContext, ToolResult, ToolCall
│   ├── handlers/
│   │   └── base.py           # Базовый ToolHandler
│   ├── builtins/
│   │   ├── __init__.py       # Регистрация builtin tools
│   │   └── rag_search.py     # RAG Search tool
│   ├── protocol.py           # Парсинг tool_calls
│   ├── registry.py           # ToolRegistry singleton
│   └── runtime.py            # AgentRuntime (tool-call loop)
├── models/
│   ├── agent.py              # Agent model
│   ├── prompt.py             # Prompt model
│   └── agent_run.py          # AgentRun, AgentRunStep models
├── services/
│   ├── agent_service.py      # AgentService (profile loading)
│   ├── chat_stream_service.py # ChatStreamService
│   ├── run_store.py          # RunStore (logging)
│   └── rag_search_service.py # RAG search logic
└── api/v1/routers/
    └── chat.py               # Chat API endpoints
```

---

*Документация создана: 2026-01-17*
*Версия: 1.0*
