"""
Cursor-based pagination tests
"""
import pytest
from httpx import AsyncClient
from fastapi import status
from app.core.security import create_access_token

@pytest.mark.pagination
@pytest.mark.cursor
class TestCursorPagination:
    """Test cursor-based pagination"""
    
    async def test_basic_pagination(self, client: AsyncClient):
        """Test basic pagination functionality"""
        token = create_access_token(
            user_id="test-user",
            email="test@example.com",
            role="reader",
            tenant_ids=["tenant-123"],
            scopes=["read"]
        )
        
        # First page
        response = await client.get(
            "/api/v1/chats",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant-Id": "tenant-123"
            },
            params={"limit": 5}
        )
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        assert "items" in data
        assert "next_cursor" in data
        assert "prev_cursor" in data
        assert len(data["items"]) <= 5
        
        # If there are more items, next_cursor should be present
        if data["next_cursor"]:
            # Second page
            response2 = await client.get(
                "/api/v1/chats",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Tenant-Id": "tenant-123"
                },
                params={"limit": 5, "cursor": data["next_cursor"]}
            )
            assert response2.status_code == status.HTTP_200_OK
            
            data2 = response2.json()
            assert "items" in data2
            
            # No overlap between pages
            page1_ids = {item["id"] for item in data["items"]}
            page2_ids = {item["id"] for item in data2["items"]}
            assert len(page1_ids.intersection(page2_ids)) == 0
    
    async def test_pagination_stability(self, client: AsyncClient):
        """Test pagination stability - same cursor returns same results"""
        token = create_access_token(
            user_id="test-user",
            email="test@example.com",
            role="reader",
            tenant_ids=["tenant-123"],
            scopes=["read"]
        )
        
        # Get first page
        response1 = await client.get(
            "/api/v1/chats",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant-Id": "tenant-123"
            },
            params={"limit": 10}
        )
        assert response1.status_code == status.HTTP_200_OK
        
        cursor = response1.json()["next_cursor"]
        if cursor:
            # Request same page twice
            response2 = await client.get(
                "/api/v1/chats",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Tenant-Id": "tenant-123"
                },
                params={"limit": 10, "cursor": cursor}
            )
            assert response2.status_code == status.HTTP_200_OK
            
            response3 = await client.get(
                "/api/v1/chats",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Tenant-Id": "tenant-123"
                },
                params={"limit": 10, "cursor": cursor}
            )
            assert response3.status_code == status.HTTP_200_OK
            
            # Results should be identical
            items2 = response2.json()["items"]
            items3 = response3.json()["items"]
            assert len(items2) == len(items3)
            
            for item2, item3 in zip(items2, items3):
                assert item2["id"] == item3["id"]
    
    async def test_invalid_cursor(self, client: AsyncClient):
        """Test invalid cursor handling"""
        token = create_access_token(
            user_id="test-user",
            email="test@example.com",
            role="reader",
            tenant_ids=["tenant-123"],
            scopes=["read"]
        )
        
        invalid_cursors = [
            "invalid-cursor",
            "not-base64",
            "",
            "eyJpZCI6InRlc3QiLCJjcmVhdGVkX2F0IjoiMjAyMy0wMS0wMVQwMDowMDowMCJ9",  # Invalid format
        ]
        
        for cursor in invalid_cursors:
            response = await client.get(
                "/api/v1/chats",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Tenant-Id": "tenant-123"
                },
                params={"limit": 10, "cursor": cursor}
            )
            assert response.status_code == status.HTTP_400_BAD_REQUEST
    
    async def test_limit_validation(self, client: AsyncClient):
        """Test limit parameter validation"""
        token = create_access_token(
            user_id="test-user",
            email="test@example.com",
            role="reader",
            tenant_ids=["tenant-123"],
            scopes=["read"]
        )
        
        # Test limit too small
        response = await client.get(
            "/api/v1/chats",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant-Id": "tenant-123"
            },
            params={"limit": 0}
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        
        # Test limit too large
        response = await client.get(
            "/api/v1/chats",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant-Id": "tenant-123"
            },
            params={"limit": 1000}
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        
        # Test valid limit
        response = await client.get(
            "/api/v1/chats",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant-Id": "tenant-123"
            },
            params={"limit": 50}
        )
        assert response.status_code == status.HTTP_200_OK
    
    async def test_order_parameter(self, client: AsyncClient):
        """Test order parameter"""
        token = create_access_token(
            user_id="test-user",
            email="test@example.com",
            role="reader",
            tenant_ids=["tenant-123"],
            scopes=["read"]
        )
        
        # Test ascending order
        response_asc = await client.get(
            "/api/v1/chats",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant-Id": "tenant-123"
            },
            params={"limit": 10, "order": "asc"}
        )
        assert response_asc.status_code == status.HTTP_200_OK
        
        # Test descending order
        response_desc = await client.get(
            "/api/v1/chats",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant-Id": "tenant-123"
            },
            params={"limit": 10, "order": "desc"}
        )
        assert response_desc.status_code == status.HTTP_200_OK
        
        # Test invalid order
        response_invalid = await client.get(
            "/api/v1/chats",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant-Id": "tenant-123"
            },
            params={"limit": 10, "order": "invalid"}
        )
        assert response_invalid.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    async def test_empty_result_set(self, client: AsyncClient):
        """Test pagination with empty result set"""
        token = create_access_token(
            user_id="test-user",
            email="test@example.com",
            role="reader",
            tenant_ids=["empty-tenant"],
            scopes=["read"]
        )
        
        response = await client.get(
            "/api/v1/chats",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant-Id": "empty-tenant"
            },
            params={"limit": 10}
        )
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        assert data["items"] == []
        assert data["next_cursor"] is None
        assert data["prev_cursor"] is None
    
    async def test_pagination_with_filters(self, client: AsyncClient):
        """Test pagination with additional filters"""
        token = create_access_token(
            user_id="test-user",
            email="test@example.com",
            role="reader",
            tenant_ids=["tenant-123"],
            scopes=["read"]
        )
        
        # Test pagination with search query
        response = await client.get(
            "/api/v1/chats",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant-Id": "tenant-123"
            },
            params={"limit": 5, "q": "test"}
        )
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        assert "items" in data
        assert "next_cursor" in data
    
    async def test_backward_pagination(self, client: AsyncClient):
        """Test backward pagination (prev_cursor)"""
        token = create_access_token(
            user_id="test-user",
            email="test@example.com",
            role="reader",
            tenant_ids=["tenant-123"],
            scopes=["read"]
        )
        
        # Get first page
        response1 = await client.get(
            "/api/v1/chats",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant-Id": "tenant-123"
            },
            params={"limit": 5}
        )
        assert response1.status_code == status.HTTP_200_OK
        
        data1 = response1.json()
        if data1["next_cursor"]:
            # Get second page
            response2 = await client.get(
                "/api/v1/chats",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Tenant-Id": "tenant-123"
                },
                params={"limit": 5, "cursor": data1["next_cursor"]}
            )
            assert response2.status_code == status.HTTP_200_OK
            
            data2 = response2.json()
            if data2["prev_cursor"]:
                # Go back to first page using prev_cursor
                response3 = await client.get(
                    "/api/v1/chats",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "X-Tenant-Id": "tenant-123"
                    },
                    params={"limit": 5, "cursor": data2["prev_cursor"]}
                )
                assert response3.status_code == status.HTTP_200_OK
                
                # Should return to first page
                data3 = response3.json()
                assert len(data3["items"]) == len(data1["items"])
    
    async def test_pagination_performance(self, client: AsyncClient):
        """Test pagination performance with large datasets"""
        token = create_access_token(
            user_id="test-user",
            email="test@example.com",
            role="reader",
            tenant_ids=["tenant-123"],
            scopes=["read"]
        )
        
        import time
        
        # Test that pagination is fast even with large datasets
        start_time = time.time()
        
        response = await client.get(
            "/api/v1/chats",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant-Id": "tenant-123"
            },
            params={"limit": 100}
        )
        
        end_time = time.time()
        duration = end_time - start_time
        
        assert response.status_code == status.HTTP_200_OK
        assert duration < 1.0  # Should respond within 1 second
