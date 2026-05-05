"""Health check engine for periodic monitoring of system components."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Type, TypeVar, Union
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger
from app.models.model_registry import Model
from app.models.tool_instance import ToolInstance
from app.services.health.base import (
    HealthCheckAdapter,
    HealthCheckTarget,
    HealthProbeResult,
    HealthStatus,
    BackoffPolicy,
    add_jitter,
    BACKOFF_POLICY_1M,
    BACKOFF_POLICY_10M,
)

logger = get_logger(__name__)

T = TypeVar("T", bound=Union[ToolInstance, Model])


class HealthCheckEngine:
    """Engine for performing health checks on various system components."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self._adapters: Dict[str, HealthCheckAdapter] = {}
        self._policies: Dict[str, BackoffPolicy] = {}
        
    def register_adapter(
        self, 
        target_type: str, 
        adapter: HealthCheckAdapter,
        policy: Optional[BackoffPolicy] = None
    ) -> None:
        """Register a health check adapter for a target type.
        
        Args:
            target_type: Type identifier (e.g., "mcp_connector", "embedding_model")
            adapter: Health check adapter implementation
            policy: Backoff policy for this type (defaults to 1m policy)
        """
        self._adapters[target_type] = adapter
        self._policies[target_type] = policy or BACKOFF_POLICY_1M
        logger.info(f"Registered health check adapter for {target_type}")
    
    async def check_tool_instances(
        self,
        connector_type: Optional[str] = None,
        limit: Optional[int] = None
    ) -> Dict[str, HealthProbeResult]:
        """Check health of tool instances due for checking.
        
        Args:
            connector_type: Filter by connector type (e.g., "mcp")
            limit: Maximum number of instances to check
            
        Returns:
            Dict mapping instance_id to probe results
        """
        now = datetime.now(timezone.utc)
        
        # Build query for candidates
        stmt = select(ToolInstance).where(
            ToolInstance.is_active == True,
            ToolInstance.next_check_at <= now,
        )
        
        if connector_type:
            stmt = stmt.where(ToolInstance.connector_type == connector_type)
        
        if limit:
            stmt = stmt.limit(limit)
        
        result = await self.session.execute(stmt)
        instances = result.scalars().all()
        
        if not instances:
            logger.debug(f"No tool instances due for health check (connector_type={connector_type})")
            return {}
        
        logger.info(f"Checking {len(instances)} tool instances (connector_type={connector_type})")
        
        # Check each instance
        results = {}
        for instance in instances:
            try:
                adapter = self._get_adapter_for_instance(instance)
                if not adapter:
                    logger.warning(f"No adapter registered for instance {instance.id} (type: {instance.connector_type})")
                    continue
                
                probe_result = await adapter.probe(instance)
                results[str(instance.id)] = probe_result
                
                # Update instance health status
                await self._update_tool_instance_health(instance, probe_result, now)
                
            except Exception as e:
                logger.exception(f"Health check failed for instance {instance.id}: {e}")
                error_result = HealthProbeResult(
                    status=HealthStatus.UNHEALTHY,
                    error=str(e)
                )
                results[str(instance.id)] = error_result
                await self._update_tool_instance_health(instance, error_result, now)
        
        await self.session.flush()
        return results
    
    async def check_models(
        self,
        model_type: Optional[str] = None,
        limit: Optional[int] = None
    ) -> Dict[str, HealthProbeResult]:
        """Check health of models due for checking.
        
        Args:
            model_type: Filter by model type (e.g., "embedding", "rerank", "llm")
            limit: Maximum number of models to check
            
        Returns:
            Dict mapping model_id to probe results
        """
        now = datetime.now(timezone.utc)
        
        # Build query for candidates
        stmt = select(Model).where(
            Model.status == "AVAILABLE",  # Only check available models
            Model.next_check_at <= now,
        )
        
        if model_type:
            stmt = stmt.where(Model.type == model_type)
        
        if limit:
            stmt = stmt.limit(limit)
        
        result = await self.session.execute(stmt)
        models = result.scalars().all()
        
        if not models:
            logger.debug(f"No models due for health check (type={model_type})")
            return {}
        
        logger.info(f"Checking {len(models)} models (type={model_type})")
        
        # Check each model
        results = {}
        for model in models:
            try:
                adapter = self._get_adapter_for_model(model)
                if not adapter:
                    logger.warning(f"No adapter registered for model {model.id} (type: {model.type})")
                    continue
                
                probe_result = await adapter.probe(model)
                results[str(model.id)] = probe_result
                
                # Update model health status
                await self._update_model_health(model, probe_result, now)
                
            except Exception as e:
                logger.exception(f"Health check failed for model {model.id}: {e}")
                error_result = HealthProbeResult(
                    status=HealthStatus.UNHEALTHY,
                    error=str(e)
                )
                results[str(model.id)] = error_result
                await self._update_model_health(model, error_result, now)
        
        await self.session.flush()
        return results
    
    def _get_adapter_for_instance(self, instance: ToolInstance) -> Optional[HealthCheckAdapter]:
        """Get adapter for a tool instance."""
        if instance.connector_type == "mcp":
            return self._adapters.get("mcp_connector")
        return None
    
    def _get_adapter_for_model(self, model: Model) -> Optional[HealthCheckAdapter]:
        """Get adapter for a model."""
        return self._adapters.get(f"{model.type}_model")
    
    async def _update_tool_instance_health(
        self,
        instance: ToolInstance,
        result: HealthProbeResult,
        now: datetime
    ) -> None:
        """Update tool instance health status and schedule next check."""
        # Update health status
        if result.is_healthy():
            instance.health_status = "healthy"
            instance.consecutive_failures = 0
            instance.last_error = None
        else:
            instance.health_status = "unhealthy"
            instance.consecutive_failures += 1
            instance.last_error = result.error
        
        # Calculate next check time
        policy = self._policies.get("mcp_connector", BACKOFF_POLICY_1M)
        status = HealthStatus.HEALTHY if result.is_healthy() else HealthStatus.UNHEALTHY
        next_check = policy.compute_next_check(status, instance.consecutive_failures, now)
        instance.next_check_at = add_jitter(next_check)
        
        logger.debug(
            f"Updated instance {instance.id} health: {instance.health_status}, "
            f"failures: {instance.consecutive_failures}, next_check: {instance.next_check_at}"
        )
    
    async def _update_model_health(
        self,
        model: Model,
        result: HealthProbeResult,
        now: datetime
    ) -> None:
        """Update model health status and schedule next check."""
        # Update health status
        if result.is_healthy():
            model.health_status = "healthy"
            model.consecutive_failures = 0
            model.last_error = None
        else:
            model.health_status = "unhealthy"
            model.consecutive_failures += 1
            model.last_error = result.error
        
        # Calculate next check time
        model_type = f"{model.type}_model"
        policy = self._policies.get(model_type, BACKOFF_POLICY_1M)
        status = HealthStatus.HEALTHY if result.is_healthy() else HealthStatus.UNHEALTHY
        next_check = policy.compute_next_check(status, model.consecutive_failures, now)
        model.next_check_at = add_jitter(next_check)
        
        logger.debug(
            f"Updated model {model.id} health: {model.health_status}, "
            f"failures: {model.consecutive_failures}, next_check: {model.next_check_at}"
        )


