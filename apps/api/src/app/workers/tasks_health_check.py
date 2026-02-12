"""Periodic health check tasks for models

Runs health checks on all enabled models periodically.
Updates model status based on results.
"""
from __future__ import annotations
import asyncio
from app.core.logging import get_logger
from datetime import datetime, timezone

from celery import Task
from app.celery_app import app as celery_app
from app.core.db import get_session_factory
from app.services.model_service import ModelService
from app.services.model_health_checker import get_health_checker
from app.models.model_registry import HealthStatus

logger = get_logger(__name__)


@celery_app.task(
    queue="default",
    bind=True,
    acks_late=True,
    max_retries=0,
)
def health_check_all_models(self: Task) -> dict:
    """
    Periodic task to check health of all enabled models.
    
    Runs every 5 minutes (configured in celery beat schedule).
    Updates model health_status, health_latency_ms, health_error fields.
    Auto-disables models that fail health check.
    
    Returns:
        Dict with summary: total, healthy, unhealthy counts
    """
    logger.info("Starting periodic health check for all models")
    
    async def _check_all():
        session_factory = get_session_factory()
        health_checker = get_health_checker()
        
        results = {
            "total": 0,
            "healthy": 0,
            "unhealthy": 0,
            "errors": []
        }
        
        async with session_factory() as session:
            service = ModelService(session)
            models = await service.list_models(enabled_only=True)
            
            results["total"] = len(models)
            
            for model in models:
                try:
                    result = await health_checker.check_model(model, session=session)
                    
                    await service.update_health_status(
                        model.id,
                        result.status,
                        latency_ms=result.latency_ms,
                        error=result.error
                    )
                    
                    if result.status == HealthStatus.HEALTHY:
                        results["healthy"] += 1
                        logger.debug(f"✓ {model.alias}: healthy ({result.latency_ms}ms)")
                    else:
                        results["unhealthy"] += 1
                        logger.warning(f"✗ {model.alias}: {result.status.value} - {result.error}")
                        results["errors"].append({
                            "alias": model.alias,
                            "error": result.error
                        })
                        
                except Exception as e:
                    results["unhealthy"] += 1
                    logger.error(f"✗ {model.alias}: exception - {e}")
                    results["errors"].append({
                        "alias": model.alias,
                        "error": str(e)
                    })
            
            await session.commit()
        
        return results
    
    try:
        result = asyncio.run(_check_all())
        logger.info(
            f"Health check complete: {result['healthy']}/{result['total']} healthy, "
            f"{result['unhealthy']} unhealthy"
        )
        return result
    except Exception as e:
        logger.error(f"Health check task failed: {e}", exc_info=True)
        raise


@celery_app.task(
    queue="default",
    bind=True,
    acks_late=True,
    max_retries=3,
    default_retry_delay=60,
)
def health_check_single_model(self: Task, model_id: str) -> dict:
    """
    Check health of a single model.
    
    Args:
        model_id: UUID of the model to check
        
    Returns:
        Dict with model_id, alias, status, latency_ms, error
    """
    import uuid
    
    logger.info(f"Health check for model {model_id}")
    
    async def _check():
        session_factory = get_session_factory()
        health_checker = get_health_checker()
        
        async with session_factory() as session:
            service = ModelService(session)
            model = await service.get_by_id(uuid.UUID(model_id))
            
            if not model:
                raise ValueError(f"Model {model_id} not found")
            
            result = await health_checker.check_model(model, session=session)
            
            await service.update_health_status(
                model.id,
                result.status,
                latency_ms=result.latency_ms,
                error=result.error
            )
            
            await session.commit()
            
            return {
                "model_id": str(model.id),
                "alias": model.alias,
                "status": result.status.value,
                "latency_ms": result.latency_ms,
                "error": result.error
            }
    
    try:
        return asyncio.run(_check())
    except Exception as e:
        logger.error(f"Health check failed for {model_id}: {e}", exc_info=True)
        raise self.retry(exc=e)
