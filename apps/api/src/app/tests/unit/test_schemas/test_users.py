"""
Unit тесты для схем пользователей.
"""
import pytest
from app.schemas.users import (
    UserCreate, UserUpdate, UserResponse, UserRole
)


class TestUserSchemas:
    """Unit тесты для схем пользователей."""

    def test_user_create(self):
        """Тест схемы UserCreate."""
        # Arrange
        user_data = {
            "email": "test@example.com",
            "password": "testpassword123",
            "role": UserRole.READER
        }

        # Act
        user_request = UserCreate(**user_data)

        # Assert
        assert user_request.email == "test@example.com"
        assert user_request.password == "testpassword123"
        assert user_request.role == UserRole.READER

    def test_user_update(self):
        """Тест схемы UserUpdate."""
        # Arrange
        update_data = {
            "email": "updated@example.com",
            "role": UserRole.EDITOR
        }

        # Act
        user_request = UserUpdate(**update_data)

        # Assert
        assert user_request.email == "updated@example.com"
        assert user_request.role == UserRole.EDITOR

    def test_user_response(self):
        """Тест схемы UserResponse."""
        # Arrange
        import uuid
        user_data = {
            "id": uuid.uuid4(),
            "email": "test@example.com",
            "role": UserRole.READER,
            "is_active": True,
            "created_at": "2024-01-01T00:00:00Z"
        }

        # Act
        user_response = UserResponse(**user_data)

        # Assert
        assert user_response.id == user_data["id"]
        assert user_response.email == "test@example.com"
        assert user_response.role == UserRole.READER
        assert user_response.is_active is True

    def test_user_role_enum(self):
        """Тест enum UserRole."""
        # Assert
        assert UserRole.ADMIN == "admin"
        assert UserRole.EDITOR == "editor"
        assert UserRole.READER == "reader"

    def test_user_create_with_defaults(self):
        """Тест схемы UserCreate с значениями по умолчанию."""
        # Arrange
        user_data = {
            "email": "test@example.com",
            "password": "testpassword123"
        }

        # Act
        user_request = UserCreate(**user_data)

        # Assert
        assert user_request.email == "test@example.com"
        assert user_request.password == "testpassword123"
        assert user_request.role == UserRole.READER  # Значение по умолчанию
        assert user_request.is_active is True  # Значение по умолчанию
