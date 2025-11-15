# Backend Audit Report
**Дата:** 2025-01-14  
**Статус:** Критические проблемы выявлены

---

## 🔴 КРИТИЧЕСКИЕ ПРОБЛЕМЫ

### 1. **SECURITY: JWT Secret в JWKS (HIGH)**
**Файл:** `apps/api/src/app/core/security.py:98-113`

```python
def get_jwks() -> Dict[str, Any]:
    # For now, we'll use symmetric key, but in production should use RSA keys
    return {
        "keys": [{
            "kty": "oct",  # symmetric key type
            "k": jwt.encode({"secret": s.JWT_SECRET}, "", algorithm="none").split('.')[2],  # ❌ EXPOSING SECRET
        }]
    }
```

**Проблема:** Симметричный секрет JWT_SECRET экспортируется в JWKS endpoint, что полностью компрометирует безопасность.

**Риск:** Любой может получить секрет и подделывать токены.

**Решение:**
- Использовать RSA/ECDSA ключи (асимметричная криптография)
- Публиковать только публичный ключ в JWKS
- Приватный ключ хранить в секретах

---

### 2. **TRANSACTION MANAGEMENT: Commit в Workers (MEDIUM-HIGH)**
**Файлы:** 
- `apps/api/src/app/workers/tasks_rag_ingest/*.py` (множественные)
- `apps/api/src/app/services/*.py` (несколько)

**Примеры:**
```python
# workers/tasks_rag_ingest/chunk.py:95
await session.commit()  # ❌ Commit immediately to send status update via SSE

# workers/tasks_rag_ingest/embed.py:116, 123, 138, 152, 204, 251
await session.commit()  # ❌ Multiple commits in single task

# services/model_registry_service.py:122, 196, 235
await self.session.commit()  # ❌ Service committing directly

# services/users_service.py:69, 100, 110
await self.users_repo.session.commit()  # ❌ Accessing repo session
```

**Проблема:** 
- Нарушение UoW паттерна
- Частичные коммиты при ошибках
- Невозможность отката всей транзакции
- Смешивание бизнес-логики и управления транзакциями

**Решение:**
- Убрать все `session.commit()` из workers и services
- Использовать `session.flush()` для промежуточных операций
- Commit делать только в endpoint/task wrapper на верхнем уровне

---

### 3. **TRANSACTION MANAGEMENT: UoW в deps.py (MEDIUM)**
**Файл:** `apps/api/src/app/api/deps.py:16-26`

```python
async def db_uow() -> AsyncGenerator[AsyncSession, None]:
    """Unit of Work dependency that handles transactions automatically"""
    async for session in get_db():
        try:
            yield session
            await session.commit()  # ✅ Правильное место для commit
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
```

**Проблема:** Dependency `db_uow` есть, но НЕ используется в роутерах. Вместо этого роутеры делают `await session.commit()` вручную.

**Примеры:**
```python
# v1/routers/rag.py:323, 403, 445, 531
await session.commit()

# v1/routers/tenants.py:76, 129, 174
await session.commit()

# v1/routers/rag_jobs.py:68, 109, 232, 287
await session.commit()
```

**Решение:**
- Использовать `db_uow` вместо `db_session` в роутерах
- Убрать все `await session.commit()` из роутеров

---

### 4. **TENANT ISOLATION: Хардкод tenant_id (MEDIUM)**
**Файлы:** Множественные роутеры

```python
# v1/routers/rag_search.py:74, 132
tenant_id = current_user.tenant_ids[0] if current_user.tenant_ids else "fb983a10-c5f8-4840-a9d3-856eea0dc729"  # ❌

# v1/routers/chat.py:368
tenant_id = current_user.tenant_ids[0] if current_user.tenant_ids else "fb983a10-c5f8-4840-a9d3-856eea0dc729"  # ❌
```

**Проблема:**
- Хардкод дефолтного tenant_id
- Небезопасный fallback
- Нет валидации tenant_ids

**Решение:**
- Требовать tenant_id всегда
- Убрать fallback на хардкод
- Добавить middleware для извлечения tenant_id из токена

---

### 5. **AUTH: Небезопасный fallback в get_current_user_optional (MEDIUM)**
**Файл:** `apps/api/src/app/api/deps.py:42-100`

```python
def get_current_user_optional(request: Request) -> UserCtx | None:
    # Special case for SSE endpoint
    if path.endswith("/api/v1/rag/events") or path.endswith("/rag/events"):
        pass  # ❌ Allow anonymous in ANY ENV
    
    if not token:
        if settings.ENV == "production":
            return None
        return UserCtx(
            id="dev-user",
            email="dev@localhost",
            role="reader",
            tenant_ids=["fb983a10-c5f8-4840-a9d3-856eea0dc729"],  # ❌ Hardcoded
            scopes=["read"]
        )
```

**Проблема:**
- SSE endpoint доступен без аутентификации даже в production
- Хардкод tenant_id в dev user
- Потенциальная утечка данных через SSE

**Решение:**
- Убрать специальную обработку SSE endpoint
- Использовать query param `?token=` для SSE (уже реализовано на фронте)
- Убрать dev user fallback в production

---

## 🟡 СРЕДНИЕ ПРОБЛЕМЫ

### 6. **DATA CONSISTENCY: Отсутствие индексов**
**Файлы:** Модели

**Проблемы:**
- `RAGStatus` нет индекса на `(doc_id, node_type, node_key)` - частые запросы
- `EventOutbox` нет индекса на `(delivered_at, created_at)` - для cleanup
- `Job` нет индекса на `celery_task_id` - поиск по task_id

