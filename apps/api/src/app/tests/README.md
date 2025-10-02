# Тесты Backend приложения ML Portal

## Быстрый старт

### Запуск всех тестов
```bash
make test-backend
```

### Запуск только unit-тестов
```bash
make test-unit
```

### Запуск только интеграционных тестов
```bash
make test-integration
```

### Запуск функциональных тестов
```bash
make test-functional
```

## Структура тестов

```
tests/
├── conftest.py              # Глобальные фикстуры и конфигурация
├── pytest-unit.ini         # Конфигурация pytest для unit-тестов
├── unit/                    # Unit тесты (быстрые, изолированные)
│   ├── test_services.py     # Тесты сервисов
│   ├── test_repositories.py # Тесты репозиториев
│   ├── test_utils.py        # Тесты утилит
│   └── test_api/           # Тесты API endpoints
│       └── test_auth.py
├── integration/            # Интеграционные тесты
│   └── test_database.py
└── fixtures/               # Тестовые фикстуры
    └── database.py
```

## Типы тестов

### Unit тесты
- **Расположение**: `tests/unit/`
- **Характеристики**: Быстрые (< 1 сек), изолированные, используют моки
- **Запуск**: `make test-unit`

### Интеграционные тесты
- **Расположение**: `tests/integration/`
- **Характеристики**: Используют реальные внешние сервисы
- **Запуск**: `make test-integration`

### Функциональные тесты
- **Расположение**: `tests/functional/`
- **Характеристики**: End-to-end тесты с ML моделями
- **Запуск**: `make test-functional`

## Примеры тестов

### Unit тест сервиса
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

### Интеграционный тест БД
```python
@pytest.mark.integration
async def test_user_crud_operations(self, db_session, users_repo):
    """Тест CRUD операций с пользователями."""
    # Arrange
    user_data = {"email": "test@example.com", "username": "testuser"}
    
    # Act - Create
    created_user = await users_repo.create(user_data)
    
    # Assert
    assert created_user is not None
    assert created_user.email == user_data["email"]
```

## Фикстуры

### Глобальные фикстуры (conftest.py)
- `mock_db_session` - Мок для database session
- `mock_redis` - Мок для Redis клиента
- `mock_s3_client` - Мок для S3 клиента
- `sample_user_data` - Тестовые данные пользователя

### Фикстуры БД (fixtures/database.py)
- `test_db_session` - Реальная сессия БД для тестов
- `sample_user` - Тестовый пользователь
- `sample_chat` - Тестовый чат
- `clean_database` - Очистка БД перед тестом

## Покрытие кода

Требования к покрытию:
- **Unit тесты**: минимум 80%
- **Критические компоненты**: минимум 90%

Отчет о покрытии генерируется автоматически в `htmlcov/index.html`

## Маркеры тестов

```python
@pytest.mark.unit          # Unit тесты
@pytest.mark.integration   # Интеграционные тесты
@pytest.mark.slow          # Медленные тесты
@pytest.mark.e2e           # End-to-end тесты
```

## Отладка тестов

### Запуск конкретного теста
```bash
docker-compose -f docker-compose.test.yml run --rm backend-test pytest tests/unit/test_services.py::TestAuthService::test_authenticate_user_success -v -s
```

### Запуск с подробным выводом
```bash
docker-compose -f docker-compose.test.yml run --rm backend-test pytest tests/unit/ -v -s --tb=long
```

### Просмотр логов
```bash
docker-compose -f docker-compose.test.yml logs backend-test
```

## Лучшие практики

### ✅ DO (Делать)
- Использовать AAA pattern (Arrange-Act-Assert)
- Писать описательные имена тестов
- Группировать связанные тесты в классы
- Использовать фикстуры для общих данных
- Мокать внешние зависимости в unit-тестах

### ❌ DON'T (Не делать)
- Не использовать реальные внешние сервисы в unit-тестах
- Не оставлять тестовые данные в БД
- Не писать тесты без проверки результата
- Не дублировать логику приложения в тестах

## CI/CD

Тесты автоматически запускаются при:
- Push в main ветку
- Создании Pull Request
- Ручном запуске pipeline

Все тесты должны проходить перед мержем кода.
