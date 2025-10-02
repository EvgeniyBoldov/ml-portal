# Руководство по тестированию ML Portal

## Обзор

Данный документ описывает стратегию тестирования backend приложения ML Portal, включая структуру тестов, критерии написания и способы запуска.

## Структура тестов

### Расположение тестов

```
apps/api/src/app/tests/
├── __init__.py
├── conftest.py                 # Глобальная конфигурация pytest
├── pytest-unit.ini            # Конфигурация для unit-тестов
├── unit/                       # Unit тесты
│   ├── __init__.py
│   ├── test_services.py       # Тесты сервисов
│   ├── test_repositories.py   # Тесты репозиториев
│   ├── test_utils.py          # Тесты утилит
│   ├── test_models.py         # Тесты моделей
│   ├── test_api/              # Тесты API endpoints
│   │   ├── __init__.py
│   │   ├── test_auth.py
│   │   ├── test_users.py
│   │   └── test_chats.py
│   └── test_adapters/         # Тесты адаптеров
│       ├── __init__.py
│       ├── test_s3_client.py
│       └── test_qdrant.py
├── integration/               # Интеграционные тесты
│   ├── __init__.py
│   ├── test_database.py
│   └── test_external_services.py
└── fixtures/                  # Тестовые фикстуры
    ├── __init__.py
    ├── database.py
    ├── users.py
    └── chats.py
```

### Типы тестов

#### 1. Unit тесты (`tests/unit/`)
- **Назначение**: Тестирование отдельных компонентов в изоляции
- **Характеристики**:
  - Быстрые (< 1 секунды на тест)
  - Изолированные (используют моки)
  - Не требуют внешних зависимостей
  - Покрывают бизнес-логику

#### 2. Интеграционные тесты (`tests/integration/`)
- **Назначение**: Тестирование взаимодействия между компонентами
- **Характеристики**:
  - Используют реальные внешние сервисы (БД, Redis, S3)
  - Запускаются в Docker контейнерах
  - Проверяют корректность интеграций

#### 3. Функциональные тесты (`tests/functional/`)
- **Назначение**: Тестирование полных пользовательских сценариев
- **Характеристики**:
  - Используют легкие ML модели
  - Проверяют end-to-end функциональность
  - Запускаются в отдельном контейнере

## Критерии написания тестов

### Общие принципы

1. **AAA Pattern (Arrange-Act-Assert)**:
   ```python
   def test_example():
       # Arrange - подготовка данных
       user_data = {"email": "test@example.com"}
       
       # Act - выполнение действия
       result = service.create_user(user_data)
       
       # Assert - проверка результата
       assert result.email == "test@example.com"
   ```

2. **Именование тестов**:
   - `test_<method_name>_<scenario>_<expected_result>`
   - Пример: `test_create_user_with_valid_data_returns_user_object`

3. **Один тест = одна проверка**:
   - Каждый тест должен проверять только один аспект функциональности

4. **Независимость тестов**:
   - Тесты не должны зависеть друг от друга
   - Каждый тест должен быть самодостаточным

### Unit тесты

#### Обязательные требования:
- ✅ Использовать моки для всех внешних зависимостей
- ✅ Покрывать все ветки кода (if/else, try/catch)
- ✅ Тестировать как успешные, так и ошибочные сценарии
- ✅ Проверять исключения и их типы
- ✅ Использовать фикстуры для общих данных

#### Пример unit-теста:
```python
@pytest.mark.asyncio
async def test_authenticate_user_success(self, auth_service, mock_db_session):
    """Тест успешной аутентификации пользователя."""
    # Arrange
    email = "test@example.com"
    password = "testpassword"
    mock_db_session.scalar.return_value = sample_user_data

    # Act
    result = await auth_service.authenticate_user(email, password)

    # Assert
    assert result is not None
    assert result["email"] == email
    mock_db_session.scalar.assert_called_once()
```

### Интеграционные тесты

#### Обязательные требования:
- ✅ Использовать реальные внешние сервисы
- ✅ Очищать данные после каждого теста
- ✅ Тестировать реальные сценарии использования
- ✅ Проверять производительность критических операций

