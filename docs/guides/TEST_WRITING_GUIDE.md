# Руководство по написанию тестов ML Portal

## 🎯 Цель

Этот документ содержит конкретные инструкции для написания тестов каждого компонента ML Portal. Используйте этот документ как пошаговое руководство.

## 📋 Чек-лист перед началом

- [ ] Изучить код компонента
- [ ] Понять интерфейсы и зависимости
- [ ] Определить тестовые случаи
- [ ] Создать тест файл
- [ ] Написать тесты по шаблону
- [ ] Запустить тесты
- [ ] Исправить ошибки
- [ ] Проверить покрытие

## 🏗️ Структура тестового файла

```python
import pytest
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

# Импорты для тестируемого компонента
from app.api.routers.router_name import router
from app.services.service_name import ServiceName
from app.repositories.repo_name import RepositoryName

class TestComponentName:
    """Тесты для ComponentName"""
    
    def setup_method(self):
        """Настройка перед каждым тестом"""
        # Инициализация моков
        self.mock_dependency = Mock()
        self.component = ComponentName(self.mock_dependency)
        
    def teardown_method(self):
        """Очистка после каждого теста"""
        # Очистка моков если нужно
        pass
        
    # Тесты для каждого метода
    def test_method_success(self):
        """Тест успешного выполнения метода"""
        pass
        
    def test_method_error(self):
        """Тест обработки ошибок"""
        pass
        
    def test_method_validation(self):
        """Тест валидации входных данных"""
        pass
```

## 🔧 Шаблоны для разных типов компонентов

### 1. API Router тесты

```python
import pytest
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient

class TestRouterName:
    def setup_method(self):
        self.client = TestClient(router)
        self.mock_service = Mock()
        
    @patch('app.api.routers.router_name.service')
    def test_get_endpoint_success(self, mock_service):
        """Тест успешного GET запроса"""
        # Arrange
        mock_service.get_items.return_value = [
            {"id": "1", "name": "test"}
        ]
        
        # Act
        response = self.client.get("/endpoint")
        
        # Assert
        assert response.status_code == 200
        assert response.json() == [
            {"id": "1", "name": "test"}
        ]
        mock_service.get_items.assert_called_once()
        
    @patch('app.api.routers.router_name.service')
    def test_post_endpoint_success(self, mock_service):
        """Тест успешного POST запроса"""
        # Arrange
        mock_service.create_item.return_value = {"id": "1", "name": "test"}
        data = {"name": "test"}
        
        # Act
        response = self.client.post("/endpoint", json=data)
        
        # Assert
        assert response.status_code == 201
        assert response.json()["id"] == "1"
        mock_service.create_item.assert_called_once_with(data)
        
    @patch('app.api.routers.router_name.service')
    def test_endpoint_not_found(self, mock_service):
        """Тест ошибки 404"""
        # Arrange
        mock_service.get_item.return_value = None
        
        # Act
        response = self.client.get("/endpoint/999")
        
        # Assert
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()
        
    @patch('app.api.routers.router_name.service')
    def test_endpoint_validation_error(self, mock_service):
        """Тест ошибки валидации"""
        # Arrange
        invalid_data = {"invalid_field": "value"}
        
        # Act
        response = self.client.post("/endpoint", json=invalid_data)
        
        # Assert
        assert response.status_code == 422
        assert "validation error" in response.json()["detail"].lower()
```

### 2. Service тесты

```python
import pytest
from unittest.mock import Mock, patch

class TestServiceName:
    def setup_method(self):
        self.mock_repo = Mock()
        self.mock_dependency = Mock()
        self.service = ServiceName(
            repo=self.mock_repo,
            dependency=self.mock_dependency
        )
        
    def test_create_item_success(self):
        """Тест успешного создания элемента"""
        # Arrange
        item_data = {"name": "test", "value": 123}
        expected_item = {"id": "1", "name": "test", "value": 123}
        self.mock_repo.create.return_value = expected_item
        
        # Act
        result = self.service.create_item(item_data)
        
        # Assert
        assert result == expected_item
        self.mock_repo.create.assert_called_once_with(item_data)
        
    def test_create_item_validation_error(self):
        """Тест ошибки валидации при создании"""
        # Arrange
        invalid_data = {"invalid_field": "value"}
        
        # Act & Assert
        with pytest.raises(ValueError, match="Invalid data"):
            self.service.create_item(invalid_data)
            
    def test_get_item_success(self):
        """Тест успешного получения элемента"""
        # Arrange
        item_id = "1"
        expected_item = {"id": "1", "name": "test"}
        self.mock_repo.get_by_id.return_value = expected_item
        
        # Act
        result = self.service.get_item(item_id)
        
        # Assert
        assert result == expected_item
        self.mock_repo.get_by_id.assert_called_once_with(item_id)
        
    def test_get_item_not_found(self):
        """Тест получения несуществующего элемента"""
        # Arrange
        item_id = "999"
        self.mock_repo.get_by_id.return_value = None
        
        # Act & Assert
        with pytest.raises(ValueError, match="Item not found"):
            self.service.get_item(item_id)
            
    def test_update_item_success(self):
        """Тест успешного обновления элемента"""
        # Arrange
        item_id = "1"
        update_data = {"name": "updated"}
        existing_item = {"id": "1", "name": "old"}
        updated_item = {"id": "1", "name": "updated"}
        
        self.mock_repo.get_by_id.return_value = existing_item
        self.mock_repo.update.return_value = updated_item
        
        # Act
        result = self.service.update_item(item_id, update_data)
        
        # Assert
        assert result == updated_item
        self.mock_repo.get_by_id.assert_called_once_with(item_id)
        self.mock_repo.update.assert_called_once_with(item_id, update_data)
        
    def test_delete_item_success(self):
        """Тест успешного удаления элемента"""
        # Arrange
        item_id = "1"
        self.mock_repo.delete.return_value = True
        
        # Act
        result = self.service.delete_item(item_id)
        
        # Assert
        assert result is True
        self.mock_repo.delete.assert_called_once_with(item_id)
```

