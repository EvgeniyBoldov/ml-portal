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

### Agent/Tool v2: границы ответственности

1. **Agent container** хранит human/routing metadata (name, slug, description, short_info, tags, is_routable, routing_keywords, routing_negative_keywords).
2. **AgentVersion** хранит версионируемую конфигурацию: prompt parts (identity, mission, scope, rules, tool_use_rules, output_format, examples), execution config (model, timeout_s, max_steps, max_retries, max_tokens, temperature), safety knobs (requires_confirmation_for_write, risk_level, never_do, allowed_ops).
3. **Prompt parts храним отдельными колонками** (не JSONB) — строгая типизация, удобная дифференциация.
4. **Tool container** хранит human/routing metadata (name, slug, short_info, tags, is_routable, routing_keywords, routing_negative_keywords).
5. **ToolRelease** хранит routing metadata (resource, ops, systems, risk_level, etc.), execution config (timeout_s, max_retries, etc.), LLM help (description_for_llm, field_hints, examples, common_errors).
6. **Версионирование**: агенты по умолчанию используют active ToolRelease; AgentBinding.tool_release_id позволяет пиннить конкретную версию.

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
@router.post("/agents")
async def create_agent(
    data: AgentCreate,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    try:
        service = AgentService(db)
        result = await service.create_agent(
            slug=data.slug, name=data.name, ...
        )
        await db.commit()
        return result
    except AgentAlreadyExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))
```

## Роутеры (Admin API)

### Организация
- Путь: `app/api/v1/routers/admin/`
- **1 домен = 1 файл роутера**. Не смешивать сущности.
- `__init__.py` — импорт и include sub-роутеров с prefix/tags
- Prefix задаётся в `__init__.py`, не внутри роутера
- Каждый файл экспортирует `router = APIRouter(tags=[...])`
- Все admin-эндпоинты защищены `require_admin`
- Мутации: `await db.commit()` в роутере
- Create/Update возвращают detail response (re-fetch после commit)

## Schemas (Pydantic)

### Организация
- Путь: `app/schemas/`
- **1 домен = 1 файл**. Никаких inline-схем в роутерах.

### Паттерн Short / Detail

```python
# Мутации
class EntityCreate(BaseModel): ...
class EntityUpdate(BaseModel): ...

# Short — для списков (без вложенных объектов, с count-полями)
class EntityListItem(BaseModel):
    id: UUID
    slug: str
    name: str
    children_count: int = 0
    created_at: datetime

# Detail — для GET /{id} (с вложенными short-версиями дочерних)
class EntityDetailResponse(BaseModel):
    id: UUID
    slug: str
    name: str
    children: List[ChildListItem] = []
    created_at: datetime
```

### Правила
- `EntityListItem` — **никаких** вложенных объектов, только count/bool агрегаты
- `EntityDetailResponse` — вложенные дочерние через их `ListItem` схемы
- Для versioned entities (Agent, Tool): versions возвращаются **полными** (`VersionResponse`)
- Naming: `Create`, `Update`, `ListItem`, `Response`/`DetailResponse`

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