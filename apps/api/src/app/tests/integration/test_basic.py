"""
Простые интеграционные тесты для проверки базовой функциональности.
"""
import pytest
import uuid
from httpx import AsyncClient

from app.main import app


@pytest.mark.integration
class TestAPIBasic:
    """Базовые интеграционные тесты."""

    @pytest.mark.asyncio
    async def test_health_endpoint(self, async_client: AsyncClient):
        """Тест health endpoint."""
        async for client in async_client:
            response = await client.get("/api/v1/healthz")
            assert response.status_code == 200
            data = response.json()
            assert "status" in data
            assert data["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_ready_endpoint(self, async_client: AsyncClient):
        """Тест readiness endpoint."""
        async for client in async_client:
            response = await client.get("/api/v1/readyz")
            assert response.status_code == 200
            data = response.json()
            assert "status" in data
            assert "dependencies" in data

    @pytest.mark.asyncio
    async def test_version_endpoint(self, async_client: AsyncClient):
        """Тест version endpoint."""
        async for client in async_client:
            response = await client.get("/api/v1/version")
            assert response.status_code == 200
            data = response.json()
            assert "version" in data

    @pytest.mark.asyncio
    async def test_redis_connection(self, redis_client):
        """Тест подключения к Redis."""
        async for redis in redis_client:
            # Простой тест Redis
            await redis.set("test_key", "test_value")
            value = await redis.get("test_key")
            assert value == "test_value"
            await redis.delete("test_key")

    @pytest.mark.asyncio
    async def test_qdrant_connection(self, qdrant_client):
        """Тест подключения к Qdrant."""
        # Qdrant клиент не является async итератором
        collections_response = qdrant_client.get_collections()
        assert hasattr(collections_response, 'collections')
        assert isinstance(collections_response.collections, list)
