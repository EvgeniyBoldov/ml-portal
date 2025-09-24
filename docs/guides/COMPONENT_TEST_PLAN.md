# Детальный план тестирования компонентов ML Portal

## 🎯 Цель

Этот документ содержит детальный план написания тестов для каждого компонента системы ML Portal. План структурирован так, чтобы можно было систематически покрыть все компоненты тестами.

## 📊 Статус покрытия

### ✅ Готовые компоненты (требуют только исправлений)
- **Analyze Router** - исправлен
- **RAG Router** - исправлен  
- **Setup Router** - исправлен
- **Password Reset Router** - исправлен
- **Users Service Enhanced** - исправлен
- **Base Repository** - исправлен

### 🔧 Требуют исправлений
- **Admin Router** (14 тестов)
- **Chats Router** (12 тестов)

### ❌ Не покрыты тестами

#### API Routers
- `auth_router.py` - аутентификация
- `users_router.py` - управление пользователями
- `health_router.py` - health checks

#### Services
- `auth_service.py` - аутентификация
- `admin_service.py` - администрирование
- `chats_service.py` - чаты
- `analyze_service.py` - анализ документов
- `clients.py` - внешние клиенты
- `email_service.py` - отправка email
- `file_service.py` - работа с файлами

#### Repositories
- `users_repo.py` - пользователи
- `chats_repo.py` - чаты
- `rag_repo.py` - RAG документы
- `analyze_repo.py` - анализ документов
- `tokens_repo.py` - токены
- `password_reset_repo.py` - сброс паролей

#### Models
- `user_models.py` - модели пользователей
- `chat_models.py` - модели чатов
- `rag_models.py` - модели RAG
- `analyze_models.py` - модели анализа
- `base_models.py` - базовые модели

#### Core
- `config.py` - конфигурация
- `database.py` - подключение к БД
- `cache.py` - кэширование
- `security.py` - безопасность
- `logging.py` - логирование

## 🏗️ План написания тестов

### Этап 1: Исправление существующих тестов

#### 1.1 Admin Router (`test_admin_router.py`)
**Проблемы**:
- Моки возвращают Mock объекты вместо реальных данных
- Неправильные assertions для Pydantic моделей

**Исправления**:
```python
# Вместо:
mock_user = Mock()
mock_user.id = "user123"

# Использовать:
mock_user = {
    "id": "user123",
    "login": "testuser",
    "email": "test@example.com",
    "role": "reader"
}
```

#### 1.2 Chats Router (`test_chats_router.py`)
**Проблемы**:
- Аналогичные проблемы с моками
- Неправильные async/await

**Исправления**:
- Настроить моки для возврата правильных типов
- Исправить async/await где нужно

### Этап 2: Новые API Router тесты

#### 2.1 Auth Router (`test_auth_router.py`)
**Тестируемые endpoints**:
- `POST /auth/login` - вход в систему
- `POST /auth/logout` - выход из системы
- `POST /auth/refresh` - обновление токена
- `GET /auth/me` - информация о текущем пользователе

**Тестовые случаи**:
- Успешный вход с правильными данными
- Ошибка при неправильных данных
- Ошибка при несуществующем пользователе
- Ошибка при заблокированном пользователе
- Успешный выход
- Успешное обновление токена
- Ошибка при невалидном токене

#### 2.2 Users Router (`test_users_router.py`)
**Тестируемые endpoints**:
- `GET /users/` - список пользователей
- `GET /users/{user_id}` - информация о пользователе
- `PUT /users/{user_id}` - обновление пользователя
- `DELETE /users/{user_id}` - удаление пользователя

**Тестовые случаи**:
- Получение списка пользователей
- Получение информации о пользователе
- Обновление пользователя
- Удаление пользователя
- Ошибки доступа
- Валидация данных

#### 2.3 Health Router (`test_health_router.py`)
**Тестируемые endpoints**:
- `GET /health` - проверка здоровья системы
- `GET /health/db` - проверка БД
- `GET /health/redis` - проверка Redis
- `GET /health/s3` - проверка S3

**Тестовые случаи**:
- Все сервисы работают
- БД недоступна
- Redis недоступен
- S3 недоступен

### Этап 3: Service тесты

#### 3.1 Auth Service (`test_auth_service.py`)
**Тестируемые методы**:
- `authenticate_user()` - аутентификация
- `create_access_token()` - создание токена
- `verify_token()` - проверка токена
- `refresh_token()` - обновление токена

**Тестовые случаи**:
- Успешная аутентификация
- Неправильный пароль
- Несуществующий пользователь
- Создание токена
- Проверка токена
- Обновление токена

#### 3.2 Admin Service (`test_admin_service.py`)
**Тестируемые методы**:
- `create_user()` - создание пользователя
- `update_user()` - обновление пользователя
- `delete_user()` - удаление пользователя
- `get_user_stats()` - статистика пользователя
- `search_users()` - поиск пользователей

**Тестовые случаи**:
- Создание пользователя
- Обновление пользователя
- Удаление пользователя
- Получение статистики
- Поиск пользователей
- Валидация данных

#### 3.3 Chats Service (`test_chats_service.py`)
**Тестируемые методы**:
- `create_chat()` - создание чата
- `get_chat()` - получение чата
- `update_chat()` - обновление чата
- `delete_chat()` - удаление чата
- `add_message()` - добавление сообщения
- `get_messages()` - получение сообщений

