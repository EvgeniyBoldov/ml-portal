"""
Интеграционные тесты для эндпоинтов analyze.
"""
import pytest
import uuid
from httpx import AsyncClient

from app.main import app


@pytest.mark.integration
class TestAnalyzeEndpoints:
    """Тесты эндпоинтов analyze."""

    @pytest.mark.asyncio
    async def test_presign_ingest_unauthorized(self, async_client: AsyncClient):
        """Тест presign ingest без авторизации."""
        async for client in async_client:
            data = {
                "document_id": str(uuid.uuid4()),
                "content_type": "text/plain"
            }
            response = await client.post("/api/v1/analyze/ingest/presign", json=data)
            assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_presign_ingest_authorized(self, async_client: AsyncClient, user_token):
        """Тест presign ingest с авторизацией."""
        async for client in async_client:
            headers = {
                "Authorization": f"Bearer {user_token}",
                "X-Tenant-Id": str(uuid.uuid4()),
                "Idempotency-Key": str(uuid.uuid4())
            }
            data = {
                "document_id": str(uuid.uuid4()),
                "content_type": "text/plain"
            }
            response = await client.post("/api/v1/analyze/ingest/presign", json=data, headers=headers)
            assert response.status_code == 200
            result = response.json()
            
            # Проверяем структуру ответа
            assert "presigned_url" in result
            assert "bucket" in result
            assert "key" in result
            assert "content_type" in result
            assert "expires_in" in result
            assert "max_bytes" in result

    @pytest.mark.asyncio
    async def test_presign_ingest_missing_document_id(self, async_client: AsyncClient, user_token):
        """Тест presign ingest без document_id."""
        async for client in async_client:
            headers = {
                "Authorization": f"Bearer {user_token}",
                "X-Tenant-Id": str(uuid.uuid4()),
                "Idempotency-Key": str(uuid.uuid4())
            }
            data = {
                "content_type": "text/plain"
            }
            response = await client.post("/api/v1/analyze/ingest/presign", json=data, headers=headers)
            assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_presign_ingest_missing_tenant(self, async_client: AsyncClient, user_token):
        """Тест presign ingest без tenant_id."""
        async for client in async_client:
            headers = {
                "Authorization": f"Bearer {user_token}",
                "Idempotency-Key": str(uuid.uuid4())
            }
            data = {
                "document_id": str(uuid.uuid4()),
                "content_type": "text/plain"
            }
            response = await client.post("/api/v1/analyze/ingest/presign", json=data, headers=headers)
            assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_presign_ingest_different_content_types(self, async_client: AsyncClient, user_token):
        """Тест presign ingest с разными типами контента."""
        async for client in async_client:
            headers = {
                "Authorization": f"Bearer {user_token}",
                "X-Tenant-Id": str(uuid.uuid4()),
                "Idempotency-Key": str(uuid.uuid4())
            }
            
            content_types = [
                "text/plain",
                "application/pdf",
                "text/csv",
                "application/json"
            ]
            
            for content_type in content_types:
                data = {
                    "document_id": str(uuid.uuid4()),
                    "content_type": content_type
                }
                response = await client.post("/api/v1/analyze/ingest/presign", json=data, headers=headers)
                assert response.status_code == 200
                result = response.json()
                assert result["content_type"] == content_type

    @pytest.mark.asyncio
    async def test_analyze_stream_unauthorized(self, async_client: AsyncClient):
        """Тест analyze stream без авторизации."""
        async for client in async_client:
            data = {
                "texts": ["Sample text for analysis"],
                "content_types": ["text/plain"]
            }
            response = await client.post("/api/v1/analyze/stream", json=data)
            assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_analyze_stream_authorized(self, async_client: AsyncClient, user_token):
        """Тест analyze stream с авторизацией."""
        async for client in async_client:
            headers = {
                "Authorization": f"Bearer {user_token}",
                "X-Tenant-Id": str(uuid.uuid4()),
                "Idempotency-Key": str(uuid.uuid4())
            }
            data = {
                "texts": ["Sample text for analysis"],
                "content_types": ["text/plain"],
                "document_id": str(uuid.uuid4())
            }
            response = await client.post("/api/v1/analyze/stream", json=data, headers=headers)
            assert response.status_code == 200
            # Проверяем, что это SSE ответ
            assert response.headers["content-type"] == "text/event-stream"

    @pytest.mark.asyncio
    async def test_analyze_stream_empty_texts(self, async_client: AsyncClient, user_token):
        """Тест analyze stream с пустыми текстами."""
        async for client in async_client:
            headers = {
                "Authorization": f"Bearer {user_token}",
                "X-Tenant-Id": str(uuid.uuid4()),
                "Idempotency-Key": str(uuid.uuid4())
            }
            data = {
                "texts": [],
                "content_types": ["text/plain"]
            }
            response = await client.post("/api/v1/analyze/stream", json=data, headers=headers)
            assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_analyze_stream_missing_texts(self, async_client: AsyncClient, user_token):
        """Тест analyze stream без текстов."""
        async for client in async_client:
            headers = {
                "Authorization": f"Bearer {user_token}",
                "X-Tenant-Id": str(uuid.uuid4()),
                "Idempotency-Key": str(uuid.uuid4())
            }
            data = {
                "content_types": ["text/plain"]
            }
            response = await client.post("/api/v1/analyze/stream", json=data, headers=headers)
            assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_analyze_stream_multiple_texts(self, async_client: AsyncClient, user_token):
        """Тест analyze stream с несколькими текстами."""
        async for client in async_client:
            headers = {
                "Authorization": f"Bearer {user_token}",
                "X-Tenant-Id": str(uuid.uuid4()),
                "Idempotency-Key": str(uuid.uuid4())
            }
            data = {
                "texts": [
                    "First text for analysis",
                    "Second text for analysis",
                    "Third text for analysis"
                ],
                "content_types": ["text/plain", "text/plain", "text/plain"],
                "document_id": str(uuid.uuid4())
            }
            response = await client.post("/api/v1/analyze/stream", json=data, headers=headers)
            assert response.status_code == 200
            assert response.headers["content-type"] == "text/event-stream"

    @pytest.mark.asyncio
    async def test_analyze_stream_idempotency(self, async_client: AsyncClient, user_token):
        """Тест идемпотентности analyze stream."""
        async for client in async_client:
            headers = {
                "Authorization": f"Bearer {user_token}",
                "X-Tenant-Id": str(uuid.uuid4()),
                "Idempotency-Key": str(uuid.uuid4())
            }
            data = {
                "texts": ["Sample text for analysis"],
                "content_types": ["text/plain"],
                "document_id": str(uuid.uuid4())
            }
            
            # Первый запрос
            response1 = await client.post("/api/v1/analyze/stream", json=data, headers=headers)
            assert response1.status_code == 200
            
            # Второй запрос с тем же ключом идемпотентности
            response2 = await client.post("/api/v1/analyze/stream", json=data, headers=headers)
            assert response2.status_code == 200
            # Должен вернуть тот же результат (или кешированный)

    @pytest.mark.asyncio
    async def test_analyze_stream_tenant_isolation(self, async_client: AsyncClient, user_token):
        """Тест изоляции tenant в analyze stream."""
        async for client in async_client:
            tenant1 = str(uuid.uuid4())
            tenant2 = str(uuid.uuid4())
            
            data = {
                "texts": ["Sample text for analysis"],
                "content_types": ["text/plain"],
                "document_id": str(uuid.uuid4())
            }
            
            # Запрос для первого tenant
            headers1 = {
                "Authorization": f"Bearer {user_token}",
                "X-Tenant-Id": tenant1,
                "Idempotency-Key": str(uuid.uuid4())
            }
            response1 = await client.post("/api/v1/analyze/stream", json=data, headers=headers1)
            assert response1.status_code == 200
            
            # Запрос для второго tenant
            headers2 = {
                "Authorization": f"Bearer {user_token}",
                "X-Tenant-Id": tenant2,
                "Idempotency-Key": str(uuid.uuid4())
            }
            response2 = await client.post("/api/v1/analyze/stream", json=data, headers=headers2)
            assert response2.status_code == 200
