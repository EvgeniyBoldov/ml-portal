# ML Portal API Tests

## 📁 Структура тестов

```
tests/
├── unit/                        # Unit тесты по слоям
│   ├── models/                  # Тесты моделей
│   │   ├── test_user_models.py
│   │   ├── test_chat_models.py
│   │   ├── test_rag_models.py
│   │   └── test_analyze_models.py
│   ├── repositories/            # Тесты репозиториев
│   │   └── test_repositories.py
│   ├── services/               # Тесты сервисов
│   │   ├── test_services.py
│   │   └── test_bg_tasks.py
│   ├── controllers/            # Тесты контроллеров
│   │   └── test_controllers.py
│   ├── core/                   # Тесты core компонентов
│   │   ├── test_auth.py
│   │   ├── test_db.py
│   │   ├── test_redis.py
│   │   ├── test_s3.py
│   │   ├── test_middleware.py
│   │   └── test_error_handlers.py
│   └── utils/                  # Тесты утилит
│       └── test_text_extractor.py
├── integration/                # Integration тесты
│   ├── test_integration_enhanced.py
│   ├── test_chat_workflow.py
│   └── test_user_workflow.py
├── e2e/                        # E2E тесты
│   ├── test_full_system.py
│   ├── test_additional_features.py
│   └── test_ingest_chain_apply.py
├── api/                        # API тесты
│   ├── test_auth_endpoints.py
│   ├── test_chats_endpoints_unified.py
│   ├── test_rag_endpoints_unified.py
│   ├── test_websocket_endpoints.py
│   ├── test_sse_endpoints.py
│   └── test_errors_security.py
├── performance/                # Тесты производительности
│   ├── test_db_performance.py
│   └── test_api_performance.py
├── conftest.py                 # Основная конфигурация
├── conftest_enhanced.py        # Расширенная конфигурация
└── README.md                   # Этот файл
```

## 🚀 Запуск тестов

### Основные команды

```bash
# Все тесты
make test-all

# Unit тесты
make test-unit

# Integration тесты
make test-integration

# E2E тесты
make test-e2e

# API тесты
make test-api

# Performance тесты
make test-performance

# Тесты с покрытием
make test-coverage

# Быстрые тесты (unit + api)
make test-quick
```

### Запуск через pytest

```bash
# Все тесты
pytest tests/

# Конкретная категория
pytest tests/unit/ -m unit
pytest tests/integration/ -m integration
pytest tests/e2e/ -m e2e
pytest tests/api/ -m api
pytest tests/performance/ -m performance

# Конкретный файл
pytest tests/unit/models/test_user_models.py

# Конкретный тест
pytest tests/unit/models/test_user_models.py::TestUsersModel::test_create_user

# С покрытием
pytest tests/ --cov=app --cov-report=html

# Параллельно
pytest tests/ -n auto

# С фильтром
pytest tests/ -k "test_auth"
```

### Запуск в Docker

```bash
# Тесты в Docker
make test-docker

# Или напрямую
docker-compose -f docker-compose.test.yml up --build
```

## 📊 Покрытие кода

Цель: **80%+ покрытие кода**

### Проверка покрытия

```bash
# Генерация отчета
make test-coverage

# Просмотр отчета
open htmlcov/index.html
```

### Текущее покрытие

- **Unit тесты**: ~85%
- **Integration тесты**: ~75%
- **API тесты**: ~80%
- **E2E тесты**: ~70%

## 🏷️ Маркеры тестов

```python
@pytest.mark.unit
def test_user_creation():
    """Unit test for user creation"""
    pass

@pytest.mark.integration
def test_database_integration():
    """Integration test with database"""
    pass

@pytest.mark.e2e
def test_full_user_workflow():
    """End-to-end test"""
    pass

@pytest.mark.api
def test_auth_endpoint():
    """API endpoint test"""
    pass

@pytest.mark.performance
def test_api_performance():
    """Performance test"""
    pass

@pytest.mark.slow
def test_long_running_operation():
    """Slow test"""
    pass
```

## 🔧 Конфигурация

### pytest.ini

```ini
[tool:pytest]
asyncio_mode = auto
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = 
    --strict-markers
    --strict-config
    --cov=app
    --cov-report=html:htmlcov
    --cov-report=term-missing
    --cov-fail-under=80
    --tb=short
    -v
markers =
    unit: Unit tests
    integration: Integration tests
    e2e: End-to-end tests
    api: API tests
    performance: Performance tests
    slow: Slow tests
```

