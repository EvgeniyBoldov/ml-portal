# Потоки данных

## 1. Аутентификация

```
┌──────────┐     POST /auth/login      ┌──────────┐
│  Client  │ ─────────────────────────►│   API    │
└──────────┘                           └──────────┘
                                            │
                                            ▼
                                       ┌──────────┐
                                       │ Postgres │ verify credentials
                                       └──────────┘
                                            │
                                            ▼
┌──────────┐     Set-Cookie (refresh)  ┌──────────┐
│  Client  │ ◄─────────────────────────│   API    │
│          │     + access_token (body) │          │
└──────────┘                           └──────────┘
```

- Access token хранится в памяти (не localStorage)
- Refresh token в httpOnly cookie
- Refresh через `POST /auth/refresh`

## 2. Чат с агентом

```
┌──────────┐  POST /chats/{id}/messages  ┌──────────┐
│  Client  │ ───────────────────────────►│   API    │
└──────────┘                             └──────────┘
     │                                        │
     │                                        ▼
     │                                   ┌──────────┐
     │                                   │  Agent   │
     │                                   │  Router  │
     │                                   └──────────┘
     │                                        │
     │                                        ▼
     │                                   ┌──────────┐
     │                                   │  Agent   │
     │                                   │ Runtime  │
     │                                   └──────────┘
     │                                        │
     │    SSE: delta, tool_call, done        │
     │◄───────────────────────────────────────┘
```

### Agent Router
1. Загружает агента
2. Резолвит permissions
3. Резолвит tools + instances + credentials
4. Проверяет prerequisites
5. Определяет execution mode (full/partial/unavailable)

### Agent Runtime
1. Формирует system prompt (base + baseline merge)
2. Отправляет в LLM
3. Обрабатывает tool calls
4. Стримит результат через SSE

## 3. RAG Pipeline

```
┌──────────┐  POST /rag/upload   ┌──────────┐
│  Client  │ ───────────────────►│   API    │
└──────────┘                     └──────────┘
                                      │
                                      ▼
                                 ┌──────────┐
                                 │  MinIO   │ save file
                                 └──────────┘
                                      │
                                      ▼
                                 ┌──────────┐
                                 │ Postgres │ create document
                                 └──────────┘
                                      │
                                      ▼
                                 ┌──────────┐
                                 │  Celery  │ enqueue task
                                 └──────────┘
                                      │
     ┌────────────────────────────────┼────────────────────────────────┐
     ▼                                ▼                                ▼
┌──────────┐                    ┌──────────┐                    ┌──────────┐
│ Extract  │                    │  Chunk   │                    │  Embed   │
│  Stage   │───────────────────►│  Stage   │───────────────────►│  Stage   │
└──────────┘                    └──────────┘                    └──────────┘
     │                                │                                │
     ▼                                ▼                                ▼
┌──────────┐                    ┌──────────┐                    ┌──────────┐
│  MinIO   │                    │ Postgres │                    │  Qdrant  │
│  (text)  │                    │ (chunks) │                    │(vectors) │
└──────────┘                    └──────────┘                    └──────────┘
```

### Стадии
1. **Extract**: извлечение текста из файла (PDF, DOCX, etc.)
2. **Chunk**: разбиение на чанки с overlap
3. **Embed**: векторизация через EMB service, upsert в Qdrant

### SSE обновления
- `rag:tenant:{tenantId}` — события для списка документов
- `rag:doc:{docId}` — детальные события для документа
- `rag:doc:{docId}:pipeline` — прогресс пайплайна

## 4. RAG Search

```
┌──────────┐  POST /rag/search   ┌──────────┐
│  Client  │ ───────────────────►│   API    │
└──────────┘                     └──────────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    ▼                 ▼                 ▼
              ┌──────────┐     ┌──────────┐     ┌──────────┐
              │   EMB    │     │  Qdrant  │     │ Postgres │
              │ (embed)  │     │ (search) │     │  (FTS)   │
              └──────────┘     └──────────┘     └──────────┘
                    │                 │                 │
                    └─────────────────┼─────────────────┘
                                      ▼
                                 ┌──────────┐
                                 │  Rerank  │ (optional)
                                 └──────────┘
                                      │
                                      ▼
┌──────────┐     search results  ┌──────────┐
│  Client  │ ◄───────────────────│   API    │
└──────────┘                     └──────────┘
```

### Гибридный поиск
1. Векторный поиск в Qdrant
2. Лексический fallback в Postgres (FTS)
3. Агрегация результатов (RRF/score normalization)
4. Опциональный rerank через cross-encoder

## 5. Collection Vectorization

```
┌──────────┐  POST /collections/{slug}/vectorize  ┌──────────┐
│  Client  │ ────────────────────────────────────►│   API    │
└──────────┘                                      └──────────┘
                                                       │
                                                       ▼
                                                  ┌──────────┐
                                                  │  Celery  │
                                                  └──────────┘
                                                       │
     ┌─────────────────────────────────────────────────┘
     ▼
┌──────────┐     ┌──────────┐     ┌──────────┐
│ Postgres │────►│   EMB    │────►│  Qdrant  │
│  (data)  │     │ (embed)  │     │(vectors) │
└──────────┘     └──────────┘     └──────────┘
```

## 6. Permission Resolution

```
┌──────────────────────────────────────────────────────────────┐
│                    Permission Resolution                      │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  1. Check User scope                                         │
│     └─► if explicit (allowed/denied) → return               │
│                                                              │
│  2. Check Tenant scope                                       │
│     └─► if explicit (allowed/denied) → return               │
│                                                              │
│  3. Check Default scope                                      │
│     └─► return (allowed/denied, no undefined)               │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

## 7. Credential Resolution

```
┌──────────────────────────────────────────────────────────────┐
│                    Credential Resolution                      │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  Strategy: user_only                                         │
│     └─► only User scope                                      │
│                                                              │
│  Strategy: tenant_only                                       │
│     └─► only Tenant scope                                    │
│                                                              │
│  Strategy: prefer_user                                       │
│     └─► User → Tenant → Default                             │
│                                                              │
│  Strategy: prefer_tenant                                     │
│     └─► Tenant → User → Default                             │
│                                                              │
│  Strategy: any                                               │
│     └─► User → Tenant → Default (first found)               │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```
