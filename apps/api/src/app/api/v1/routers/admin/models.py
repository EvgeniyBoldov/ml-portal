"""Models API endpoints (New Architecture)

CRUD operations for LLM and Embedding models.
No file system scanning - models are added manually.
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import db_uow, get_current_user, require_admin
from app.core.security import UserCtx
from app.services.model_service import ModelService
from app.models.model_registry import Model
from app.schemas.model_registry import (
    Model as ModelSchema,
    ModelCreate,
    ModelUpdate,
    ModelListResponse,
    ModelTypeEnum,
    ModelStatusEnum,
    HealthCheckRequest,
    HealthCheckResponse,
)
from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["models"])


def _resolve_connector(model: Model) -> str:
    connector = getattr(model, "connector", None)
    if connector:
        return connector

    provider = (model.provider or "").lower()
    model_type = model.type.value if hasattr(model.type, "value") else str(model.type)
    if provider == "local" and model_type == "embedding":
        return "local_emb_http"
    if provider == "local" and model_type == "reranker":
        return "local_rerank_http"
    if provider == "local" and model_type == "llm_chat":
        return "local_llm_http"
    if provider == "azure":
        return "azure_openai_http"
    return "openai_http"


def _resolve_base_url(model: Model) -> Optional[str]:
    if getattr(model, "base_url", None):
        return model.base_url
    state = inspect(model)
    if "instance" not in state.unloaded and model.instance is not None and getattr(model.instance, "url", None):
        return model.instance.url
    if model.extra_config and model.extra_config.get("base_url"):
        return model.extra_config.get("base_url")
    return None


def serialize_model(model: Model) -> Dict[str, Any]:
    """Serialize Model ORM object to dict for API response"""
    state = inspect(model)
    instance_name: Optional[str] = None
    if "instance" not in state.unloaded and model.instance is not None:
        instance_name = model.instance.name

    def _enum_value(value: Any) -> Any:
        if value is None:
            return None
        return value.value if hasattr(value, "value") else value

    return {
        "id": str(model.id),
        "alias": model.alias,
        "name": model.name,
        "type": _enum_value(model.type),
        "provider": model.provider,
        "connector": _resolve_connector(model),
        "provider_model_name": model.provider_model_name,
        "base_url": _resolve_base_url(model),
        "instance_id": str(model.instance_id) if model.instance_id else None,
        "instance_name": instance_name,
        "extra_config": model.extra_config,
        "status": _enum_value(model.status),
        "enabled": model.enabled,
        "is_system": model.is_system,
        "default_for_type": model.default_for_type,
        "model_version": model.model_version,
        "description": model.description,
        "last_health_check_at": model.last_health_check_at,
        "health_status": _enum_value(model.health_status),
        "health_error": model.health_error,
        "health_latency_ms": model.health_latency_ms,
        "created_at": model.created_at,
        "updated_at": model.updated_at,
        "deleted_at": model.deleted_at,
    }


@router.get("", response_model=ModelListResponse)
async def list_models(
    type: Optional[str] = Query(None, description="Filter by type (llm_chat, embedding)"),
    status: Optional[str] = Query(None, description="Filter by status"),
    enabled_only: bool = Query(False, description="Show only enabled models"),
    search: Optional[str] = Query(None, description="Search by alias, name, or provider model"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
    admin_user = Depends(require_admin),
):
    """List models with filtering and pagination"""
    try:
        service = ModelService(session)
        
        # Parse enum filters
        type_filter = ModelTypeEnum(type) if type else None
        status_filter = ModelStatusEnum(status) if status else None
        
        models = await service.list_models(
            type=type_filter,
            status=status_filter,
            enabled_only=enabled_only,
            search=search
        )
        
        total = len(models)
        start = (page - 1) * size
        end = start + size
        items = models[start:end]
        
        return {
            "items": [serialize_model(m) for m in items],
            "total": total,
            "page": page,
            "size": size,
            "has_more": end < total,
        }
    except Exception as e:
        logger.error(f"Failed to list models: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list models: {str(e)}")


@router.post("", response_model=ModelSchema, status_code=status.HTTP_201_CREATED)
async def create_model(
    payload: ModelCreate,
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
    admin_user = Depends(require_admin),
):
    """Create a new model"""
    try:
        service = ModelService(session)
        model = await service.create_model(payload.model_dump())
        return serialize_model(model)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create model: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create model: {str(e)}")


@router.get("/{model_id}", response_model=ModelSchema)
async def get_model(
    model_id: str,
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
    admin_user = Depends(require_admin),
):
    """Get model by ID"""
    try:
        service = ModelService(session)
        model = await service.get_by_id(uuid.UUID(model_id))
        
        if not model:
            raise HTTPException(status_code=404, detail="Model not found")
        
        return serialize_model(model)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get model: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get model: {str(e)}")


@router.patch("/{model_id}", response_model=ModelSchema)
async def update_model(
    model_id: str,
    payload: ModelUpdate,
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
    admin_user = Depends(require_admin),
):
    """Update model"""
    try:
        service = ModelService(session)
        data = payload.model_dump(exclude_unset=True)
        model = await service.update_model(uuid.UUID(model_id), data)
        
        if not model:
            raise HTTPException(status_code=404, detail="Model not found")
        
        return serialize_model(model)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to update model: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update model: {str(e)}")


@router.delete("/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_model(
    model_id: str,
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
    admin_user = Depends(require_admin),
):
    """Delete model (soft delete)"""
    try:
        service = ModelService(session)
        ok = await service.delete_model(uuid.UUID(model_id))
        
        if not ok:
            raise HTTPException(status_code=404, detail="Model not found")
        
        return None
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to delete model: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete model: {str(e)}")


@router.post("/health-check-all")
async def health_check_all_models(
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
    admin_user = Depends(require_admin),
):
    """Perform health check on all enabled models
    
    Returns summary of health check results.
    """
    try:
        from app.services.model_health_checker import get_health_checker
        
        service = ModelService(session)
        models = await service.list_models(enabled_only=True)
        
        health_checker = get_health_checker()
        results = []
        
        for model in models:
            result = await health_checker.check_model(model, session=session)
            await service.update_health_status(
                model.id,
                result.status,
                latency_ms=result.latency_ms,
                error=result.error
            )
            results.append({
                "model_id": str(model.id),
                "alias": model.alias,
                "status": result.status.value,
                "latency_ms": result.latency_ms,
                "error": result.error
            })
        
        healthy = sum(1 for r in results if r["status"] == "healthy")
        
        return {
            "total": len(results),
            "healthy": healthy,
            "unhealthy": len(results) - healthy,
            "results": results
        }
    except Exception as e:
        logger.error(f"Failed to health check all models: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to health check models: {str(e)}")


@router.post("/{model_id}/health-check", response_model=HealthCheckResponse)
async def health_check_model(
    model_id: str,
    request: HealthCheckRequest,
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
    admin_user = Depends(require_admin),
):
    """Perform health check on model
    
    Calls the actual provider to verify model availability.
    Updates model status based on result.
    """
    try:
        from app.services.model_health_checker import get_health_checker
        
        service = ModelService(session)
        model = await service.get_by_id(uuid.UUID(model_id))
        
        if not model:
            raise HTTPException(status_code=404, detail="Model not found")
        
        # Perform actual health check
        health_checker = get_health_checker()
        result = await health_checker.check_model(model, session=session)
        
        # Update model health status in DB
        await service.update_health_status(
            model.id,
            result.status,
            latency_ms=result.latency_ms,
            error=result.error
        )
        
        return {
            "model_id": str(model.id),
            "alias": model.alias,
            "status": result.status.value,
            "latency_ms": result.latency_ms,
            "error": result.error,
            "checked_at": datetime.now(timezone.utc)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to health check model: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to health check model: {str(e)}")
