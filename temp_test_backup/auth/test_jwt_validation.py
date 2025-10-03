"""
JWT validation tests
"""
import pytest
import jwt
import time
from httpx import AsyncClient
from fastapi import status
from app.core.security import create_access_token, create_refresh_token, decode_jwt

@pytest.mark.auth
@pytest.mark.jwt
class TestJWTValidation:
    """Test JWT token validation"""
    
    async def test_valid_jwt_token(self, client: AsyncClient):
        """Test valid JWT token"""
        # Create a valid token
        token = create_access_token(
            user_id="test-user-123",
            email="test@example.com",
            role="reader",
            tenant_ids=["tenant-123"],
            scopes=["read"]
        )
        
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == status.HTTP_200_OK
    
    async def test_expired_jwt_token(self, client: AsyncClient):
        """Test expired JWT token"""
        # Create an expired token
        expired_token = jwt.encode(
            {
                "sub": "test-user-123",
                "email": "test@example.com",
                "role": "reader",
                "tenant_ids": ["tenant-123"],
                "scopes": ["read"],
                "iss": "urn:app",
                "aud": "urn:app:api",
                "iat": int(time.time()) - 3600,  # 1 hour ago
                "exp": int(time.time()) - 1800,  # 30 minutes ago (expired)
                "jti": "test-jti",
                "type": "access"
            },
            "change-me",
            algorithm="HS256"
        )
        
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {expired_token}"}
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "expired" in response.json()["detail"].lower()
    
    async def test_future_jwt_token(self, client: AsyncClient):
        """Test JWT token with future nbf (not before)"""
        future_token = jwt.encode(
            {
                "sub": "test-user-123",
                "email": "test@example.com",
                "role": "reader",
                "tenant_ids": ["tenant-123"],
                "scopes": ["read"],
                "iss": "urn:app",
                "aud": "urn:app:api",
                "iat": int(time.time()),
                "exp": int(time.time()) + 3600,
                "nbf": int(time.time()) + 1800,  # Not valid for 30 minutes
                "jti": "test-jti",
                "type": "access"
            },
            "change-me",
            algorithm="HS256"
        )
        
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {future_token}"}
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    async def test_invalid_jwt_signature(self, client: AsyncClient):
        """Test JWT with invalid signature"""
        # Create token with wrong secret
        invalid_token = jwt.encode(
            {
                "sub": "test-user-123",
                "email": "test@example.com",
                "role": "reader",
                "tenant_ids": ["tenant-123"],
                "scopes": ["read"],
                "iss": "urn:app",
                "aud": "urn:app:api",
                "iat": int(time.time()),
                "exp": int(time.time()) + 3600,
                "jti": "test-jti",
                "type": "access"
            },
            "wrong-secret",
            algorithm="HS256"
        )
        
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {invalid_token}"}
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    async def test_wrong_issuer(self, client: AsyncClient):
        """Test JWT with wrong issuer"""
        wrong_issuer_token = jwt.encode(
            {
                "sub": "test-user-123",
                "email": "test@example.com",
                "role": "reader",
                "tenant_ids": ["tenant-123"],
                "scopes": ["read"],
                "iss": "wrong-issuer",
                "aud": "urn:app:api",
                "iat": int(time.time()),
                "exp": int(time.time()) + 3600,
                "jti": "test-jti",
                "type": "access"
            },
            "change-me",
            algorithm="HS256"
        )
        
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {wrong_issuer_token}"}
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    async def test_wrong_audience(self, client: AsyncClient):
        """Test JWT with wrong audience"""
        wrong_audience_token = jwt.encode(
            {
                "sub": "test-user-123",
                "email": "test@example.com",
                "role": "reader",
                "tenant_ids": ["tenant-123"],
                "scopes": ["read"],
                "iss": "urn:app",
                "aud": "wrong-audience",
                "iat": int(time.time()),
                "exp": int(time.time()) + 3600,
                "jti": "test-jti",
                "type": "access"
            },
            "change-me",
            algorithm="HS256"
        )
        
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {wrong_audience_token}"}
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    async def test_refresh_token_as_access_token(self, client: AsyncClient):
        """Test using refresh token as access token"""
        refresh_token = create_refresh_token("test-user-123")
        
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {refresh_token}"}
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "token type" in response.json()["detail"].lower()
    
    async def test_access_token_as_refresh_token(self, client: AsyncClient):
        """Test using access token as refresh token"""
        access_token = create_access_token(
            user_id="test-user-123",
            email="test@example.com",
            role="reader",
            tenant_ids=["tenant-123"],
            scopes=["read"]
        )
        
        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": access_token}
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    async def test_malformed_jwt_token(self, client: AsyncClient):
        """Test malformed JWT token"""
        malformed_tokens = [
            "not.a.jwt",
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",  # Missing parts
            "header.payload.signature.extra",  # Too many parts
            "invalid-token",
            ""
        ]
        
        for token in malformed_tokens:
            response = await client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {token}"}
            )
            assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    async def test_jwt_without_required_claims(self, client: AsyncClient):
        """Test JWT without required claims"""
        # Token without 'sub' claim
        no_sub_token = jwt.encode(
            {
                "email": "test@example.com",
                "role": "reader",
                "tenant_ids": ["tenant-123"],
                "scopes": ["read"],
                "iss": "urn:app",
                "aud": "urn:app:api",
                "iat": int(time.time()),
                "exp": int(time.time()) + 3600,
                "jti": "test-jti",
                "type": "access"
            },
            "change-me",
            algorithm="HS256"
        )
        
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {no_sub_token}"}
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