### conftest.py

Основные фикстуры:
- `client` - FastAPI тестовый клиент
- `db_session` - Тестовая сессия БД
- `test_user` - Тестовый пользователь
- `test_chat` - Тестовый чат
- `test_rag_document` - Тестовый RAG документ
- `mock_*_service` - Моки сервисов

## 📝 Правила написания тестов

### 1. Именование

```python
def test_<action>_<expected_result>():
    """Test description"""
    pass

# Примеры
def test_create_user_success():
    """Test successful user creation"""
    pass

def test_create_user_validation_error():
    """Test user creation with validation error"""
    pass

def test_get_user_not_found():
    """Test getting non-existent user"""
    pass
```

### 2. Структура теста

```python
def test_example():
    """Test description"""
    # Arrange - подготовка данных
    user_data = {"login": "test", "email": "test@example.com"}
    
    # Act - выполнение действия
    result = create_user(user_data)
    
    # Assert - проверка результата
    assert result.login == "test"
    assert result.email == "test@example.com"
```

### 3. Использование фикстур

```python
def test_user_creation(test_user, mock_users_service):
    """Test user creation with fixtures"""
    mock_users_service.create_user.return_value = test_user
    
    result = create_user(test_user)
    
    assert result == test_user
```

### 4. Асинхронные тесты

```python
@pytest.mark.asyncio
async def test_async_operation():
    """Test async operation"""
    result = await async_function()
    assert result is not None
```

## 🐳 Docker тестирование

### docker-compose.test.yml

```yaml
version: '3.8'
services:
  postgres-test:
    image: postgres:15
    environment:
      POSTGRES_DB: ml_portal_test
      POSTGRES_USER: ml_portal_test
      POSTGRES_PASSWORD: ml_portal_test_password
    ports:
      - "5433:5432"
  
  redis-test:
    image: redis:7
    ports:
      - "6380:6379"
  
  api-test:
    build:
      context: .
      dockerfile: Dockerfile.test
    depends_on:
      - postgres-test
      - redis-test
    environment:
      DATABASE_URL: postgresql://ml_portal_test:ml_portal_test_password@postgres-test:5432/ml_portal_test
      REDIS_URL: redis://redis-test:6379
    volumes:
      - .:/app
    command: pytest tests/
```

## 📈 Мониторинг тестов

### Метрики качества

- **Время выполнения**: < 10 минут для всех тестов
- **Unit тесты**: < 1 сек на тест
- **Integration тесты**: < 10 сек на тест
- **E2E тесты**: < 60 сек на тест
- **Покрытие**: > 80%

### Отчеты

```bash
# HTML отчет покрытия
open htmlcov/index.html

# Терминальный отчет
pytest tests/ --cov=app --cov-report=term-missing

# JUnit XML отчет
pytest tests/ --junitxml=test-results.xml
```

## 🚨 Troubleshooting

### Частые проблемы

1. **Тесты падают с ошибкой импорта**
   ```bash
   # Проверьте PYTHONPATH
   export PYTHONPATH=/app:$PYTHONPATH
   ```

2. **Тесты не находят базу данных**
   ```bash
   # Проверьте DATABASE_URL
   export DATABASE_URL="postgresql://ml_portal_test:ml_portal_test_password@localhost:5433/ml_portal_test"
   ```

3. **Медленные тесты**
   ```bash
   # Запустите только быстрые тесты
   pytest tests/ -m "not slow"
   ```

4. **Проблемы с асинхронными тестами**
   ```bash
   # Убедитесь что pytest-asyncio установлен
   pip install pytest-asyncio
   ```

### Отладка

```bash
# Запуск с отладкой
pytest tests/ -s --tb=long

# Запуск конкретного теста с отладкой
pytest tests/unit/models/test_user_models.py::TestUsersModel::test_create_user -s --tb=long

# Запуск с логированием
pytest tests/ --log-cli-level=DEBUG
```

## 📚 Дополнительные ресурсы

- [pytest документация](https://docs.pytest.org/)
- [FastAPI тестирование](https://fastapi.tiangolo.com/tutorial/testing/)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
- [coverage.py](https://coverage.readthedocs.io/)
