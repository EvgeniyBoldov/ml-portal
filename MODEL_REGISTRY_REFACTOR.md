# Model Registry Refactoring Summary

## 🎯 Цель

Переход от «сканирования файловой системы» к «таблице конфигурации провайдеров»:
- **Было:** модели лежат в `/models_llm`, скрипт сканирует директорию и синхронизирует с БД.
- **Стало:** LLM и Embedding модели конфигурируются вручную через API, подключаются к внешним/внутренним провайдерам.

## 📊 Новая архитектура

### Что в таблице `models`

Только **динамичные** модели, которые часто меняются:
- **LLM (llm_chat):** Groq, OpenAI, локальные LLM
- **Embedding:** OpenAI, локальные HF модели

### Что НЕ в таблице (локальные контейнеры)

**Стабильные** сервисы, редко меняются, конфигурируются через `settings.py`:
- **Reranker** (http://reranker:8002) — cross-encoder для переранжирования
- **OCR** (будущее) — Tesseract/PaddleOCR
- **ASR** (будущее) — Whisper
- **Vision** (будущее) — мультимодальные модели

## 🗂️ Изменённые файлы

### 1. Модель (SQLAlchemy)

**Файл:** `apps/api/src/app/models/model_registry.py`

**Было:**
```python
class ModelRegistry:
    model: str           # from manifest
    version: str
    modality: str        # text|image|rerank
    path: str            # /models_llm/...
    vector_dim: int
    is_global: bool
```

**Стало:**
```python
class Model:
    alias: str                    # llm.chat.default
    name: str                     # Human-readable
    type: ModelType               # llm_chat | embedding
    provider: str                 # openai, groq, local
    provider_model_name: str      # gpt-4o, llama-3.1-70b
    base_url: str                 # https://api.groq.com/openai/v1
    api_key_ref: str | None       # env:GROQ_API_KEY
    extra_config: dict | None     # {temperature: 0.7, ...}
    status: ModelStatus           # available, unavailable, ...
    enabled: bool
    default_for_type: bool
    health_status: HealthStatus   # healthy, degraded, ...
    model_version: str | None     # для отслеживания изменений
```

### 2. Схемы (Pydantic)

**Файл:** `apps/api/src/app/schemas/model_registry.py`

- Убраны: `ScanResult`, `RetireRequest`, `RetireResponse`
- Добавлены: `HealthCheckRequest`, `HealthCheckResponse`
- Переименованы: `ModelRegistryBase` → `ModelBase`

### 3. Провайдеры

**Новая директория:** `apps/api/src/app/providers/`

#### `embedding_provider.py`

```python
class EmbeddingProvider(Protocol):
    async def embed_texts(texts, model) -> List[List[float]]

class OpenAIEmbeddingProvider:  # Groq, OpenAI, Azure
class LocalEmbeddingProvider:   # Локальный HF контейнер
```

#### `rerank_provider.py`

```python
class RerankProvider(Protocol):
    async def rerank(query, docs, top_k) -> List[RankedDocument]

class LocalRerankProvider:   # Локальный cross-encoder
class CohereRerankProvider:  # Cohere API
```

### 4. Конфигурация

**Файл:** `apps/api/src/app/core/config.py`

**Добавлено:**
```python
# Reranker (local service)
RERANK_SERVICE_URL: str = "http://reranker:8002"
RERANK_MODEL: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
RERANK_ENABLED: bool = True

# OCR (future)
OCR_SERVICE_URL: str = "http://ocr:8003"
OCR_ENABLED: bool = False

# ASR (future)
ASR_SERVICE_URL: str = "http://whisper:8004"
ASR_ENABLED: bool = False
```

**Помечено deprecated:**
```python
# Embedding (deprecated - moved to models table)
EMB_BASE_URL: str = ...  # Keep for backward compatibility
```

### 5. Документация

**Новый файл:** `docs/LOCAL_SERVICES.md`

Подробное описание:
- Reranker API (OpenAI-style)
- Примеры Docker контейнеров
- Python implementation
- Health checks

## 🔄 Что удалено

### ❌ Scan логика (будет удалена в следующем коммите)

- `ModelRegistryService.scan_models_directory()` — больше не нужен
- `POST /api/v1/models/scan` endpoint
- Зависимость от `/models_llm` директории
- Manifest.json файлы

## 📝 Миграция данных

### План миграции (будет в отдельном коммите)

1. **Создать новую таблицу `models`:**
   ```sql
   CREATE TABLE models (
     id UUID PRIMARY KEY,
     alias VARCHAR(100) UNIQUE,
     type VARCHAR(20),
     provider VARCHAR(50),
     ...
   );
   ```

2. **Создать дефолтные модели:**
   ```sql
   -- LLM
   INSERT INTO models (alias, name, type, provider, base_url, ...)
   VALUES ('llm.chat.default', 'Groq Llama 3.1 70B', 'llm_chat', 'groq', ...);
   
   -- Embedding
   INSERT INTO models (alias, name, type, provider, base_url, ...)
   VALUES ('embed.default', 'OpenAI text-embedding-3-large', 'embedding', 'openai', ...);
   ```

3. **Обновить Tenant модель:**
   - Убрать `extra_embed_model` FK на старую таблицу
   - Добавить `embedding_model_alias` (String, FK на models.alias)

4. **Дроп старой таблицы `model_registry`** (после проверки).

## 🚀 Как использовать

### Добавить новую модель (через API)

```bash
POST /api/v1/models
{
  "alias": "llm.chat.gpt4",
  "name": "OpenAI GPT-4",
  "type": "llm_chat",
  "provider": "openai",
  "provider_model_name": "gpt-4-turbo",
  "base_url": "https://api.openai.com/v1",
  "api_key_ref": "env:OPENAI_API_KEY",
  "extra_config": {
    "temperature": 0.7,
    "max_tokens": 4096
  },
  "enabled": true,
  "default_for_type": false
}
```

### Использовать провайдеры в коде

```python
from app.providers.embedding_provider import get_embedding_provider

# Получить модель из БД
model = await models_repo.get_by_alias("embed.default")

# Создать провайдер
provider = get_embedding_provider(
    provider=model.provider,
    base_url=model.base_url,
    api_key=get_secret(model.api_key_ref),
    model=model.provider_model_name
)

# Использовать
embeddings = await provider.embed_texts(["hello", "world"])
```

### Reranker (локальный контейнер)

```python
from app.providers.rerank_provider import get_rerank_provider
from app.core.config import get_settings

settings = get_settings()

reranker = get_rerank_provider(
    provider="local",
    base_url=settings.RERANK_SERVICE_URL,
    model=settings.RERANK_MODEL
)

ranked = await reranker.rerank(
    query="machine learning basics",
    documents=search_results,
    top_k=10
)
```

## ✅ Преимущества новой архитектуры

1. **Гибкость:**
   - Легко добавить/удалить/изменить модель через API
   - Легко переключиться с OpenAI на Groq или локальные модели

2. **Чистота:**
   - Нет сканирования файловой системы
   - Нет manifest.json зоопарка
   - Один источник правды (БД)

3. **Масштабируемость:**
   - Разные тенанты могут использовать разные модели
   - Health checks отслеживают доступность
   - Легко добавить fallback модели

4. **Безопасность:**
   - API ключи не в БД напрямую (только ссылки)
   - Можно использовать Vault/AWS Secrets Manager

5. **Мониторинг:**
   - Health checks раз в 5 минут
   - Latency tracking
   - Status transitions

## 🔜 TODO (следующие шаги)

1. ✅ Создать новую модель Model
2. ✅ Создать провайдеры (Embedding, Reranker)
3. ✅ Обновить схемы
4. ✅ Добавить конфиг для локальных сервисов
5. ✅ Документировать LOCAL_SERVICES.md
6. ⏭️ Удалить scan логику из service/API
7. ⏭️ Обновить Tenant модель
8. ⏭️ Создать миграцию Alembic
9. ⏭️ Обновить API endpoints
10. ⏭️ Создать health check Celery task
11. ⏭️ Обновить RAG pipeline (использовать провайдеры)
12. ⏭️ Создать docker-compose для reranker контейнера

---

**Автор:** Cascade AI  
**Дата:** 2025-11-29  
**Ветка:** `refactor/model-registry-providers`
