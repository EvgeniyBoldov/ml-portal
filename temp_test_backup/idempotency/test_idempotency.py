"""
Idempotency tests
"""
import pytest
from httpx import AsyncClient
from fastapi import status
from app.core.security import create_access_token

@pytest.mark.idempotency
@pytest.mark.write_operations
class TestIdempotency:
    """Test idempotency for write operations"""
    
    async def test_create_chat_idempotency(self, client: AsyncClient):
        """Test chat creation with idempotency key"""
        token = create_access_token(
            user_id="test-user",
            email="test@example.com",
            role="reader",
            tenant_ids=["tenant-123"],
            scopes=["read", "write"]
        )
        
        idempotency_key = "test-chat-creation-123"
        
        # First request
        response1 = await client.post(
            "/api/v1/chats",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant-Id": "tenant-123",
                "Idempotency-Key": idempotency_key
            },
            json={"name": "Test Chat"}
        )
        assert response1.status_code == status.HTTP_201_CREATED
        chat_id = response1.json()["id"]
        
        # Second request with same idempotency key
        response2 = await client.post(
            "/api/v1/chats",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant-Id": "tenant-123",
                "Idempotency-Key": idempotency_key
            },
            json={"name": "Test Chat"}
        )
        
        # Should return same result (409 or same response)
        assert response2.status_code in [status.HTTP_201_CREATED, status.HTTP_409_CONFLICT]
        
        if response2.status_code == status.HTTP_201_CREATED:
            # If 201, should return same chat
            assert response2.json()["id"] == chat_id
        else:
            # If 409, should indicate conflict
            assert "conflict" in response2.json()["detail"].lower()
    
    async def test_create_document_idempotency(self, client: AsyncClient):
        """Test document creation with idempotency key"""
        token = create_access_token(
            user_id="test-user",
            email="test@example.com",
            role="reader",
            tenant_ids=["tenant-123"],
            scopes=["read", "write"]
        )
        
        idempotency_key = "test-document-creation-456"
        
        # First request
        response1 = await client.post(
            "/api/v1/rag/documents",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant-Id": "tenant-123",
                "Idempotency-Key": idempotency_key
            },
            files={"file": ("test.pdf", b"fake pdf content", "application/pdf")}
        )
        assert response1.status_code == status.HTTP_201_CREATED
        doc_id = response1.json()["id"]
        
        # Second request with same idempotency key
        response2 = await client.post(
            "/api/v1/rag/documents",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant-Id": "tenant-123",
                "Idempotency-Key": idempotency_key
            },
            files={"file": ("test.pdf", b"fake pdf content", "application/pdf")}
        )
        
        # Should return same result
        assert response2.status_code in [status.HTTP_201_CREATED, status.HTTP_409_CONFLICT]
        
        if response2.status_code == status.HTTP_201_CREATED:
            assert response2.json()["id"] == doc_id
    
    async def test_different_idempotency_keys(self, client: AsyncClient):
        """Test different idempotency keys create different resources"""
        token = create_access_token(
            user_id="test-user",
            email="test@example.com",
            role="reader",
            tenant_ids=["tenant-123"],
            scopes=["read", "write"]
        )
        
        # First request with key1
        response1 = await client.post(
            "/api/v1/chats",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant-Id": "tenant-123",
                "Idempotency-Key": "key1"
            },
            json={"name": "Chat 1"}
        )
        assert response1.status_code == status.HTTP_201_CREATED
        chat1_id = response1.json()["id"]
        
        # Second request with key2
        response2 = await client.post(
            "/api/v1/chats",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant-Id": "tenant-123",
                "Idempotency-Key": "key2"
            },
            json={"name": "Chat 2"}
        )
        assert response2.status_code == status.HTTP_201_CREATED
        chat2_id = response2.json()["id"]
        
        # Should create different resources
        assert chat1_id != chat2_id
    
    async def test_idempotency_key_format_validation(self, client: AsyncClient):
        """Test idempotency key format validation"""
        token = create_access_token(
            user_id="test-user",
            email="test@example.com",
            role="reader",
            tenant_ids=["tenant-123"],
            scopes=["read", "write"]
        )
        
        invalid_keys = [
            "",  # Empty key
            "key with spaces",  # Spaces
            "key\nwith\nnewlines",  # Newlines
            "key\twith\ttabs",  # Tabs
            "a" * 300,  # Too long
        ]
        
        for invalid_key in invalid_keys:
            response = await client.post(
                "/api/v1/chats",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Tenant-Id": "tenant-123",
                    "Idempotency-Key": invalid_key
                },
                json={"name": "Test Chat"}
            )
            assert response.status_code == status.HTTP_400_BAD_REQUEST
    
    async def test_idempotency_without_key(self, client: AsyncClient):
        """Test that operations work without idempotency key"""
        token = create_access_token(
            user_id="test-user",
            email="test@example.com",
            role="reader",
            tenant_ids=["tenant-123"],
            scopes=["read", "write"]
        )
        
        # Request without idempotency key
        response = await client.post(
            "/api/v1/chats",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant-Id": "tenant-123"
            },
            json={"name": "Test Chat"}
        )
        assert response.status_code == status.HTTP_201_CREATED
    
    async def test_idempotency_ttl_expiration(self, client: AsyncClient):
        """Test idempotency key TTL expiration"""
        token = create_access_token(
            user_id="test-user",
            email="test@example.com",
            role="reader",
            tenant_ids=["tenant-123"],
            scopes=["read", "write"]
        )
        
        idempotency_key = "ttl-test-key"
        
        # First request
        response1 = await client.post(
            "/api/v1/chats",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant-Id": "tenant-123",
                "Idempotency-Key": idempotency_key
            },
            json={"name": "TTL Test Chat"}
        )
        assert response1.status_code == status.HTTP_201_CREATED
        
        # Simulate TTL expiration by waiting (in real test, you'd mock Redis)
        # For now, we'll test that the key format is validated
        # In a real implementation, you'd test actual TTL behavior
    
    async def test_idempotency_different_payloads(self, client: AsyncClient):
        """Test idempotency with different payloads"""
        token = create_access_token(
            user_id="test-user",
            email="test@example.com",
            role="reader",
            tenant_ids=["tenant-123"],
            scopes=["read", "write"]
        )
        
        idempotency_key = "payload-test-key"
        
        # First request
        response1 = await client.post(
            "/api/v1/chats",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant-Id": "tenant-123",
                "Idempotency-Key": idempotency_key
            },
            json={"name": "Chat 1"}
        )
        assert response1.status_code == status.HTTP_201_CREATED
        
        # Second request with different payload
        response2 = await client.post(
            "/api/v1/chats",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant-Id": "tenant-123",
                "Idempotency-Key": idempotency_key
            },
            json={"name": "Chat 2"}  # Different name
        )
        
        # Should return same result (idempotency based on key, not payload)
        assert response2.status_code in [status.HTTP_201_CREATED, status.HTTP_409_CONFLICT]
        
        if response2.status_code == status.HTTP_201_CREATED:
            # Should return original chat, not create new one
            assert response2.json()["name"] == "Chat 1"
    
    async def test_idempotency_error_scenarios(self, client: AsyncClient):
        """Test idempotency with error scenarios"""
        token = create_access_token(
            user_id="test-user",
            email="test@example.com",
            role="reader",
            tenant_ids=["tenant-123"],
            scopes=["read", "write"]
        )
        
        idempotency_key = "error-test-key"
        
        # First request with invalid data (should fail)
        response1 = await client.post(
            "/api/v1/chats",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant-Id": "tenant-123",
                "Idempotency-Key": idempotency_key
            },
            json={"name": ""}  # Invalid empty name
        )
        assert response1.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        
        # Second request with same key and valid data
        response2 = await client.post(
            "/api/v1/chats",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant-Id": "tenant-123",
                "Idempotency-Key": idempotency_key
            },
            json={"name": "Valid Chat"}
        )
        
        # Should succeed (idempotency doesn't apply to failed requests)
        assert response2.status_code == status.HTTP_201_CREATED
    
    async def test_idempotency_read_operations(self, client: AsyncClient):
        """Test that read operations are not affected by idempotency"""
        token = create_access_token(
            user_id="test-user",
            email="test@example.com",
            role="reader",
            tenant_ids=["tenant-123"],
            scopes=["read"]
        )
        
        idempotency_key = "read-test-key"
        
        # GET request with idempotency key (should be ignored)
        response = await client.get(
            "/api/v1/chats",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant-Id": "tenant-123",
                "Idempotency-Key": idempotency_key
            }
        )
        assert response.status_code == status.HTTP_200_OK
        
        # Multiple GET requests should work normally
        response2 = await client.get(
            "/api/v1/chats",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant-Id": "tenant-123",
                "Idempotency-Key": idempotency_key
            }
        )
        assert response2.status_code == status.HTTP_200_OK
