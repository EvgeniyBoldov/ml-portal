# Стратегия управления транзакциями в Celery тасках

## Принципы

### 1. Одна транзакция = одна таска
Каждая Celery таска работает в рамках одной транзакции БД. Commit происходит только в конце успешного выполнения, rollback — при ошибке.

### 2. Разделение ответственности

**Репозиторий (`AsyncRAGStatusRepository`)**:
- Делает только `flush()` после изменений
- НЕ делает `commit()` — это ответственность вызывающего кода
- `flush()` отправляет изменения в БД, но не фиксирует транзакцию

**Celery таска**:
- Открывает сессию через `async with session_factory() as session`
- Выполняет всю бизнес-логику
- Делает `flush()` после критичных операций (для триггера SSE событий)
- Делает **один** `commit()` в самом конце перед `return`
- При ошибке автоматический rollback (контекстный менеджер)

### 3. SSE события и flush

```python
# Обновляем статус
await status_manager.transition_stage(
    doc_id=doc_id,
    stage='extract',
    new_status=StageStatus.PROCESSING
)
await session.flush()  # Trigger SSE - изменения видны в БД, но не зафиксированы
```

**Важно**: `flush()` делает изменения видимыми для других запросов в той же транзакции и триггерит SSE события, но НЕ фиксирует транзакцию. Если таска упадёт после flush, все изменения откатятся.

## Паттерн для Celery таски

```python
@celery_app.task(bind=True, autoretry_for=(Exception,))
def my_task(self: Task, doc_id: str, tenant_id: str):
    try:
        import asyncio
        
        async def _process():
            # Создаём engine и session для этого event loop
            engine = create_async_engine(settings.ASYNC_DB_URL, ...)
            session_factory = async_sessionmaker(engine, expire_on_commit=False)
            
            redis_client = None
            try:
                async with session_factory() as session:
                    # Вся работа здесь
                    redis_client = redis.from_url(settings.REDIS_URL)
                    status_manager = RAGStatusManager(session, ...)
                    
                    # Начало работы
                    await status_manager.transition_stage(
                        doc_id=doc_id,
                        stage='my_stage',
                        new_status=StageStatus.PROCESSING
                    )
                    await session.flush()  # Trigger SSE
                    
                    # Основная работа
                    result = await do_work()
                    
                    # Завершение
                    await status_manager.transition_stage(
                        doc_id=doc_id,
                        stage='my_stage',
                        new_status=StageStatus.COMPLETED
                    )
                    await session.flush()  # Trigger SSE
                    
                    # Сохраняем idempotency key
                    await redis_client.setex(idem_key, 86400, json.dumps(result))
                    
                    # ЕДИНСТВЕННЫЙ commit в конце
                    await session.commit()
                    
                    return result
                    
            except Exception as e:
                # Обработка ошибок
                await notify_stage_error(doc_id, tenant_id, 'my_stage', e)
                raise
            finally:
                # Cleanup
                if redis_client:
                    await redis_client.close()
                await engine.dispose()
        
        return asyncio.run(_process())
        
    except Exception as e:
        logger.error(f"Error in my_task: {e}")
        raise self.retry(exc=e, countdown=60, max_retries=3)
```

## Почему это работает

1. **Атомарность**: Вся работа таски либо фиксируется целиком (commit), либо откатывается (rollback при ошибке)

2. **SSE в реальном времени**: `flush()` делает изменения видимыми и триггерит события, пользователь видит прогресс

3. **Безопасность**: Если таска упадёт после flush но до commit, все изменения откатятся — не будет частично обработанных документов

4. **Idempotency**: Redis ключ сохраняется после commit, поэтому повторный запуск таски не дублирует работу

## Антипаттерны (НЕ делать)

❌ **Множественные commit в таске**
```python
await session.commit()  # После каждого шага
await do_step_2()
await session.commit()  # Ещё один
```
Проблема: Если step_2 упадёт, step_1 уже зафиксирован — частичное состояние.

❌ **Commit в репозитории**
```python
class MyRepository:
    async def update(self, ...):
        self.session.add(obj)
        await self.session.commit()  # ❌
```
Проблема: Репозиторий не знает о контексте транзакции таски.

❌ **Забыть flush перед commit**
```python
await status_manager.transition_stage(...)
# Нет flush - SSE события не отправятся до commit
await session.commit()
```
Проблема: SSE события придут только после commit, пользователь не видит прогресс.

## Обработка ошибок

```python
try:
    async with session_factory() as session:
        # Работа
        await session.commit()
        return result
except Exception as e:
    # Rollback автоматический (контекстный менеджер)
    # Уведомляем о проблеме
    await notify_stage_error(doc_id, tenant_id, stage, e)
    raise  # Celery retry
```

## Проверка

После изменений проверьте:
1. Worker запускается без ошибок
2. Таски выполняются успешно
3. SSE события приходят в реальном времени
4. При ошибке статусы откатываются (не остаются в PROCESSING)
5. Повторный запуск таски (idempotency) работает корректно