**Решение:** Добавить составные индексы для частых запросов

---

### 7. **ERROR HANDLING: Неконсистентная обработка ошибок**
**Файлы:** Workers

```python
# workers/tasks_rag_ingest/error_utils.py:39, 93
await session.commit()  # ❌ Commit в error handler
```

**Проблема:** Error handlers сами коммитят, что может скрыть ошибки основной транзакции.

**Решение:** Error handlers должны только логировать, не коммитить.

---

### 8. **CODE QUALITY: Deprecated код не удален**
**Файл:** `apps/api/src/app/services/rag_service.py`

```python
class RAGDocumentsService(RepositoryService[RAGDocument]):
    """DEPRECATED: This service uses non-existent factory functions."""
    def __init__(self, session: Session):
        raise NotImplementedError("Use AsyncRepositoryFactory instead")
```

**Проблема:** Deprecated классы оставлены в кодовой базе, создают путаницу.

**Решение:** Удалить полностью или вынести в отдельный модуль `_deprecated.py`.

---

### 9. **MODELS: Inconsistent datetime usage**
**Файлы:** Модели

```python
# tenant.py:20-21
created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)  # ❌ utcnow deprecated
updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# user.py:24-25
created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())  # ✅ Правильно
```

**Проблема:** Смешивание `datetime.utcnow()` (deprecated в Python 3.12) и `func.now()`.

**Решение:** Везде использовать `server_default=func.now()` для консистентности.

---

### 10. **TYPING: Неконсистентные типы**

```python
# user.py:20
email: Mapped[str | None] = mapped_column(...)  # ✅ Modern union

# tenant.py:13
description: Mapped[str | None] = mapped_column(...)  # ✅ Modern union

# state_engine.py:61
celery_task_id: Mapped[Optional[str]] = mapped_column(...)  # ❌ Old Optional
```

**Решение:** Унифицировать на `str | None` (PEP 604).

---

## 🟢 НИЗКИЕ ПРОБЛЕМЫ / УЛУЧШЕНИЯ

### 11. **OBSERVABILITY: Недостаточное логирование**
- Workers не логируют начало/конец транзакций
- Нет correlation ID между связанными операциями
- Отсутствует structured logging для метрик

### 12. **PERFORMANCE: N+1 queries**
- `RAGStatus` запросы без `selectinload` для связанных документов
- Множественные запросы в циклах в workers

### 13. **TESTING: Отсутствие интеграционных тестов**
- Нет тестов для transaction rollback scenarios
- Нет тестов для tenant isolation
- Нет тестов для concurrent updates

---

## 📊 СТАТИСТИКА

| Категория | Критичность | Количество |
|-----------|-------------|------------|
| Security | 🔴 HIGH | 2 |
| Transaction Management | 🔴 HIGH | 15+ |
| Tenant Isolation | 🟡 MEDIUM | 5+ |
| Auth | 🟡 MEDIUM | 1 |
| Data Consistency | 🟡 MEDIUM | 3 |
| Code Quality | 🟢 LOW | 5+ |

**Всего проблем:** ~30+

---

## 🎯 ПРИОРИТЕТНЫЙ ПЛАН ИСПРАВЛЕНИЙ

### Фаза 1: Критические (1-2 дня)
1. ✅ Исправить JWKS - использовать RSA ключи
2. ✅ Убрать все `session.commit()` из services
3. ✅ Убрать все `session.commit()` из workers (кроме top-level)
4. ✅ Использовать `db_uow` в роутерах

### Фаза 2: Безопасность (1 день)
5. ✅ Убрать хардкод tenant_id
6. ✅ Исправить SSE auth
7. ✅ Добавить tenant_id validation middleware

### Фаза 3: Качество (2-3 дня)
8. ✅ Удалить deprecated код
9. ✅ Унифицировать datetime usage
10. ✅ Добавить недостающие индексы
11. ✅ Исправить error handling в workers

### Фаза 4: Улучшения (ongoing)
12. Добавить интеграционные тесты
13. Улучшить observability
14. Оптимизировать N+1 queries

---

## 🔍 МЕТОДОЛОГИЯ ПРОВЕРКИ

Проверено:
- ✅ Все модели (`app/models/*.py`)
- ✅ Все репозитории (`app/repositories/*.py`)
- ✅ Все сервисы (`app/services/*.py`)
- ✅ Все роутеры (`app/api/v1/routers/*.py`)
- ✅ Все workers (`app/workers/*.py`)
- ✅ Core компоненты (`app/core/*.py`)
- ✅ Dependencies (`app/api/deps*.py`)

Инструменты:
- grep для поиска паттернов
- Ручной code review критических файлов
- Анализ transaction flow
- Security audit

---

## 💡 РЕКОМЕНДАЦИИ

1. **Transaction Management:**
   - Принять строгое правило: commit только на границе системы (endpoint/task)
   - Использовать декораторы для автоматического UoW
   - Добавить линтер для проверки `session.commit()` в неправильных местах

2. **Security:**
   - Переход на асимметричную криптографию для JWT
   - Ротация ключей каждые 90 дней
   - Аудит всех auth endpoints

3. **Tenant Isolation:**
   - Middleware для автоматической проверки tenant_id
   - Row-level security в PostgreSQL
   - Аудит логи для cross-tenant access attempts

4. **Code Quality:**
   - Pre-commit hooks для проверки паттернов
   - Обязательный code review для изменений в core
   - Документация архитектурных решений
