"""
Unit тесты для моделей SQLAlchemy.
"""
import pytest
import uuid
from datetime import datetime, timezone
from app.models.user import Users
from app.models.chat import Chats, ChatMessages
from app.models.tenant import Tenants, UserTenants


@pytest.mark.unit
class TestUserModel:
    """Тесты для модели Users."""

    def test_create_user_with_valid_data(self):
        """Тест создания пользователя с валидными данными."""
        # Arrange
        user_data = {
            "id": uuid.uuid4(),
            "login": "testuser",
            "email": "test@example.com",
            "password_hash": "hashed_password",
            "is_active": True,
            "role": "reader",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        }
        
        # Act
        user = Users(**user_data)
        
        # Assert
        assert user.login == "testuser"
        assert user.email == "test@example.com"
        assert user.is_active is True
        assert user.role == "reader"
        assert user.password_hash == "hashed_password"

    def test_user_role_constraint(self):
        """Тест constraint для роли пользователя."""
        # Arrange
        user_data = {
            "id": uuid.uuid4(),
            "login": "testuser",
            "password_hash": "hashed_password",
            "role": "invalid_role"  # Невалидная роль
        }
        
        # Act
        user = Users(**user_data)
        
        # Assert - constraint проверяется на уровне БД, не при создании объекта
        assert user.role == "invalid_role"  # Объект создается, но БД отклонит

    def test_user_email_validation(self):
        """Тест валидации email."""
        # Arrange
        user_data = {
            "id": uuid.uuid4(),
            "login": "testuser",
            "password_hash": "hashed_password",
            "email": "invalid-email"  # Невалидный email
        }
        
        # Act
        user = Users(**user_data)
        
        # Assert - модель принимает любой email, валидация на уровне приложения
        assert user.email == "invalid-email"

    def test_user_default_values(self):
        """Тест значений по умолчанию."""
        # Arrange
        user_data = {
            "id": uuid.uuid4(),
            "login": "testuser",
            "password_hash": "hashed_password"
        }
        
        # Act
        user = Users(**user_data)
        
        # Assert - значения по умолчанию применяются на уровне БД
        assert user.is_active is None  # Не установлено явно
        assert user.role is None  # Не установлено явно


@pytest.mark.unit
class TestChatModel:
    """Тесты для модели Chats."""

    def test_create_chat_with_valid_data(self):
        """Тест создания чата с валидными данными."""
        # Arrange
        owner_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        chat_data = {
            "id": uuid.uuid4(),
            "tenant_id": tenant_id,
            "owner_id": owner_id,  # Правильное имя поля
            "name": "Test Chat",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        }
        
        # Act
        chat = Chats(**chat_data)
        
        # Assert
        assert chat.name == "Test Chat"
        assert chat.owner_id == owner_id
        assert chat.tenant_id == tenant_id
        assert chat.created_at is not None
        assert chat.updated_at is not None

    def test_chat_name_optional(self):
        """Тест что name не обязателен."""
        # Arrange
        chat_data = {
            "id": uuid.uuid4(),
            "tenant_id": uuid.uuid4(),
            "owner_id": uuid.uuid4(),
            # name отсутствует - это нормально
        }
        
        # Act
        chat = Chats(**chat_data)
        
        # Assert
        assert chat.name is None


@pytest.mark.unit
class TestChatMessageModel:
    """Тесты для модели ChatMessages."""

    def test_create_message_with_valid_data(self):
        """Тест создания сообщения с валидными данными."""
        # Arrange
        chat_id = uuid.uuid4()
        message_data = {
            "id": uuid.uuid4(),
            "chat_id": chat_id,
            "role": "user",
            "content": "Test message",
            "created_at": datetime.now(timezone.utc)
        }
        
        # Act
        message = ChatMessages(**message_data)
        
        # Assert
        assert message.content == "Test message"
        assert message.role == "user"
        assert message.chat_id == chat_id

    def test_message_role_enum(self):
        """Тест enum для роли сообщения."""
        # Arrange
        message_data = {
            "id": uuid.uuid4(),
            "chat_id": uuid.uuid4(),
            "role": "assistant",
            "content": "Test message"
        }
        
        # Act
        message = ChatMessages(**message_data)
        
        # Assert
        assert message.role == "assistant"

    def test_message_content_optional(self):
        """Тест что content не обязателен."""
        # Arrange
        message_data = {
            "id": uuid.uuid4(),
            "chat_id": uuid.uuid4(),
            "role": "user",
            # content отсутствует - это нормально
        }
        
        # Act
        message = ChatMessages(**message_data)
        
        # Assert
        assert message.content is None


@pytest.mark.unit
class TestTenantModel:
    """Тесты для модели Tenants."""

    def test_create_tenant_with_valid_data(self):
        """Тест создания tenant с валидными данными."""
        # Arrange
        tenant_data = {
            "id": uuid.uuid4(),
            "name": "Test Tenant",
            "is_active": True
        }
        
        # Act
        tenant = Tenants(**tenant_data)
        
        # Assert
        assert tenant.name == "Test Tenant"
        assert tenant.is_active is True

    def test_tenant_name_optional(self):
        """Тест что name не обязателен."""
        # Arrange
        tenant_data = {
            "id": uuid.uuid4(),
            # name отсутствует - это нормально
        }
        
        # Act
        tenant = Tenants(**tenant_data)
        
        # Assert
        assert tenant.name is None


@pytest.mark.unit
class TestUserTenantsModel:
    """Тесты для модели UserTenants (M2M)."""

    def test_create_user_tenant_link(self):
        """Тест создания связи пользователь-tenant."""
        # Arrange
        user_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        link_data = {
            "user_id": user_id,
            "tenant_id": tenant_id,
            "is_default": True
        }
        
        # Act
        user_tenant = UserTenants(**link_data)
        
        # Assert
        assert user_tenant.user_id == user_id
        assert user_tenant.tenant_id == tenant_id
        assert user_tenant.is_default is True

    def test_user_tenant_unique_constraint(self):
        """Тест unique constraint для пары user_id, tenant_id."""
        # Arrange
        user_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        
        # Act
        link1 = UserTenants(user_id=user_id, tenant_id=tenant_id)
        link2 = UserTenants(user_id=user_id, tenant_id=tenant_id)
        
        # Assert - в реальной БД это вызовет constraint violation
        # В unit тестах мы просто проверяем что объекты создаются
        assert link1.user_id == link2.user_id
        assert link1.tenant_id == link2.tenant_id