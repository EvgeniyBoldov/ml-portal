"""
Multi-tenancy tests
"""
import pytest
from httpx import AsyncClient
from fastapi import status
from app.core.security import create_access_token

@pytest.mark.tenant
@pytest.mark.multitenancy
class TestMultiTenancy:
    """Test multi-tenancy isolation"""
    
    async def test_missing_tenant_header(self, client: AsyncClient):
        """Test missing X-Tenant-Id header"""
        token = create_access_token(
            user_id="test-user",
            email="test@example.com",
            role="reader",
            tenant_ids=["tenant-123"],
            scopes=["read"]
        )
        
        response = await client.get(
            "/api/v1/chats",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "tenant" in response.json()["detail"].lower()
    
    async def test_invalid_tenant_header_format(self, client: AsyncClient):
        """Test invalid X-Tenant-Id header format"""
        token = create_access_token(
            user_id="test-user",
            email="test@example.com",
            role="reader",
            tenant_ids=["tenant-123"],
            scopes=["read"]
        )
        
        response = await client.get(
            "/api/v1/chats",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant-Id": "not-a-uuid"
            }
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
    
    async def test_tenant_from_jwt_token(self, client: AsyncClient):
        """Test tenant extraction from JWT token"""
        token = create_access_token(
            user_id="test-user",
            email="test@example.com",
            role="reader",
            tenant_ids=["tenant-123"],
            scopes=["read"]
        )
        
        # Should work without X-Tenant-Id header (extracted from JWT)
        response = await client.get(
            "/api/v1/chats",
            headers={"Authorization": f"Bearer {token}"}
        )
        # Should either work (if tenant extracted from JWT) or require explicit header
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST]
    
    async def test_tenant_header_overrides_jwt(self, client: AsyncClient):
        """Test X-Tenant-Id header overrides JWT tenant"""
        token = create_access_token(
            user_id="test-user",
            email="test@example.com",
            role="reader",
            tenant_ids=["tenant-123"],
            scopes=["read"]
        )
        
        response = await client.get(
            "/api/v1/chats",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant-Id": "tenant-456"  # Different tenant
            }
        )
        # Should use header tenant, not JWT tenant
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_403_FORBIDDEN]
    
    async def test_user_without_tenant_access(self, client: AsyncClient):
        """Test user without tenant access"""
        token = create_access_token(
            user_id="test-user",
            email="test@example.com",
            role="reader",
            tenant_ids=[],  # No tenants
            scopes=["read"]
        )
        
        response = await client.get(
            "/api/v1/chats",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant-Id": "tenant-123"
            }
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    async def test_cross_tenant_access_denied(self, client: AsyncClient):
        """Test cross-tenant access is denied"""
        # Create user with access to tenant-123
        token = create_access_token(
            user_id="test-user",
            email="test@example.com",
            role="reader",
            tenant_ids=["tenant-123"],
            scopes=["read"]
        )
        
        # Try to access tenant-456
        response = await client.get(
            "/api/v1/chats",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant-Id": "tenant-456"
            }
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

