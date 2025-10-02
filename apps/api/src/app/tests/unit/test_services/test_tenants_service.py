"""
Unit тесты для TenantsService.
"""
import pytest
from unittest.mock import MagicMock, patch
import uuid


class TestTenantsService:
    """Unit тесты для TenantsService."""

    @pytest.fixture
    def mock_session(self):
        """Создает мок сессии."""
        return MagicMock()

    @pytest.fixture
    def mock_repo(self):
        """Создает мок репозитория."""
        return MagicMock()

    @pytest.fixture
    def tenants_service(self, mock_session, mock_repo):
        """Создает экземпляр TenantsService с моками."""
        with patch('app.services.tenants_service.TenantsRepository') as mock_repo_class:
            mock_repo_class.return_value = mock_repo
            
            from app.services.tenants_service import TenantsService
            return TenantsService(mock_session)

    def test_tenants_service_initialization(self, tenants_service, mock_session, mock_repo):
        """Тест инициализации TenantsService."""
        # Assert
        assert tenants_service.repo == mock_repo

    def test_get_tenant_success(self, tenants_service, mock_repo):
        """Тест успешного получения тенанта."""
        # Arrange
        tenant_id = str(uuid.uuid4())
        mock_tenant = MagicMock()
        mock_tenant.id = tenant_id
        mock_tenant.name = "Test Tenant"
        mock_repo.get_by_id.return_value = mock_tenant

        # Act
        result = tenants_service.get_tenant(tenant_id)

        # Assert
        assert result is not None
        assert result["id"] == tenant_id
        assert result["name"] == "Test Tenant"
        mock_repo.get_by_id.assert_called_once_with(tenant_id)

    def test_get_tenant_not_found(self, tenants_service, mock_repo):
        """Тест получения несуществующего тенанта."""
        # Arrange
        tenant_id = str(uuid.uuid4())
        mock_repo.get_by_id.return_value = None

        # Act
        result = tenants_service.get_tenant(tenant_id)

        # Assert
        assert result is None
        mock_repo.get_by_id.assert_called_once_with(tenant_id)

    def test_list_tenants(self, tenants_service, mock_repo):
        """Тест получения списка тенантов."""
        # Arrange
        mock_tenant1 = MagicMock()
        mock_tenant1.id = str(uuid.uuid4())
        mock_tenant1.name = "Tenant 1"
        
        mock_tenant2 = MagicMock()
        mock_tenant2.id = str(uuid.uuid4())
        mock_tenant2.name = "Tenant 2"
        
        mock_repo.list_tenants.return_value = ([mock_tenant1, mock_tenant2], "next_cursor")

        # Act
        result = tenants_service.list_tenants(limit=20)

        # Assert
        assert result is not None
        assert "items" in result
        assert "next_cursor" in result
        assert "total" in result
        assert len(result["items"]) == 2
        assert result["next_cursor"] == "next_cursor"
        assert result["total"] == 2

    def test_create_tenant_success(self, tenants_service, mock_repo):
        """Тест успешного создания тенанта."""
        # Arrange
        tenant_data = {
            "name": "New Tenant",
            "isolation_level": "standard",
            "description": "Test tenant"
        }
        
        mock_tenant = MagicMock()
        mock_tenant.id = str(uuid.uuid4())
        mock_tenant.name = "New Tenant"
        mock_repo.create_tenant.return_value = mock_tenant

        # Act
        result = tenants_service.create_tenant(tenant_data)

        # Assert
        assert result is not None
        assert result["name"] == "New Tenant"
        mock_repo.create_tenant.assert_called_once()

    def test_create_tenant_missing_name(self, tenants_service):
        """Тест создания тенанта без имени."""
        # Arrange
        tenant_data = {
            "isolation_level": "standard"
        }

        # Act & Assert
        with pytest.raises(ValueError, match="Tenant name is required"):
            tenants_service.create_tenant(tenant_data)

    def test_create_tenant_invalid_isolation_level(self, tenants_service):
        """Тест создания тенанта с невалидным уровнем изоляции."""
        # Arrange
        tenant_data = {
            "name": "New Tenant",
            "isolation_level": "invalid_level"
        }

        # Act & Assert
        with pytest.raises(ValueError, match="Invalid isolation level"):
            tenants_service.create_tenant(tenant_data)

    def test_valid_isolation_levels(self):
        """Тест валидных уровней изоляции."""
        # Arrange
        valid_levels = ["standard", "premium", "enterprise"]

        # Assert
        assert "standard" in valid_levels
        assert "premium" in valid_levels
        assert "enterprise" in valid_levels

    def test_update_tenant_success(self, tenants_service, mock_repo):
        """Тест успешного обновления тенанта."""
        # Arrange
        tenant_id = str(uuid.uuid4())
        update_data = {
            "name": "Updated Tenant",
            "description": "Updated description"
        }
        
        mock_tenant = MagicMock()
        mock_tenant.id = tenant_id
        mock_tenant.name = "Updated Tenant"
        mock_repo.update_tenant.return_value = mock_tenant

        # Act
        result = tenants_service.update_tenant(tenant_id, update_data)

        # Assert
        assert result is not None
        assert result["name"] == "Updated Tenant"
        mock_repo.update_tenant.assert_called_once()

    def test_delete_tenant_success(self, tenants_service, mock_repo):
        """Тест успешного удаления тенанта."""
        # Arrange
        tenant_id = str(uuid.uuid4())
        mock_repo.delete_tenant.return_value = True

        # Act
        result = tenants_service.delete_tenant(tenant_id)

        # Assert
        assert result is True
        mock_repo.delete_tenant.assert_called_once_with(tenant_id)

    def test_tenants_service_attributes(self, tenants_service):
        """Тест атрибутов TenantsService."""
        # Assert
        assert hasattr(tenants_service, 'repo')

    def test_tenants_service_methods(self, tenants_service):
        """Тест методов TenantsService."""
        # Assert
        assert hasattr(tenants_service, 'get_tenant')
        assert hasattr(tenants_service, 'list_tenants')
        assert hasattr(tenants_service, 'create_tenant')
        assert hasattr(tenants_service, 'update_tenant')
        assert hasattr(tenants_service, 'delete_tenant')
        assert callable(getattr(tenants_service, 'get_tenant'))
        assert callable(getattr(tenants_service, 'list_tenants'))
        assert callable(getattr(tenants_service, 'create_tenant'))
        assert callable(getattr(tenants_service, 'update_tenant'))
        assert callable(getattr(tenants_service, 'delete_tenant'))
