"""Unit tests for HealthCheckEngine."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.model_registry import Model
from app.models.tool_instance import ToolInstance
from app.services.health.base import HealthStatus, HealthProbeResult, BackoffPolicy, BACKOFF_POLICY_1M
from app.services.health.engine import HealthCheckEngine, mark_instance_unhealthy, mark_model_unhealthy


class TestHealthCheckEngine:
    """Test cases for HealthCheckEngine."""
    
    @pytest.fixture
    def session(self):
        return AsyncMock(spec=AsyncSession)
    
    @pytest.fixture
    def engine(self, session):
        return HealthCheckEngine(session)
    
    @pytest.fixture
    def mcp_adapter(self):
        adapter = AsyncMock()
        adapter.probe.return_value = HealthProbeResult(
            status=HealthStatus.HEALTHY,
            latency_ms=50
        )
        return adapter
    
    @pytest.fixture
    def embedding_adapter(self):
        adapter = AsyncMock()
        adapter.probe.return_value = HealthProbeResult(
            status=HealthStatus.HEALTHY,
            latency_ms=100
        )
        return adapter
    
    def test_register_adapter(self, engine, mcp_adapter):
        """Test adapter registration."""
        engine.register_adapter("mcp_connector", mcp_adapter)
        
        assert "mcp_connector" in engine._adapters
        assert engine._adapters["mcp_connector"] == mcp_adapter
        assert engine._policies["mcp_connector"] == BACKOFF_POLICY_1M
    
    def test_register_adapter_with_custom_policy(self, engine, mcp_adapter):
        """Test adapter registration with custom policy."""
        custom_policy = BackoffPolicy(
            base_interval=timedelta(minutes=2),
            max_interval=timedelta(minutes=10),
            failure_threshold=5
        )
        
        engine.register_adapter("mcp_connector", mcp_adapter, custom_policy)
        
        assert engine._policies["mcp_connector"] == custom_policy
    
    @pytest.mark.asyncio
    async def test_check_tool_instances_success(self, engine, mcp_adapter):
        """Test successful tool instance health check."""
        engine.register_adapter("mcp_connector", mcp_adapter)
        
        # Mock database query
        mock_instance = MagicMock(spec=ToolInstance)
        mock_instance.id = uuid4()
        mock_instance.slug = "test-mcp"
        mock_instance.url = "http://localhost:8080"
        mock_instance.connector_type = "mcp"
        mock_instance.health_status = "healthy"
        mock_instance.consecutive_failures = 0
        mock_instance.last_error = None
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_instance]
        engine.session.execute.return_value = mock_result
        
        # Run health check
        results = await engine.check_tool_instances(connector_type="mcp")
        
        # Verify results
        assert len(results) == 1
        assert str(mock_instance.id) in results
        assert results[str(mock_instance.id)].status == HealthStatus.HEALTHY
        
        # Verify adapter was called
        mcp_adapter.probe.assert_called_once_with(mock_instance)
        
        # Verify session operations
        engine.session.flush.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_check_tool_instances_no_candidates(self, engine):
        """Test health check with no instances to check."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        engine.session.execute.return_value = mock_result
        
        results = await engine.check_tool_instances()
        
        assert results == {}
    
    @pytest.mark.asyncio
    async def test_check_tool_instances_adapter_failure(self, engine, mcp_adapter):
        """Test health check when adapter fails."""
        engine.register_adapter("mcp_connector", mcp_adapter)
        mcp_adapter.probe.side_effect = Exception("Connection failed")
        
        mock_instance = MagicMock(spec=ToolInstance)
        mock_instance.id = uuid4()
        mock_instance.connector_type = "mcp"
        mock_instance.consecutive_failures = 0
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_instance]
        engine.session.execute.return_value = mock_result
        
        results = await engine.check_tool_instances()
        
        assert len(results) == 1
        assert results[str(mock_instance.id)].status == HealthStatus.UNHEALTHY
        assert "Connection failed" in results[str(mock_instance.id)].error
    
    @pytest.mark.asyncio
    async def test_check_models_success(self, engine, embedding_adapter):
        """Test successful model health check."""
        engine.register_adapter("embedding_model", embedding_adapter)
        
        mock_model = MagicMock(spec=Model)
        mock_model.id = uuid4()
        mock_model.alias = "test-embedding"
        mock_model.type = "embedding"
        mock_model.health_status = "healthy"
        mock_model.consecutive_failures = 0
        mock_model.last_error = None
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_model]
        engine.session.execute.return_value = mock_result
        
        results = await engine.check_models(model_type="embedding")
        
        assert len(results) == 1
        assert str(mock_model.id) in results
        assert results[str(mock_model.id)].status == HealthStatus.HEALTHY
        
        embedding_adapter.probe.assert_called_once_with(mock_model)
        engine.session.flush.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_update_tool_instance_health_healthy(self, engine):
        """Test updating tool instance health when healthy."""
        instance = MagicMock(spec=ToolInstance)
        instance.consecutive_failures = 5
        instance.last_error = "Previous error"
        
        result = HealthProbeResult(status=HealthStatus.HEALTHY, latency_ms=50)
        now = datetime.now(timezone.utc)
        
        await engine._update_tool_instance_health(instance, result, now)
        
        assert instance.health_status == "healthy"
        assert instance.consecutive_failures == 0
        assert instance.last_error is None
        assert instance.next_check_at is not None
    
    @pytest.mark.asyncio
    async def test_update_tool_instance_health_unhealthy(self, engine):
        """Test updating tool instance health when unhealthy."""
        instance = MagicMock(spec=ToolInstance)
        instance.consecutive_failures = 0
        instance.last_error = None
        
        result = HealthProbeResult(
            status=HealthStatus.UNHEALTHY,
            error="Connection timeout"
        )
        now = datetime.now(timezone.utc)
        
        await engine._update_tool_instance_health(instance, result, now)
        
        assert instance.health_status == "unhealthy"
        assert instance.consecutive_failures == 1
        assert instance.last_error == "Connection timeout"
        assert instance.next_check_at is not None
    
    @pytest.mark.asyncio
    async def test_update_model_health_healthy(self, engine):
        """Test updating model health when healthy."""
        model = MagicMock(spec=Model)
        model.consecutive_failures = 3
        model.last_error = "Previous error"
        
        result = HealthProbeResult(status=HealthStatus.HEALTHY, latency_ms=100)
        now = datetime.now(timezone.utc)
        
        await engine._update_model_health(model, result, now)
        
        assert model.health_status == "healthy"
        assert model.consecutive_failures == 0
        assert model.last_error is None
        assert model.next_check_at is not None
    
    @pytest.mark.asyncio
    async def test_get_adapter_for_instance(self, engine, mcp_adapter):
        """Test getting adapter for tool instance."""
        engine.register_adapter("mcp_connector", mcp_adapter)
        
        instance = MagicMock(spec=ToolInstance)
        instance.connector_type = "mcp"
        
        adapter = engine._get_adapter_for_instance(instance)
        assert adapter == mcp_adapter
        
        # Test unknown type
        instance.connector_type = "unknown"
        adapter = engine._get_adapter_for_instance(instance)
        assert adapter is None
    
    @pytest.mark.asyncio
    async def test_get_adapter_for_model(self, engine, embedding_adapter):
        """Test getting adapter for model."""
        engine.register_adapter("embedding_model", embedding_adapter)
        
        model = MagicMock(spec=Model)
        model.type = "embedding"
        
        adapter = engine._get_adapter_for_model(model)
        assert adapter == embedding_adapter
        
        # Test unknown type
        model.type = "unknown"
        adapter = engine._get_adapter_for_model(model)
        assert adapter is None


