"""
Unit тесты для утилит.
"""
import pytest
from datetime import datetime, timedelta
from app.core.security import verify_password, hash_password, encode_jwt, decode_jwt
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

    def test_encode_jwt(self):
        """Тест кодирования JWT токена."""
        # Arrange
        payload = {"sub": "test@example.com", "user_id": 1}

        # Act
        token = encode_jwt(payload)

        # Assert
        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    def test_decode_jwt_success(self):
        """Тест успешного декодирования токена."""
        # Arrange
        payload = {"sub": "test@example.com", "user_id": 1}
        token = encode_jwt(payload)

        # Act
        result = decode_jwt(token)

        # Assert
        assert result is not None
        assert result["sub"] == "test@example.com"
        assert result["user_id"] == 1

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
