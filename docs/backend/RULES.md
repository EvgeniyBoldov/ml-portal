# Правила разработки Backend

## Общие принципы

1. **Асинхронность**: Весь код только асинхронный (async/await)
2. **Типизация**: Полная типизация через type hints
3. **Scope-based isolation**: Default → Tenant → User для политик и кредов
4. **No hardcoded values**: Все константы в config или enum

## Transaction Management

### В роутерах (API endpoints)
**ВСЕГДА** `await session.commit()` после мутирующих операций.

```python
@router.post("/agents")
async def create_agent(
    data: AgentCreate,
    db: AsyncSession = Depends(get_db),
):
    service = AgentService(db)
    result = await service.create(data)
    await db.commit()  # ОБЯЗАТЕЛЬНО!
    return result
```

### В репозиториях
**ТОЛЬКО** `await session.flush()` — репозиторий не коммитит.

```python
class AgentRepository:
    async def create(self, agent: Agent) -> Agent:
        self.session.add(agent)
        await self.session.flush()  # Только flush!
        return agent
```

### В Celery воркерах
Используй `worker_transaction()` context manager.

```python
async with worker_transaction(session, "task_name"):
    await update_status(...)
    await session.flush()  # Для SSE событий
    result = await process(...)
    # Commit автоматически при выходе
```

## Модели

### Обязательные поля

```python
id: Mapped[UUID] = mapped_column(
    UUID(as_uuid=True), 
    primary_key=True, 
    default=uuid.uuid4
)
created_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True), 
    default=lambda: datetime.now(timezone.utc)
)
updated_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True), 
    default=lambda: datetime.now(timezone.utc), 
    onupdate=lambda: datetime.now(timezone.utc)
)
```

### Scope-based модели

```python
scope: Mapped[str] = mapped_column(String(20), nullable=False)
tenant_id: Mapped[UUID | None] = mapped_column(
    UUID(as_uuid=True), 
    ForeignKey("tenants.id"), 
    nullable=True
)
user_id: Mapped[UUID | None] = mapped_column(
    UUID(as_uuid=True), 
    ForeignKey("users.id"), 
    nullable=True
)
```

## Сервисы

### Dependency Injection

```python
class AgentService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = AgentRepository(session)
```

### Error Handling

```python
from app.core.exceptions import NotFoundError, ValidationError

async def get_agent(self, slug: str) -> Agent:
    agent = await self.repo.get_by_slug(slug)
    if not agent:
        raise NotFoundError(f"Agent {slug} not found")
    return agent
```

## API

### Response Models

```python
@router.get("/agents/{slug}", response_model=AgentResponse)
async def get_agent(
    slug: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AgentResponse:
    service = AgentService(db)
    return await service.get(slug)
```

### Pagination

```python
@router.get("/agents", response_model=PaginatedResponse[AgentResponse])
async def list_agents(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    service = AgentService(db)
    items, total = await service.list(skip=skip, limit=limit)
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)
```

## Логирование

### Structured Logging

```python
import structlog

logger = structlog.get_logger()

logger.info(
    "agent_run_completed",
    agent_slug=agent.slug,
    user_id=str(user_id),
    tenant_id=str(tenant_id),
    duration_ms=duration,
    status="completed"
)
```

### Correlation ID

```python
@app.middleware("http")
async def add_correlation_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response
```

## Безопасность

### Tenant Isolation

```python
async def get_collection(
    self,
    collection_id: UUID,
    tenant_id: UUID
) -> Collection:
    collection = await self.repo.get_by_id(collection_id)
    if not collection or collection.tenant_id != tenant_id:
        raise NotFoundError()
    return collection
```

### Credentials Encryption

```python
class CryptoService:
    def __init__(self):
        self.fernet = Fernet(settings.CREDENTIALS_MASTER_KEY.encode())
    
    def encrypt(self, payload: dict) -> str:
        return self.fernet.encrypt(json.dumps(payload).encode()).decode()
    
    def decrypt(self, encrypted: str) -> dict:
        return json.loads(self.fernet.decrypt(encrypted.encode()).decode())
```

## Тестирование

### Unit Tests

```python
@pytest.mark.asyncio
async def test_resolve_credentials_user_priority():
    service = CredentialService(mock_repo, mock_session)
    creds = await service.resolve_credentials(instance_id, user_id, tenant_id)
    assert creds.scope == "user"
```

### Fixtures

```python
@pytest.fixture
async def db_session():
    async with async_session_maker() as session:
        yield session
        await session.rollback()
```
