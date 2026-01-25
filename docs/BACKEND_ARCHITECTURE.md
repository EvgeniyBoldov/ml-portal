# Backend Architecture

Архитектура бэкенда ML Portal.

## Общая структура

```
apps/api/src/
├── app/
│   ├── core/              — Конфигурация, middleware, ошибки
│   ├── models/            — SQLAlchemy модели
│   ├── schemas/           — Pydantic схемы (request/response)
│   ├── repositories/      — Data access layer
│   ├── services/          — Бизнес-логика
│   ├── api/               — FastAPI роутеры
│   │   ├── v1/            — API v1 endpoints
│   │   └── mcp/           — MCP protocol endpoints
│   ├── agents/            — Agent Runtime система
│   │   ├── runtime.py     — Tool-call loop engine
│   │   ├── router.py      — Pre-runtime маршрутизатор
│   │   ├── context.py     — Execution context
│   │   ├── registry.py    — Tool registry
│   │   ├── handlers/      — Tool handlers
│   │   └── builtins/      — Встроенные инструменты
│   ├── workers/           — Celery tasks
│   └── adapters/          — Внешние клиенты (LLM, Qdrant, MinIO)
└── main.py                — Точка входа приложения
```

---

## Core Layer

### Configuration (`core/config.py`)

```python
class Settings(BaseSettings):
    # Database
    DATABASE_URL: str
    
    # Redis
    REDIS_URL: str
    
    # S3/MinIO
    S3_ENDPOINT: str
    S3_ACCESS_KEY: str
    S3_SECRET_KEY: str
    S3_BUCKET: str
    
    # Qdrant
    QDRANT_URL: str
    QDRANT_API_KEY: str | None
    
    # LLM
    LLM_API_URL: str
    LLM_API_KEY: str
    LLM_DEFAULT_MODEL: str
    
    # Embedding
    EMBEDDING_API_URL: str
    EMBEDDING_DEFAULT_MODEL: str
    
    # Security
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # Credentials encryption
    CREDENTIALS_MASTER_KEY: str
    
    # Agent Router
    AGENT_ROUTER_ENABLED: bool = True
    
    # Retention
    AGENT_RUNS_RETENTION_DAYS: int = 30
    AUDIT_LOGS_RETENTION_DAYS: int = 90
```

### Middleware (`core/middleware.py`)

- **CORS**: настроенный для фронтенда
- **Request ID**: генерация уникального ID для трейсинга
- **Logging**: структурированное логирование всех запросов
- **Error handling**: глобальный обработчик исключений

### Errors (`core/errors.py`)

```python
class AppException(Exception):
    """Base application exception"""
    status_code: int = 500
    detail: str = "Internal server error"

class NotFoundException(AppException):
    status_code = 404
    detail = "Resource not found"

class PermissionDeniedException(AppException):
    status_code = 403
    detail = "Permission denied"

class AgentUnavailableError(AppException):
    status_code = 400
    detail = "Agent cannot run: missing prerequisites"
```

---

## Data Layer

### Models (`models/`)

SQLAlchemy модели с полной типизацией (см. `DATA_MODEL.md`).

**Ключевые модели:**
- `Users`, `Tenants`, `UserTenants`
- `Model`, `Prompt`, `Tool`, `Agent`
- `ToolInstance`, `CredentialSet`, `PermissionSet`
- `Collection`
- `AgentRun`, `AgentRunStep`, `AuditLog`

### Repositories (`repositories/`)

Слой доступа к данным. Один репозиторий на модель.

**Пример:**
```python
class AgentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_by_slug(self, slug: str) -> Agent | None:
        stmt = select(Agent).where(Agent.slug == slug)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def list_active(self) -> list[Agent]:
        stmt = select(Agent).where(Agent.is_active == True)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
    
    async def create(self, agent: Agent) -> Agent:
        self.session.add(agent)
        await self.session.flush()
        return agent
    
    async def update(self, agent: Agent) -> Agent:
        await self.session.flush()
        return agent
```