### 3. Repository тесты

```python
import pytest
from unittest.mock import Mock, patch
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

class TestRepositoryName:
    def setup_method(self):
        self.mock_db = Mock(spec=Session)
        self.repo = RepositoryName(self.mock_db)
        
    def test_create_success(self):
        """Тест успешного создания записи"""
        # Arrange
        item_data = {"name": "test", "value": 123}
        mock_item = Mock()
        mock_item.id = "1"
        mock_item.name = "test"
        mock_item.value = 123
        
        self.mock_db.add.return_value = None
        self.mock_db.commit.return_value = None
        self.mock_db.refresh.return_value = None
        
        # Act
        result = self.repo.create(item_data)
        
        # Assert
        assert result is not None
        self.mock_db.add.assert_called_once()
        self.mock_db.commit.assert_called_once()
        self.mock_db.refresh.assert_called_once()
        
    def test_create_database_error(self):
        """Тест ошибки базы данных при создании"""
        # Arrange
        item_data = {"name": "test"}
        self.mock_db.add.side_effect = SQLAlchemyError("Database error")
        
        # Act & Assert
        with pytest.raises(SQLAlchemyError):
            self.repo.create(item_data)
            
    def test_get_by_id_success(self):
        """Тест успешного получения по ID"""
        # Arrange
        item_id = "1"
        mock_item = Mock()
        mock_item.id = "1"
        mock_item.name = "test"
        
        self.mock_db.query.return_value.filter.return_value.first.return_value = mock_item
        
        # Act
        result = self.repo.get_by_id(item_id)
        
        # Assert
        assert result == mock_item
        self.mock_db.query.assert_called_once()
        
    def test_get_by_id_not_found(self):
        """Тест получения несуществующей записи"""
        # Arrange
        item_id = "999"
        self.mock_db.query.return_value.filter.return_value.first.return_value = None
        
        # Act
        result = self.repo.get_by_id(item_id)
        
        # Assert
        assert result is None
        
    def test_update_success(self):
        """Тест успешного обновления"""
        # Arrange
        item_id = "1"
        update_data = {"name": "updated"}
        mock_item = Mock()
        mock_item.id = "1"
        mock_item.name = "updated"
        
        self.mock_db.query.return_value.filter.return_value.first.return_value = mock_item
        self.mock_db.commit.return_value = None
        
        # Act
        result = self.repo.update(item_id, update_data)
        
        # Assert
        assert result == mock_item
        self.mock_db.commit.assert_called_once()
        
    def test_delete_success(self):
        """Тест успешного удаления"""
        # Arrange
        item_id = "1"
        mock_item = Mock()
        
        self.mock_db.query.return_value.filter.return_value.first.return_value = mock_item
        self.mock_db.delete.return_value = None
        self.mock_db.commit.return_value = None
        
        # Act
        result = self.repo.delete(item_id)
        
        # Assert
        assert result is True
        self.mock_db.delete.assert_called_once_with(mock_item)
        self.mock_db.commit.assert_called_once()
```

### 4. Model тесты

```python
import pytest
from pydantic import ValidationError
from app.models.model_name import ModelName, ModelCreate, ModelUpdate

class TestModelName:
    def test_model_creation_success(self):
        """Тест успешного создания модели"""
        # Arrange
        data = {
            "name": "test",
            "value": 123,
            "email": "test@example.com"
        }
        
        # Act
        model = ModelName(**data)
        
        # Assert
        assert model.name == "test"
        assert model.value == 123
        assert model.email == "test@example.com"
        
    def test_model_validation_error(self):
        """Тест ошибки валидации"""
        # Arrange
        invalid_data = {
            "name": "",  # Пустое имя
            "value": -1,  # Отрицательное значение
            "email": "invalid-email"  # Невалидный email
        }
        
        # Act & Assert
        with pytest.raises(ValidationError):
            ModelName(**invalid_data)
            
    def test_model_create_schema(self):
        """Тест схемы создания"""
        # Arrange
        data = {
            "name": "test",
            "value": 123
        }
        
        # Act
        model_create = ModelCreate(**data)
        
        # Assert
        assert model_create.name == "test"
        assert model_create.value == 123
        
    def test_model_update_schema(self):
        """Тест схемы обновления"""
        # Arrange
        data = {
            "name": "updated"
        }
        
        # Act
        model_update = ModelUpdate(**data)
        
        # Assert
        assert model_update.name == "updated"
        assert model_update.value is None  # Необязательное поле
```