class TestUtilityFunctions:
    """Test cases for utility functions."""
    
    @pytest.mark.asyncio
    async def test_mark_instance_unhealthy(self):
        """Test marking instance as unhealthy."""
        session = AsyncMock(spec=AsyncSession)
        instance_id = uuid4()
        error = "Connection failed"
        now = datetime.now(timezone.utc)
        
        await mark_instance_unhealthy(session, instance_id, error, now)
        
        # Verify SQL update was called
        session.execute.assert_called_once()
        call_args = session.execute.call_args[0][0]
        
        # Check that it's an update statement
        assert hasattr(call_args, 'where')
        
        # Verify parameters in the update
        values = call_args.values
        assert 'health_status' in values.compile().params
        assert 'consecutive_failures' in values.compile().params
        assert 'last_error' in values.compile().params
        assert 'next_check_at' in values.compile().params
    
    @pytest.mark.asyncio
    async def test_mark_model_unhealthy(self):
        """Test marking model as unhealthy."""
        session = AsyncMock(spec=AsyncSession)
        model_id = uuid4()
        error = "Model unavailable"
        now = datetime.now(timezone.utc)
        
        await mark_model_unhealthy(session, model_id, error, now)
        
        # Verify SQL update was called
        session.execute.assert_called_once()
        call_args = session.execute.call_args[0][0]
        
        # Check that it's an update statement
        assert hasattr(call_args, 'where')
        
        # Verify parameters in the update
        values = call_args.values
        assert 'health_status' in values.compile().params
        assert 'consecutive_failures' in values.compile().params
        assert 'last_error' in values.compile().params
        assert 'next_check_at' in values.compile().params
