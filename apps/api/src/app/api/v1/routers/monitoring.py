"""Monitoring endpoints for health metrics and system observability."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from prometheus_client import CollectorRegistry, generate_latest, CONTENT_TYPE_LATEST
from prometheus_client.core import GaugeMetricFamily, CounterMetricFamily
from typing import Dict, Any

from app.api.deps import db_session
from app.services.health.metrics import MetricsCollector

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


@router.get("/metrics")
async def get_metrics(
    response: Response,
    session: AsyncSession = Depends(db_session)
) -> Response:
    """
    Prometheus metrics endpoint.
    
    Exposes metrics in Prometheus exposition format for:
    - Connector health status and latency
    - Model health status and latency  
    - Discovery metrics (tools found, updated, removed)
    - Collection metrics (documents by status)
    """
    collector = MetricsCollector(session)
    registry = CollectorRegistry()
    
    # Collect metrics
    await collector.collect_all()
    
    # Register custom metrics
    registry.register(collector)
    
    # Generate Prometheus output
    output = generate_latest(registry)
    
    response.headers["Content-Type"] = CONTENT_TYPE_LATEST
    return Response(content=output, media_type=CONTENT_TYPE_LATEST)


@router.get("/health")
async def health_check() -> Dict[str, str]:
    """Simple health check endpoint for load balancers."""
    return {"status": "healthy", "service": "ml-portal-api"}


@router.get("/health/detailed")
async def detailed_health_check(
    session: AsyncSession = Depends(db_session)
) -> Dict[str, Any]:
    """Detailed health check with system status."""
    collector = MetricsCollector(session)
    
    # Collect basic health metrics
    await collector.collect_all()
    
    return {
        "status": "healthy",
        "service": "ml-portal-api",
        "metrics": {
            "connectors": {
                "total": collector.connector_count,
                "healthy": collector.healthy_connectors,
                "unhealthy": collector.unhealthy_connectors
            },
            "models": {
                "total": collector.model_count,
                "healthy": collector.healthy_models,
                "unhealthy": collector.unhealthy_models
            },
            "discovery": {
                "total_tools": collector.total_discovered_tools,
                "active_tools": collector.active_discovered_tools
            }
        }
    }
