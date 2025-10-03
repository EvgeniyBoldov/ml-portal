"""
Unit тесты для утилит.
"""
import pytest
from datetime import datetime, timedelta
"""
Unit тесты для утилит.
"""
import pytest
from datetime import datetime, timedelta
from app.core.security import verify_password, hash_password, create_access_token, create_refresh_token, decode_jwt
from app.utils.sse import sse_response
from app.utils.sse import sse_response


class TestSecurityUtils:
    """Unit тесты для утилит безопасности."""

    def test_password_hashing(self):
        """Тест хеширования пароля."""
        # Arrange
        password = "testpassword123"

        # Act
        hashed = hash_password(password)

        # Assert
        assert hashed != password
        assert len(hashed) > 0
        assert verify_password(password, hashed)

    def test_password_verification_success(self):
        """Тест успешной проверки пароля."""
        # Arrange
        password = "testpassword123"
        hashed = hash_password(password)

        # Act
        result = verify_password(password, hashed)

        # Assert
        assert result is True

    def test_password_verification_failure(self):
        """Тест неуспешной проверки пароля."""
        # Arrange
        password = "testpassword123"
        wrong_password = "wrongpassword"
        hashed = hash_password(password)

        # Act
        result = verify_password(wrong_password, hashed)

        # Assert
        assert result is False


class TestJWTUtils:
    """Unit тесты для JWT утилит."""

    def test_create_access_token(self):
        """Тест создания access токена."""
        # Arrange
        user_id = "test-user-id"
        email = "test@example.com"
        role = "user"
        tenant_ids = ["tenant-1"]
        scopes = ["read", "write"]

        # Act
        token = create_access_token(user_id, email, role, tenant_ids, scopes)

        # Assert
        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    def test_create_refresh_token(self):
        """Тест создания refresh токена."""
        # Arrange
        user_id = "test-user-id"

        # Act
        token = create_refresh_token(user_id)

        # Assert
        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    def test_decode_jwt_success(self):
        """Тест успешного декодирования токена."""
        # Arrange
        user_id = "test-user-id"
        email = "test@example.com"
        role = "user"
        tenant_ids = ["tenant-1"]
        scopes = ["read", "write"]
        token = create_access_token(user_id, email, role, tenant_ids, scopes)

        # Act
        result = decode_jwt(token)

        # Assert
        assert result is not None
        assert result["sub"] == user_id
        assert result["email"] == email
        assert result["role"] == role
        assert result["tenant_ids"] == tenant_ids
        assert result["scopes"] == scopes

    def test_decode_jwt_invalid(self):
        """Тест декодирования невалидного токена."""
        # Arrange
        invalid_token = "invalid.token.here"

        # Act & Assert
        with pytest.raises(Exception):  # JWT decode error
            decode_jwt(invalid_token)


class TestSSEUtils:
    """Unit тесты для SSE утилит."""

    def test_sse_response_creation(self):
        """Тест создания SSE response."""
        # Arrange
        async def mock_generator():
            yield b"data: test message\n\n"

        # Act
        response = sse_response(mock_generator())

        # Assert
        assert response is not None
        assert response.media_type == "text/event-stream"
        assert "Cache-Control" in response.headers
        assert response.headers["Cache-Control"] == "no-store"