@pytest.mark.auth
@pytest.mark.rbac
class TestRBACValidation:
    """Test Role-Based Access Control"""
    
    async def test_reader_role_access(self, client: AsyncClient):
        """Test reader role has appropriate access"""
        reader_token = create_access_token(
            user_id="reader-user",
            email="reader@example.com",
            role="reader",
            tenant_ids=["tenant-123"],
            scopes=["read"]
        )
        
        # Reader should be able to access their own profile
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {reader_token}"}
        )
        assert response.status_code == status.HTTP_200_OK
        
        # Reader should NOT be able to access admin endpoints
        response = await client.get(
            "/api/v1/users",
            headers={"Authorization": f"Bearer {reader_token}"}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    async def test_admin_role_access(self, client: AsyncClient):
        """Test admin role has full access"""
        admin_token = create_access_token(
            user_id="admin-user",
            email="admin@example.com",
            role="admin",
            tenant_ids=["tenant-123"],
            scopes=["read", "write", "admin"]
        )
        
        # Admin should be able to access their profile
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == status.HTTP_200_OK
        
        # Admin should be able to access admin endpoints
        response = await client.get(
            "/api/v1/users",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == status.HTTP_200_OK
    
    async def test_insufficient_scopes(self, client: AsyncClient):
        """Test insufficient scopes"""
        limited_token = create_access_token(
            user_id="limited-user",
            email="limited@example.com",
            role="reader",
            tenant_ids=["tenant-123"],
            scopes=["read"]  # Missing 'write' scope
        )
        
        # Should not be able to create resources without write scope
        response = await client.post(
            "/api/v1/chats",
            headers={"Authorization": f"Bearer {limited_token}"},
            json={"name": "test chat"}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    async def test_no_scopes(self, client: AsyncClient):
        """Test token with no scopes"""
        no_scopes_token = create_access_token(
            user_id="no-scopes-user",
            email="noscopes@example.com",
            role="reader",
            tenant_ids=["tenant-123"],
            scopes=[]  # No scopes
        )
        
        # Should not be able to access protected resources
        response = await client.get(
            "/api/v1/chats",
            headers={"Authorization": f"Bearer {no_scopes_token}"}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