## 🎯 Конкретные инструкции по компонентам

### Auth Router (`test_auth_router.py`)

**Создать тесты для**:
- `POST /auth/login` - вход в систему
- `POST /auth/logout` - выход из системы  
- `POST /auth/refresh` - обновление токена
- `GET /auth/me` - информация о пользователе

**Тестовые случаи**:
```python
def test_login_success(self):
    """Успешный вход с правильными данными"""
    
def test_login_invalid_credentials(self):
    """Ошибка при неправильных данных"""
    
def test_login_user_not_found(self):
    """Ошибка при несуществующем пользователе"""
    
def test_logout_success(self):
    """Успешный выход"""
    
def test_refresh_token_success(self):
    """Успешное обновление токена"""
    
def test_refresh_token_invalid(self):
    """Ошибка при невалидном токене"""
    
def test_get_me_success(self):
    """Получение информации о пользователе"""
    
def test_get_me_unauthorized(self):
    """Ошибка при отсутствии авторизации"""
```

### Users Router (`test_users_router.py`)

**Создать тесты для**:
- `GET /users/` - список пользователей
- `GET /users/{user_id}` - информация о пользователе
- `PUT /users/{user_id}` - обновление пользователя
- `DELETE /users/{user_id}` - удаление пользователя

**Тестовые случаи**:
```python
def test_get_users_success(self):
    """Получение списка пользователей"""
    
def test_get_users_pagination(self):
    """Пагинация списка пользователей"""
    
def test_get_user_success(self):
    """Получение информации о пользователе"""
    
def test_get_user_not_found(self):
    """Пользователь не найден"""
    
def test_update_user_success(self):
    """Успешное обновление пользователя"""
    
def test_update_user_not_found(self):
    """Обновление несуществующего пользователя"""
    
def test_delete_user_success(self):
    """Успешное удаление пользователя"""
    
def test_delete_user_not_found(self):
    """Удаление несуществующего пользователя"""
```

### Auth Service (`test_auth_service.py`)

**Создать тесты для методов**:
- `authenticate_user(login, password)`
- `create_access_token(user_id)`
- `verify_token(token)`
- `refresh_token(refresh_token)`

**Тестовые случаи**:
```python
def test_authenticate_user_success(self):
    """Успешная аутентификация"""
    
def test_authenticate_user_invalid_password(self):
    """Неправильный пароль"""
    
def test_authenticate_user_not_found(self):
    """Пользователь не найден"""
    
def test_create_access_token_success(self):
    """Создание токена доступа"""
    
def test_verify_token_success(self):
    """Проверка валидного токена"""
    
def test_verify_token_invalid(self):
    """Проверка невалидного токена"""
    
def test_refresh_token_success(self):
    """Обновление токена"""
    
def test_refresh_token_invalid(self):
    """Обновление невалидного токена"""
```

## 🔍 Отладка тестов

### Частые проблемы и решения

1. **Mock не работает**
   ```python
   # Неправильно
   @patch('module.function')
   
   # Правильно
   @patch('app.module.function')
   ```

2. **Async функции**
   ```python
   # Неправильно
   result = await sync_function()
   
   # Правильно
   result = sync_function()
   ```

3. **Pydantic модели**
   ```python
   # Неправильно
   assert result.id == "1"
   
   # Правильно
   assert result["id"] == "1"  # Если возвращается dict
   ```

4. **Database моки**
   ```python
   # Правильно
   self.mock_db.query.return_value.filter.return_value.first.return_value = mock_item
   ```

## 📊 Проверка покрытия

```bash
# Запуск тестов с покрытием
pytest --cov=app tests/unit/

# Детальный отчет
pytest --cov=app --cov-report=html tests/unit/

# Проверка конкретного модуля
pytest --cov=app.api.routers.auth tests/unit/api/test_auth_router.py
```

## 🎯 Критерии готовности теста

- [ ] Тест покрывает happy path
- [ ] Тест покрывает error cases
- [ ] Тест покрывает edge cases
- [ ] Моки настроены правильно
- [ ] Assertions проверяют правильные значения
- [ ] Тест изолирован
- [ ] Тест детерминирован
- [ ] Тест быстрый (< 1 секунды)
- [ ] Тест читаемый и понятный
- [ ] Тест документирован

---

**Последнее обновление**: 2024-01-15
**Статус**: Готов к использованию
**Ответственный**: AI Assistant
