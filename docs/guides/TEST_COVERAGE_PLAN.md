# План полного покрытия тестами ML Portal

## 📋 Обзор

Этот документ содержит детальный план для достижения 100% покрытия тестами всех компонентов ML Portal. План структурирован по уровням тестирования и компонентам системы.

## 🎯 Цели покрытия

- **Unit тесты**: 90%+ покрытие кода
- **Integration тесты**: 100% покрытие API endpoints
- **E2E тесты**: 100% покрытие пользовательских сценариев
- **Performance тесты**: Критические операции

## 📊 Текущее состояние

### Unit тесты (79% успешности)
- ✅ **288 тестов проходят**
- ❌ **73 теста требуют исправлений**
- ⏭️ **4 теста пропускаются**

## 🏗️ Структура тестов

### 1. Unit тесты (`tests/unit/`)

#### 1.1 API Layer (`tests/unit/api/`)

**Статус**: Требует исправлений моков

**Файлы для исправления**:
- `test_admin_router.py` - 14 тестов (проблемы с моками)
- `test_chats_router.py` - 12 тестов (проблемы с моками)
- `test_password_reset_router.py` - ✅ Исправлен
- `test_rag_router.py` - ✅ Исправлен
- `test_analyze_router.py` - ✅ Исправлен
- `test_setup_router.py` - ✅ Исправлен

**Новые тесты для создания**:
- `test_auth_router.py` - аутентификация
- `test_users_router.py` - управление пользователями
- `test_health_router.py` - health checks

#### 1.2 Services Layer (`tests/unit/services/`)

**Статус**: Частично покрыт

**Существующие**:
- `test_users_service_enhanced.py` - ✅ Исправлен
- `test_rag_service_pagination.py` - ✅ Исправлен

**Новые тесты для создания**:
- `test_auth_service.py` - аутентификация
- `test_admin_service.py` - администрирование
- `test_chats_service.py` - чаты
- `test_analyze_service.py` - анализ документов
- `test_clients.py` - внешние клиенты (Qdrant, S3)
- `test_email_service.py` - отправка email
- `test_file_service.py` - работа с файлами

#### 1.3 Repositories Layer (`tests/unit/repositories/`)

**Статус**: Требует исправлений

**Существующие**:
- `test_base_repository.py` - ✅ Исправлен

**Новые тесты для создания**:
- `test_users_repo.py` - пользователи
- `test_chats_repo.py` - чаты
- `test_rag_repo.py` - RAG документы
- `test_analyze_repo.py` - анализ документов
- `test_tokens_repo.py` - токены
- `test_password_reset_repo.py` - сброс паролей

#### 1.4 Models Layer (`tests/unit/models/`)

**Статус**: Не покрыт

**Новые тесты для создания**:
- `test_user_models.py` - модели пользователей
- `test_chat_models.py` - модели чатов
- `test_rag_models.py` - модели RAG
- `test_analyze_models.py` - модели анализа
- `test_base_models.py` - базовые модели

#### 1.5 Core Layer (`tests/unit/core/`)

**Статус**: Не покрыт

**Новые тесты для создания**:
- `test_config.py` - конфигурация
- `test_database.py` - подключение к БД
- `test_cache.py` - кэширование
- `test_security.py` - безопасность
- `test_logging.py` - логирование

### 2. Integration тесты (`tests/integration/`)

**Статус**: Частично покрыт

**Существующие**:
- `test_auth_integration.py`
- `test_chats_integration.py`
- `test_rag_integration.py`

**Новые тесты для создания**:
- `test_admin_integration.py` - админ функции
- `test_analyze_integration.py` - анализ документов
- `test_file_upload_integration.py` - загрузка файлов
- `test_search_integration.py` - поиск
- `test_pagination_integration.py` - пагинация

### 3. E2E тесты (`tests/e2e/`)

**Статус**: Частично покрыт

**Существующие**:
- `test_auth_e2e.py`
- `test_chats_e2e.py`
- `test_rag_e2e.py`

**Новые тесты для создания**:
- `test_admin_e2e.py` - админ панель
- `test_analyze_e2e.py` - анализ документов
- `test_file_management_e2e.py` - управление файлами
- `test_search_e2e.py` - поиск
- `test_user_management_e2e.py` - управление пользователями

### 4. Performance тесты (`tests/performance/`)

**Статус**: Частично покрыт

**Существующие**:
- `test_api_performance.py`
- `test_db_performance.py` - ✅ Исправлен

