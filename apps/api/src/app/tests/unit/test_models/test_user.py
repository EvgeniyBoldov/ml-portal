"""
Unit тесты для модели User.
"""
import pytest
from datetime import datetime
from app.models.user import Users


class TestUserModel:
    """Unit тесты для модели User."""

    def test_users_model_creation(self):
        """Тест создания модели Users."""
        # Arrange
        import uuid
        user_data = {
            "id": uuid.uuid4(),
            "login": "testuser",
            "email": "test@example.com",
            "password_hash": "hashed_password",
            "role": "reader",
            "is_active": True,
            "require_password_change": False
        }

        # Act
        user = Users(**user_data)

        # Assert
        assert user.id == user_data["id"]
        assert user.login == "testuser"
        assert user.email == "test@example.com"
        assert user.password_hash == "hashed_password"
        assert user.role == "reader"
        assert user.is_active is True
        assert user.require_password_change is False

