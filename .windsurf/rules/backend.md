---
trigger: always_on
---

# Backend Rules

## Общие принципы

1. **Асинхронность**: Весь код только асинхронный (async/await)
2. **Типизация**: Полная типизация через type hints
3. **Scope-based isolation**: Default → Tenant → User для всех политик и кредов
4. **No hardcoded values**: Все константы в config или enum

## Архитектура

### Слои
- **Models** — SQLAlchemy модели с полной типизацией
- **Repositories** — Data access layer, только flush() (не commit!)
- **Services** — Бизнес-логика, commit() делается здесь
- **API** — FastAPI роутеры, валидация через Pydantic

### Naming
- Файлы: `snake_case.py`
- Классы: `PascalCase`
- Функции/методы: `snake_case`
- Константы: `UPPER_SNAKE_CASE`

## Модели

### Обязательные поля
```python
id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
```

### Scope-based модели
Для моделей с scope (PermissionSet, CredentialSet):
```python
scope: Mapped[str] = mapped_column(String(20), nullable=False)  # default | tenant | user
tenant_id: Mapped[UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True)
user_id: Mapped[UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
```

## Сервисы

### Credential Resolution
Приоритет: User > Tenant > Default

```python
async def resolve_credentials(
    self,
    instance_id: UUID,
    user_id: UUID,
    tenant_id: UUID
) -> CredentialSet | None:
    # 1. User scope
    creds = await self.repo.get_by_scope(instance_id, "user", user_id=user_id)
    if creds:
        return creds
    
    # 2. Tenant scope
    creds = await self.repo.get_by_scope(instance_id, "tenant", tenant_id=tenant_id)
    if creds:
        return creds
    
    # 3. Default scope
    return await self.repo.get_by_scope(instance_id, "default")
```

### Permission Resolution
Приоритет: User > Tenant > Default

```python
async def get_effective_permissions(
    self,
    user_id: UUID,
    tenant_id: UUID
) -> EffectivePermissions:
    user_perms = await self.repo.get_by_scope("user", user_id=user_id)
    tenant_perms = await self.repo.get_by_scope("tenant", tenant_id=tenant_id)
    default_perms = await self.repo.get_by_scope("default")
    
    return self._merge_permissions(user_perms, tenant_perms, default_perms)
```

### Baseline Merge
Приоритет агента над default:

```python
async def merge_baselines(
    self,
    default_baseline: Prompt | None,
    agent_baseline: Prompt | None
) -> str:
    if not default_baseline and not agent_baseline:
        return ""
    
    if not default_baseline:
        return agent_baseline.template
    
    if not agent_baseline:
        return default_baseline.template
    
    # Merge с приоритетом агента
    return f"{default_baseline.template}\n\n{agent_baseline.template}"
```

## API

### Dependency Injection
```python
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_session)
) -> Users:
    # Validate token and return user
    pass

async def get_current_admin(
    user: Users = Depends(get_current_user)
) -> Users:
    if user.role not in ["admin", "tenant_admin"]:
        raise PermissionDeniedException()
    return user
```

### Error Handling
```python
@router.post("/agents/{slug}")
async def create_agent(
    slug: str,
    request: CreateAgentRequest,
    session: AsyncSession = Depends(get_session),
    user: Users = Depends(get_current_admin)
):
    try:
        service = AgentService(AgentRepository(session), session)
        agent = await service.create(slug, request)
        return agent
    except AgentAlreadyExistsError:
        raise HTTPException(status_code=409, detail="Agent already exists")
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

## Agent Runtime

### Pre-runtime Router
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
        # 5. Determine execution mode (full/partial/unavailable)
        # 6. Create ExecutionRequest
        # 7. Log routing decision
        pass
```

### Partial Mode
Если required инструмент недоступен:
- `supports_partial_mode=False` → raise AgentUnavailableError
- `supports_partial_mode=True` → продолжить с warning

Для recommended инструментов: всегда продолжать с warning.

## Миграции

### Naming
`XXXX_description.py` где XXXX — порядковый номер

### Обязательные проверки
- Добавление NOT NULL колонки → сначала nullable, заполнить данные, потом alter
- Удаление колонки → сначала deprecated, потом удалить через N релизов
- Изменение типа → через промежуточную колонку

## Тестирование

### Unit Tests
```python
@pytest.mark.asyncio
async def test_resolve_credentials_user_priority():
    # Arrange
    service = CredentialService(mock_repo, mock_session)
    
    # Act
    creds = await service.resolve_credentials(instance_id, user_id, tenant_id)
    
    # Assert
    assert creds.scope == "user"
```

### Integration Tests
```python
@pytest.mark.asyncio
async def test_agent_runtime_with_partial_mode(test_db):
    # Test agent execution with missing recommended tools
    pass
```

## Безопасность

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

### Tenant Isolation
Всегда проверяем tenant_id в запросах:
```python
async def get_collection(
    self,
    collection_id: UUID,
    tenant_id: UUID
) -> Collection:
    collection = await self.repo.get_by_id(collection_id)
    if not collection or collection.tenant_id != tenant_id:
        raise NotFoundException()
    return collection
```

## Логирование

### Structured Logging
```python
logger.info(
    "agent_run_completed",
    extra={
        "agent_slug": agent.slug,
        "user_id": str(user_id),
        "tenant_id": str(tenant_id),
        "duration_ms": duration,
        "status": "completed"
    }
)
```

### Correlation ID
Добавляем request_id в контекст:
```python
@app.middleware("http")
async def add_correlation_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response
```