## Запуск тестов

### Все тесты выполняются только в Docker контейнерах

#### 1. Unit тесты
```bash
# Запуск всех unit-тестов
make test-backend

# Запуск только unit-тестов (если добавить отдельную команду)
docker-compose -f docker-compose.test.yml run --rm backend-test pytest tests/unit/ -v
```

#### 2. Интеграционные тесты
```bash
# Запуск интеграционных тестов
docker-compose -f docker-compose.test.yml run --rm backend-test pytest tests/integration/ -v
```

#### 3. Функциональные тесты
```bash
# Запуск функциональных тестов с ML моделями
make test-functional
```

#### 4. Все тесты
```bash
# Запуск всех типов тестов
make test
```

### Конфигурация Docker Compose

Тесты монтируются в контейнер через volumes:

```yaml
backend-test:
  volumes:
    - ./apps/api/src/app:/app/app          # Исходный код
    - ./apps/api/src/app/tests:/app/tests  # Тесты
    - ./models:/app/models:ro              # ML модели (только чтение)
```

### Переменные окружения для тестов

```bash
# В .env.test
TESTING=true
DB_URL=postgresql://ml_portal_test:ml_portal_test_password@postgres-test:5432/ml_portal_test
REDIS_URL=redis://redis-test:6379
QDRANT_URL=http://qdrant-test:6333
S3_ENDPOINT=http://minio-test:9000
S3_ACCESS_KEY=testadmin
S3_SECRET_KEY=testadmin123
JWT_SECRET_KEY=test-secret-key
JWT_ALGORITHM=HS256
```

## Покрытие кода

### Требования к покрытию:
- **Unit тесты**: минимум 80% покрытия
- **Критические компоненты**: минимум 90% покрытия
  - Сервисы аутентификации
  - Сервисы безопасности
  - Основная бизнес-логика

### Генерация отчета о покрытии:
```bash
# HTML отчет будет доступен в htmlcov/index.html
make test-backend
```

## Маркеры тестов

```python
@pytest.mark.unit          # Unit тесты
@pytest.mark.integration   # Интеграционные тесты
@pytest.mark.slow          # Медленные тесты
@pytest.mark.e2e           # End-to-end тесты
```

## CI/CD интеграция

Тесты автоматически запускаются при:
- Push в main ветку
- Создании Pull Request
- Ручном запуске pipeline

## Лучшие практики

### DO (Делать):
- ✅ Писать тесты перед кодом (TDD)
- ✅ Использовать описательные имена тестов
- ✅ Группировать связанные тесты в классы
- ✅ Использовать фикстуры для общих данных
- ✅ Мокать внешние зависимости в unit-тестах
- ✅ Очищать данные после интеграционных тестов

### DON'T (Не делать):
- ❌ Не писать тесты после написания кода
- ❌ Не использовать реальные внешние сервисы в unit-тестах
- ❌ Не оставлять тестовые данные в БД
- ❌ Не писать тесты без проверки результата
- ❌ Не дублировать логику приложения в тестах

## Отладка тестов

### Локальная отладка:
```bash
# Запуск с подробным выводом
docker-compose -f docker-compose.test.yml run --rm backend-test pytest tests/unit/test_services.py::TestAuthService::test_authenticate_user_success -v -s

# Запуск с остановкой на первой ошибке
docker-compose -f docker-compose.test.yml run --rm backend-test pytest tests/unit/ -x -v
```

### Просмотр логов:
```bash
# Логи тестового контейнера
docker-compose -f docker-compose.test.yml logs backend-test
```

## Мониторинг качества

### Метрики качества:
- Покрытие кода: минимум 80%
- Время выполнения unit-тестов: < 30 секунд
- Время выполнения всех тестов: < 5 минут
- Количество тестов: минимум 1 тест на публичный метод

### Автоматические проверки:
- Линтеры: black, isort, ruff, mypy
- Безопасность: bandit
- Зависимости: safety

---

**Важно**: Все тесты должны проходить в CI/CD pipeline перед мержем кода в основную ветку.
