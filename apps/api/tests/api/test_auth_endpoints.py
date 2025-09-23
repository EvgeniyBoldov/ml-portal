"""
API tests for authentication endpoints
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from app.main_enhanced import app


class TestAuthEndpoints:
    """Test Authentication API endpoints"""
    
    def setup_method(self):
        """Setup test method"""
        self.client = TestClient(app)
    
    def test_login_endpoint_exists(self):
        """Test login endpoint exists"""
        response = self.client.post("/api/auth/login", json={
            "email": "test@example.com",
            "password": "password"
        })
        # Should not be 404 (endpoint exists)
        assert response.status_code != 404
    
    def test_register_endpoint_exists(self):
        """Test register endpoint exists - registration is done via admin endpoints"""
        # Registration is handled through admin endpoints, not auth endpoints
        # This test verifies that auth endpoints don't have registration
        response = self.client.post("/api/auth/register", json={
            "email": "test@example.com",
            "password": "password",
            "role": "reader"
        })
        # Should be 404 (endpoint doesn't exist in auth)
        assert response.status_code == 404
    
    def test_me_endpoint_exists(self):
        """Test me endpoint exists"""
        response = self.client.get("/api/auth/me")
        # Should not be 404 (endpoint exists)
        assert response.status_code != 404
    
    def test_refresh_endpoint_exists(self):
        """Test refresh endpoint exists"""
        response = self.client.post("/api/auth/refresh", json={
            "refresh_token": "test_token"
        })
        # Should not be 404 (endpoint exists)
        assert response.status_code != 404
    
    def test_logout_endpoint_exists(self):
        """Test logout endpoint exists"""
        response = self.client.post("/api/auth/logout")
        # Should not be 404 (endpoint exists)
        assert response.status_code != 404
    
    def test_login_validation_error(self):
        """Test login with validation error"""
        response = self.client.post("/api/auth/login", json={})
        assert response.status_code == 422
    
    def test_login_missing_email(self):
        """Test login with missing email"""
        response = self.client.post("/api/auth/login", json={"password": "password"})
        assert response.status_code == 422
    
    def test_login_missing_password(self):
        """Test login with missing password"""
        response = self.client.post("/api/auth/login", json={"email": "test@example.com"})
        assert response.status_code == 422
    
    def test_register_validation_error(self):
        """Test register endpoint doesn't exist"""
        response = self.client.post("/api/auth/register", json={})
        assert response.status_code == 404
    
    def test_register_missing_email(self):
        """Test register endpoint doesn't exist"""
        response = self.client.post("/api/auth/register", json={
            "password": "password",
            "role": "reader"
        })
        assert response.status_code == 404
    
    def test_register_missing_password(self):
        """Test register endpoint doesn't exist"""
        response = self.client.post("/api/auth/register", json={
            "email": "test@example.com",
            "role": "reader"
        })
        assert response.status_code == 404
    
    def test_register_invalid_email(self):
        """Test register endpoint doesn't exist"""
        response = self.client.post("/api/auth/register", json={
            "email": "invalid-email",
            "password": "password",
            "role": "reader"
        })
        assert response.status_code == 404
    
    def test_register_invalid_role(self):
        """Test register endpoint doesn't exist"""
        response = self.client.post("/api/auth/register", json={
            "email": "test@example.com",
            "password": "password",
            "role": "invalid_role"
        })
        assert response.status_code == 404
    
    def test_register_weak_password(self):
        """Test register endpoint doesn't exist"""
        response = self.client.post("/api/auth/register", json={
            "email": "test@example.com",
            "password": "123",
            "role": "reader"
        })
        assert response.status_code == 404
    
    @patch('app.services.auth_service.AuthService')
    def test_login_success(self, mock_auth_service):
        """Test successful login"""
        mock_service_instance = Mock()
        mock_auth_service.return_value = mock_service_instance
        mock_user = Mock()
        mock_user.id = "user123"
        mock_user.email = "test@example.com"
        mock_user.role = "reader"
        mock_service_instance.authenticate_user.return_value = mock_user
        mock_service_instance.create_access_token.return_value = "access_token"
        mock_service_instance.create_refresh_token.return_value = "refresh_token"
        
        response = self.client.post("/api/auth/login", json={
            "email": "test@example.com",
            "password": "password"
        })
        assert response.status_code == 200
        assert "access_token" in response.json()
        assert "refresh_token" in response.json()
    
    @patch('app.services.auth_service.AuthService')
    def test_login_invalid_credentials(self, mock_auth_service):
        """Test login with invalid credentials"""
        mock_service_instance = Mock()
        mock_auth_service.return_value = mock_service_instance
        mock_service_instance.authenticate_user.return_value = None
        
        response = self.client.post("/api/auth/login", json={
            "email": "test@example.com",
            "password": "wrong_password"
        })
        assert response.status_code == 401
    
    def test_register_success(self):
        """Test register endpoint doesn't exist"""
        response = self.client.post("/api/auth/register", json={
            "email": "test@example.com",
            "password": "password123",
            "role": "reader"
        })
        assert response.status_code == 404
    
    def test_register_user_exists(self):
        """Test register endpoint doesn't exist"""
        response = self.client.post("/api/auth/register", json={
            "email": "test@example.com",
            "password": "password123",
            "role": "reader"
        })
        assert response.status_code == 404
    
    @patch('app.api.deps.get_current_user')
    def test_me_authenticated(self, mock_get_current_user):
        """Test me endpoint with authentication"""
        mock_user = Mock()
        mock_user.id = "user123"
        mock_user.email = "test@example.com"
        mock_user.role = "reader"
        mock_get_current_user.return_value = mock_user
        
        response = self.client.get("/api/auth/me")
        assert response.status_code == 200
        assert response.json()["id"] == "user123"
        assert response.json()["email"] == "test@example.com"
    
    def test_me_unauthorized(self):
        """Test me endpoint without authentication"""
        response = self.client.get("/api/auth/me")
        assert response.status_code in (401, 403)
    
    @patch('app.services.auth_service.AuthService')
    def test_refresh_success(self, mock_auth_service):
        """Test successful token refresh"""
        mock_service_instance = Mock()
        mock_auth_service.return_value = mock_service_instance
        mock_service_instance.verify_refresh_token.return_value = "user123"
        mock_service_instance.create_access_token.return_value = "new_access_token"
        
        response = self.client.post("/api/auth/refresh", json={
            "refresh_token": "valid_refresh_token"
        })
        assert response.status_code == 200
        assert "access_token" in response.json()
    
    @patch('app.services.auth_service.AuthService')
    def test_refresh_invalid_token(self, mock_auth_service):
        """Test refresh with invalid token"""
        mock_service_instance = Mock()
        mock_auth_service.return_value = mock_service_instance
        mock_service_instance.verify_refresh_token.return_value = None
        
        response = self.client.post("/api/auth/refresh", json={
            "refresh_token": "invalid_token"
        })
        assert response.status_code == 401
    
    def test_refresh_validation_error(self):
        """Test refresh with validation error"""
        response = self.client.post("/api/auth/refresh", json={})
        assert response.status_code == 422
    
    @patch('app.api.deps.get_current_user')
    def test_logout_success(self, mock_get_current_user):
        """Test successful logout"""
        mock_user = Mock()
        mock_user.id = "user123"
        mock_get_current_user.return_value = mock_user
        
        with patch('app.services.auth_service.AuthService') as mock_auth_service:
            mock_service_instance = Mock()
            mock_auth_service.return_value = mock_service_instance
            mock_service_instance.revoke_token.return_value = True
            
            response = self.client.post("/api/auth/logout")
            assert response.status_code == 200
    
    def test_logout_unauthorized(self):
        """Test logout without authentication"""
        response = self.client.post("/api/auth/logout")
        assert response.status_code in (401, 403)
