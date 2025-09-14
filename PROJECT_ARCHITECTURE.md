# ML Portal - Архитектура и Логика Работы
============================================================

## Общая Архитектура

ML Portal состоит из следующих компонентов:

### Контейнеры
- **API** (легкий) - HTTP API, аутентификация, координация
- **Worker** (тяжелый) - обработка документов, ML задачи
- **Embedding** - создание эмбеддингов
- **LLM** - генерация ответов
- **PostgreSQL** - основная БД
- **Redis** - кэш и брокер сообщений
- **Qdrant** - векторная БД
- **MinIO** - файловое хранилище

## Система Очередей Celery

### Очереди по приоритетам

#### Критический приоритет (priority=10)
- **chat_critical** - обработка сообщений чата
  - `app.tasks.chat.process_message`
  - `app.tasks.chat.generate_response`
  - Воркеры: 3-4 на тяжелых ВМ

#### Высокий приоритет (priority=8)
- **upload_high** - загрузка и нормализация файлов
  - `app.tasks.upload_watch.*`
  - `app.tasks.normalize.normalize`
  - `app.tasks.chunk.split`
  - Воркеры: 2-3 на тяжелых ВМ

#### Средний приоритет (priority=5)
- **analyze_medium** - анализ документов
  - `app.tasks.analyze.*`
  - Воркеры: 2-3 на тяжелых ВМ

- **ocr_medium** - OCR и извлечение таблиц
  - `app.tasks.ocr_tables.*`
  - Воркеры: 2-3 на тяжелых ВМ

#### Низкий приоритет (priority=2-1)
- **rag_low** - RAG индексация
  - `app.tasks.embed.*`
  - `app.tasks.index.*`
  - Воркеры: 1-2 на легкой ВМ

- **cleanup_low** - очистка
  - `app.tasks.delete.*`
  - Воркеры: 1 на легкой ВМ

## Распределение по ВМ

### Легкая ВМ (6 CPU, 43GB RAM, много HDD)
- API (1 контейнер)
- PostgreSQL, Redis, Qdrant, MinIO
- Worker-RAG (1 воркер) - только RAG задачи
- Frontend

### Тяжелые ВМ (12 CPU, 86GB RAM) - 2 ВМ
**На каждой ВМ:**
- Worker-Mixed (2 воркера) - чат + анализ
- Embedding (1 сервис)
- LLM (1 сервис)

## Потоки Данных

### 1. Загрузка документа
```
Frontend -> API -> MinIO
API -> upload_watch (upload_high) -> normalize (upload_high)
normalize -> chunk (upload_high) -> embed (rag_low)
embed -> index (rag_low) -> Qdrant
```

### 2. Анализ документа
```
Frontend -> API -> analyze (analyze_medium)
analyze -> ocr_tables (ocr_medium) -> результат
```

### 3. Чат с RAG
```
Frontend -> API -> process_message (chat_critical)
process_message -> RAG search -> generate_response (chat_critical)
generate_response -> LLM -> ответ
```

## Метрики и Мониторинг

### RAG метрики
- `rag_ingest_stage_duration_seconds` - время на стадии инжеста
- `rag_ingest_errors_total` - ошибки инжеста
- `rag_vectors_total` - общее количество векторов
- `rag_chunks_total` - общее количество чанков
- `rag_search_latency_seconds` - задержка поиска
- `rag_quality_mrr` - качество поиска (MRR@K)

### Чат метрики
- `chat_rag_usage_total` - использование RAG в чате
- `chat_rag_fallback_total` - fallback без RAG

## Конфигурация

### Переменные окружения
- `DATABASE_URL` - подключение к PostgreSQL
- `REDIS_URL` - подключение к Redis
- `QDRANT_URL` - подключение к Qdrant
- `S3_ENDPOINT` - MinIO endpoint
- `S3_BUCKET_RAG` - бакет для RAG документов
- `S3_BUCKET_ANALYSIS` - бакет для анализа

### Docker Compose файлы
- `docker-compose.local.yml` - для локальной разработки
- `docker-compose.prod.yml` - для продакшна (Docker Swarm)

## Команды Управления

### Локальная разработка
```bash
make build-local    # Собрать образы
make up-local       # Запустить стек
make down-local     # Остановить стек
make logs           # Показать логи
```

### Продакшн
```bash
make build-prod     # Собрать образы
make up-prod        # Запустить стек
make down-prod      # Остановить стек
```

### Генерация кода
```bash
make gen-backend    # Код бэкенда
make gen-frontend   # Код фронтенда
make gen-all        # Весь код
make gen-docs       # Документация
```

