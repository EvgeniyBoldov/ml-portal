# Новая система эмбеддингов

Реализация диспетчера эмбеддингов и сервисов согласно ТЗ.

## Архитектура

### Компоненты

1. **Model Registry** (`app/core/model_registry.py`) - реестр моделей в Redis
2. **Embedding Dispatcher** (`app/services/embedding_dispatcher.py`) - маршрутизатор задач
3. **Embedding Worker** (`app/tasks/embedding_worker.py`) - воркер для конкретной модели
4. **Интеграция** - обновленный `clients.py` с fallback на HTTP

### Очереди

- `embed.dispatch` - входная очередь диспетчера
- `embed.<alias>.rt` - RT очереди для каждой модели
- `embed.<alias>.bulk` - BULK очереди для каждой модели

## Конфигурация

### Переменные окружения

```bash
# Модели (формат: alias:model_id:rev:dim:max_seq)
EMB_MODELS="minilm:sentence-transformers/all-MiniLM-L6-v2:default:384:256"

# Дефолтные модели для профилей
EMB_DEFAULT_RT_MODELS="minilm"
EMB_DEFAULT_BULK_MODELS="minilm"

# MinIO настройки
MODELS_BUCKET=models
MODELS_CACHE_DIR=/models-cache
S3_ENDPOINT=http://minio:9000
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin

# Настройки воркера
EMB_MODEL_ID=sentence-transformers/all-MiniLM-L6-v2
EMB_MODEL_ALIAS=minilm
EMB_MODEL_REV=default
EMB_DIM=384
EMB_MAX_SEQ=256
EMB_DEVICE=cpu
```

## Запуск

### 1. Инициализация MinIO

```bash
# Создать бакет для моделей
python backend/scripts/bootstrap_models_bucket.py
```

### 2. Запуск системы

```bash
# Запуск всех сервисов
docker-compose -f docker-compose.local.yml up --build

# Или только embedding worker
docker-compose -f docker-compose.local.yml up embedding-worker
```

### 3. Тестирование

```bash
# Тест системы эмбеддингов
python backend/scripts/test_embedding_system.py
```

## Использование

### В коде

```python
from app.services.clients import embed_texts

# RT профиль (быстрый)
vectors = embed_texts(["Hello world"], profile="rt")

# BULK профиль (массовый)
vectors = embed_texts(["Hello world"], profile="bulk")

# С указанием моделей
vectors = embed_texts(["Hello world"], models=["minilm"])
```

### API

Система прозрачно интегрирована в существующий API. Все вызовы `embed_texts()` автоматически используют новую систему с fallback на старый HTTP API.

## Мониторинг

### Health Check

```bash
# Проверка здоровья воркера
curl http://localhost:8001/health
```

### Логи

```bash
# Логи embedding worker
docker-compose -f docker-compose.local.yml logs embedding-worker

# Логи всех сервисов
docker-compose -f docker-compose.local.yml logs
```

## Добавление новой модели

### 1. Обновить переменные окружения

```bash
EMB_MODELS="minilm:sentence-transformers/all-MiniLM-L6-v2:default:384:256,newmodel:sentence-transformers/all-mpnet-base-v2:abc123:768:512"
```

### 2. Добавить воркер в docker-compose

```yaml
embedding-worker-newmodel:
  # ... аналогично embedding-worker
  environment:
    - EMB_MODEL_ALIAS=newmodel
    - EMB_MODEL_ID=sentence-transformers/all-mpnet-base-v2
    # ...
```

### 3. Обновить очереди в celery_app.py

```python
Queue('embed.newmodel.rt', routing_key='embed.newmodel.rt', priority=8),
Queue('embed.newmodel.bulk', routing_key='embed.newmodel.bulk', priority=3),
```

## Преимущества

1. **Масштабируемость** - каждая модель в отдельном воркере
2. **Кэширование** - модели загружаются из MinIO в общий том
3. **Профили** - RT и BULK очереди с разными настройками
4. **Fallback** - автоматический откат на HTTP API
5. **Простота** - конфигурация через переменные окружения

## Ограничения

1. **Только CPU** - для GPU нужно обновить Dockerfile
2. **Простая модель** - только sentence-transformers
3. **Нет проверки checksums** - пока только базовая валидация
4. **Нет метрик** - можно добавить Prometheus метрики

## Планы развития

1. Добавить поддержку GPU
2. Реализовать проверку checksums
3. Добавить метрики Prometheus
4. Создать админку для управления моделями
5. Добавить поддержку LLM воркеров
