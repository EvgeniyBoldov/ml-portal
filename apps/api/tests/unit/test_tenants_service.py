"""
Unit tests for AsyncTenantsService
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime, timezone

from app.services.tenants_service import AsyncTenantsService
from app.models.model_registry import ModelType, ModelStatus


class TestAsyncTenantsService:
    """Test AsyncTenantsService methods"""
    
    @pytest.fixture
    def mock_session(self):
        """Mock SQLAlchemy async session"""
        return AsyncMock()
    
    @pytest.fixture
    def mock_tenants_repo(self):
        """Mock tenants repository"""
        repo = AsyncMock()
        repo.get_by_id = AsyncMock(return_value=None)
        repo.list = AsyncMock(return_value=[])
        repo.create = AsyncMock()
        repo.update = AsyncMock()
        repo.delete = AsyncMock(return_value=True)
        return repo
    
    @pytest.fixture
    def mock_model_repo(self):
        """Mock model registry repository"""
        repo = AsyncMock()
        repo.get_by_alias = AsyncMock(return_value=None)
        repo.get_global_by_type = AsyncMock(return_value=None)
        return repo
    
    @pytest.fixture
    def tenants_service(self, mock_session, mock_tenants_repo, mock_model_repo):
        """Create AsyncTenantsService with mock repos"""
        service = AsyncTenantsService(mock_session)
        service.repo = mock_tenants_repo
        service.model_repo = mock_model_repo
        return service
    
    @pytest.fixture
    def sample_tenant(self):
        """Create sample tenant mock"""
        tenant = MagicMock()
        tenant.id = uuid4()
        tenant.name = "Test Tenant"
        tenant.description = "Test description"
        tenant.is_active = True
        tenant.embedding_model_alias = None
        tenant.ocr = True
        tenant.layout = False
        tenant.created_at = datetime.now(timezone.utc)
        tenant.updated_at = datetime.now(timezone.utc)
        return tenant
    
    @pytest.fixture
    def sample_embed_model(self):
        """Create sample embedding model mock"""
        model = MagicMock()
        model.id = uuid4()
        model.alias = "text-embedding-ada-002"
        model.type = ModelType.EMBEDDING
        model.status = ModelStatus.AVAILABLE
        model.default_for_type = True
        model.model_version = "1.0"
        model.extra_config = {"vector_dim": 1536}
        return model
    
    @pytest.fixture
    def sample_rerank_model(self):
        """Create sample reranker model mock"""
        model = MagicMock()
        model.id = uuid4()
        model.alias = "rerank-v1"
        model.type = ModelType.RERANKER
        model.status = ModelStatus.AVAILABLE
        model.default_for_type = True
        model.model_version = "1.0"
        return model


class TestGetTenant(TestAsyncTenantsService):
    """Test get_tenant method"""
    
    @pytest.mark.asyncio
    async def test_get_tenant_found(
        self, tenants_service, mock_tenants_repo, mock_model_repo, 
        sample_tenant, sample_embed_model, sample_rerank_model
    ):
        """Should return tenant when found"""
        mock_tenants_repo.get_by_id.return_value = sample_tenant
        mock_model_repo.get_global_by_type.side_effect = [sample_embed_model, sample_rerank_model]
        
        result = await tenants_service.get_tenant(str(sample_tenant.id))
        
        assert result is not None
        assert result["id"] == str(sample_tenant.id)
        assert result["name"] == sample_tenant.name
    
    @pytest.mark.asyncio
    async def test_get_tenant_not_found(self, tenants_service, mock_tenants_repo):
        """Should return None when not found"""
        mock_tenants_repo.get_by_id.return_value = None
        
        result = await tenants_service.get_tenant(str(uuid4()))
        
        assert result is None


class TestListTenants(TestAsyncTenantsService):
    """Test list_tenants method"""
    
    @pytest.mark.asyncio
    async def test_list_tenants(
        self, tenants_service, mock_tenants_repo, mock_model_repo,
        sample_tenant, sample_embed_model, sample_rerank_model
    ):
        """Should list all tenants"""
        mock_tenants_repo.list.return_value = [sample_tenant]
        mock_model_repo.get_global_by_type.side_effect = [sample_embed_model, sample_rerank_model]
        
        result = await tenants_service.list_tenants()
        
        assert len(result) == 1
        assert result[0]["name"] == sample_tenant.name
    
    @pytest.mark.asyncio
    async def test_list_tenants_empty(self, tenants_service, mock_tenants_repo):
        """Should return empty list when no tenants"""
        mock_tenants_repo.list.return_value = []
        
        result = await tenants_service.list_tenants()
        
        assert result == []
    
    @pytest.mark.asyncio
    async def test_list_tenants_with_limit(self, tenants_service, mock_tenants_repo):
        """Should pass limit to repository"""
        mock_tenants_repo.list.return_value = []
        
        await tenants_service.list_tenants(limit=50)
        
        mock_tenants_repo.list.assert_called_once_with(limit=50)


class TestCreateTenant(TestAsyncTenantsService):
    """Test create_tenant method"""
    
    @pytest.mark.asyncio
    async def test_create_tenant_success(
        self, tenants_service, mock_tenants_repo, mock_model_repo,
        sample_tenant, sample_embed_model, sample_rerank_model
    ):
        """Should create tenant successfully"""
        mock_tenants_repo.create.return_value = sample_tenant
        mock_model_repo.get_global_by_type.side_effect = [sample_embed_model, sample_rerank_model]
        
        result = await tenants_service.create_tenant({
            "name": "New Tenant",
            "description": "New description"
        })
        
        assert result is not None
        mock_tenants_repo.create.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_create_tenant_missing_name(self, tenants_service):
        """Should raise ValueError for missing name"""
        with pytest.raises(ValueError) as exc_info:
            await tenants_service.create_tenant({"description": "No name"})
        
        assert "name is required" in str(exc_info.value).lower()
    
    @pytest.mark.asyncio
    async def test_create_tenant_maps_extra_embed_model(
        self, tenants_service, mock_tenants_repo, mock_model_repo,
        sample_tenant, sample_embed_model, sample_rerank_model
    ):
        """Should map extra_embed_model to embedding_model_alias"""
        extra_model = MagicMock()
        extra_model.type = ModelType.EMBEDDING
        extra_model.status = ModelStatus.AVAILABLE
        extra_model.default_for_type = False
        mock_model_repo.get_by_alias.return_value = extra_model
        mock_tenants_repo.create.return_value = sample_tenant
        mock_model_repo.get_global_by_type.side_effect = [sample_embed_model, sample_rerank_model]
        
        await tenants_service.create_tenant({
            "name": "Tenant",
            "extra_embed_model": "custom-embed"
        })
        
        call_kwargs = mock_tenants_repo.create.call_args.kwargs
        assert "embedding_model_alias" in call_kwargs
        assert "extra_embed_model" not in call_kwargs


class TestUpdateTenant(TestAsyncTenantsService):
    """Test update_tenant method"""
    
    @pytest.mark.asyncio
    async def test_update_tenant_success(
        self, tenants_service, mock_tenants_repo, mock_model_repo,
        sample_tenant, sample_embed_model, sample_rerank_model
    ):
        """Should update tenant successfully"""
        mock_tenants_repo.update.return_value = sample_tenant
        mock_model_repo.get_global_by_type.side_effect = [sample_embed_model, sample_rerank_model]
        
        result = await tenants_service.update_tenant(
            str(sample_tenant.id),
            {"name": "Updated Name"}
        )
        
        assert result is not None
        mock_tenants_repo.update.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_update_tenant_not_found(self, tenants_service, mock_tenants_repo):
        """Should return None when tenant not found"""
        mock_tenants_repo.update.return_value = None
        
        result = await tenants_service.update_tenant(str(uuid4()), {"name": "New"})
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_update_tenant_maps_extra_embed_model(
        self, tenants_service, mock_tenants_repo, mock_model_repo,
        sample_tenant, sample_embed_model, sample_rerank_model
    ):
        """Should map extra_embed_model to embedding_model_alias"""
        extra_model = MagicMock()
        extra_model.type = ModelType.EMBEDDING
        extra_model.status = ModelStatus.AVAILABLE
        extra_model.default_for_type = False
        mock_model_repo.get_by_alias.return_value = extra_model
        mock_tenants_repo.update.return_value = sample_tenant
        mock_model_repo.get_global_by_type.side_effect = [sample_embed_model, sample_rerank_model]
        
        await tenants_service.update_tenant(
            str(sample_tenant.id),
            {"extra_embed_model": "custom-embed"}
        )
        
        call_kwargs = mock_tenants_repo.update.call_args.kwargs
        assert "embedding_model_alias" in call_kwargs


class TestDeleteTenant(TestAsyncTenantsService):
    """Test delete_tenant method"""
    
    @pytest.mark.asyncio
    async def test_delete_tenant_success(self, tenants_service, mock_tenants_repo):
        """Should delete tenant successfully"""
        mock_tenants_repo.delete.return_value = True
        
        result = await tenants_service.delete_tenant(str(uuid4()))
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_delete_tenant_not_found(self, tenants_service, mock_tenants_repo):
        """Should return False when tenant not found"""
        mock_tenants_repo.delete.return_value = False
        
        result = await tenants_service.delete_tenant(str(uuid4()))
        
        assert result is False


class TestValidateTenantModels(TestAsyncTenantsService):
    """Test validate_tenant_models method"""
    
    @pytest.mark.asyncio
    async def test_validate_none_alias(self, tenants_service):
        """Should pass for None alias"""
        await tenants_service.validate_tenant_models(None)
        # No exception = success
    
    @pytest.mark.asyncio
    async def test_validate_model_not_found(self, tenants_service, mock_model_repo):
        """Should raise ValueError for non-existent model"""
        mock_model_repo.get_by_alias.return_value = None
        
        with pytest.raises(ValueError) as exc_info:
            await tenants_service.validate_tenant_models("nonexistent")
        
        assert "not found" in str(exc_info.value).lower()
    
    @pytest.mark.asyncio
    async def test_validate_wrong_type(self, tenants_service, mock_model_repo):
        """Should raise ValueError for non-embedding model"""
        model = MagicMock()
        model.type = ModelType.LLM_CHAT
        mock_model_repo.get_by_alias.return_value = model
        
        with pytest.raises(ValueError) as exc_info:
            await tenants_service.validate_tenant_models("llm-model")
        
        assert "not an embedding model" in str(exc_info.value).lower()
    
    @pytest.mark.asyncio
    async def test_validate_unavailable_model(self, tenants_service, mock_model_repo):
        """Should raise ValueError for unavailable model"""
        model = MagicMock()
        model.type = ModelType.EMBEDDING
        model.status = ModelStatus.UNAVAILABLE
        mock_model_repo.get_by_alias.return_value = model
        
        with pytest.raises(ValueError) as exc_info:
            await tenants_service.validate_tenant_models("unavailable-embed")
        
        assert "not available" in str(exc_info.value).lower()
    
    @pytest.mark.asyncio
    async def test_validate_default_model_rejected(self, tenants_service, mock_model_repo):
        """Should raise ValueError for default model"""
        model = MagicMock()
        model.type = ModelType.EMBEDDING
        model.status = ModelStatus.AVAILABLE
        model.default_for_type = True
        mock_model_repo.get_by_alias.return_value = model
        
        with pytest.raises(ValueError) as exc_info:
            await tenants_service.validate_tenant_models("default-embed")
        
        assert "default" in str(exc_info.value).lower()
    
    @pytest.mark.asyncio
    async def test_validate_valid_model(self, tenants_service, mock_model_repo):
        """Should pass for valid extra embedding model"""
        model = MagicMock()
        model.type = ModelType.EMBEDDING
        model.status = ModelStatus.AVAILABLE
        model.default_for_type = False
        mock_model_repo.get_by_alias.return_value = model
        
        await tenants_service.validate_tenant_models("valid-embed")
        # No exception = success


class TestGetTenantActiveModels(TestAsyncTenantsService):
    """Test get_tenant_active_models method"""
    
    @pytest.mark.asyncio
    async def test_get_active_models_success(
        self, tenants_service, mock_tenants_repo, mock_model_repo,
        sample_tenant, sample_embed_model, sample_rerank_model
    ):
        """Should return active models for tenant"""
        mock_tenants_repo.get_by_id.return_value = sample_tenant
        mock_model_repo.get_global_by_type.side_effect = [sample_embed_model, sample_rerank_model]
        
        result = await tenants_service.get_tenant_active_models(str(sample_tenant.id))
        
        assert "embed_models" in result
        assert "rerank_model" in result
        assert "ocr" in result
        assert "layout" in result
    
    @pytest.mark.asyncio
    async def test_get_active_models_tenant_not_found(self, tenants_service, mock_tenants_repo):
        """Should raise ValueError for non-existent tenant"""
        mock_tenants_repo.get_by_id.return_value = None
        
        with pytest.raises(ValueError) as exc_info:
            await tenants_service.get_tenant_active_models(str(uuid4()))
        
        assert "not found" in str(exc_info.value).lower()


class TestBuildTenantResponse(TestAsyncTenantsService):
    """Test _build_tenant_response method"""
    
    @pytest.mark.asyncio
    async def test_build_response_with_global_models(
        self, tenants_service, mock_model_repo, sample_tenant, 
        sample_embed_model, sample_rerank_model
    ):
        """Should include global models in response"""
        mock_model_repo.get_global_by_type.side_effect = [sample_embed_model, sample_rerank_model]
        
        result = await tenants_service._build_tenant_response(sample_tenant)
        
        assert len(result["embed_models"]) == 1
        assert result["embed_models"][0] == sample_embed_model.alias
        assert result["rerank_model"] == sample_rerank_model.alias
    
    @pytest.mark.asyncio
    async def test_build_response_with_extra_embed_model(
        self, tenants_service, mock_model_repo, sample_tenant,
        sample_embed_model, sample_rerank_model
    ):
        """Should include extra embedding model"""
        sample_tenant.embedding_model_alias = "extra-embed"
        
        extra_model = MagicMock()
        extra_model.alias = "extra-embed"
        extra_model.status = ModelStatus.AVAILABLE
        extra_model.model_version = "2.0"
        extra_model.extra_config = {"vector_dim": 768}
        
        mock_model_repo.get_global_by_type.side_effect = [sample_embed_model, sample_rerank_model]
        mock_model_repo.get_by_alias.return_value = extra_model
        
        result = await tenants_service._build_tenant_response(sample_tenant)
        
        assert len(result["embed_models"]) == 2
        assert "extra-embed" in result["embed_models"]
    
    @pytest.mark.asyncio
    async def test_build_response_no_global_models(
        self, tenants_service, mock_model_repo, sample_tenant
    ):
        """Should handle missing global models"""
        mock_model_repo.get_global_by_type.return_value = None
        
        result = await tenants_service._build_tenant_response(sample_tenant)
        
        assert result["embed_models"] == []
        assert result["rerank_model"] is None
    
    @pytest.mark.asyncio
    async def test_build_response_includes_all_fields(
        self, tenants_service, mock_model_repo, sample_tenant,
        sample_embed_model, sample_rerank_model
    ):
        """Should include all required fields"""
        mock_model_repo.get_global_by_type.side_effect = [sample_embed_model, sample_rerank_model]
        
        result = await tenants_service._build_tenant_response(sample_tenant)
        
        assert "id" in result
        assert "name" in result
        assert "description" in result
        assert "is_active" in result
        assert "embed_models" in result
        assert "embed_models_info" in result
        assert "rerank_model" in result
        assert "rerank_model_info" in result
        assert "extra_embed_model" in result
        assert "ocr" in result
        assert "layout" in result
        assert "created_at" in result
        assert "updated_at" in result