**Новые тесты для создания**:
- `test_search_performance.py` - производительность поиска
- `test_file_upload_performance.py` - производительность загрузки
- `test_concurrent_users_performance.py` - одновременные пользователи

## 🔧 План исправлений существующих тестов

### Приоритет 1: Критические исправления

1. **Admin Router** (`test_admin_router.py`)
   - Проблема: Моки возвращают Mock объекты вместо реальных данных
   - Решение: Настроить моки для возврата правильных типов данных

2. **Chats Router** (`test_chats_router.py`)
   - Проблема: Аналогичные проблемы с моками
   - Решение: Исправить моки и assertions

3. **Base Repository** (`test_base_repository.py`)
   - Проблема: Моки не настроены правильно
   - Решение: Добавить правильные specs для моков

### Приоритет 2: Новые тесты

1. **Auth Service** - аутентификация и авторизация
2. **Admin Service** - администрирование
3. **Chats Service** - управление чатами
4. **Analyze Service** - анализ документов
5. **Clients** - внешние сервисы

## 📝 Шаблоны тестов

### Unit тест для API Router
```python
import pytest
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient

class TestRouterName:
    def setup_method(self):
        self.mock_service = Mock()
        self.mock_repo = Mock()
        
    @patch('app.api.routers.router_name.service')
    def test_endpoint_success(self, mock_service):
        # Arrange
        mock_service.method.return_value = expected_result
        
        # Act
        result = endpoint_function()
        
        # Assert
        assert result == expected_result
        mock_service.method.assert_called_once_with(expected_args)
```

### Unit тест для Service
```python
import pytest
from unittest.mock import Mock, patch

class TestServiceName:
    def setup_method(self):
        self.mock_repo = Mock()
        self.service = ServiceName(self.mock_repo)
        
    def test_method_success(self):
        # Arrange
        self.mock_repo.method.return_value = expected_result
        
        # Act
        result = self.service.method(input_data)
        
        # Assert
        assert result == expected_result
        self.mock_repo.method.assert_called_once_with(input_data)
```

### Unit тест для Repository
```python
import pytest
from unittest.mock import Mock, patch
from sqlalchemy.orm import Session

class TestRepositoryName:
    def setup_method(self):
        self.mock_db = Mock(spec=Session)
        self.repo = RepositoryName(self.mock_db)
        
    def test_method_success(self):
        # Arrange
        self.mock_db.query.return_value.filter.return_value.first.return_value = expected_result
        
        # Act
        result = self.repo.method(query_params)
        
        # Assert
        assert result == expected_result
        self.mock_db.query.assert_called_once()
```

## 🎯 Метрики успеха

### Unit тесты
- **Покрытие кода**: 90%+
- **Успешность**: 95%+
- **Время выполнения**: < 30 секунд

### Integration тесты
- **Покрытие API**: 100%
- **Успешность**: 90%+
- **Время выполнения**: < 5 минут

### E2E тесты
- **Покрытие сценариев**: 100%
- **Успешность**: 85%+
- **Время выполнения**: < 15 минут

## 🚀 Команды для запуска

```bash
# Unit тесты
make test-unit

# Integration тесты
make test-integration

# E2E тесты
make test-e2e

# Все тесты
make test-all

# Покрытие кода
make test-coverage
```

## 📋 Чек-лист для каждого теста

- [ ] Тест покрывает happy path
- [ ] Тест покрывает error cases
- [ ] Тест покрывает edge cases
- [ ] Моки настроены правильно
- [ ] Assertions проверяют правильные значения
- [ ] Тест изолирован (не зависит от других тестов)
- [ ] Тест детерминирован (дает одинаковый результат)
- [ ] Тест быстрый (< 1 секунды для unit тестов)

## 🔄 Процесс разработки тестов

1. **Анализ кода** - изучить что тестируем
2. **Создание теста** - написать тест по шаблону
3. **Запуск теста** - проверить что тест работает
4. **Исправление** - исправить проблемы если есть
5. **Рефакторинг** - улучшить тест если нужно
6. **Документирование** - добавить комментарии

## 📚 Дополнительные ресурсы

- [Pytest документация](https://docs.pytest.org/)
- [FastAPI тестирование](https://fastapi.tiangolo.com/tutorial/testing/)
- [SQLAlchemy тестирование](https://docs.sqlalchemy.org/en/14/orm/session_transaction.html#joining-a-session-into-an-external-transaction-such-as-for-test-suites)
- [Mock документация](https://docs.python.org/3/library/unittest.mock.html)

---

**Последнее обновление**: 2024-01-15
**Статус**: В разработке
**Ответственный**: AI Assistant
