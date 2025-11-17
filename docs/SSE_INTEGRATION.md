# SSE Integration для RAG документов

## Архитектура

### Backend (FastAPI + Redis)

**Endpoint:** `GET /api/v1/rag/status/events`

**Каналы Redis Pub/Sub:**
- `rag:status:admin` — все события для админов
- `rag:status:tenant:{tenant_id}` — события конкретного тенанта
- `rag:status:updates` — legacy канал (для обратной совместимости)

**Типы событий:**
- `status_update` — обновление статуса этапа (extract, chunk, embed, index)
- `status_initialized` — инициализация статусов нового документа
- `ingest_started` — начало инжеста
- `document_archived` / `document_unarchived` — архивация/разархивация

**Формат события:**
```json
{
  "event_type": "status_update",
  "document_id": "uuid",
  "tenant_id": "uuid",
  "stage": "extract",
  "status": "processing",
  "error": null,
  "metrics": {},
  "timestamp": "2025-11-15T14:30:00Z"
}
```

**Права доступа:**
- `reader` — НЕ имеет доступа (403)
- `editor` — получает события только своего тенанта
- `admin` — получает все события

### Frontend (React + TanStack Query)

**Провайдер:** `SSEProvider` в `app/AppProviders.tsx`
- Подключается глобально после `AuthProvider`
- Использует httpOnly cookies для аутентификации
- Батчит события каждые 100ms для оптимизации

**Обработчик событий:** `applyRagEvents` в `app/providers/applyRagEvents.ts`
- Обновляет кэш TanStack Query атомарно
- Поддерживает идемпотентность через sequence numbers
- Автоматически инвалидирует список при появлении новых документов

**Типы обновлений:**
1. **Список документов** (`useRagDocuments`)
   - Обновление статусов существующих документов
   - Добавление новых документов через invalidation
   - Удаление архивированных документов

2. **Детальный статус** (`useRagDocument`)
   - Обновление StatusGraph в реальном времени
   - Пересчет агрегированного статуса на фронте
   - Обновление метрик и прогресса эмбеддингов

3. **StatusModal**
   - Автоматическое обновление графа этапов
   - Обновление деталей выбранного этапа
   - Обновление списка моделей эмбеддингов

## Полный цикл работы

### 1. Загрузка документа

```typescript
// User uploads file
await uploadMutation.mutateAsync({ file, filename, tags });

// Backend:
// 1. Сохраняет файл в S3
// 2. Создает запись в БД
// 3. Инициализирует статусы (RAGStatusManager.initialize_document_statuses)
// 4. Публикует событие status_initialized в Redis

// Frontend:
// 1. uploadMutation.onSuccess инвалидирует список
// 2. SSE получает status_initialized
// 3. applyRagEvents проверяет, что документа нет в списке
// 4. Инвалидирует список для подтягивания нового документа
// 5. useRagDocuments рефетчит список с новым документом
```

### 2. Запуск инжеста

```typescript
// User clicks "Start ingest"
await apiRequest(`/rag/status/${docId}/ingest/start`, { method: 'POST' });

// Backend:
// 1. Переводит все pending этапы в queued
// 2. Публикует событие ingest_started
// 3. Запускает Celery pipeline: extract → normalize → chunk → group(embed per model)

// Frontend:
// 1. SSE получает ingest_started
// 2. applyRagEvents обновляет статусы в кэше
// 3. UI мгновенно показывает "queued" для всех этапов
```

### 3. Обработка документа

```typescript
// Celery worker starts extract task
// Backend:
// 1. Обновляет статус в БД: extract = processing
// 2. Публикует status_update в Redis

// Frontend:
// 1. SSE получает status_update
// 2. applyRagEvents обновляет StatusGraph и список
// 3. UI показывает "processing" для extract
// 4. StatusModal обновляет граф в реальном времени

// ... аналогично для normalize, chunk, embed, index
```

### 4. Прогресс эмбеддингов

```typescript
// Celery worker reports embedding progress
// Backend:
// 1. Публикует rag.embed.progress в Redis

// Frontend:
// 1. SSE получает rag.embed.progress
// 2. applyEmbedProgressEvent обновляет emb_status в списке
// 3. applyEmbedProgressEvent обновляет embeddings в StatusGraph
// 4. UI показывает прогресс-бар для каждой модели
```

## Конфигурация

### Backend

```python
# apps/api/src/app/core/config.py
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# apps/api/src/app/services/rag_event_publisher.py
CHANNEL_ADMIN = "rag:status:admin"
CHANNEL_TENANT_FMT = "rag:status:tenant:{tenant_id}"
```

### Frontend

```typescript
// apps/web/src/shared/config.ts
export const config = {
  ragEventsUrl: `${API_BASE}/rag/status/events`,
  enableSSELogging: import.meta.env.VITE_ENABLE_SSE_LOGGING === 'true',
};
```

## Отладка

### Включить логирование SSE

```bash
# .env.dev
VITE_ENABLE_SSE_LOGGING=true
```

### Проверить подключение

```bash
# Browser console
# Должны появиться логи:
# [SSE] Connecting to /api/v1/rag/status/events
# [SSE] { total: 10, lastSecond: 2, url: '...' }
```

### Проверить Redis

```bash
# Redis CLI
redis-cli
> SUBSCRIBE rag:status:admin
> SUBSCRIBE rag:status:tenant:YOUR_TENANT_ID
```

## Best Practices

1. **Не используй оптимистичные обновления** — SSE и так быстро доставляет события
2. **Используй sequence numbers** — для идемпотентности и защиты от дубликатов
3. **Батчи события** — 100ms батчинг предотвращает UI thrashing
4. **Инвалидируй при необходимости** — если документ не найден в кэше, инвалидируй список
5. **Используй httpOnly cookies** — для безопасной аутентификации SSE

## Troubleshooting

### SSE не подключается

- Проверь, что Redis запущен
- Проверь, что пользователь авторизован (httpOnly cookies)
- Проверь права доступа (reader не имеет доступа к SSE)

### События не приходят

- Проверь, что Celery worker публикует события
- Проверь Redis каналы через `redis-cli SUBSCRIBE`
- Проверь логи бэкенда на ошибки публикации

### UI не обновляется

- Проверь, что SSEProvider подключен в AppProviders
- Проверь, что applyRagEvents корректно обновляет кэш
- Проверь React Query DevTools для состояния кэша
