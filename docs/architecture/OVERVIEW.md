# Обзор системы

## Высокоуровневая архитектура

```
┌─────────────────────────────────────────────────────────────────┐
│                         NGINX (Reverse Proxy)                    │
│                    TLS termination, routing, limits              │
└─────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
              ┌──────────┐   ┌──────────┐   ┌──────────┐
              │ Frontend │   │   API    │   │  MinIO   │
              │  (Vite)  │   │(FastAPI) │   │  Files   │
              └──────────┘   └──────────┘   └──────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
              ┌──────────┐   ┌──────────┐   ┌──────────┐
              │  Redis   │   │ Postgres │   │  Qdrant  │
              │  Cache   │   │   Data   │   │ Vectors  │
              └──────────┘   └──────────┘   └──────────┘
                    │
                    ▼
              ┌──────────┐   ┌──────────┐   ┌──────────┐
              │  Worker  │   │   EMB    │   │  Rerank  │
              │ (Celery) │   │ Service  │   │ Service  │
              └──────────┘   └──────────┘   └──────────┘
```

## Компоненты

### Frontend (React + Vite)
- SPA с React 18, TypeScript, TanStack Query
- SSE для real-time обновлений
- CSS Modules для стилизации

### API (FastAPI)
- REST API с JWT аутентификацией
- SSE endpoints для стриминга
- WebSocket для чата (опционально)
- Оркестрация Celery задач

### Worker (Celery)
- RAG pipeline (extract, chunk, embed)
- Фоновые задачи (health check, cleanup)
- Асинхронная обработка документов

### EMB Service
- HTTP сервис эмбеддингов
- Мультимодельная поддержка
- Батчинг и backpressure

### Rerank Service
- Переранжирование результатов поиска
- Cross-encoder модели

## Хранилища

### PostgreSQL
**System of Record** — единственный источник истины.
- Пользователи, тенанты, роли
- Агенты, промпты, политики
- Чаты, сообщения
- RAG документы (метаданные)
- Коллекции, права доступа

### Qdrant
**Векторное хранилище** для семантического поиска.
- RAG эмбеддинги (multi-model)
- Collection эмбеддинги
- Payload с метаданными

### Redis
**Ephemeral storage** — кэш и очереди.
- Session cache
- Rate limiting
- Idempotency keys
- Celery broker/backend
- SSE pub/sub

### MinIO
**Object storage** — файлы и артефакты.
- Загруженные документы
- Извлечённый текст
- Модели (offline)

## Сети

### External
- NGINX → Frontend (80/443)
- NGINX → API (80/443)
- NGINX → MinIO files (443)

### Internal
- API ↔ Postgres, Redis, Qdrant, MinIO
- Worker ↔ Postgres, Redis, Qdrant, MinIO, EMB
- EMB ↔ Qdrant (опционально)

## Масштабирование

### Горизонтальное
- API: stateless, можно добавлять реплики
- Worker: увеличение concurrency
- EMB: реплики для throughput

### Вертикальное
- Postgres: RAM для кэша
- Qdrant: RAM для индексов
- EMB: CPU/GPU для inference