**Тестовые случаи**:
- Создание чата
- Получение чата
- Обновление чата
- Удаление чата
- Добавление сообщения
- Получение сообщений
- Пагинация сообщений

#### 3.4 Analyze Service (`test_analyze_service.py`)
**Тестируемые методы**:
- `upload_document()` - загрузка документа
- `process_document()` - обработка документа
- `get_document()` - получение документа
- `delete_document()` - удаление документа
- `search_documents()` - поиск документов

**Тестовые случаи**:
- Загрузка документа
- Обработка документа
- Получение документа
- Удаление документа
- Поиск документов
- Обработка ошибок

#### 3.5 Clients (`test_clients.py`)
**Тестируемые методы**:
- `qdrant_search()` - поиск в Qdrant
- `s3_upload()` - загрузка в S3
- `s3_download()` - скачивание из S3
- `s3_delete()` - удаление из S3

**Тестовые случаи**:
- Поиск в Qdrant
- Загрузка в S3
- Скачивание из S3
- Удаление из S3
- Обработка ошибок сети

### Этап 4: Repository тесты

#### 4.1 Users Repository (`test_users_repo.py`)
**Тестируемые методы**:
- `create()` - создание пользователя
- `get_by_id()` - получение по ID
- `get_by_login()` - получение по логину
- `get_by_email()` - получение по email
- `update()` - обновление
- `delete()` - удаление
- `search()` - поиск

**Тестовые случаи**:
- CRUD операции
- Поиск по различным полям
- Валидация данных
- Обработка ошибок БД

#### 4.2 Chats Repository (`test_chats_repo.py`)
**Тестируемые методы**:
- `create_chat()` - создание чата
- `get_chat()` - получение чата
- `update_chat()` - обновление чата
- `delete_chat()` - удаление чата
- `add_message()` - добавление сообщения
- `get_messages()` - получение сообщений

**Тестовые случаи**:
- CRUD операции для чатов
- CRUD операции для сообщений
- Пагинация
- Фильтрация

#### 4.3 RAG Repository (`test_rag_repo.py`)
**Тестируемые методы**:
- `create_document()` - создание документа
- `get_document()` - получение документа
- `update_document()` - обновление документа
- `delete_document()` - удаление документа
- `search_documents()` - поиск документов

**Тестовые случаи**:
- CRUD операции
- Поиск по тексту
- Поиск по тегам
- Пагинация

### Этап 5: Model тесты

#### 5.1 User Models (`test_user_models.py`)
**Тестируемые модели**:
- `User` - пользователь
- `UserCreate` - создание пользователя
- `UserUpdate` - обновление пользователя
- `UserResponse` - ответ с пользователем

**Тестовые случаи**:
- Валидация полей
- Преобразование типов
- Сериализация/десериализация
- Валидация email
- Валидация пароля

#### 5.2 Chat Models (`test_chat_models.py`)
**Тестируемые модели**:
- `Chat` - чат
- `Message` - сообщение
- `ChatCreate` - создание чата
- `MessageCreate` - создание сообщения

**Тестовые случаи**:
- Валидация полей
- Связи между моделями
- Валидация типов сообщений
- Валидация длины текста

### Этап 6: Core тесты

#### 6.1 Config (`test_config.py`)
**Тестируемые компоненты**:
- `Settings` - настройки
- `DatabaseSettings` - настройки БД
- `RedisSettings` - настройки Redis
- `S3Settings` - настройки S3

**Тестовые случаи**:
- Загрузка настроек из переменных окружения
- Валидация настроек
- Значения по умолчанию
- Обработка ошибок конфигурации

#### 6.2 Database (`test_database.py`)
**Тестируемые компоненты**:
- `get_db()` - получение сессии БД
- `init_db()` - инициализация БД
- `close_db()` - закрытие соединения

**Тестовые случаи**:
- Подключение к БД
- Создание сессии
- Закрытие соединения
- Обработка ошибок подключения

## 📋 Шаблоны тестов

### Шаблон для API Router
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
        
    @patch('app.api.routers.router_name.service')
    def test_endpoint_error(self, mock_service):
        # Arrange
        mock_service.method.side_effect = Exception("Error")
        
        # Act & Assert
        with pytest.raises(Exception):
            endpoint_function()
```

### Шаблон для Service
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
        
    def test_method_error(self):
        # Arrange
        self.mock_repo.method.side_effect = Exception("Error")
        
        # Act & Assert
        with pytest.raises(Exception):
            self.service.method(input_data)
```

### Шаблон для Repository
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
        
    def test_method_not_found(self):
        # Arrange
        self.mock_db.query.return_value.filter.return_value.first.return_value = None
        
        # Act
        result = self.repo.method(query_params)
        
        # Assert
        assert result is None
```

## 🎯 Приоритеты

### Высокий приоритет
1. Исправить Admin Router (14 тестов)
2. Исправить Chats Router (12 тестов)
3. Создать Auth Router тесты
4. Создать Users Router тесты

### Средний приоритет
1. Создать Service тесты
2. Создать Repository тесты
3. Создать Model тесты

### Низкий приоритет
1. Создать Core тесты
2. Создать Integration тесты
3. Создать E2E тесты

## 📊 Метрики успеха

- **Unit тесты**: 90%+ покрытие кода
- **Успешность тестов**: 95%+
- **Время выполнения**: < 30 секунд
- **Количество тестов**: 500+ unit тестов

---

**Последнее обновление**: 2024-01-15
**Статус**: Готов к реализации
**Ответственный**: AI Assistant