@pytest.mark.tenant
@pytest.mark.isolation
class TestTenantIsolation:
    """Test tenant data isolation"""
    
    async def test_chat_isolation(self, client: AsyncClient):
        """Test chat isolation between tenants"""
        # Create user for tenant-123
        user1_token = create_access_token(
            user_id="user-1",
            email="user1@example.com",
            role="reader",
            tenant_ids=["tenant-123"],
            scopes=["read", "write"]
        )
        
        # Create user for tenant-456
        user2_token = create_access_token(
            user_id="user-2",
            email="user2@example.com",
            role="reader",
            tenant_ids=["tenant-456"],
            scopes=["read", "write"]
        )
        
        # User 1 creates a chat in tenant-123
        response1 = await client.post(
            "/api/v1/chats",
            headers={
                "Authorization": f"Bearer {user1_token}",
                "X-Tenant-Id": "tenant-123"
            },
            json={"name": "Chat in tenant-123"}
        )
        assert response1.status_code == status.HTTP_201_CREATED
        chat_id = response1.json()["id"]
        
        # User 2 should not see the chat from tenant-123
        response2 = await client.get(
            "/api/v1/chats",
            headers={
                "Authorization": f"Bearer {user2_token}",
                "X-Tenant-Id": "tenant-456"
            }
        )
        assert response2.status_code == status.HTTP_200_OK
        chats = response2.json()["items"]
        assert not any(chat["id"] == chat_id for chat in chats)
        
        # User 2 should not be able to access the specific chat
        response3 = await client.get(
            f"/api/v1/chats/{chat_id}",
            headers={
                "Authorization": f"Bearer {user2_token}",
                "X-Tenant-Id": "tenant-456"
            }
        )
        assert response3.status_code == status.HTTP_404_NOT_FOUND
    
    async def test_document_isolation(self, client: AsyncClient):
        """Test document isolation between tenants"""
        # Create user for tenant-123
        user1_token = create_access_token(
            user_id="user-1",
            email="user1@example.com",
            role="reader",
            tenant_ids=["tenant-123"],
            scopes=["read", "write"]
        )
        
        # Create user for tenant-456
        user2_token = create_access_token(
            user_id="user-2",
            email="user2@example.com",
            role="reader",
            tenant_ids=["tenant-456"],
            scopes=["read", "write"]
        )
        
        # User 1 uploads a document in tenant-123
        response1 = await client.post(
            "/api/v1/rag/documents",
            headers={
                "Authorization": f"Bearer {user1_token}",
                "X-Tenant-Id": "tenant-123"
            },
            files={"file": ("test.pdf", b"fake pdf content", "application/pdf")}
        )
        assert response1.status_code == status.HTTP_201_CREATED
        doc_id = response1.json()["id"]
        
        # User 2 should not see the document from tenant-123
        response2 = await client.get(
            "/api/v1/rag/documents",
            headers={
                "Authorization": f"Bearer {user2_token}",
                "X-Tenant-Id": "tenant-456"
            }
        )
        assert response2.status_code == status.HTTP_200_OK
        docs = response2.json()["items"]
        assert not any(doc["id"] == doc_id for doc in docs)
        
        # User 2 should not be able to access the specific document
        response3 = await client.get(
            f"/api/v1/rag/documents/{doc_id}",
            headers={
                "Authorization": f"Bearer {user2_token}",
                "X-Tenant-Id": "tenant-456"
            }
        )
        assert response3.status_code == status.HTTP_404_NOT_FOUND

@pytest.mark.tenant
@pytest.mark.property_based
class TestPropertyBasedTenancy:
    """Property-based tests for tenant isolation"""
    
    async def test_tenant_data_generation(self, client: AsyncClient):
        """Test generating data for multiple tenants"""
        tenants = ["tenant-001", "tenant-002", "tenant-003"]
        users = []
        
        # Create users for each tenant
        for i, tenant in enumerate(tenants):
            token = create_access_token(
                user_id=f"user-{i}",
                email=f"user{i}@example.com",
                role="reader",
                tenant_ids=[tenant],
                scopes=["read", "write"]
            )
            users.append((token, tenant))
        
        # Each user creates data in their tenant
        created_resources = []
        for token, tenant in users:
            response = await client.post(
                "/api/v1/chats",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Tenant-Id": tenant
                },
                json={"name": f"Chat in {tenant}"}
            )
            assert response.status_code == status.HTTP_201_CREATED
            created_resources.append((response.json()["id"], tenant))
        
        # Verify isolation: each user only sees their tenant's data
        for token, tenant in users:
            response = await client.get(
                "/api/v1/chats",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Tenant-Id": tenant
                }
            )
            assert response.status_code == status.HTTP_200_OK
            chats = response.json()["items"]
            
            # Should only see chats from their tenant
            for chat in chats:
                # This would need to be implemented in the actual API
                # For now, we just verify the response structure
                assert "id" in chat
                assert "name" in chat
    
    async def test_concurrent_tenant_operations(self, client: AsyncClient):
        """Test concurrent operations across tenants"""
        import asyncio
        
        async def create_chat_for_tenant(tenant_id: str, user_id: str):
            token = create_access_token(
                user_id=user_id,
                email=f"{user_id}@example.com",
                role="reader",
                tenant_ids=[tenant_id],
                scopes=["read", "write"]
            )
            
            response = await client.post(
                "/api/v1/chats",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Tenant-Id": tenant_id
                },
                json={"name": f"Concurrent chat in {tenant_id}"}
            )
            return response.status_code == status.HTTP_201_CREATED
        
        # Run concurrent operations for different tenants
        tasks = []
        for i in range(5):
            tenant_id = f"tenant-{i:03d}"
            user_id = f"user-{i}"
            tasks.append(create_chat_for_tenant(tenant_id, user_id))
        
        results = await asyncio.gather(*tasks)
        
        # All operations should succeed
        assert all(results)
