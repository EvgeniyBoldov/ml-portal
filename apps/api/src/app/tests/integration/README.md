# Интеграционные тесты

Интеграционные тесты проверяют взаимодействие между различными компонентами системы с использованием реальных сервисов.

## Структура тестов

```
tests/integration/
├── conftest.py              # Конфигурация и фикстуры
├── test_database.py         # Тесты PostgreSQL
├── test_redis.py            # Тесты Redis
├── test_minio.py            # Тесты MinIO (S3)
├── test_qdrant.py           # Тесты Qdrant
├── test_api.py              # Тесты API endpoints
├── test_rag_system.py       # Тесты полного цикла RAG
└── pytest-integration.ini   # Конфигурация pytest
```

## Запуск тестов

### Все интеграционные тесты
```bash
make test-integration
```

### Отдельные компоненты
```bash
# База данных
make test-integration-database

# Redis
make test-integration-redis

# MinIO (S3)
make test-integration-minio

# Qdrant
make test-integration-qdrant

# API endpoints
make test-integration-api

# RAG система
make test-integration-rag
```

### Конкретный тест
```bash
docker-compose -f docker-compose.test.yml run --rm backend-test pytest tests/integration/test_database.py::TestDatabaseIntegration::test_user_crud_operations -v
```

## Тестовые сервисы

Интеграционные тесты используют реальные сервисы из `docker-compose.test.yml`:

- **PostgreSQL** (порт 5433) - тестовая база данных
- **Redis** (порт 6380) - кеширование и сессии
- **MinIO** (порт 9002) - S3-совместимое хранилище
- **Qdrant** (порт 6335) - векторная база данных

## Особенности

### Изоляция тестов
- Каждый тест использует отдельную транзакцию БД с откатом
- Redis очищается перед каждым тестом
- MinIO bucket'ы очищаются между тестами
- Qdrant коллекции создаются и удаляются для каждого теста

### Асинхронность
- Все тесты поддерживают `asyncio`
- Используется `asyncio_mode = auto`
- Конкурентные операции тестируются с `asyncio.gather()`

### Реальные данные
- Тесты работают с реальными файлами в S3
- Векторные эмбеддинги (моки для тестов)
- Реальные SQL запросы и транзакции
- Настоящие HTTP запросы к API

## Типы тестов

### Database Tests (`test_database.py`)
- CRUD операции с пользователями, чатами, RAG документами
- Транзакции и откаты
- Конкурентные операции
- Связи между таблицами

### Redis Tests (`test_redis.py`)
- Кеширование данных
- Управление сессиями
- Pub/Sub сообщения
- Rate limiting
- Распределенные блокировки

### MinIO Tests (`test_minio.py`)
- Загрузка/скачивание файлов
- Presigned URL'ы
- Метаданные файлов
- Batch операции
- Обработка ошибок

### Qdrant Tests (`test_qdrant.py`)
- Создание коллекций
- Векторные операции
- Поиск с фильтрами
- Batch операции
- RAG интеграция

### API Tests (`test_api.py`)
- Полный цикл аутентификации
- CRUD операции через API
- Обработка ошибок
- Конкурентные запросы

### RAG System Tests (`test_rag_system.py`)
- Загрузка документов в S3
- Извлечение и обработка текста
- Создание чанков
- Векторный поиск
- Полный пайплайн RAG

## Конфигурация

### pytest-integration.ini
```ini
[tool:pytest]
testpaths = tests/integration
asyncio_mode = auto
log_cli = true
log_cli_level = INFO
timeout = 300
```

### Фикстуры (conftest.py)
- `test_db_engine` - тестовая БД engine
- `db_session` - сессия БД с откатом транзакций
- `test_user` - тестовый пользователь
- `redis_client` - Redis клиент
- `minio_client` - MinIO клиент
- `qdrant_client` - Qdrant клиент
- `clean_*` - фикстуры очистки

## Отладка

### Логи
```bash
# С логами
docker-compose -f docker-compose.test.yml run --rm backend-test pytest tests/integration/test_database.py -v -s --log-cli-level=DEBUG
```

### Интерактивная отладка
```bash
# Запуск контейнера для отладки
docker-compose -f docker-compose.test.yml run --rm backend-test bash

# Внутри контейнера
pytest tests/integration/test_database.py::TestDatabaseIntegration::test_user_crud_operations -v -s
```

### Проверка сервисов
```bash
# PostgreSQL
docker-compose -f docker-compose.test.yml exec postgres-test psql -U ml_portal_test -d ml_portal_test

# Redis
docker-compose -f docker-compose.test.yml exec redis-test redis-cli

# MinIO
# Веб-интерфейс: http://localhost:9003 (testadmin/testadmin123)

# Qdrant
# API: http://localhost:6335
```

## Лучшие практики

1. **Изоляция**: Каждый тест должен быть независимым
2. **Очистка**: Всегда очищайте данные после тестов
3. **Реализм**: Используйте реальные данные и сценарии
4. **Производительность**: Тесты должны выполняться быстро
5. **Надежность**: Тесты должны быть стабильными и повторяемыми

## Расширение

Для добавления новых интеграционных тестов:

1. Создайте файл `test_*.py` в `tests/integration/`
2. Используйте маркер `@pytest.mark.integration`
3. Добавьте необходимые фикстуры в `conftest.py`
4. Обновите `Makefile` с новой командой
5. Добавьте документацию в этот README
