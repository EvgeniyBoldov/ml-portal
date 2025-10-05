"""
Интеграционные тесты для эндпоинтов tenants.
"""
import pytest
import uuid
from httpx import AsyncClient

from app.main import app


@pytest.mark.integration
class TestTenantsEndpoints:
    """Тесты эндпоинтов tenants."""

    @pytest.mark.asyncio
    async def test_list_tenants_unauthorized(self, async_client: AsyncClient):
        """Тест получения списка tenants без авторизации."""
        async for client in async_client:
            response = await client.get("/api/v1/tenants")
            assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_list_tenants_admin(self, async_client: AsyncClient, simple_admin_token):
        """Тест получения списка tenants с админ правами."""
        async for client in async_client:
            headers = {"Authorization": f"Bearer {simple_admin_token}"}
            response = await client.get("/api/v1/tenants", headers=headers)
            assert response.status_code == 200
            data = response.json()
            assert "items" in data
            assert isinstance(data["items"], list)

    @pytest.mark.asyncio
    async def test_list_tenants_with_pagination(self, async_client: AsyncClient, simple_admin_token):
        """Тест пагинации списка tenants."""
        async for client in async_client:
            headers = {"Authorization": f"Bearer {simple_admin_token}"}
            response = await client.get("/api/v1/tenants?limit=5", headers=headers)
            assert response.status_code == 200
            data = response.json()
            assert "items" in data
            assert len(data["items"]) <= 5

    @pytest.mark.asyncio
    async def test_create_tenant_unauthorized(self, async_client: AsyncClient):
        """Тест создания tenant без авторизации."""
        async for client in async_client:
            tenant_data = {
                "name": "test_tenant",
                "description": "Test tenant description"
            }
            response = await client.post("/api/v1/tenants", json=tenant_data)
            assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_tenant_admin(self, async_client: AsyncClient, simple_admin_token):
        """Тест создания tenant с админ правами."""
        async for client in async_client:
            headers = {"Authorization": f"Bearer {simple_admin_token}"}
            tenant_data = {
                "name": f"test_tenant_{uuid.uuid4().hex[:8]}",
                "description": "Test tenant description"
            }
            response = await client.post("/api/v1/tenants", json=tenant_data, headers=headers)
            assert response.status_code == 200
            data = response.json()
            assert "id" in data
            assert data["name"] == tenant_data["name"]

    @pytest.mark.asyncio
    async def test_get_tenant_by_id_unauthorized(self, async_client: AsyncClient):
        """Тест получения tenant по ID без авторизации."""
        async for client in async_client:
            tenant_id = str(uuid.uuid4())
            response = await client.get(f"/api/v1/tenants/{tenant_id}")
            assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_tenant_by_id_admin(self, async_client: AsyncClient, simple_admin_token):
        """Тест получения tenant по ID с админ правами."""
        async for client in async_client:
            headers = {"Authorization": f"Bearer {simple_admin_token}"}
            
            # Сначала создаем tenant
            tenant_data = {
                "name": f"test_tenant_{uuid.uuid4().hex[:8]}",
                "description": "Test tenant description"
            }
            create_response = await client.post("/api/v1/tenants", json=tenant_data, headers=headers)
            assert create_response.status_code == 200
            created_tenant = create_response.json()
            
            # Затем получаем его по ID
            tenant_id = created_tenant["id"]
            response = await client.get(f"/api/v1/tenants/{tenant_id}", headers=headers)
            assert response.status_code == 200
            data = response.json()
            assert data["id"] == tenant_id
            assert data["name"] == tenant_data["name"]

    @pytest.mark.asyncio
    async def test_update_tenant_unauthorized(self, async_client: AsyncClient):
        """Тест обновления tenant без авторизации."""
        async for client in async_client:
            tenant_id = str(uuid.uuid4())
            update_data = {"name": "updated_tenant"}
            response = await client.put(f"/api/v1/tenants/{tenant_id}", json=update_data)
            assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_update_tenant_admin(self, async_client: AsyncClient, simple_admin_token):
        """Тест обновления tenant с админ правами."""
        async for client in async_client:
            headers = {"Authorization": f"Bearer {simple_admin_token}"}
            
            # Сначала создаем tenant
            tenant_data = {
                "name": f"test_tenant_{uuid.uuid4().hex[:8]}",
                "description": "Test tenant description"
            }
            create_response = await client.post("/api/v1/tenants", json=tenant_data, headers=headers)
            assert create_response.status_code == 200
            created_tenant = create_response.json()
            
            # Затем обновляем его
            tenant_id = created_tenant["id"]
            update_data = {"name": f"updated_{tenant_data['name']}"}
            response = await client.put(f"/api/v1/tenants/{tenant_id}", json=update_data, headers=headers)
            assert response.status_code == 200
            data = response.json()
            assert data["name"] == update_data["name"]

    @pytest.mark.asyncio
    async def test_delete_tenant_unauthorized(self, async_client: AsyncClient):
        """Тест удаления tenant без авторизации."""
        async for client in async_client:
            tenant_id = str(uuid.uuid4())
            response = await client.delete(f"/api/v1/tenants/{tenant_id}")
            assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_delete_tenant_admin(self, async_client: AsyncClient, simple_admin_token):
        """Тест удаления tenant с админ правами."""
        async for client in async_client:
            headers = {"Authorization": f"Bearer {simple_admin_token}"}
            
            # Сначала создаем tenant
            tenant_data = {
                "name": f"test_tenant_{uuid.uuid4().hex[:8]}",
                "description": "Test tenant description"
            }
            create_response = await client.post("/api/v1/tenants", json=tenant_data, headers=headers)
            assert create_response.status_code == 200
            created_tenant = create_response.json()
            
            # Затем удаляем его
            tenant_id = created_tenant["id"]
            response = await client.delete(f"/api/v1/tenants/{tenant_id}", headers=headers)
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_tenant_not_found(self, async_client: AsyncClient, simple_admin_token):
        """Тест получения несуществующего tenant."""
        async for client in async_client:
            headers = {"Authorization": f"Bearer {simple_admin_token}"}
            tenant_id = str(uuid.uuid4())
            response = await client.get(f"/api/v1/tenants/{tenant_id}", headers=headers)
            assert response.status_code == 404
