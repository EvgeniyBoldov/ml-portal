"""
Интеграционные тесты для эндпоинтов models.
"""
import pytest
import uuid
from httpx import AsyncClient

from app.main import app


@pytest.mark.integration
class TestModelsEndpoints:
    """Тесты эндпоинтов models."""

    @pytest.mark.asyncio
    async def test_list_llm_models_unauthorized(self, async_client: AsyncClient):
        """Тест получения списка LLM моделей без авторизации."""
        async for client in async_client:
            response = await client.get("/api/v1/models/llm")
            assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_list_llm_models_reader(self, async_client: AsyncClient, simple_user_token):
        """Тест получения списка LLM моделей с правами reader."""
        async for client in async_client:
            headers = {"Authorization": f"Bearer {simple_user_token}"}
            response = await client.get("/api/v1/models/llm", headers=headers)
            assert response.status_code == 200
            data = response.json()
            assert "models" in data
            assert isinstance(data["models"], list)
            
            # Проверяем, что есть базовые модели
            model_ids = [model["id"] for model in data["models"]]
            assert "gpt-3.5-turbo" in model_ids
            assert "llama-2-7b" in model_ids

    @pytest.mark.asyncio
    async def test_list_llm_models_admin(self, async_client: AsyncClient, simple_admin_token):
        """Тест получения списка LLM моделей с правами admin."""
        async for client in async_client:
            headers = {"Authorization": f"Bearer {simple_admin_token}"}
            response = await client.get("/api/v1/models/llm", headers=headers)
            assert response.status_code == 200
            data = response.json()
            assert "models" in data
            assert isinstance(data["models"], list)
            
            # Админ должен видеть больше моделей
            assert len(data["models"]) >= 2

    @pytest.mark.asyncio
    async def test_list_embeddings_models_unauthorized(self, async_client: AsyncClient):
        """Тест получения списка embedding моделей без авторизации."""
        async for client in async_client:
            response = await client.get("/api/v1/models/embeddings")
            assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_list_embeddings_models_authorized(self, async_client: AsyncClient, simple_user_token):
        """Тест получения списка embedding моделей с авторизацией."""
        async for client in async_client:
            headers = {"Authorization": f"Bearer {simple_user_token}"}
            response = await client.get("/api/v1/models/embeddings", headers=headers)
            assert response.status_code == 200
            data = response.json()
            assert "models" in data
            assert isinstance(data["models"], list)
            
            # Проверяем структуру модели
            if data["models"]:
                model = data["models"][0]
                assert "id" in model
                assert "name" in model
                assert "provider" in model
                assert "dimensions" in model

    @pytest.mark.asyncio
    async def test_model_role_isolation(self, async_client: AsyncClient, simple_user_token, simple_admin_token):
        """Тест изоляции моделей по ролям."""
        async for client in async_client:
            # Получаем модели для обычного пользователя
            headers_user = {"Authorization": f"Bearer {simple_user_token}"}
            response_user = await client.get("/api/v1/models/llm", headers=headers_user)
            assert response_user.status_code == 200
            user_models = response_user.json()["models"]
            
            # Получаем модели для админа
            headers_admin = {"Authorization": f"Bearer {simple_admin_token}"}
            response_admin = await client.get("/api/v1/models/llm", headers=headers_admin)
            assert response_admin.status_code == 200
            admin_models = response_admin.json()["models"]
            
            # Админ должен видеть больше или столько же моделей
            assert len(admin_models) >= len(user_models)
            
            # Все модели пользователя должны быть доступны админу
            user_model_ids = {model["id"] for model in user_models}
            admin_model_ids = {model["id"] for model in admin_models}
            assert user_model_ids.issubset(admin_model_ids)

    @pytest.mark.asyncio
    async def test_model_structure(self, async_client: AsyncClient, simple_user_token):
        """Тест структуры модели."""
        async for client in async_client:
            headers = {"Authorization": f"Bearer {simple_user_token}"}
            response = await client.get("/api/v1/models/llm", headers=headers)
            assert response.status_code == 200
            data = response.json()
            
            if data["models"]:
                model = data["models"][0]
                required_fields = ["id", "name", "provider", "version", "context_window", "capabilities", "available"]
                for field in required_fields:
                    assert field in model, f"Missing field: {field}"
                
                # Проверяем типы полей
                assert isinstance(model["id"], str)
                assert isinstance(model["name"], str)
                assert isinstance(model["provider"], str)
                assert isinstance(model["version"], str)
                assert isinstance(model["context_window"], int)
                assert isinstance(model["capabilities"], list)
                assert isinstance(model["available"], bool)

    @pytest.mark.asyncio
    async def test_model_capabilities(self, async_client: AsyncClient, simple_user_token):
        """Тест возможностей моделей."""
        async for client in async_client:
            headers = {"Authorization": f"Bearer {simple_user_token}"}
            response = await client.get("/api/v1/models/llm", headers=headers)
            assert response.status_code == 200
            data = response.json()
            
            for model in data["models"]:
                capabilities = model["capabilities"]
                assert isinstance(capabilities, list)
                # Проверяем, что есть хотя бы одна возможность
                assert len(capabilities) > 0
                
                # Проверяем валидные возможности
                valid_capabilities = ["chat", "completion", "embedding", "image", "audio"]
                for capability in capabilities:
                    assert capability in valid_capabilities, f"Invalid capability: {capability}"

    @pytest.mark.asyncio
    async def test_model_availability(self, async_client: AsyncClient, simple_user_token):
        """Тест доступности моделей."""
        async for client in async_client:
            headers = {"Authorization": f"Bearer {simple_user_token}"}
            response = await client.get("/api/v1/models/llm", headers=headers)
            assert response.status_code == 200
            data = response.json()
            
            # Проверяем, что есть хотя бы одна доступная модель
            available_models = [model for model in data["models"] if model["available"]]
            assert len(available_models) > 0, "No available models found"

    @pytest.mark.asyncio
    async def test_embedding_model_dimensions(self, async_client: AsyncClient, simple_user_token):
        """Тест размерности embedding моделей."""
        async for client in async_client:
            headers = {"Authorization": f"Bearer {simple_user_token}"}
            response = await client.get("/api/v1/models/embeddings", headers=headers)
            assert response.status_code == 200
            data = response.json()
            
            for model in data["models"]:
                dimensions = model["dimensions"]
                assert isinstance(dimensions, int)
                assert dimensions > 0, f"Invalid dimensions: {dimensions}"
                # Проверяем разумные размерности (обычно 384, 512, 768, 1024, 1536)
                assert dimensions in [384, 512, 768, 1024, 1536, 2048], f"Unexpected dimensions: {dimensions}"
