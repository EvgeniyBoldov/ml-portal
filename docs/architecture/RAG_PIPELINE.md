# RAG Pipeline

## Обзор

RAG (Retrieval-Augmented Generation) Pipeline — система обработки документов для семантического поиска.

## Стадии обработки

```
Upload → Extract → Chunk → Embed → Ready
```

### 1. Upload
Загрузка файла в систему.

- Сохранение в MinIO (bucket: `rag`)
- Создание записи в Postgres (status: `pending`)
- Вычисление content_hash для дедупликации
- Постановка в очередь Celery

### 2. Extract
Извлечение текста из файла.

**Поддерживаемые форматы:**
- PDF (PyMuPDF + OCR опционально)
- DOCX, DOC
- TXT, MD
- HTML
- XLSX, CSV

**Результат:**
- Сырой текст сохраняется в MinIO
- Метаданные: страницы, язык, MIME-type

### 3. Chunk
Разбиение текста на чанки.

**Параметры:**
- `chunk_size`: размер чанка (default: 512 tokens)
- `chunk_overlap`: перекрытие (default: 50 tokens)

**Стратегии:**
- Sentence-based: разбиение по предложениям
- Recursive: рекурсивное разбиение по разделителям

**Результат:**
- Чанки сохраняются в Postgres
- Каждый чанк имеет уникальный `chunk_id`

### 4. Embed
Векторизация чанков.

**Мультимодельный эмбеддинг:**
- Глобальная модель (default для всех)
- Дополнительные модели тенанта

**Процесс:**
1. Батчинг чанков
2. Отправка в EMB service
3. Upsert в Qdrant

**Payload в Qdrant:**
```json
{
  "tenant_id": "uuid",
  "document_id": "uuid",
  "chunk_id": "uuid",
  "page": 1,
  "lang": "ru",
  "mime": "application/pdf",
  "version": 1,
  "updated_at": "2024-01-01T00:00:00Z",
  "tags": ["tag1", "tag2"]
}
```

## Статусы документа

| Статус | Описание |
|--------|----------|
| `pending` | Ожидает обработки |
| `processing` | В процессе |
| `ready` | Готов к поиску |
| `failed` | Ошибка обработки |
| `archived` | Архивирован |

## Статусы стадий

Каждая стадия имеет свой статус в `RagIngest`:

| Статус | Описание |
|--------|----------|
| `pending` | Ожидает |
| `running` | Выполняется |
| `completed` | Завершена |
| `failed` | Ошибка |
| `skipped` | Пропущена |

## SSE события

### Tenant feed
Канал: `rag:tenant:{tenantId}`

События:
- `document.created` — новый документ
- `document.status_changed` — изменение статуса
- `document.deleted` — удаление

### Document detail
Канал: `rag:doc:{docId}`

События:
- `stage.started` — начало стадии
- `stage.progress` — прогресс (%)
- `stage.completed` — завершение стадии
- `stage.failed` — ошибка стадии

## Поиск

### Векторный поиск
```python
async def vector_search(
    tenant_id: UUID,
    query: str,
    limit: int = 10,
    filters: dict = None
) -> list[SearchResult]:
    # 1. Embed query
    embedding = await emb_service.embed(query)
    
    # 2. Search in Qdrant
    results = await qdrant.search(
        collection=f"rag_{tenant_id}",
        vector=embedding,
        limit=limit,
        filter=build_filter(filters)
    )
    
    return results
```

### Гибридный поиск
```python
async def hybrid_search(
    tenant_id: UUID,
    query: str,
    limit: int = 10
) -> list[SearchResult]:
    # 1. Vector search
    vector_results = await vector_search(tenant_id, query, limit * 2)
    
    # 2. Lexical search (FTS)
    fts_results = await fts_search(tenant_id, query, limit * 2)
    
    # 3. Merge with RRF
    merged = reciprocal_rank_fusion(vector_results, fts_results)
    
    # 4. Optional rerank
    if rerank_enabled:
        merged = await rerank_service.rerank(query, merged)
    
    return merged[:limit]
```

## Конфигурация

### Tenant settings
```python
class TenantRagConfig:
    ocr: bool = False  # включить OCR
    layout: bool = False  # анализ layout
    extra_embed_model: str | None = None  # доп. модель
```

### Environment
```bash
EMB_BASE_URL=http://emb:8001
EMB_MODELS=all-MiniLM-L6-v2,multilingual-e5-small
QDRANT_URL=http://qdrant:6333
```

## Celery Tasks

### ingest_document
Основная задача обработки.

```python
@celery.task(bind=True, max_retries=3)
def ingest_document(self, document_id: str):
    async with worker_transaction() as session:
        # Extract
        await extract_stage(session, document_id)
        
        # Chunk
        await chunk_stage(session, document_id)
        
        # Embed
        await embed_stage(session, document_id)
```

### reindex_document
Переиндексация документа.

### delete_document_vectors
Удаление векторов из Qdrant.

## Дедупликация

### Content hash
SHA-256 от содержимого файла.

### Chunk deduplication
Уникальный `chunk_id` = hash(document_id + chunk_index + content).

## Версионирование

### Embed model version
Каждый вектор хранит `embed_model_alias` и `embed_model_version`.

### Document version
При обновлении документа создаётся новая версия, старые векторы удаляются.