**Принципы:**
- Все методы асинхронные
- Используем `AsyncSession`
- Не делаем `commit()` в репозиториях (только `flush()`)
- Commit делает сервисный слой или контроллер

---

## Service Layer

### Services (`services/`)

Бизнес-логика приложения. Один сервис на домен.

**Ключевые сервисы:**

#### `AuthService`
- Регистрация, логин, refresh token
- Генерация JWT
- Валидация токенов

#### `PromptService`
- CRUD промптов
- Версионирование (создание новой версии, активация)
- Рендеринг Jinja2 templates
- Merge baseline промптов

#### `AgentService`
- CRUD агентов
- Резолв промптов (system + baseline merge)
- Валидация tools_config и collections_config

#### `PermissionService`
- Резолв effective permissions (user > tenant > default)
- Проверка доступа к инструментам/коллекциям
- Автоматическое добавление новых айтемов в default permissions

#### `ToolInstanceService`
- CRUD инстансов
- Health check
- Резолв credential sets (user > tenant > default)

#### `CredentialService`
- CRUD кредов
- Шифрование/дешифрование через `CryptoService`
- Выбор дефолтного credential set для scope

#### `CollectionService`
- CRUD коллекций
- Создание динамических таблиц в БД
- Векторизация данных
- Поиск (SQL + векторный)

#### `ChatStreamService`
- Обработка чат-запросов
- Создание `ToolContext`
- Делегирование в `AgentRuntime`
- Сохранение сообщений

#### `RAGStatusManager`
- Управление статусами RAG pipeline
- SSE уведомления
- Каскадные обновления статусов

**Пример сервиса:**
```python
class PromptService:
    def __init__(
        self,
        prompt_repo: PromptRepository,
        session: AsyncSession
    ):
        self.prompt_repo = prompt_repo
        self.session = session
    
    async def create_version(
        self,
        slug: str,
        template: str,
        input_variables: list[str],
        generation_config: dict
    ) -> Prompt:
        # Получаем последнюю версию
        latest = await self.prompt_repo.get_latest_version(slug)
        version = (latest.version + 1) if latest else 1
        
        # Создаем новую версию
        prompt = Prompt(
            slug=slug,
            template=template,
            input_variables=input_variables,
            generation_config=generation_config,
            version=version,
            status=PromptStatus.DRAFT,
            parent_version_id=latest.id if latest else None
        )
        
        await self.prompt_repo.create(prompt)
        await self.session.commit()
        return prompt
    
    async def activate_version(self, prompt_id: UUID) -> Prompt:
        prompt = await self.prompt_repo.get_by_id(prompt_id)
        if not prompt:
            raise NotFoundException("Prompt not found")
        
        if not prompt.can_activate:
            raise AppException("Only draft versions can be activated")
        
        # Деактивируем текущую активную версию
        active = await self.prompt_repo.get_active_version(prompt.slug)
        if active:
            active.status = PromptStatus.ARCHIVED
        
        # Активируем новую версию
        prompt.status = PromptStatus.ACTIVE
        await self.session.commit()
        return prompt
    
    async def render_template(
        self,
        prompt: Prompt,
        context: dict
    ) -> str:
        """Рендер Jinja2 template с контекстом"""
        template = Template(prompt.template)
        return template.render(**context)
    
    async def merge_baselines(
        self,
        default_baseline: Prompt | None,
        agent_baseline: Prompt | None
    ) -> str:
        """Мерж baseline промптов с приоритетом агента"""
        if not default_baseline and not agent_baseline:
            return ""
        
        if not default_baseline:
            return agent_baseline.template
        
        if not agent_baseline:
            return default_baseline.template
        
        # Мерж с приоритетом агента
        # TODO: реализовать умный merge (сейчас просто конкатенация)
        return f"{default_baseline.template}\n\n{agent_baseline.template}"
```

