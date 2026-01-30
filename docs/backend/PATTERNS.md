# Архитектурные паттерны Backend

## Repository Pattern

Изоляция data access от бизнес-логики.

```python
class BaseRepository(Generic[T]):
    def __init__(self, session: AsyncSession, model: type[T]):
        self.session = session
        self.model = model
    
    async def get_by_id(self, id: UUID) -> T | None:
        return await self.session.get(self.model, id)
    
    async def create(self, entity: T) -> T:
        self.session.add(entity)
        await self.session.flush()
        return entity
    
    async def delete(self, entity: T) -> None:
        await self.session.delete(entity)
        await self.session.flush()
```

### Специализированные репозитории

```python
class AgentRepository(BaseRepository[Agent]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Agent)
    
    async def get_by_slug(self, slug: str) -> Agent | None:
        stmt = select(Agent).where(Agent.slug == slug)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def list_active(self) -> list[Agent]:
        stmt = select(Agent).where(Agent.is_active == True)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
```

## Service Layer

Бизнес-логика и оркестрация.

```python
class AgentService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = AgentRepository(session)
        self.prompt_repo = PromptRepository(session)
        self.permission_service = PermissionService(session)
    
    async def create(self, data: AgentCreate) -> Agent:
        # Validation
        existing = await self.repo.get_by_slug(data.slug)
        if existing:
            raise ValidationError(f"Agent {data.slug} already exists")
        
        # Create agent
        agent = Agent(**data.model_dump())
        await self.repo.create(agent)
        
        # Side effects
        await self._add_to_default_permissions(agent.slug)
        
        return agent
    
    async def _add_to_default_permissions(self, slug: str) -> None:
        await self.permission_service.set_agent_permission(
            scope="default",
            agent_slug=slug,
            value="denied"
        )
```

## Dependency Injection

Через FastAPI Depends.

```python
# deps.py
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_db)
) -> User:
    payload = decode_jwt(token)
    user = await UserRepository(session).get_by_id(payload["sub"])
    if not user:
        raise UnauthorizedError()
    return user

async def get_current_admin(
    user: User = Depends(get_current_user)
) -> User:
    if user.role not in ["admin", "tenant_admin"]:
        raise ForbiddenError()
    return user
```

## Event Publishing

SSE события через Redis pub/sub.

```python
class RagEventPublisher:
    def __init__(self, redis: Redis):
        self.redis = redis
    
    async def publish_status_change(
        self,
        tenant_id: UUID,
        document_id: UUID,
        status: str
    ) -> None:
        event = {
            "type": "document.status_changed",
            "document_id": str(document_id),
            "status": status,
            "timestamp": datetime.utcnow().isoformat()
        }
        await self.redis.publish(
            f"rag:tenant:{tenant_id}",
            json.dumps(event)
        )
```

## Scope Resolution

Иерархический резолв настроек.

```python
class PermissionService:
    async def resolve_permissions(
        self,
        user_id: UUID,
        tenant_id: UUID
    ) -> EffectivePermissions:
        # Load all scopes
        user_perms = await self.repo.get_by_scope("user", user_id=user_id)
        tenant_perms = await self.repo.get_by_scope("tenant", tenant_id=tenant_id)
        default_perms = await self.repo.get_by_scope("default")
        
        # Merge with priority
        return self._merge_permissions(user_perms, tenant_perms, default_perms)
    
    def _resolve_single(
        self,
        slug: str,
        user_perms: dict,
        tenant_perms: dict,
        default_perms: dict
    ) -> bool:
        # User takes priority
        if slug in user_perms and user_perms[slug] != "undefined":
            return user_perms[slug] == "allowed"
        
        # Then tenant
        if slug in tenant_perms and tenant_perms[slug] != "undefined":
            return tenant_perms[slug] == "allowed"
        
        # Finally default
        return default_perms.get(slug, "denied") == "allowed"
```

## Celery Task Pattern

Фоновые задачи с транзакциями.

```python
@celery.task(bind=True, max_retries=3)
def ingest_document(self, document_id: str):
    """RAG pipeline task."""
    try:
        asyncio.run(_ingest_document_async(document_id))
    except Exception as exc:
        self.retry(exc=exc, countdown=60)

async def _ingest_document_async(document_id: str):
    async with worker_transaction() as session:
        service = RagIngestService(session)
        await service.process(UUID(document_id))
```

## Adapter Pattern

Абстракция внешних сервисов.

```python
class LLMClient(ABC):
    @abstractmethod
    async def complete(
        self,
        messages: list[dict],
        model: str,
        stream: bool = False
    ) -> AsyncIterator[str] | str:
        pass

class GroqClient(LLMClient):
    def __init__(self, api_key: str, base_url: str):
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    
    async def complete(self, messages, model, stream=False):
        response = await self.client.chat.completions.create(
            model=model,
            messages=messages,
            stream=stream
        )
        if stream:
            async for chunk in response:
                yield chunk.choices[0].delta.content or ""
        else:
            return response.choices[0].message.content
```

## Factory Pattern

Создание сервисов с зависимостями.

```python
def get_llm_client() -> LLMClient:
    provider = settings.LLM_PROVIDER
    if provider == "groq":
        return GroqClient(settings.LLM_API_KEY, settings.LLM_BASE_URL)
    elif provider == "local":
        return LocalLLMClient(settings.LLM_BASE_URL)
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")
```

## Outbox Pattern

Надёжная доставка событий.

```python
class OutboxHelper:
    async def add_event(
        self,
        session: AsyncSession,
        event_type: str,
        payload: dict
    ) -> None:
        event = OutboxEvent(
            event_type=event_type,
            payload=payload,
            status="pending"
        )
        session.add(event)
        await session.flush()

# Worker processes outbox
async def process_outbox():
    async with get_session() as session:
        events = await get_pending_events(session)
        for event in events:
            try:
                await deliver_event(event)
                event.status = "delivered"
            except Exception:
                event.retry_count += 1
                if event.retry_count > 3:
                    event.status = "failed"
        await session.commit()
```
