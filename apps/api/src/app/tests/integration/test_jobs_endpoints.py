"""
Интеграционные тесты для эндпоинтов jobs.
"""
import pytest
import uuid
from httpx import AsyncClient

from app.main import app


@pytest.mark.integration
class TestJobsEndpoints:
    """Тесты эндпоинтов jobs."""

    @pytest.mark.asyncio
    async def test_list_jobs_unauthorized(self, async_client: AsyncClient):
        """Тест получения списка jobs без авторизации."""
        async for client in async_client:
            response = await client.get("/api/v1/jobs")
            assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_list_jobs_authorized(self, async_client: AsyncClient, user_token):
        """Тест получения списка jobs с авторизацией."""
        async for client in async_client:
            headers = {"Authorization": f"Bearer {user_token}"}
            response = await client.get("/api/v1/jobs", headers=headers)
            assert response.status_code == 200
            data = response.json()
            assert "items" in data
            assert isinstance(data["items"], list)

    @pytest.mark.asyncio
    async def test_list_jobs_with_pagination(self, async_client: AsyncClient, user_token):
        """Тест пагинации списка jobs."""
        async for client in async_client:
            headers = {"Authorization": f"Bearer {user_token}"}
            response = await client.get("/api/v1/jobs?limit=5", headers=headers)
            assert response.status_code == 200
            data = response.json()
            assert "items" in data
            assert len(data["items"]) <= 5

    @pytest.mark.asyncio
    async def test_list_jobs_with_status_filter(self, async_client: AsyncClient, user_token):
        """Тест фильтрации jobs по статусу."""
        async for client in async_client:
            headers = {"Authorization": f"Bearer {user_token}"}
            response = await client.get("/api/v1/jobs?status=running", headers=headers)
            assert response.status_code == 200
            data = response.json()
            assert "items" in data
            # Проверяем, что все jobs имеют статус "running"
            for job in data["items"]:
                assert job["status"] == "running"

    @pytest.mark.asyncio
    async def test_list_jobs_invalid_status(self, async_client: AsyncClient, user_token):
        """Тест фильтрации jobs с неверным статусом."""
        async for client in async_client:
            headers = {"Authorization": f"Bearer {user_token}"}
            response = await client.get("/api/v1/jobs?status=invalid_status", headers=headers)
            assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_get_job_by_id_unauthorized(self, async_client: AsyncClient):
        """Тест получения job по ID без авторизации."""
        async for client in async_client:
            job_id = str(uuid.uuid4())
            response = await client.get(f"/api/v1/jobs/{job_id}")
            assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_job_by_id_authorized(self, async_client: AsyncClient, user_token):
        """Тест получения job по ID с авторизацией."""
        async for client in async_client:
            headers = {"Authorization": f"Bearer {user_token}"}
            job_id = str(uuid.uuid4())
            response = await client.get(f"/api/v1/jobs/{job_id}", headers=headers)
            assert response.status_code == 200
            data = response.json()
            assert "job_id" in data
            assert data["job_id"] == job_id

    @pytest.mark.asyncio
    async def test_cancel_job_unauthorized(self, async_client: AsyncClient):
        """Тест отмены job без авторизации."""
        async for client in async_client:
            job_id = str(uuid.uuid4())
            response = await client.post(f"/api/v1/jobs/{job_id}/cancel")
            assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_cancel_job_authorized(self, async_client: AsyncClient, user_token):
        """Тест отмены job с авторизацией."""
        async for client in async_client:
            headers = {"Authorization": f"Bearer {user_token}"}
            job_id = str(uuid.uuid4())
            response = await client.post(f"/api/v1/jobs/{job_id}/cancel", headers=headers)
            assert response.status_code == 200
            data = response.json()
            assert "job_id" in data
            assert data["job_id"] == job_id

    @pytest.mark.asyncio
    async def test_retry_job_unauthorized(self, async_client: AsyncClient):
        """Тест повторного запуска job без авторизации."""
        async for client in async_client:
            job_id = str(uuid.uuid4())
            response = await client.post(f"/api/v1/jobs/{job_id}/retry")
            assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_retry_job_authorized(self, async_client: AsyncClient, user_token):
        """Тест повторного запуска job с авторизацией."""
        async for client in async_client:
            headers = {"Authorization": f"Bearer {user_token}"}
            job_id = str(uuid.uuid4())
            response = await client.post(f"/api/v1/jobs/{job_id}/retry", headers=headers)
            assert response.status_code == 200
            data = response.json()
            assert "job_id" in data
            assert data["job_id"] == job_id

    @pytest.mark.asyncio
    async def test_job_pagination_cursor(self, async_client: AsyncClient, user_token):
        """Тест пагинации с курсором."""
        async for client in async_client:
            headers = {"Authorization": f"Bearer {user_token}"}
            
            # Первая страница
            response1 = await client.get("/api/v1/jobs?limit=3", headers=headers)
            assert response1.status_code == 200
            data1 = response1.json()
            
            if data1.get("next_cursor"):
                # Вторая страница с курсором
                response2 = await client.get(f"/api/v1/jobs?limit=3&cursor={data1['next_cursor']}", headers=headers)
                assert response2.status_code == 200
                data2 = response2.json()
                assert "items" in data2
                # Проверяем, что это разные jobs
                job_ids_1 = {job["job_id"] for job in data1["items"]}
                job_ids_2 = {job["job_id"] for job in data2["items"]}
                assert job_ids_1.isdisjoint(job_ids_2)

    @pytest.mark.asyncio
    async def test_job_limit_validation(self, async_client: AsyncClient, user_token):
        """Тест валидации лимита."""
        async for client in async_client:
            headers = {"Authorization": f"Bearer {user_token}"}
            
            # Тест минимального лимита
            response = await client.get("/api/v1/jobs?limit=0", headers=headers)
            assert response.status_code == 422
            
            # Тест максимального лимита
            response = await client.get("/api/v1/jobs?limit=101", headers=headers)
            assert response.status_code == 422
            
            # Тест валидного лимита
            response = await client.get("/api/v1/jobs?limit=50", headers=headers)
            assert response.status_code == 200
