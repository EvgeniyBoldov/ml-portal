"""
Интеграционные тесты для эндпоинтов artifacts.
"""
import pytest
import uuid
from httpx import AsyncClient

from app.main import app


@pytest.mark.integration
class TestArtifactsEndpoints:
    """Тесты эндпоинтов artifacts."""

    @pytest.mark.asyncio
    async def test_presign_artifact_unauthorized(self, async_client: AsyncClient):
        """Тест presign artifact без авторизации."""
        async for client in async_client:
            data = {
                "job_id": str(uuid.uuid4()),
                "filename": "test.txt",
                "content_type": "text/plain"
            }
            response = await client.post("/api/v1/artifacts/presign", json=data)
            assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_presign_artifact_authorized(self, async_client: AsyncClient, user_token):
        """Тест presign artifact с авторизацией."""
        async for client in async_client:
            headers = {
                "Authorization": f"Bearer {user_token}",
                "X-Tenant-Id": str(uuid.uuid4()),
                "Idempotency-Key": str(uuid.uuid4())
            }
            data = {
                "job_id": str(uuid.uuid4()),
                "filename": "test.txt",
                "content_type": "text/plain"
            }
            response = await client.post("/api/v1/artifacts/presign", json=data, headers=headers)
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
    async def test_presign_artifact_missing_job_id(self, async_client: AsyncClient, user_token):
        """Тест presign artifact без job_id."""
        async for client in async_client:
            headers = {
                "Authorization": f"Bearer {user_token}",
                "X-Tenant-Id": str(uuid.uuid4()),
                "Idempotency-Key": str(uuid.uuid4())
            }
            data = {
                "filename": "test.txt",
                "content_type": "text/plain"
            }
            response = await client.post("/api/v1/artifacts/presign", json=data, headers=headers)
            assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_presign_artifact_missing_filename(self, async_client: AsyncClient, user_token):
        """Тест presign artifact без filename."""
        async for client in async_client:
            headers = {
                "Authorization": f"Bearer {user_token}",
                "X-Tenant-Id": str(uuid.uuid4()),
                "Idempotency-Key": str(uuid.uuid4())
            }
            data = {
                "job_id": str(uuid.uuid4()),
                "content_type": "text/plain"
            }
            response = await client.post("/api/v1/artifacts/presign", json=data, headers=headers)
            assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_presign_artifact_different_content_types(self, async_client: AsyncClient, user_token):
        """Тест presign artifact с разными типами контента."""
        async for client in async_client:
            headers = {
                "Authorization": f"Bearer {user_token}",
                "X-Tenant-Id": str(uuid.uuid4()),
                "Idempotency-Key": str(uuid.uuid4())
            }
            
            content_types = [
                "text/plain",
                "application/pdf",
                "image/jpeg",
                "application/json",
                "text/csv"
            ]
            
            for content_type in content_types:
                data = {
                    "job_id": str(uuid.uuid4()),
                    "filename": f"test.{content_type.split('/')[1]}",
                    "content_type": content_type
                }
                response = await client.post("/api/v1/artifacts/presign", json=data, headers=headers)
                assert response.status_code == 200
                result = response.json()
                assert result["content_type"] == content_type

    @pytest.mark.asyncio
    async def test_presign_artifact_different_filenames(self, async_client: AsyncClient, user_token):
        """Тест presign artifact с разными именами файлов."""
        async for client in async_client:
            headers = {
                "Authorization": f"Bearer {user_token}",
                "X-Tenant-Id": str(uuid.uuid4()),
                "Idempotency-Key": str(uuid.uuid4())
            }
            
            filenames = [
                "document.pdf",
                "image.jpg",
                "data.csv",
                "report.xlsx",
                "config.json"
            ]
            
            for filename in filenames:
                data = {
                    "job_id": str(uuid.uuid4()),
                    "filename": filename,
                    "content_type": "application/octet-stream"
                }
                response = await client.post("/api/v1/artifacts/presign", json=data, headers=headers)
                assert response.status_code == 200
                result = response.json()
                # Проверяем, что ключ содержит имя файла
                assert filename in result["key"]

    @pytest.mark.asyncio
    async def test_presign_artifact_idempotency(self, async_client: AsyncClient, user_token):
        """Тест идемпотентности presign artifact."""
        async for client in async_client:
            headers = {
                "Authorization": f"Bearer {user_token}",
                "X-Tenant-Id": str(uuid.uuid4()),
                "Idempotency-Key": str(uuid.uuid4())
            }
            data = {
                "job_id": str(uuid.uuid4()),
                "filename": "test.txt",
                "content_type": "text/plain"
            }
            
            # Первый запрос
            response1 = await client.post("/api/v1/artifacts/presign", json=data, headers=headers)
            assert response1.status_code == 200
            result1 = response1.json()
            
            # Второй запрос с тем же ключом идемпотентности
            response2 = await client.post("/api/v1/artifacts/presign", json=data, headers=headers)
            assert response2.status_code == 200
            result2 = response2.json()
            
            # Должен вернуть тот же результат
            assert result1["presigned_url"] == result2["presigned_url"]
            assert result1["key"] == result2["key"]

    @pytest.mark.asyncio
    async def test_presign_artifact_tenant_isolation(self, async_client: AsyncClient, user_token):
        """Тест изоляции tenant в presign artifact."""
        async for client in async_client:
            tenant1 = str(uuid.uuid4())
            tenant2 = str(uuid.uuid4())
            
            data = {
                "job_id": str(uuid.uuid4()),
                "filename": "test.txt",
                "content_type": "text/plain"
            }
            
            # Запрос для первого tenant
            headers1 = {
                "Authorization": f"Bearer {user_token}",
                "X-Tenant-Id": tenant1,
                "Idempotency-Key": str(uuid.uuid4())
            }
            response1 = await client.post("/api/v1/artifacts/presign", json=data, headers=headers1)
            assert response1.status_code == 200
            result1 = response1.json()
            
            # Запрос для второго tenant
            headers2 = {
                "Authorization": f"Bearer {user_token}",
                "X-Tenant-Id": tenant2,
                "Idempotency-Key": str(uuid.uuid4())
            }
            response2 = await client.post("/api/v1/artifacts/presign", json=data, headers=headers2)
            assert response2.status_code == 200
            result2 = response2.json()
            
            # Ключи должны быть разными для разных tenant
            assert result1["key"] != result2["key"]

    @pytest.mark.asyncio
    async def test_presign_artifact_expires_in(self, async_client: AsyncClient, user_token):
        """Тест времени истечения presign artifact."""
        async for client in async_client:
            headers = {
                "Authorization": f"Bearer {user_token}",
                "X-Tenant-Id": str(uuid.uuid4()),
                "Idempotency-Key": str(uuid.uuid4())
            }
            data = {
                "job_id": str(uuid.uuid4()),
                "filename": "test.txt",
                "content_type": "text/plain"
            }
            response = await client.post("/api/v1/artifacts/presign", json=data, headers=headers)
            assert response.status_code == 200
            result = response.json()
            
            # Проверяем, что время истечения разумное (например, от 300 до 3600 секунд)
            expires_in = result["expires_in"]
            assert isinstance(expires_in, int)
            assert 300 <= expires_in <= 3600

    @pytest.mark.asyncio
    async def test_presign_artifact_max_bytes(self, async_client: AsyncClient, user_token):
        """Тест максимального размера файла."""
        async for client in async_client:
            headers = {
                "Authorization": f"Bearer {user_token}",
                "X-Tenant-Id": str(uuid.uuid4()),
                "Idempotency-Key": str(uuid.uuid4())
            }
            data = {
                "job_id": str(uuid.uuid4()),
                "filename": "test.txt",
                "content_type": "text/plain"
            }
            response = await client.post("/api/v1/artifacts/presign", json=data, headers=headers)
            assert response.status_code == 200
            result = response.json()
            
            # Проверяем, что максимальный размер файла установлен
            max_bytes = result["max_bytes"]
            assert isinstance(max_bytes, int)
            assert max_bytes > 0
