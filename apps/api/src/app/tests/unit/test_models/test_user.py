"""
Unit тесты для модели User.
"""
import pytest
from datetime import datetime
from app.models.user import Users, UserTokens, UserRefreshTokens, PasswordResetTokens, AuditLogs


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

    def test_user_tokens_model_creation(self):
        """Тест создания модели UserTokens."""
        # Arrange
        import uuid
        token_data = {
            "id": uuid.uuid4(),
            "user_id": uuid.uuid4(),
            "token_hash": "hashed_token_value",
            "name": "Test Token",
            "scopes": ["read", "write"],
            "expires_at": datetime.now()
        }

        # Act
        token = UserTokens(**token_data)

        # Assert
        assert token.id == token_data["id"]
        assert token.user_id == token_data["user_id"]
        assert token.token_hash == "hashed_token_value"
        assert token.name == "Test Token"
        assert token.scopes == ["read", "write"]

    def test_user_refresh_tokens_model_creation(self):
        """Тест создания модели UserRefreshTokens."""
        # Arrange
        import uuid
        refresh_token_data = {
            "id": uuid.uuid4(),
            "user_id": uuid.uuid4(),
            "refresh_hash": "hashed_refresh_token_value",
            "expires_at": datetime.now(),
            "rotating": True,
            "revoked": False
        }

        # Act
        refresh_token = UserRefreshTokens(**refresh_token_data)

        # Assert
        assert refresh_token.id == refresh_token_data["id"]
        assert refresh_token.user_id == refresh_token_data["user_id"]
        assert refresh_token.refresh_hash == "hashed_refresh_token_value"
        assert refresh_token.rotating is True
        assert refresh_token.revoked is False

    def test_password_reset_tokens_model_creation(self):
        """Тест создания модели PasswordResetTokens."""
        # Arrange
        import uuid
        reset_token_data = {
            "id": uuid.uuid4(),
            "user_id": uuid.uuid4(),
            "token_hash": "hashed_reset_token_value",
            "expires_at": datetime.now()
        }

        # Act
        reset_token = PasswordResetTokens(**reset_token_data)

        # Assert
        assert reset_token.id == reset_token_data["id"]
        assert reset_token.user_id == reset_token_data["user_id"]
        assert reset_token.token_hash == "hashed_reset_token_value"

    def test_audit_logs_model_creation(self):
        """Тест создания модели AuditLogs."""
        # Arrange
        import uuid
        audit_data = {
            "id": uuid.uuid4(),
            "actor_user_id": uuid.uuid4(),
            "action": "login",
            "object_type": "user",
            "object_id": "test-user-id",
            "meta": {"ip": "127.0.0.1"},
            "ip": "127.0.0.1",
            "user_agent": "Mozilla/5.0"
        }

        # Act
        audit_log = AuditLogs(**audit_data)

        # Assert
        assert audit_log.id == audit_data["id"]
        assert audit_log.actor_user_id == audit_data["actor_user_id"]
        assert audit_log.action == "login"
        assert audit_log.object_type == "user"
        assert audit_log.object_id == "test-user-id"
        assert audit_log.meta == {"ip": "127.0.0.1"}
        assert audit_log.ip == "127.0.0.1"
        assert audit_log.user_agent == "Mozilla/5.0"