---

## API Layer

### Routers (`api/v1/`)

FastAPI роутеры, сгруппированные по доменам.

**Структура:**
```
api/v1/
├── __init__.py           — Монтирование всех роутеров
├── auth.py               — Аутентификация
├── users.py              — Управление пользователями
├── tenants.py            — Управление департаментами
├── models.py             — Модели (LLM, Embedding)
├── prompts.py            — Промпты
├── tools.py              — Инструменты (read-only)
├── agents.py             — Агенты
├── tool_instances.py     — Инстансы инструментов
├── credentials.py        — Креды
├── permissions.py        — Политики доступа
├── collections.py        — Коллекции
├── chat.py               — Чат с агентами
├── rag.py                — RAG pipeline
├── agent_runs.py         — Логи запусков агентов
└── audit.py              — Audit logs
```

**Пример роутера:**
```python
router = APIRouter(prefix="/prompts", tags=["prompts"])

@router.get("/", response_model=list[PromptListResponse])
async def list_prompts(
    type: PromptType | None = None,
    status: PromptStatus | None = None,
    session: AsyncSession = Depends(get_session),
    current_user: Users = Depends(get_current_admin)
):
    """Список промптов с фильтрацией"""
    repo = PromptRepository(session)
    prompts = await repo.list_all(type=type, status=status)
    return prompts

@router.get("/{slug}", response_model=PromptDetailResponse)
async def get_prompt_detail(
    slug: str,
    session: AsyncSession = Depends(get_session),
    current_user: Users = Depends(get_current_admin)
):
    """Детальный вид промпта со всеми версиями"""
    repo = PromptRepository(session)
    versions = await repo.get_all_versions(slug)
    if not versions:
        raise NotFoundException(f"Prompt {slug} not found")
    
    return {
        "slug": slug,
        "versions": versions,
        "active_version": next((v for v in versions if v.status == "active"), None)
    }

@router.post("/{slug}/versions", response_model=PromptResponse)
async def create_prompt_version(
    slug: str,
    request: CreatePromptVersionRequest,
    session: AsyncSession = Depends(get_session),
    current_user: Users = Depends(get_current_admin)
):
    """Создание новой версии промпта"""
    service = PromptService(PromptRepository(session), session)
    prompt = await service.create_version(
        slug=slug,
        template=request.template,
        input_variables=request.input_variables,
        generation_config=request.generation_config
    )
    return prompt

@router.post("/{prompt_id}/activate", response_model=PromptResponse)
async def activate_prompt_version(
    prompt_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_user: Users = Depends(get_current_admin)
):
    """Активация версии промпта"""
    service = PromptService(PromptRepository(session), session)
    prompt = await service.activate_version(prompt_id)
    return prompt
```

**Принципы:**
- Все эндпоинты асинхронные
- Используем dependency injection (`Depends`)
- Валидация через Pydantic схемы
- Авторизация через `get_current_user` / `get_current_admin`
- Ошибки через исключения (обрабатываются middleware)

---

## Agent Runtime

### Architecture

```
ChatStreamService
    ↓
AgentRouter (pre-runtime)
    ├─ Load Agent
    ├─ Resolve Permissions
    ├─ Resolve Tools + Instances + Credentials
    ├─ Check Prerequisites
    └─ Create ExecutionRequest
    ↓
AgentRuntime (tool-call loop)
    ├─ Build System Prompt (prompt + baseline + tools)
    ├─ LLM Call (non-streaming)
    ├─ Parse Tool Calls
    ├─ Execute Tools (via ToolHandler)
    ├─ Add Results to Context
    ├─ Repeat (max 10 iterations)
    └─ Final Answer (streaming)
```

### AgentRouter (`agents/router.py`)

Pre-runtime маршрутизатор. Выполняется ДО tool-call loop.

