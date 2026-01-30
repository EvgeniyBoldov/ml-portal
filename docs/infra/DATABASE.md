# База данных

## PostgreSQL

### Версия
PostgreSQL 15 с расширениями:
- `uuid-ossp` — генерация UUID
- `pgvector` — векторный поиск (опционально)

### Подключение

```bash
# Через docker
docker compose exec postgres psql -U mlportal -d mlportal

# Напрямую
psql postgresql://mlportal:password@localhost:5432/mlportal
```

### Backup

```bash
# Создание бэкапа
docker compose exec postgres pg_dump -U mlportal mlportal > backup.sql

# Восстановление
docker compose exec -T postgres psql -U mlportal mlportal < backup.sql
```

## Миграции

### Alembic

```bash
# Применить все миграции
docker compose exec api alembic upgrade head

# Откатить одну
docker compose exec api alembic downgrade -1

# Создать новую миграцию
docker compose exec api alembic revision --autogenerate -m "description"

# Показать текущую версию
docker compose exec api alembic current

# История миграций
docker compose exec api alembic history
```

### При первом запуске

```bash
# 1. Запустить PostgreSQL
docker compose up -d postgres

# 2. Применить миграции
docker compose exec api alembic upgrade head

# 3. Создать суперюзера (см. SUPERUSER.md)
```

## Redis

### Использование
- Celery broker и backend
- SSE pub/sub
- Кэширование (опционально)

### Подключение

```bash
docker compose exec redis redis-cli
```

### Команды

```bash
# Проверка
PING

# Список ключей
KEYS *

# Очистка
FLUSHALL
```

## Qdrant

### Использование
Векторное хранилище для RAG.

### Коллекции
Создаются автоматически при первом upsert:
- `rag_{tenant_id}` — документы тенанта

### API

```bash
# Список коллекций
curl http://localhost:6333/collections

# Информация о коллекции
curl http://localhost:6333/collections/rag_<tenant_id>

# Удаление коллекции
curl -X DELETE http://localhost:6333/collections/rag_<tenant_id>
```

### Dashboard
http://localhost:6333/dashboard

## MinIO

### Использование
S3-совместимое хранилище для файлов.

### Buckets
- `rag` — загруженные документы и извлечённый текст
- `exports` — экспорты данных

### Console
http://localhost:9001

### CLI

```bash
# Установка mc
brew install minio/stable/mc

# Конфигурация
mc alias set local http://localhost:9000 minioadmin minioadmin

# Список buckets
mc ls local

# Создание bucket
mc mb local/rag

# Загрузка файла
mc cp file.pdf local/rag/

# Скачивание
mc cp local/rag/file.pdf ./
```

## Мониторинг

### PostgreSQL

```sql
-- Активные соединения
SELECT * FROM pg_stat_activity;

-- Размер БД
SELECT pg_size_pretty(pg_database_size('mlportal'));

-- Размер таблиц
SELECT relname, pg_size_pretty(pg_total_relation_size(relid))
FROM pg_catalog.pg_statio_user_tables
ORDER BY pg_total_relation_size(relid) DESC;
```

### Redis

```bash
# Информация
INFO

# Память
INFO memory

# Клиенты
CLIENT LIST
```

### Qdrant

```bash
# Метрики
curl http://localhost:6333/metrics
```

## Troubleshooting

### PostgreSQL не запускается

```bash
# Проверить логи
docker compose logs postgres

# Проверить права на volume
ls -la /var/lib/docker/volumes/mlportal_postgres_data
```

### Миграции не применяются

```bash
# Проверить текущую версию
docker compose exec api alembic current

# Проверить историю
docker compose exec api alembic history

# Сбросить и применить заново (ОСТОРОЖНО!)
docker compose exec api alembic downgrade base
docker compose exec api alembic upgrade head
```

### Redis переполнен

```bash
# Проверить память
docker compose exec redis redis-cli INFO memory

# Очистить (ОСТОРОЖНО!)
docker compose exec redis redis-cli FLUSHALL
```
