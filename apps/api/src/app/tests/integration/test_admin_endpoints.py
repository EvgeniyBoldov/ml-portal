"""
Интеграционные тесты для эндпоинтов admin.
"""
import pytest
import uuid
from httpx import AsyncClient

from app.main import app


@pytest.mark.integration
class TestAdminEndpoints:
    """Тесты эндпоинтов admin."""

    @pytest.mark.asyncio
    async def test_get_admin_status_unauthorized(self, async_client: AsyncClient):
        """Тест получения статуса админа без авторизации."""
        async for client in async_client:
            response = await client.get("/api/v1/admin/status")
            assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_admin_status_non_admin(self, async_client: AsyncClient, user_token):
        """Тест получения статуса админа с правами обычного пользователя."""
        async for client in async_client:
            headers = {"Authorization": f"Bearer {user_token}"}
            response = await client.get("/api/v1/admin/status", headers=headers)
            assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_get_admin_status_admin(self, async_client: AsyncClient, admin_token):
        """Тест получения статуса админа с правами админа."""
        async for client in async_client:
            headers = {"Authorization": f"Bearer {admin_token}"}
            response = await client.get("/api/v1/admin/status", headers=headers)
            assert response.status_code == 200
            data = response.json()
            
            # Проверяем структуру ответа
            assert "services" in data
            assert "metrics" in data
            
            # Проверяем сервисы
            services = data["services"]
            expected_services = ["api", "workers", "qdrant", "minio"]
            for service in expected_services:
                assert service in services
                assert services[service] in ["ready", "not_ready", "error"]
            
            # Проверяем метрики
            metrics = data["metrics"]
            assert "sse_active" in metrics
            assert "queue_depth" in metrics
            assert isinstance(metrics["sse_active"], int)
            assert isinstance(metrics["queue_depth"], int)

    @pytest.mark.asyncio
    async def test_set_admin_mode_unauthorized(self, async_client: AsyncClient):
        """Тест установки режима админа без авторизации."""
        async for client in async_client:
            mode_data = {"mode": "maintenance"}
            response = await client.post("/api/v1/admin/mode", json=mode_data)
            assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_set_admin_mode_non_admin(self, async_client: AsyncClient, user_token):
        """Тест установки режима админа с правами обычного пользователя."""
        async for client in async_client:
            headers = {"Authorization": f"Bearer {user_token}"}
            mode_data = {"mode": "maintenance"}
            response = await client.post("/api/v1/admin/mode", json=mode_data, headers=headers)
            assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_set_admin_mode_admin(self, async_client: AsyncClient, admin_token):
        """Тест установки режима админа с правами админа."""
        async for client in async_client:
            headers = {"Authorization": f"Bearer {admin_token}"}
            mode_data = {"mode": "maintenance"}
            response = await client.post("/api/v1/admin/mode", json=mode_data, headers=headers)
            assert response.status_code == 200
            data = response.json()
            
            # Проверяем структуру ответа
            assert "mode" in data
            assert data["mode"] == "maintenance"

    @pytest.mark.asyncio
    async def test_set_admin_mode_invalid_mode(self, async_client: AsyncClient, admin_token):
        """Тест установки неверного режима админа."""
        async for client in async_client:
            headers = {"Authorization": f"Bearer {admin_token}"}
            mode_data = {"mode": "invalid_mode"}
            response = await client.post("/api/v1/admin/mode", json=mode_data, headers=headers)
            assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_admin_mode_values(self, async_client: AsyncClient, admin_token):
        """Тест различных значений режима админа."""
        async for client in async_client:
            headers = {"Authorization": f"Bearer {admin_token}"}
            
            valid_modes = ["normal", "maintenance", "readonly"]
            for mode in valid_modes:
                mode_data = {"mode": mode}
                response = await client.post("/api/v1/admin/mode", json=mode_data, headers=headers)
                assert response.status_code == 200
                data = response.json()
                assert data["mode"] == mode

    @pytest.mark.asyncio
    async def test_admin_status_services_status(self, async_client: AsyncClient, admin_token):
        """Тест статуса сервисов в админ панели."""
        async for client in async_client:
            headers = {"Authorization": f"Bearer {admin_token}"}
            response = await client.get("/api/v1/admin/status", headers=headers)
            assert response.status_code == 200
            data = response.json()
            
            services = data["services"]
            for service_name, service_status in services.items():
                assert service_status in ["ready", "not_ready", "error"], f"Invalid status for {service_name}: {service_status}"

    @pytest.mark.asyncio
    async def test_admin_metrics_values(self, async_client: AsyncClient, admin_token):
        """Тест значений метрик в админ панели."""
        async for client in async_client:
            headers = {"Authorization": f"Bearer {admin_token}"}
            response = await client.get("/api/v1/admin/status", headers=headers)
            assert response.status_code == 200
            data = response.json()
            
            metrics = data["metrics"]
            
            # Проверяем SSE активные соединения
            assert metrics["sse_active"] >= 0, "SSE active connections should be non-negative"
            
            # Проверяем глубину очереди
            assert metrics["queue_depth"] >= 0, "Queue depth should be non-negative"

    @pytest.mark.asyncio
    async def test_admin_mode_missing_data(self, async_client: AsyncClient, admin_token):
        """Тест установки режима админа без данных."""
        async for client in async_client:
            headers = {"Authorization": f"Bearer {admin_token}"}
            response = await client.post("/api/v1/admin/mode", json={}, headers=headers)
            assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_admin_endpoints_require_admin_auth(self, async_client: AsyncClient):
        """Тест что все админ эндпоинты требуют админ авторизацию."""
        async for client in async_client:
            # Тест без токена
            response1 = await client.get("/api/v1/admin/status")
            assert response1.status_code == 401
            
            response2 = await client.post("/api/v1/admin/mode", json={"mode": "normal"})
            assert response2.status_code == 401
