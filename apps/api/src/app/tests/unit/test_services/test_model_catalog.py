"""
Unit тесты для ModelCatalog.
"""
import pytest


class TestModelCatalog:
    """Unit тесты для ModelCatalog."""

    @pytest.fixture
    def model_catalog(self):
        """Создает экземпляр ModelCatalog."""
        from app.services.model_catalog import ModelCatalog
        return ModelCatalog()

    def test_model_catalog_initialization(self, model_catalog):
        """Тест инициализации ModelCatalog."""
        # Assert
        assert model_catalog is not None
        assert hasattr(model_catalog, 'list_llm')
        assert hasattr(model_catalog, 'list_embeddings')

    def test_list_llm_method_exists(self, model_catalog):
        """Тест наличия метода list_llm."""
        # Assert
        assert callable(getattr(model_catalog, 'list_llm'))

    def test_list_embeddings_method_exists(self, model_catalog):
        """Тест наличия метода list_embeddings."""
        # Assert
        assert callable(getattr(model_catalog, 'list_embeddings'))

    def test_list_llm_without_tenant(self, model_catalog):
        """Тест list_llm без tenant_id."""
        # Act
        result = model_catalog.list_llm()

        # Assert
        assert isinstance(result, list)
        assert result == []

    def test_list_llm_with_tenant(self, model_catalog):
        """Тест list_llm с tenant_id."""
        # Arrange
        tenant_id = "test-tenant-123"

        # Act
        result = model_catalog.list_llm(tenant_id)

        # Assert
        assert isinstance(result, list)
        assert result == []

    def test_list_embeddings_without_tenant(self, model_catalog):
        """Тест list_embeddings без tenant_id."""
        # Act
        result = model_catalog.list_embeddings()

        # Assert
        assert isinstance(result, list)
        assert result == []

    def test_list_embeddings_with_tenant(self, model_catalog):
        """Тест list_embeddings с tenant_id."""
        # Arrange
        tenant_id = "test-tenant-123"

        # Act
        result = model_catalog.list_embeddings(tenant_id)

        # Assert
        assert isinstance(result, list)
        assert result == []

    def test_model_catalog_methods_signature(self, model_catalog):
        """Тест сигнатур методов ModelCatalog."""
        # Arrange
        import inspect

        # Act
        list_llm_sig = inspect.signature(model_catalog.list_llm)
        list_embeddings_sig = inspect.signature(model_catalog.list_embeddings)

        # Assert
        assert 'tenant_id' in list_llm_sig.parameters
        assert 'tenant_id' in list_embeddings_sig.parameters
        
        # Проверяем, что tenant_id имеет значение по умолчанию None
        assert list_llm_sig.parameters['tenant_id'].default is None
        assert list_embeddings_sig.parameters['tenant_id'].default is None

    def test_model_catalog_return_types(self, model_catalog):
        """Тест типов возвращаемых значений."""
        # Act
        llm_result = model_catalog.list_llm()
        embeddings_result = model_catalog.list_embeddings()

        # Assert
        assert isinstance(llm_result, list)
        assert isinstance(embeddings_result, list)

    def test_model_catalog_with_different_tenant_ids(self, model_catalog):
        """Тест ModelCatalog с разными tenant_id."""
        # Arrange
        tenant_ids = ["tenant1", "tenant2", "tenant3", None]

        # Act & Assert
        for tenant_id in tenant_ids:
            llm_result = model_catalog.list_llm(tenant_id)
            embeddings_result = model_catalog.list_embeddings(tenant_id)
            
            assert isinstance(llm_result, list)
            assert isinstance(embeddings_result, list)
            assert llm_result == []
            assert embeddings_result == []

    def test_model_catalog_attributes(self, model_catalog):
        """Тест атрибутов ModelCatalog."""
        # Assert
        assert hasattr(model_catalog, 'list_llm')
        assert hasattr(model_catalog, 'list_embeddings')

    def test_model_catalog_methods(self, model_catalog):
        """Тест методов ModelCatalog."""
        # Assert
        assert callable(getattr(model_catalog, 'list_llm'))
        assert callable(getattr(model_catalog, 'list_embeddings'))