**Обязанности:**
1. Загрузить агента по slug
2. Резолвить permissions для user/tenant
3. Резолвить tools — проверить доступность, найти instances, проверить креды
4. Резолвить collections — проверить доступность
5. Проверить prerequisites — все required tools/collections доступны?
6. Определить режим — full | partial | unavailable
7. Создать ExecutionRequest для Runtime
8. Логировать решение в routing_logs

**Режимы выполнения:**
- `full` — все required tools/collections доступны
- `partial` — часть недоступна, но агент поддерживает partial mode
- `unavailable` — критичные prerequisites отсутствуют

**Пример:**
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
        agent = await self.agent_repo.get_by_slug(agent_slug)
        if not agent or not agent.is_active:
            raise NotFoundException(f"Agent {agent_slug} not found")
        
        # 2. Resolve permissions
        permissions = await self.permission_service.get_effective_permissions(
            user_id=user_id,
            tenant_id=tenant_id
        )
        
        # 3. Resolve tools
        available_tools = []
        missing_required_tools = []
        
        for tool_config in agent.tools_config:
            tool_slug = tool_config["tool_slug"]
            required = tool_config.get("required", False)
            
            # Check permission
            if tool_slug not in permissions.allowed_tools:
                if required:
                    missing_required_tools.append(tool_slug)
                continue
            
            # Find instance + credentials
            instance = await self.tool_instance_service.get_default_instance(tool_slug)
            if not instance:
                if required:
                    missing_required_tools.append(tool_slug)
                continue
            
            creds = await self.credential_service.resolve_credentials(
                instance_id=instance.id,
                user_id=user_id,
                tenant_id=tenant_id
            )
            if not creds:
                if required:
                    missing_required_tools.append(tool_slug)
                continue
            
            available_tools.append({
                "slug": tool_slug,
                "instance": instance,
                "credentials": creds
            })
        
        # 4. Determine execution mode
        if missing_required_tools:
            if agent.supports_partial_mode:
                mode = ExecutionMode.PARTIAL
            else:
                raise AgentUnavailableError(
                    f"Missing required tools: {', '.join(missing_required_tools)}"
                )
        else:
            mode = ExecutionMode.FULL
        
        # 5. Create ExecutionRequest
        return ExecutionRequest(
            agent=agent,
            user_id=user_id,
            tenant_id=tenant_id,
            available_tools=available_tools,
            mode=mode,
            request_text=request_text
        )
```

### AgentRuntime (`agents/runtime.py`)

Tool-call loop engine.

**Алгоритм:**
```python
async def run(
    self,
    exec_request: ExecutionRequest,
    messages: list[dict],
    ctx: ToolContext
) -> AsyncGenerator[dict, None]:
    # Build system prompt
    system_prompt = await self._build_system_prompt(exec_request)
    
    # Add system prompt to messages
    messages = [{"role": "system", "content": system_prompt}] + messages
    
    # Tool-call loop (max 10 iterations)
    for iteration in range(10):
        # Call LLM (non-streaming)
        response = await self.llm_client.chat(
            messages=messages,
            model=exec_request.agent.generation_config.get("model"),
            temperature=exec_request.agent.generation_config.get("temperature", 0.7)
        )
        
        # Parse tool calls
        tool_calls = self._parse_tool_calls(response.content)
        
        if not tool_calls:
            # No more tool calls → final answer
            # Stream response to client
            async for chunk in self._stream_final_answer(response.content):
                yield chunk
            break
        
        # Execute tool calls
        for tool_call in tool_calls:
            tool_handler = self.registry.get_handler(tool_call["tool"])
            result = await tool_handler.execute(
                arguments=tool_call["arguments"],
                context=ctx
            )
            
            # Add result to messages
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call["id"],
                "content": json.dumps(result)
            })
        
        # Continue loop with updated context
