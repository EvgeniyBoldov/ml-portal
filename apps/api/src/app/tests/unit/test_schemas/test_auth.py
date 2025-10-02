"""
Unit тесты для схем аутентификации.
"""
import pytest
from app.schemas.auth import (
    AuthLoginRequest, AuthRefreshRequest, AuthTokensResponse,
    UserMeResponse, PasswordForgotRequest, PasswordResetRequest,
    PasswordResetResponse, PATTokenCreateRequest, PATTokenResponse,
    PATTokensListResponse
)


class TestAuthSchemas:
    """Unit тесты для схем аутентификации."""

    def test_auth_login_request(self):
        """Тест схемы AuthLoginRequest."""
        # Arrange
        login_data = {
            "email": "test@example.com",
            "password": "testpassword"
        }

        # Act
        login_request = AuthLoginRequest(**login_data)

        # Assert
        assert login_request.email == "test@example.com"
        assert login_request.password == "testpassword"

    def test_auth_refresh_request(self):
        """Тест схемы AuthRefreshRequest."""
        # Arrange
        refresh_data = {
            "refresh_token": "refresh_token_value"
        }

        # Act
        refresh_request = AuthRefreshRequest(**refresh_data)

        # Assert
        assert refresh_request.refresh_token == "refresh_token_value"

    def test_auth_tokens_response(self):
        """Тест схемы AuthTokensResponse."""
        # Arrange
        tokens_data = {
            "access_token": "access_token_value",
            "refresh_token": "refresh_token_value",
            "token_type": "bearer",
            "expires_in": 3600
        }

        # Act
        tokens_response = AuthTokensResponse(**tokens_data)

        # Assert
        assert tokens_response.access_token == "access_token_value"
        assert tokens_response.refresh_token == "refresh_token_value"
        assert tokens_response.token_type == "bearer"
        assert tokens_response.expires_in == 3600

    def test_user_me_response(self):
        """Тест схемы UserMeResponse."""
        # Arrange
        user_data = {
            "id": "test-user-id",
            "role": "user",
            "login": "testuser",
            "fio": "Test User"
        }

        # Act
        user_response = UserMeResponse(**user_data)

        # Assert
        assert user_response.id == "test-user-id"
        assert user_response.role == "user"
        assert user_response.login == "testuser"
        assert user_response.fio == "Test User"

    def test_password_forgot_request(self):
        """Тест схемы PasswordForgotRequest."""
        # Arrange
        forgot_data = {
            "email": "test@example.com"
        }

        # Act
        forgot_request = PasswordForgotRequest(**forgot_data)

        # Assert
        assert forgot_request.email == "test@example.com"

    def test_password_reset_request(self):
        """Тест схемы PasswordResetRequest."""
        # Arrange
        reset_data = {
            "token": "reset_token_value",
            "new_password": "newpassword123"
        }

        # Act
        reset_request = PasswordResetRequest(**reset_data)

        # Assert
        assert reset_request.token == "reset_token_value"
        assert reset_request.new_password == "newpassword123"

    def test_password_reset_response(self):
        """Тест схемы PasswordResetResponse."""
        # Arrange
        reset_response_data = {
            "message": "Password reset successfully"
        }

        # Act
        reset_response = PasswordResetResponse(**reset_response_data)

        # Assert
        assert reset_response.message == "Password reset successfully"

    def test_pat_token_create_request(self):
        """Тест схемы PATTokenCreateRequest."""
        # Arrange
        pat_data = {
            "name": "Test PAT Token",
            "expires_at": 1735689599  # Unix timestamp
        }

        # Act
        pat_request = PATTokenCreateRequest(**pat_data)

        # Assert
        assert pat_request.name == "Test PAT Token"
        assert pat_request.expires_at == 1735689599

    def test_pat_token_response(self):
        """Тест схемы PATTokenResponse."""
        # Arrange
        pat_response_data = {
            "id": "test-pat-id",
            "name": "Test PAT Token",
            "token": "pat_token_value",
            "token_mask": "pat_****_value",
            "expires_at": 1735689599,  # Unix timestamp
            "created_at": "2024-01-01T00:00:00Z",
            "is_active": True
        }

        # Act
        pat_response = PATTokenResponse(**pat_response_data)

        # Assert
        assert pat_response.id == "test-pat-id"
        assert pat_response.name == "Test PAT Token"
        assert pat_response.token == "pat_token_value"
        assert pat_response.token_mask == "pat_****_value"
        assert pat_response.expires_at == 1735689599
        assert pat_response.is_active is True

    def test_pat_tokens_list_response(self):
        """Тест схемы PATTokensListResponse."""
        # Arrange
        pat_tokens_data = {
            "tokens": [
                {
                    "id": "test-pat-id-1",
                    "name": "Test PAT Token 1",
                    "token_mask": "pat_****_1",
                    "expires_at": 1735689599,
                    "created_at": "2024-01-01T00:00:00Z",
                    "is_active": True
                },
                {
                    "id": "test-pat-id-2",
                    "name": "Test PAT Token 2",
                    "token_mask": "pat_****_2",
                    "expires_at": 1735689599,
                    "created_at": "2024-01-01T00:00:00Z",
                    "is_active": True
                }
            ]
        }

        # Act
        pat_tokens_response = PATTokensListResponse(**pat_tokens_data)

        # Assert
        assert len(pat_tokens_response.tokens) == 2
        assert pat_tokens_response.tokens[0].name == "Test PAT Token 1"
        assert pat_tokens_response.tokens[1].name == "Test PAT Token 2"
        assert pat_tokens_response.tokens[0].token_mask == "pat_****_1"
        assert pat_tokens_response.tokens[1].token_mask == "pat_****_2"
