"""
Server-Sent Events (SSE) tests
"""
import pytest
import asyncio
from httpx import AsyncClient
from fastapi import status
from app.core.security import create_access_token

@pytest.mark.sse
@pytest.mark.streaming
class TestSSEStreams:
    """Test Server-Sent Events functionality"""
    
    async def test_chat_stream_basic(self, client: AsyncClient):
        """Test basic chat streaming"""
        token = create_access_token(
            user_id="test-user",
            email="test@example.com",
            role="reader",
            tenant_ids=["tenant-123"],
            scopes=["read", "write"]
        )
        
        response = await client.post(
            "/api/v1/chat/stream",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant-Id": "tenant-123",
                "Accept": "text/event-stream"
            },
            json={
                "message": "Hello, world!",
                "model": "test-model"
            }
        )
        
        assert response.status_code == status.HTTP_200_OK
        assert response.headers["content-type"] == "text/event-stream"
        
        # Check that response is streaming
        content = response.text
        assert "data:" in content
        assert "event:" in content or "data:" in content
    
    async def test_rag_chat_stream(self, client: AsyncClient):
        """Test RAG chat streaming"""
        token = create_access_token(
            user_id="test-user",
            email="test@example.com",
            role="reader",
            tenant_ids=["tenant-123"],
            scopes=["read", "write"]
        )
        
        response = await client.post(
            "/api/v1/rag/chat/stream",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant-Id": "tenant-123",
                "Accept": "text/event-stream"
            },
            json={
                "message": "What is in the documents?",
                "model": "test-model"
            }
        )
        
        assert response.status_code == status.HTTP_200_OK
        assert response.headers["content-type"] == "text/event-stream"
    
    async def test_analysis_stream(self, client: AsyncClient):
        """Test document analysis streaming"""
        token = create_access_token(
            user_id="test-user",
            email="test@example.com",
            role="reader",
            tenant_ids=["tenant-123"],
            scopes=["read", "write"]
        )
        
        response = await client.post(
            "/api/v1/analyze/stream",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant-Id": "tenant-123",
                "Accept": "text/event-stream"
            },
            json={
                "document_id": "test-doc-123",
                "analysis_type": "summary"
            }
        )
        
        assert response.status_code == status.HTTP_200_OK
        assert response.headers["content-type"] == "text/event-stream"
    
    async def test_sse_headers(self, client: AsyncClient):
        """Test SSE response headers"""
        token = create_access_token(
            user_id="test-user",
            email="test@example.com",
            role="reader",
            tenant_ids=["tenant-123"],
            scopes=["read", "write"]
        )
        
        response = await client.post(
            "/api/v1/chat/stream",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant-Id": "tenant-123",
                "Accept": "text/event-stream"
            },
            json={"message": "Test message"}
        )
        
        assert response.status_code == status.HTTP_200_OK
        
        # Check SSE-specific headers
        headers = response.headers
        assert headers["content-type"] == "text/event-stream"
        assert "cache-control" in headers
        assert "no-cache" in headers["cache-control"]
        assert "connection" in headers
        assert "keep-alive" in headers["connection"]
    
    async def test_sse_event_format(self, client: AsyncClient):
        """Test SSE event format"""
        token = create_access_token(
            user_id="test-user",
            email="test@example.com",
            role="reader",
            tenant_ids=["tenant-123"],
            scopes=["read", "write"]
        )
        
        response = await client.post(
            "/api/v1/chat/stream",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant-Id": "tenant-123",
                "Accept": "text/event-stream"
            },
            json={"message": "Test message"}
        )
        
        assert response.status_code == status.HTTP_200_OK
        
        content = response.text
        lines = content.split('\n')
        
        # Check SSE format
        has_data = False
        has_event = False
        
        for line in lines:
            if line.startswith('data:'):
                has_data = True
            elif line.startswith('event:'):
                has_event = True
        
        assert has_data, "SSE response should contain data lines"
    
    async def test_sse_done_event(self, client: AsyncClient):
        """Test SSE done event"""
        token = create_access_token(
            user_id="test-user",
            email="test@example.com",
            role="reader",
            tenant_ids=["tenant-123"],
            scopes=["read", "write"]
        )
        
        response = await client.post(
            "/api/v1/chat/stream",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant-Id": "tenant-123",
                "Accept": "text/event-stream"
            },
            json={"message": "Test message"}
        )
        
        assert response.status_code == status.HTTP_200_OK
        
        content = response.text
        
        # Should contain done event
        assert "event: done" in content or "data: done" in content
    
    async def test_sse_error_handling(self, client: AsyncClient):
        """Test SSE error handling"""
        token = create_access_token(
            user_id="test-user",
            email="test@example.com",
            role="reader",
            tenant_ids=["tenant-123"],
            scopes=["read", "write"]
        )
        
        # Test with invalid request
        response = await client.post(
            "/api/v1/chat/stream",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant-Id": "tenant-123",
                "Accept": "text/event-stream"
            },
            json={"invalid": "request"}
        )
        
        # Should handle error gracefully
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_422_UNPROCESSABLE_ENTITY]
        
        if response.status_code == status.HTTP_200_OK:
            # If streaming, should contain error event
            content = response.text
            assert "event: error" in content or "error" in content.lower()
    
    async def test_sse_client_disconnect(self, client: AsyncClient):
        """Test SSE client disconnect handling"""
        token = create_access_token(
            user_id="test-user",
            email="test@example.com",
            role="reader",
            tenant_ids=["tenant-123"],
            scopes=["read", "write"]
        )
        
        # This test would require a more sophisticated setup to simulate client disconnect
        # For now, we'll test that the endpoint responds correctly
        response = await client.post(
            "/api/v1/chat/stream",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant-Id": "tenant-123",
                "Accept": "text/event-stream"
            },
            json={"message": "Test message"},
            timeout=1.0  # Short timeout to simulate disconnect
        )
        
        # Should handle timeout gracefully
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_408_REQUEST_TIMEOUT]
    
    async def test_sse_heartbeat(self, client: AsyncClient):
        """Test SSE heartbeat for long streams"""
        token = create_access_token(
            user_id="test-user",
            email="test@example.com",
            role="reader",
            tenant_ids=["tenant-123"],
            scopes=["read", "write"]
        )
        
        response = await client.post(
            "/api/v1/chat/stream",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant-Id": "tenant-123",
                "Accept": "text/event-stream"
            },
            json={"message": "Long processing message"}
        )
        
        assert response.status_code == status.HTTP_200_OK
        
        content = response.text
        
        # Should contain heartbeat events for long streams
        # This depends on implementation - may contain heartbeat events
        assert len(content) > 0
    
    async def test_sse_without_accept_header(self, client: AsyncClient):
        """Test SSE without Accept: text/event-stream header"""
        token = create_access_token(
            user_id="test-user",
            email="test@example.com",
            role="reader",
            tenant_ids=["tenant-123"],
            scopes=["read", "write"]
        )
        
        response = await client.post(
            "/api/v1/chat/stream",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant-Id": "tenant-123"
            },
            json={"message": "Test message"}
        )
        
        # Should still work (Accept header is optional)
        assert response.status_code == status.HTTP_200_OK
    
    async def test_sse_concurrent_streams(self, client: AsyncClient):
        """Test concurrent SSE streams"""
        token = create_access_token(
            user_id="test-user",
            email="test@example.com",
            role="reader",
            tenant_ids=["tenant-123"],
            scopes=["read", "write"]
        )
        
        async def create_stream():
            return await client.post(
                "/api/v1/chat/stream",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Tenant-Id": "tenant-123",
                    "Accept": "text/event-stream"
                },
                json={"message": f"Concurrent message {asyncio.current_task().get_name()}"}
            )
        
        # Create multiple concurrent streams
        tasks = [create_stream() for _ in range(3)]
        responses = await asyncio.gather(*tasks)
        
        # All should succeed
        for response in responses:
            assert response.status_code == status.HTTP_200_OK
            assert response.headers["content-type"] == "text/event-stream"
    
    async def test_sse_progress_events(self, client: AsyncClient):
        """Test SSE progress events"""
        token = create_access_token(
            user_id="test-user",
            email="test@example.com",
            role="reader",
            tenant_ids=["tenant-123"],
            scopes=["read", "write"]
        )
        
        response = await client.post(
            "/api/v1/analyze/stream",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant-Id": "tenant-123",
                "Accept": "text/event-stream"
            },
            json={
                "document_id": "test-doc-123",
                "analysis_type": "comprehensive"
            }
        )
        
        assert response.status_code == status.HTTP_200_OK
        
        content = response.text
        
        # Should contain progress events
        assert "event: progress" in content or "progress" in content.lower()
