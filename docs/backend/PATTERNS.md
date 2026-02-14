# Backend Patterns

Практические шаблоны реализации.  
RULES.md отвечает на вопрос «что обязательно», этот документ — «как мы это обычно реализуем».

## 1) Startup/Lifespan pattern

```python
app = FastAPI(..., lifespan=lifespan)
```

В `lifespan`:

1. Инициализируем engine/session factory.
2. Выполняем bootstrap-сценарии (seed/sync/check).
3. На shutdown корректно закрываем engine.

Принцип: startup должен быть идемпотентным и безопасным при повторном запуске.

## 2) Router → Service → Repository pattern

```python
@router.post("/entities")
async def create_entity(
    payload: EntityCreate,
    session: AsyncSession = Depends(db_session),
) -> EntityResponse:
    service = EntityService(session)
    entity = await service.create(payload)
    await session.commit()
    return EntityResponse.model_validate(entity)
```

- Router: HTTP/валидация/response model.
- Service: бизнес-правила и orchestration.
- Repository: SQL и доступ к данным.

## 3) Transaction pattern

### Репозиторий

```python
class EntityRepository:
    async def create(self, entity: Entity) -> Entity:
        self.session.add(entity)
        await self.session.flush()
        return entity
```

### Service/API

- Если используем `db_session`, commit на уровне API после успешной мутации.
- Если используем `db_uow`, commit делает dependency.

### Worker

```python
async with worker_transaction(session, "task_name"):
    await service.process(...)
```

## 4) Scope resolution pattern

### Credentials

```python
async def resolve_credentials(instance_id: UUID, user_id: UUID, tenant_id: UUID):
    return (
        await repo.get_by_scope(instance_id, "user", user_id=user_id)
        or await repo.get_by_scope(instance_id, "tenant", tenant_id=tenant_id)
        or await repo.get_by_scope(instance_id, "default")
    )
```

### Permissions

Та же последовательность: `user -> tenant -> default`, затем merge в effective policy.

## 5) Error handling pattern

```python
class DomainError(Exception):
    pass

class NotFoundError(DomainError):
    pass

class ValidationError(DomainError):
    pass
```

- В сервисе кидаем доменные ошибки.
- В API маппим в `HTTPException`/общий exception handler.
- Ошибки логируем с контекстом (entity, tenant, user, operation).

## 6) Tenant isolation pattern

```python
async def get_entity_for_tenant(entity_id: UUID, tenant_id: UUID) -> Entity:
    entity = await repo.get_by_id(entity_id)
    if not entity or entity.tenant_id != tenant_id:
        raise NotFoundError()
    return entity
```

Принцип: при нарушении tenant-границы всегда возвращаем not found/forbidden по контракту эндпойнта.

## 7) Logging pattern

```python
logger.info(
    "entity_updated",
    extra={
        "entity_id": str(entity.id),
        "tenant_id": str(tenant_id),
        "user_id": str(user_id),
        "status": "ok",
    },
)
```

- Событийные имена (`snake_case`).
- Структурированный `extra`.
- Без утечки секретов/credentials в логи.

## 8) Migration pattern

1. Добавление обязательного поля:
   - add nullable
   - backfill
   - alter to not null
2. Изменение типа:
   - temp column
   - migrate data
   - switch
3. Всегда проверять уникальность revision id.

## 9) Testing patterns

### Unit

Тестируем бизнес-правила сервиса (resolve/merge/validation).

### Integration

Тестируем полный flow:

- API -> Service -> Repository
- транзакции
- tenant isolation
- scope resolution

## 10) Legacy refactor pattern

Если сервис слишком большой:

1. Выделить чистые use-case методы.
2. Вынести query-only части в отдельные repository-методы.
3. Стабилизировать контракт тестами.
4. Разбить на под-сервисы без изменения API-контракта.