# Utility functions for runtime health updates
async def mark_instance_unhealthy(
    session: AsyncSession,
    instance_id: UUID,
    error: str,
    now: Optional[datetime] = None
) -> None:
    """Mark a tool instance as unhealthy immediately (runtime push)."""
    if now is None:
        now = datetime.now(timezone.utc)
    
    stmt = (
        update(ToolInstance)
        .where(ToolInstance.id == instance_id)
        .values(
            health_status="unhealthy",
            consecutive_failures=ToolInstance.consecutive_failures + 1,
            last_error=error,
            next_check_at=now + timedelta(minutes=1),  # Check again soon
        )
    )
    await session.execute(stmt)
    logger.info(f"Marked instance {instance_id} unhealthy due to runtime error: {error}")


async def mark_model_unhealthy(
    session: AsyncSession,
    model_id: UUID,
    error: str,
    now: Optional[datetime] = None
) -> None:
    """Mark a model as unhealthy immediately (runtime push)."""
    if now is None:
        now = datetime.now(timezone.utc)
    
    stmt = (
        update(Model)
        .where(Model.id == model_id)
        .values(
            health_status="unhealthy",
            consecutive_failures=Model.consecutive_failures + 1,
            last_error=error,
            next_check_at=now + timedelta(minutes=1),  # Check again soon
        )
    )
    await session.execute(stmt)
    logger.info(f"Marked model {model_id} unhealthy due to runtime error: {error}")
