"""Periodic health monitoring tasks for connectors, models, and discovery.

Runs health checks on MCP connectors, embedding/rerank/LLM models, and discovery rescan.
Uses distributed locks to prevent concurrent execution across API replicas.
Implements backoff policy and event hooks for health transitions.
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional

from celery import Task
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.celery_app import app as celery_app
from app.core.logging import get_logger


def get_async_session():
    """Create async session for Celery tasks."""
    db_url = os.getenv("ASYNC_DB_URL") or os.getenv("DATABASE_URL", "").replace(
        "postgresql://", "postgresql+asyncpg://"
    )
    
    engine = create_async_engine(db_url)
    AsyncSessionLocal = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    return AsyncSessionLocal
from app.services.health import (
    HealthCheckEngine,
    MCPHealthAdapter,
    EmbeddingHealthAdapter,
    RerankHealthAdapter,
    LLMHealthAdapter,
    BACKOFF_POLICY_1M,
    BACKOFF_POLICY_10M,
)
from app.services.tool_discovery_service import ToolDiscoveryService

logger = get_logger(__name__)


# Distributed lock using Postgres advisory locks
async def acquire_advisory_lock(session: AsyncSession, lock_key: int) -> bool:
    """Acquire Postgres advisory lock for distributed coordination."""
    try:
        result = await session.execute(
            text("SELECT pg_try_advisory_lock(:lock_key)"),
            {"lock_key": lock_key}
        )
        return result.scalar()
    except Exception as e:
        logger.error(f"Failed to acquire advisory lock {lock_key}: {e}")
        return False


async def release_advisory_lock(session: AsyncSession, lock_key: int) -> bool:
    """Release Postgres advisory lock."""
    try:
        result = await session.execute(
            text("SELECT pg_advisory_unlock(:lock_key)"),
            {"lock_key": lock_key}
        )
        return result.scalar()
    except Exception as e:
        logger.error(f"Failed to release advisory lock {lock_key}: {e}")
        return False


def get_lock_key(task_name: str) -> int:
    """Generate consistent lock key for task."""
    return hash(task_name) & 0x7FFFFFFF  # Ensure positive integer


@celery_app.task(
    queue="health",
    bind=True,
    acks_late=True,
    max_retries=0,
)
def probe_mcp_connectors(self: Task) -> Dict[str, Any]:
    """
    Periodic health check for MCP connectors.
    
    Runs every 1 minute for active MCP connectors.
    Implements backoff policy and event hooks for health transitions.
    """
    task_name = "probe_mcp_connectors"
    lock_key = get_lock_key(task_name)
    
    async def _probe():
        AsyncSessionLocal = get_async_session()
        async with AsyncSessionLocal() as session:
            # Acquire distributed lock
            if not await acquire_advisory_lock(session, lock_key):
                logger.info(f"Another instance is already running {task_name}")
                return {"status": "skipped", "reason": "locked"}
            
            try:
                # Initialize health check engine
                engine = HealthCheckEngine(session)
                engine.register_adapter(
                    "mcp_connector", 
                    MCPHealthAdapter(), 
                    BACKOFF_POLICY_1M
                )
                
                # Snapshot health states BEFORE the engine overwrites them
                from sqlalchemy import select
                from app.models.tool_instance import ToolInstance
                mcp_stmt = select(ToolInstance.id, ToolInstance.health_status).where(
                    ToolInstance.is_active == True,
                    ToolInstance.connector_type == "mcp",
                )
                mcp_rows = await session.execute(mcp_stmt)
                previous_health_map: Dict[str, str] = {
                    str(row.id): str(row.health_status or "unknown")
                    for row in mcp_rows
                }
                
                # Run health checks
                results = await engine.check_tool_instances(connector_type="mcp", limit=50)
                
                # Process health transitions using the pre-check snapshot
                await _process_mcp_health_transitions(session, results, previous_health_map)
                
                await session.commit()
                
                summary = {
                    "status": "completed",
                    "checked": len(results),
                    "healthy": sum(1 for r in results.values() if r.is_healthy()),
                    "unhealthy": sum(1 for r in results.values() if not r.is_healthy()),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                
                logger.info(f"MCP connector health check: {summary}")
                return summary
                
            finally:
                await release_advisory_lock(session, lock_key)
    
    try:
        return asyncio.run(_probe())
    except Exception as e:
        logger.error(f"MCP connector health check failed: {e}", exc_info=True)
        raise


@celery_app.task(
    queue="health",
    bind=True,
    acks_late=True,
    max_retries=0,
)
def probe_data_connectors(self: Task) -> Dict[str, Any]:
    """
    Periodic health check for data connectors (e.g. SQL instances).

    Runs every 1 minute. Uses ToolInstanceHealthService which correctly
    routes connector_type=data/connector_subtype=sql through the MCP provider.
    """
    task_name = "probe_data_connectors"
    lock_key = get_lock_key(task_name)

    async def _probe():
        from sqlalchemy import select
        from app.models.tool_instance import ToolInstance
        from app.services.tool_instance_service import ToolInstanceService

        AsyncSessionLocal = get_async_session()
        async with AsyncSessionLocal() as session:
            if not await acquire_advisory_lock(session, lock_key):
                logger.info(f"Another instance is already running {task_name}")
                return {"status": "skipped", "reason": "locked"}

            try:
                stmt = select(ToolInstance).where(
                    ToolInstance.is_active == True,
                    ToolInstance.connector_type == "data",
                )
                result = await session.execute(stmt)
                instances = result.scalars().all()

                if not instances:
                    return {"status": "completed", "checked": 0}

                service = ToolInstanceService(session)
                healthy = 0
                unhealthy = 0

                for instance in instances:
                    try:
                        check = await service.health_service.check_health(instance.id)
                        if check.status == "healthy":
                            healthy += 1
                        else:
                            unhealthy += 1
                    except Exception as e:
                        logger.error(f"Data connector health check failed for {instance.id}: {e}")
                        unhealthy += 1

                await session.commit()

                summary = {
                    "status": "completed",
                    "checked": len(instances),
                    "healthy": healthy,
                    "unhealthy": unhealthy,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                logger.info(f"Data connector health check: {summary}")
                return summary

            finally:
                await release_advisory_lock(session, lock_key)

    try:
        return asyncio.run(_probe())
    except Exception as e:
        logger.error(f"Data connector health check failed: {e}", exc_info=True)
        raise


@celery_app.task(
    queue="health",
    bind=True,
    acks_late=True,
    max_retries=0,
)
def probe_embedding_models(self: Task) -> Dict[str, Any]:
    """
    Periodic health check for embedding models.
    
    Runs every 1 minute for available embedding models.
    """
    task_name = "probe_embedding_models"
    lock_key = get_lock_key(task_name)
    
    async def _probe():
        AsyncSessionLocal = get_async_session()
        async with AsyncSessionLocal() as session:
            if not await acquire_advisory_lock(session, lock_key):
                logger.info(f"Another instance is already running {task_name}")
                return {"status": "skipped", "reason": "locked"}
            
            try:
                engine = HealthCheckEngine(session)
                engine.register_adapter(
                    "embedding_model",
                    EmbeddingHealthAdapter(),
                    BACKOFF_POLICY_1M
                )
                
                results = await engine.check_models(model_type="embedding", limit=20)
                
                await session.commit()
                
                summary = {
                    "status": "completed",
                    "checked": len(results),
                    "healthy": sum(1 for r in results.values() if r.is_healthy()),
                    "unhealthy": sum(1 for r in results.values() if not r.is_healthy()),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                
                logger.info(f"Embedding model health check: {summary}")
                return summary
                
            finally:
                await release_advisory_lock(session, lock_key)
    
    try:
        return asyncio.run(_probe())
    except Exception as e:
        logger.error(f"Embedding model health check failed: {e}", exc_info=True)
        raise


@celery_app.task(
    queue="health",
    bind=True,
    acks_late=True,
    max_retries=0,
)
def probe_rerank_models(self: Task) -> Dict[str, Any]:
    """
    Periodic health check for rerank models.
    
    Runs every 1 minute for available rerank models.
    """
    task_name = "probe_rerank_models"
    lock_key = get_lock_key(task_name)
    
    async def _probe():
        AsyncSessionLocal = get_async_session()
        async with AsyncSessionLocal() as session:
            if not await acquire_advisory_lock(session, lock_key):
                logger.info(f"Another instance is already running {task_name}")
                return {"status": "skipped", "reason": "locked"}
            
            try:
                engine = HealthCheckEngine(session)
                engine.register_adapter(
                    "rerank_model",
                    RerankHealthAdapter(),
                    BACKOFF_POLICY_1M
                )
                
                results = await engine.check_models(model_type="rerank", limit=10)
                
                await session.commit()
                
                summary = {
                    "status": "completed",
                    "checked": len(results),
                    "healthy": sum(1 for r in results.values() if r.is_healthy()),
                    "unhealthy": sum(1 for r in results.values() if not r.is_healthy()),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                
                logger.info(f"Rerank model health check: {summary}")
                return summary
                
            finally:
                await release_advisory_lock(session, lock_key)
    
    try:
        return asyncio.run(_probe())
    except Exception as e:
        logger.error(f"Rerank model health check failed: {e}", exc_info=True)
        raise


@celery_app.task(
    queue="health",
    bind=True,
    acks_late=True,
    max_retries=0,
)
def probe_llm_models(self: Task) -> Dict[str, Any]:
    """
    Periodic health check for LLM models.
    
    Runs every 10 minutes for available LLM models (less frequent).
    """
    task_name = "probe_llm_models"
    lock_key = get_lock_key(task_name)
    
    async def _probe():
        AsyncSessionLocal = get_async_session()
        async with AsyncSessionLocal() as session:
            if not await acquire_advisory_lock(session, lock_key):
                logger.info(f"Another instance is already running {task_name}")
                return {"status": "skipped", "reason": "locked"}
            
            try:
                engine = HealthCheckEngine(session)
                engine.register_adapter(
                    "llm_model",
                    LLMHealthAdapter(),
                    BACKOFF_POLICY_10M
                )
                
                results = await engine.check_models(model_type="llm", limit=10)
                
                await session.commit()
                
                summary = {
                    "status": "completed",
                    "checked": len(results),
                    "healthy": sum(1 for r in results.values() if r.is_healthy()),
                    "unhealthy": sum(1 for r in results.values() if not r.is_healthy()),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                
                logger.info(f"LLM model health check: {summary}")
                return summary
                
            finally:
                await release_advisory_lock(session, lock_key)
    
    try:
        return asyncio.run(_probe())
    except Exception as e:
        logger.error(f"LLM model health check failed: {e}", exc_info=True)
        raise


@celery_app.task(
    queue="health",
    bind=True,
    acks_late=True,
    max_retries=0,
)
def rescan_discovery(self: Task) -> Dict[str, Any]:
    """
    Periodic discovery rescan for all active MCP providers.
    
    Runs every 10 minutes to refresh tool discovery.
    """
    task_name = "rescan_discovery"
    lock_key = get_lock_key(task_name)
    
    async def _rescan():
        AsyncSessionLocal = get_async_session()
        async with AsyncSessionLocal() as session:
            if not await acquire_advisory_lock(session, lock_key):
                logger.info(f"Another instance is already running {task_name}")
                return {"status": "skipped", "reason": "locked"}
            
            try:
                discovery_service = ToolDiscoveryService(session)
                
                # Get all active MCP providers
                from sqlalchemy import select
                from app.models.tool_instance import ToolInstance
                
                stmt = select(ToolInstance).where(
                    ToolInstance.is_active == True,
                    ToolInstance.connector_type == "mcp"
                )
                result = await session.execute(stmt)
                mcp_instances = result.scalars().all()
                
                rescan_results = []
                
                for instance in mcp_instances:
                    try:
                        # Rescan tools for this MCP provider (local tools are excluded here)
                        scan_result = await discovery_service.rescan(
                            include_local=False,
                            provider_instance_id=instance.id,
                        )

                        rescan_results.append({
                            "instance_id": str(instance.id),
                            "slug": instance.slug,
                            "tools_found": scan_result.get("mcp_upserted", 0),
                            "tools_updated": scan_result.get("mcp_upserted", 0),
                            "tools_removed": scan_result.get("marked_inactive", 0),
                            "scan_meta": scan_result,
                            "success": True
                        })
                        
                        logger.info(f"Discovery rescan for {instance.slug}: {scan_result}")
                        
                    except Exception as e:
                        logger.error(f"Discovery rescan failed for {instance.slug}: {e}")
                        rescan_results.append({
                            "instance_id": str(instance.id),
                            "slug": instance.slug,
                            "error": str(e),
                            "success": False
                        })
                
                await session.commit()
                
                summary = {
                    "status": "completed",
                    "providers_scanned": len(mcp_instances),
                    "successful_scans": sum(1 for r in rescan_results if r["success"]),
                    "failed_scans": sum(1 for r in rescan_results if not r["success"]),
                    "total_tools_found": sum(r.get("tools_found", 0) for r in rescan_results),
                    "total_tools_updated": sum(r.get("tools_updated", 0) for r in rescan_results),
                    "total_tools_removed": sum(r.get("tools_removed", 0) for r in rescan_results),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "details": rescan_results
                }
                
                logger.info(f"Discovery rescan complete: {summary}")
                return summary
                
            finally:
                await release_advisory_lock(session, lock_key)
    
    try:
        return asyncio.run(_rescan())
    except Exception as e:
        logger.error(f"Discovery rescan failed: {e}", exc_info=True)
        raise


async def _process_mcp_health_transitions(
    session: AsyncSession,
    results: Dict[str, Any],
    previous_health_map: Dict[str, str],
) -> None:
    """Process health transitions for MCP connectors with event hooks."""
    from sqlalchemy import select, update
    from app.models.tool_instance import ToolInstance
    from app.models.discovered_tool import DiscoveredTool
    
    for instance_id, result in results.items():
        try:
            stmt = select(ToolInstance).where(ToolInstance.id == instance_id)
            instance_result = await session.execute(stmt)
            instance = instance_result.scalar_one_or_none()
            
            if not instance:
                continue
            
            # Use pre-check snapshot — health_status is already updated by engine at this point
            previous_health = previous_health_map.get(str(instance_id), "unknown")
            current_health = "healthy" if result.is_healthy() else "unhealthy"
            
            if previous_health != current_health:
                logger.info(f"MCP {instance.slug} health transition: {previous_health} → {current_health}")
                
                # Healthy → Unhealthy: invalidate discovered tools
                if previous_health == "healthy" and current_health == "unhealthy":
                    await _invalidate_discovered_tools(session, instance_id)
                
                # Unhealthy → Healthy: trigger discovery rescan
                elif previous_health == "unhealthy" and current_health == "healthy":
                    await _schedule_discovery_rescan(session, instance)
        
        except Exception as e:
            logger.error(f"Failed to process health transition for {instance_id}: {e}")


async def _invalidate_discovered_tools(session: AsyncSession, instance_id: str) -> None:
    """Mark all discovered tools from an MCP provider as inactive."""
    from sqlalchemy import update
    from app.models.discovered_tool import DiscoveredTool
    
    stmt = (
        update(DiscoveredTool)
        .where(DiscoveredTool.provider_instance_id == str(instance_id))
        .values(is_active=False)
    )
    await session.execute(stmt)
    logger.info(f"Invalidated discovered tools for MCP provider {instance_id}")


async def _schedule_discovery_rescan(
    session: AsyncSession,
    instance: Any
) -> None:
    """Schedule immediate discovery rescan for recovered MCP provider."""
    # Update next_check_at to trigger immediate rescan
    from sqlalchemy import update
    from app.models.tool_instance import ToolInstance
    
    stmt = (
        update(ToolInstance)
        .where(ToolInstance.id == instance.id)
        .values(next_check_at=datetime.now(timezone.utc))
    )
    await session.execute(stmt)
    logger.info(f"Scheduled discovery rescan for recovered MCP provider {instance.slug}")
