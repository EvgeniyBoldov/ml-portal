# Стримы и SSE

## Обзор

Система использует Server-Sent Events (SSE) для real-time обновлений.

## Архитектура

```
┌──────────┐     SSE      ┌──────────┐     Redis     ┌──────────┐
│  Client  │◄────────────│   API    │◄──────────────│  Worker  │
└──────────┘              └──────────┘               └──────────┘
                               │
                               ▼
                          ┌──────────┐
                          │  Redis   │
                          │  Pub/Sub │
                          └──────────┘
```

## Каналы

### RAG события

| Канал | Описание |
|-------|----------|
| `rag:tenant:{tenantId}` | События для списка документов тенанта |
| `rag:doc:{docId}` | Детальные события документа |
| `rag:doc:{docId}:pipeline` | Прогресс пайплайна |

### Chat события

| Канал | Описание |
|-------|----------|
| `chat:{chatId}:{streamId}` | Стрим ответа агента |

## SSE Endpoint

```python
@router.get("/sse")
async def sse_stream(
    request: Request,
    token: str = Query(...),  # Auth через query param
    redis: Redis = Depends(get_redis),
):
    # Validate token
    user = await validate_token(token)
    
    async def event_generator():
        pubsub = redis.pubsub()
        await pubsub.subscribe(f"rag:tenant:{user.tenant_id}")
        
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    yield {
                        "event": "message",
                        "data": message["data"]
                    }
        finally:
            await pubsub.unsubscribe()
    
    return EventSourceResponse(event_generator())
```

## Публикация событий

### Из сервиса

```python
class RagEventPublisher:
    def __init__(self, redis: Redis):
        self.redis = redis
    
    async def publish_stage_progress(
        self,
        document_id: UUID,
        stage: str,
        progress: int
    ) -> None:
        event = {
            "type": "stage.progress",
            "document_id": str(document_id),
            "stage": stage,
            "progress": progress,
            "timestamp": datetime.utcnow().isoformat()
        }
        await self.redis.publish(
            f"rag:doc:{document_id}",
            json.dumps(event)
        )
```

### Из Celery worker

```python
async def embed_stage(session: AsyncSession, document_id: UUID):
    publisher = RagEventPublisher(get_redis())
    
    chunks = await get_chunks(session, document_id)
    total = len(chunks)
    
    for i, batch in enumerate(batched(chunks, 100)):
        await embed_batch(batch)
        
        # Publish progress
        progress = int((i + 1) * 100 / total)
        await publisher.publish_stage_progress(
            document_id, "embed", progress
        )
        
        await session.flush()  # Для видимости изменений
```

## Chat Streaming

### Инициация стрима

```python
@router.post("/chats/{chat_id}/messages")
async def send_message(
    chat_id: UUID,
    data: MessageCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    service = ChatStreamService(db)
    stream_id = await service.start_stream(chat_id, user.id, data.content)
    
    return {"stream_id": stream_id}
```

### Стриминг ответа

```python
async def stream_response(
    self,
    chat_id: UUID,
    stream_id: str,
    on_event: Callable
):
    # Build context
    context = await self._build_context(chat_id)
    
    # Run agent
    async for event in self.runtime.run(context):
        # Publish to Redis
        await self.redis.publish(
            f"chat:{chat_id}:{stream_id}",
            json.dumps(event)
        )
        
        # Also call callback
        on_event(event)
    
    # Signal completion
    await self.redis.publish(
        f"chat:{chat_id}:{stream_id}",
        json.dumps({"type": "done"})
    )
```

## Типы событий

### RAG события

```typescript
// Document status changed
{
  "type": "document.status_changed",
  "document_id": "uuid",
  "status": "processing" | "ready" | "failed",
  "timestamp": "ISO8601"
}

// Stage progress
{
  "type": "stage.progress",
  "document_id": "uuid",
  "stage": "extract" | "chunk" | "embed",
  "progress": 0-100,
  "timestamp": "ISO8601"
}

// Stage completed
{
  "type": "stage.completed",
  "document_id": "uuid",
  "stage": "extract" | "chunk" | "embed",
  "timestamp": "ISO8601"
}
```

### Chat события

```typescript
// Delta (text chunk)
{
  "type": "delta",
  "content": "partial text..."
}

// Tool call
{
  "type": "tool_call",
  "tool": "rag.search",
  "arguments": {"query": "..."}
}

// Tool result
{
  "type": "tool_result",
  "tool": "rag.search",
  "result": "..."
}

// Done
{
  "type": "done"
}

// Error
{
  "type": "error",
  "message": "..."
}
```

## Heartbeat

Поддержание соединения.

```python
async def event_generator():
    last_heartbeat = time.time()
    
    while True:
        # Check for messages
        message = await pubsub.get_message(timeout=1.0)
        
        if message:
            yield {"event": "message", "data": message["data"]}
        
        # Send heartbeat every 30s
        if time.time() - last_heartbeat > 30:
            yield {"event": "heartbeat", "data": ""}
            last_heartbeat = time.time()
```

## Подписки

### Управление подписками

```python
class SubscriptionManager:
    def __init__(self, redis: Redis):
        self.redis = redis
    
    async def subscribe(self, channel: str, user_id: UUID) -> None:
        # Increment subscriber count
        await self.redis.incr(f"subs:{channel}")
        await self.redis.sadd(f"subs:{channel}:users", str(user_id))
    
    async def unsubscribe(self, channel: str, user_id: UUID) -> None:
        # Decrement subscriber count
        count = await self.redis.decr(f"subs:{channel}")
        await self.redis.srem(f"subs:{channel}:users", str(user_id))
        
        # Cleanup if no subscribers
        if count <= 0:
            await self.redis.delete(f"subs:{channel}")
            await self.redis.delete(f"subs:{channel}:users")
```

## Nginx конфигурация

```nginx
location /api/v1/sse {
    proxy_pass http://api:8000;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 3600s;
    chunked_transfer_encoding off;
}
```
