"""
Unit tests for ModelService
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime, timezone

from app.services.model_service import ModelService
from app.models.model_registry import Model, ModelType, ModelStatus, HealthStatus


class TestModelService:
    """Test ModelService methods"""
    
    @pytest.fixture
    def mock_session(self):
        """Mock SQLAlchemy async session"""
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.execute = AsyncMock()
        return session
    
    @pytest.fixture
    def model_service(self, mock_session):
        """Create ModelService with mock session"""
        return ModelService(mock_session)
    
    @pytest.fixture
    def sample_model(self):
        """Create sample model mock"""
        model = MagicMock()
        model.id = uuid4()
        model.alias = "test-model"
        model.type = ModelType.LLM_CHAT
        model.status = ModelStatus.AVAILABLE
        model.provider = "openai"
        model.model_version = "gpt-3.5-turbo"
        model.default_for_type = False
        model.is_system = False
        model.deleted_at = None
        model.health_status = HealthStatus.HEALTHY
        model.health_latency_ms = 150
        model.health_error = None
        model.extra_config = {}
        return model


class TestCreateModel(TestModelService):
    """Test model creation"""
    
    @pytest.mark.asyncio
    async def test_create_model_success(self, model_service, mock_session):
        """Should create model successfully"""
        # Mock no existing model
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        
        data = {
            "alias": "new-model",
            "name": "New Model",
            "type": ModelType.LLM_CHAT,
            "provider": "openai",
            "provider_model_name": "gpt-4"
        }
        
        result = await model_service.create_model(data)
        
        assert result is not None
        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_create_model_duplicate_alias(self, model_service, mock_session, sample_model):
        """Should raise ValueError for duplicate alias"""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_model
        mock_session.execute.return_value = mock_result
        
        data = {
            "alias": "gpt-4",
            "name": "Duplicate",
            "type": ModelType.LLM_CHAT
        }
        
        with pytest.raises(ValueError) as exc_info:
            await model_service.create_model(data)
        
        assert "already exists" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_create_model_as_default_unsets_previous(self, model_service, mock_session):
        """Should unset previous default when creating new default"""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        
        data = {
            "alias": "new-default",
            "name": "New Default",
            "type": ModelType.LLM_CHAT,
            "default_for_type": True
        }
        
        await model_service.create_model(data)
        
        # Should have called execute twice: check alias + unset default
        assert mock_session.execute.call_count >= 2


class TestGetModel(TestModelService):
    """Test getting models"""
    
    @pytest.mark.asyncio
    async def test_get_by_id_found(self, model_service, mock_session, sample_model):
        """Should return model when found by ID"""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_model
        mock_session.execute.return_value = mock_result
        
        result = await model_service.get_by_id(sample_model.id)
        
        assert result == sample_model
    
    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, model_service, mock_session):
        """Should return None when not found"""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        
        result = await model_service.get_by_id(uuid4())
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_get_by_alias_found(self, model_service, mock_session, sample_model):
        """Should return model when found by alias"""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_model
        mock_session.execute.return_value = mock_result
        
        result = await model_service.get_by_alias("gpt-4")
        
        assert result == sample_model
    
    @pytest.mark.asyncio
    async def test_get_by_alias_not_found(self, model_service, mock_session):
        """Should return None when alias not found"""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        
        result = await model_service.get_by_alias("nonexistent")
        
        assert result is None


class TestListModels(TestModelService):
    """Test listing models"""
    
    @pytest.mark.asyncio
    async def test_list_models_all(self, model_service, mock_session):
        """Should list all models"""
        mock_models = [MagicMock(), MagicMock(), MagicMock()]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_models
        mock_session.execute.return_value = mock_result
        
        result = await model_service.list_models()
        
        assert len(result) == 3
    
    @pytest.mark.asyncio
    async def test_list_models_by_type(self, model_service, mock_session):
        """Should filter by type"""
        mock_models = [MagicMock()]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_models
        mock_session.execute.return_value = mock_result
        
        result = await model_service.list_models(type=ModelType.EMBEDDING)
        
        assert len(result) == 1
        mock_session.execute.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_list_models_by_status(self, model_service, mock_session):
        """Should filter by status"""
        mock_models = [MagicMock(), MagicMock()]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_models
        mock_session.execute.return_value = mock_result
        
        result = await model_service.list_models(status=ModelStatus.AVAILABLE)
        
        assert len(result) == 2
    
    @pytest.mark.asyncio
    async def test_list_models_enabled_only(self, model_service, mock_session):
        """Should filter enabled only"""
        mock_models = [MagicMock()]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_models
        mock_session.execute.return_value = mock_result
        
        result = await model_service.list_models(enabled_only=True)
        
        assert len(result) == 1
    
    @pytest.mark.asyncio
    async def test_list_models_with_search(self, model_service, mock_session):
        """Should filter by search term"""
        mock_models = [MagicMock()]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_models
        mock_session.execute.return_value = mock_result
        
        result = await model_service.list_models(search="gpt")
        
        assert len(result) == 1


class TestUpdateModel(TestModelService):
    """Test updating models"""
    
    @pytest.mark.asyncio
    async def test_update_model_success(self, model_service, mock_session, sample_model):
        """Should update model fields"""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_model
        mock_session.execute.return_value = mock_result
        
        result = await model_service.update_model(
            sample_model.id,
            {"name": "Updated Name", "enabled": False}
        )
        
        assert result is not None
        assert sample_model.name == "Updated Name"
        assert sample_model.enabled is False
        mock_session.flush.assert_called()
    
    @pytest.mark.asyncio
    async def test_update_model_not_found(self, model_service, mock_session):
        """Should return None for non-existent model"""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        
        result = await model_service.update_model(uuid4(), {"name": "New"})
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_update_model_set_default_unsets_previous(self, model_service, mock_session, sample_model):
        """Should unset previous default when setting new default"""
        sample_model.default_for_type = False
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_model
        mock_session.execute.return_value = mock_result
        
        await model_service.update_model(
            sample_model.id,
            {"default_for_type": True}
        )
        
        # Should call execute multiple times (get + unset default)
        assert mock_session.execute.call_count >= 2


class TestDeleteModel(TestModelService):
    """Test deleting models"""
    
    @pytest.mark.asyncio
    async def test_delete_model_success(self, model_service, mock_session, sample_model):
        """Should soft delete model"""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_model
        mock_session.execute.return_value = mock_result
        
        result = await model_service.delete_model(sample_model.id)
        
        assert result is True
        assert sample_model.deleted_at is not None
        assert sample_model.enabled is False
    
    @pytest.mark.asyncio
    async def test_delete_model_not_found(self, model_service, mock_session):
        """Should return False for non-existent model"""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        
        result = await model_service.delete_model(uuid4())
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_delete_system_model_raises(self, model_service, mock_session, sample_model):
        """Should raise ValueError for system model"""
        sample_model.is_system = True
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_model
        mock_session.execute.return_value = mock_result
        
        with pytest.raises(ValueError) as exc_info:
            await model_service.delete_model(sample_model.id)
        
        assert "Cannot delete system model" in str(exc_info.value)


class TestGetDefaultModel(TestModelService):
    """Test getting default model"""
    
    @pytest.mark.asyncio
    async def test_get_default_model_found(self, model_service, mock_session, sample_model):
        """Should return default model for type"""
        sample_model.default_for_type = True
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_model
        mock_session.execute.return_value = mock_result
        
        result = await model_service.get_default_model(ModelType.LLM_CHAT)
        
        assert result == sample_model
    
    @pytest.mark.asyncio
    async def test_get_default_model_not_found(self, model_service, mock_session):
        """Should return None when no default"""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        
        result = await model_service.get_default_model(ModelType.EMBEDDING)
        
        assert result is None


class TestUpdateHealthStatus(TestModelService):
    """Test updating health status"""
    
    @pytest.mark.asyncio
    async def test_update_health_healthy(self, model_service, mock_session, sample_model):
        """Should update health status to healthy"""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_model
        mock_session.execute.return_value = mock_result
        
        result = await model_service.update_health_status(
            sample_model.id,
            HealthStatus.HEALTHY,
            latency_ms=100
        )
        
        assert result is True
        assert sample_model.health_status == HealthStatus.HEALTHY
        assert sample_model.health_latency_ms == 100
        assert sample_model.last_health_check_at is not None
    
    @pytest.mark.asyncio
    async def test_update_health_unavailable_disables_model(self, model_service, mock_session, sample_model):
        """Should set status to UNAVAILABLE when health check fails"""
        sample_model.status = ModelStatus.AVAILABLE
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_model
        mock_session.execute.return_value = mock_result
        
        result = await model_service.update_health_status(
            sample_model.id,
            HealthStatus.UNAVAILABLE,
            error="Connection timeout"
        )
        
        assert result is True
        assert sample_model.health_status == HealthStatus.UNAVAILABLE
        assert sample_model.health_error == "Connection timeout"
        assert sample_model.status == ModelStatus.UNAVAILABLE
    
    @pytest.mark.asyncio
    async def test_update_health_healthy_restores_available(self, model_service, mock_session, sample_model):
        """Should restore AVAILABLE status when healthy again"""
        sample_model.status = ModelStatus.UNAVAILABLE
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_model
        mock_session.execute.return_value = mock_result
        
        result = await model_service.update_health_status(
            sample_model.id,
            HealthStatus.HEALTHY,
            latency_ms=50
        )
        
        assert result is True
        assert sample_model.status == ModelStatus.AVAILABLE
    
    @pytest.mark.asyncio
    async def test_update_health_not_found(self, model_service, mock_session):
        """Should return False for non-existent model"""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        
        result = await model_service.update_health_status(
            uuid4(),
            HealthStatus.HEALTHY
        )
        
        assert result is False