```

### ToolHandler (`agents/handlers/base.py`)

Базовый класс для инструментов.

```python
class ToolHandler(ABC):
    @property
    @abstractmethod
    def slug(self) -> str:
        """Unique tool identifier"""
        pass
    
    @property
    @abstractmethod
    def input_schema(self) -> dict:
        """JSON Schema for input validation"""
        pass
    
    @abstractmethod
    async def execute(
        self,
        arguments: dict,
        context: ToolContext
    ) -> dict:
        """Execute tool with given arguments"""
        pass
```

**Встроенные инструменты:**
- `rag.search` — поиск в базе знаний
- `collection.search` — поиск в коллекциях

---

## Workers

### Celery Tasks (`workers/`)

Фоновые задачи для RAG pipeline.

**Задачи:**
- `extract_text` — извлечение текста из файлов
- `normalize_text` — нормализация текста
- `chunk_text` — разбиение на чанки
- `embed_chunks` — эмбеддинг чанков
- `index_embeddings` — индексирование в Qdrant
- `vectorize_collection` — векторизация коллекции
- `cleanup_old_runs` — удаление старых agent_runs и audit_logs

**Оркестрация:**
```python
# RAG ingest pipeline
chain(
    extract_text.si(doc_id),
    normalize_text.si(doc_id),
    chunk_text.si(doc_id),
    group([
        chain(
            embed_chunks.si(doc_id, model_alias),
            index_embeddings.si(doc_id, model_alias)
        )
        for model_alias in target_models
    ])
)()
```

---

## Adapters

### External Clients (`adapters/`)

Клиенты для внешних сервисов.

**LLM Client:**
```python
class LLMClient:
    async def chat(
        self,
        messages: list[dict],
        model: str,
        temperature: float = 0.7,
        stream: bool = False
    ) -> ChatResponse | AsyncGenerator[str, None]:
        """OpenAI-compatible chat endpoint"""
        pass
```

**Embedding Client:**
```python
class EmbeddingClient:
    async def embed(
        self,
        texts: list[str],
        model: str
    ) -> list[list[float]]:
        """Generate embeddings"""
        pass
```

**Qdrant Client:**
```python
class QdrantClient:
    async def upsert(
        self,
        collection_name: str,
        points: list[dict]
    ) -> None:
        """Upsert vectors"""
        pass
    
    async def search(
        self,
        collection_name: str,
        query_vector: list[float],
        limit: int = 10
    ) -> list[dict]:
        """Vector search"""
        pass
```

**MinIO Client:**
```python
class MinIOClient:
    async def upload(
        self,
        bucket: str,
        key: str,
        data: bytes
    ) -> str:
        """Upload file"""
        pass
    
    async def download(
        self,
        bucket: str,
        key: str
    ) -> bytes:
        """Download file"""
        pass
```

---

## Startup Hooks

При старте приложения:

1. **Sync tools from registry** — синхронизирует ToolHandler из кода в таблицу `tools`
2. **Ensure default permission set** — создает default PermissionSet если его нет
3. **Run migrations** — применяет Alembic миграции

---

## Testing Strategy

### Unit Tests
- Сервисы (мокаем репозитории)
- Репозитории (in-memory SQLite)
- Tool handlers (мокаем внешние API)

### Integration Tests
- API endpoints (TestClient)
- Agent Runtime (мокаем LLM, реальные tool handlers)
- RAG pipeline (реальные Celery tasks, тестовая БД)

### E2E Tests
- Playwright (фронт + бэк)
- Smoke tests: login → create agent → chat → logout

---

## Performance Considerations

### Database
- Индексы на часто используемых колонках (slug, tenant_id, user_id)
- Connection pooling (SQLAlchemy async pool)
- Query optimization (select_related, prefetch_related)

### Caching
- Redis для session storage
- Query result caching (TTL 30s для списков)
- Credential caching (TTL 5m)

### Async
- Все IO операции асинхронные
- Параллельные запросы через `asyncio.gather`
- Streaming responses для LLM

### Rate Limiting
- Redis sliding window
- Per-tenant limits (TODO)
- Per-endpoint limits (MCP)
