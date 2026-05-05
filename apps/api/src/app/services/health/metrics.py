"""Metrics collector for health monitoring and system observability."""
from __future__ import annotations

from typing import Dict, Any, List
from datetime import datetime, timezone
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from prometheus_client.core import GaugeMetricFamily, CounterMetricFamily

from app.core.logging import get_logger

logger = get_logger(__name__)


class MetricsCollector:
    """Custom Prometheus metrics collector for health monitoring."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self._metrics_cache = {}
        
        # Metric counters for quick access
        self.connector_count = 0
        self.healthy_connectors = 0
        self.unhealthy_connectors = 0
        
        self.model_count = 0
        self.healthy_models = 0
        self.unhealthy_models = 0
        
        self.total_discovered_tools = 0
        self.active_discovered_tools = 0
        
        self.collection_count = 0
        self.total_documents = 0
        self.documents_by_status = {}
    
    async def collect_all(self) -> None:
        """Collect all metrics from the database."""
        try:
            await self._collect_connector_metrics()
            await self._collect_model_metrics()
            await self._collect_discovery_metrics()
            await self._collect_collection_metrics()
        except Exception as e:
            logger.error(f"Failed to collect metrics: {e}")
    
    async def _collect_connector_metrics(self) -> None:
        """Collect MCP connector health metrics."""
        from app.models.tool_instance import ToolInstance
        
        # Total connectors
        stmt_total = select(func.count()).select_from(ToolInstance).where(
            ToolInstance.connector_type == 'mcp'
        )
        result = await self.session.execute(stmt_total)
        self.connector_count = result.scalar() or 0
        
        # Healthy connectors
        stmt_healthy = select(func.count()).select_from(ToolInstance).where(
            ToolInstance.connector_type == 'mcp',
            ToolInstance.is_active == True,
            ToolInstance.health_status == 'healthy'
        )
        result = await self.session.execute(stmt_healthy)
        self.healthy_connectors = result.scalar() or 0
        
        # Unhealthy connectors
        stmt_unhealthy = select(func.count()).select_from(ToolInstance).where(
            ToolInstance.connector_type == 'mcp',
            ToolInstance.is_active == True,
            ToolInstance.health_status == 'unhealthy'
        )
        result = await self.session.execute(stmt_unhealthy)
        self.unhealthy_connectors = result.scalar() or 0
    
    async def _collect_model_metrics(self) -> None:
        """Collect model health metrics."""
        from app.models.model_registry import Model
        
        # Total available models
        stmt_total = select(func.count()).select_from(Model).where(
            Model.status == 'AVAILABLE'
        )
        result = await self.session.execute(stmt_total)
        self.model_count = result.scalar() or 0
        
        # Healthy models
        stmt_healthy = select(func.count()).select_from(Model).where(
            Model.status == 'AVAILABLE',
            Model.health_status == 'healthy'
        )
        result = await self.session.execute(stmt_healthy)
        self.healthy_models = result.scalar() or 0
        
        # Unhealthy models
        stmt_unhealthy = select(func.count()).select_from(Model).where(
            Model.status == 'AVAILABLE',
            Model.health_status == 'unhealthy'
        )
        result = await self.session.execute(stmt_unhealthy)
        self.unhealthy_models = result.scalar() or 0
    
    async def _collect_discovery_metrics(self) -> None:
        """Collect tool discovery metrics."""
        from app.models.discovered_tool import DiscoveredTool
        
        # Total discovered tools
        stmt_total = select(func.count()).select_from(DiscoveredTool)
        result = await self.session.execute(stmt_total)
        self.total_discovered_tools = result.scalar() or 0
        
        # Active discovered tools
        stmt_active = select(func.count()).select_from(DiscoveredTool).where(
            DiscoveredTool.is_active == True
        )
        result = await self.session.execute(stmt_active)
        self.active_discovered_tools = result.scalar() or 0
    
    async def _collect_collection_metrics(self) -> None:
        """Collect collection and document metrics."""
        # Total collections
        stmt_collections = select(func.count()).select_from(text("collections"))
        result = await self.session.execute(stmt_collections)
        self.collection_count = result.scalar() or 0
        
        # Total documents
        stmt_docs = select(func.count()).select_from(text("collection_documents"))
        result = await self.session.execute(stmt_docs)
        self.total_documents = result.scalar() or 0
        
        # Documents by status
        stmt_status = select(
            text("status"),
            func.count().label("count")
        ).select_from(text("collection_documents")).group_by(text("status"))
        
        result = await self.session.execute(stmt_status)
        self.documents_by_status = {row.status: row.count for row in result}
    
    def collect(self) -> List[GaugeMetricFamily]:
        """Generate Prometheus metrics."""
        metrics = []
        
        # Connector metrics
        metrics.append(GaugeMetricFamily(
            'ml_portal_connectors_total',
            'Total number of MCP connectors',
            value=self.connector_count
        ))
        
        metrics.append(GaugeMetricFamily(
            'ml_portal_connectors_healthy',
            'Number of healthy MCP connectors',
            value=self.healthy_connectors
        ))
        
        metrics.append(GaugeMetricFamily(
            'ml_portal_connectors_unhealthy',
            'Number of unhealthy MCP connectors',
            value=self.unhealthy_connectors
        ))
        
        # Model metrics
        metrics.append(GaugeMetricFamily(
            'ml_portal_models_total',
            'Total number of available models',
            value=self.model_count
        ))
        
        metrics.append(GaugeMetricFamily(
            'ml_portal_models_healthy',
            'Number of healthy models',
            value=self.healthy_models
        ))
        
        metrics.append(GaugeMetricFamily(
            'ml_portal_models_unhealthy',
            'Number of unhealthy models',
            value=self.unhealthy_models
        ))
        
        # Discovery metrics
        metrics.append(GaugeMetricFamily(
            'ml_portal_discovered_tools_total',
            'Total number of discovered tools',
            value=self.total_discovered_tools
        ))
        
        metrics.append(GaugeMetricFamily(
            'ml_portal_discovered_tools_active',
            'Number of active discovered tools',
            value=self.active_discovered_tools
        ))
        
        # Collection metrics
        metrics.append(GaugeMetricFamily(
            'ml_portal_collections_total',
            'Total number of collections',
            value=self.collection_count
        ))
        
        metrics.append(GaugeMetricFamily(
            'ml_portal_documents_total',
            'Total number of documents',
            value=self.total_documents
        ))
        
        # Documents by status (multi-label metric)
        for status, count in self.documents_by_status.items():
            metrics.append(GaugeMetricFamily(
                'ml_portal_documents_by_status',
                'Number of documents by status',
                labels=[{'status': status}],
                value=count
            ))
        
        # Health check latency metrics (if available)
        # Note: These would be populated from health check results
        # For now, we'll create placeholder metrics
        
        return metrics
