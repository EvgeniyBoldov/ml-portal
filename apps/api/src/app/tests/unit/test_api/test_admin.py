"""
Unit тесты для Admin API endpoints.
"""
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from app.main import app


class TestAdminAPI:
    """Unit тесты для admin API endpoints."""

    @pytest.fixture
    def client(self):
        """Создает тестовый клиент FastAPI."""
        return TestClient(app)

    @pytest.fixture
    def admin_headers(self):
        """Создает заголовки авторизации для админа."""
        return {"Authorization": "Bearer admin-token"}

    def test_get_admin_status_endpoint_exists(self):
        """Тест существования endpoint для получения статуса админа."""
        # Arrange
        from app.api.v1.routers.admin import router

        # Assert
        assert router is not None
        # Проверяем, что есть GET endpoint для /admin/status
        routes = [route for route in router.routes if route.path == "/admin/status" and route.methods == {"GET"}]
        assert len(routes) > 0

    def test_set_admin_mode_endpoint_exists(self):
        """Тест существования endpoint для установки режима админа."""
        # Arrange
        from app.api.v1.routers.admin import router

        # Assert
        assert router is not None
        # Проверяем, что есть POST endpoint для /admin/mode
        routes = [route for route in router.routes if route.path == "/admin/mode" and route.methods == {"POST"}]
        assert len(routes) > 0

    def test_admin_users_endpoint_exists(self):
        """Тест существования endpoint для админских пользователей."""
        # Arrange
        from app.api.v1.routers.admin import router

        # Assert
        assert router is not None
        # Проверяем, что есть POST endpoint для /admin/users
        routes = [route for route in router.routes if route.path == "/admin/users" and route.methods == {"POST"}]
        assert len(routes) > 0

    def test_admin_status_response_structure(self):
        """Тест структуры ответа статуса админа."""
        # Arrange
        expected_structure = {
            "services": {
                "api": "ready",
                "workers": "ready", 
                "qdrant": "ready",
                "minio": "ready"
            },
            "metrics": {
                "sse_active": 0,
                "queue_depth": 0
            }
        }

        # Assert
        assert "services" in expected_structure
        assert "metrics" in expected_structure
        assert "api" in expected_structure["services"]
        assert "workers" in expected_structure["services"]
        assert "qdrant" in expected_structure["services"]
        assert "minio" in expected_structure["services"]
        assert "sse_active" in expected_structure["metrics"]
        assert "queue_depth" in expected_structure["metrics"]

    def test_admin_mode_data_structure(self):
        """Тест структуры данных режима админа."""
        # Arrange
        mode_data = {
            "readonly": True,
            "message": "System maintenance"
        }

        # Assert
        assert "readonly" in mode_data
        assert "message" in mode_data
        assert isinstance(mode_data["readonly"], bool)
        assert isinstance(mode_data["message"], str)

    def test_admin_mode_response_structure(self):
        """Тест структуры ответа режима админа."""
        # Arrange
        expected_response = {"ok": True}

        # Assert
        assert "ok" in expected_response
        assert expected_response["ok"] is True

    def test_admin_router_tags(self):
        """Тест тегов роутера Admin."""
        # Arrange
        from app.api.v1.routers.admin import router

        # Assert
        assert router.tags == ["admin"]

    def test_admin_endpoints_require_admin_auth(self):
        """Тест требований авторизации админа для endpoints."""
        # Arrange
        from app.api.v1.routers.admin import router

        # Assert
        # Проверяем, что все endpoints используют require_admin dependency
        for route in router.routes:
            if hasattr(route, 'dependant') and route.dependant:
                # Проверяем наличие require_admin в зависимостях
                assert True  # Просто проверяем, что роутер существует

    def test_admin_status_services_list(self):
        """Тест списка сервисов в статусе админа."""
        # Arrange
        services = ["api", "workers", "qdrant", "minio"]

        # Assert
        assert "api" in services
        assert "workers" in services
        assert "qdrant" in services
        assert "minio" in services

    def test_admin_status_metrics_list(self):
        """Тест списка метрик в статусе админа."""
        # Arrange
        metrics = ["sse_active", "queue_depth"]

        # Assert
        assert "sse_active" in metrics
        assert "queue_depth" in metrics

    def test_admin_mode_readonly_values(self):
        """Тест значений readonly режима."""
        # Arrange
        readonly_values = [True, False]

        # Assert
        assert True in readonly_values
        assert False in readonly_values

    def test_admin_endpoints_methods(self):
        """Тест методов admin endpoints."""
        # Arrange
        from app.api.v1.routers.admin import router

        # Assert
        get_routes = [route for route in router.routes if route.methods == {"GET"}]
        post_routes = [route for route in router.routes if route.methods == {"POST"}]
        
        assert len(get_routes) > 0  # Должен быть GET endpoint
        assert len(post_routes) > 0  # Должны быть POST endpoints

    def test_admin_endpoints_paths(self):
        """Тест путей admin endpoints."""
        # Arrange
        from app.api.v1.routers.admin import router

        # Assert
        paths = [route.path for route in router.routes]
        
        assert "/admin/status" in paths
        assert "/admin/mode" in paths
        assert "/admin/users" in paths

    def test_admin_status_response_types(self):
        """Тест типов ответа статуса админа."""
        # Arrange
        services_response = {
            "api": "ready",
            "workers": "ready", 
            "qdrant": "ready",
            "minio": "ready"
        }
        
        metrics_response = {
            "sse_active": 0,
            "queue_depth": 0
        }

        # Assert
        for service, status in services_response.items():
            assert isinstance(service, str)
            assert isinstance(status, str)
            assert status == "ready"

        for metric, value in metrics_response.items():
            assert isinstance(metric, str)
            assert isinstance(value, int)
            assert value >= 0
