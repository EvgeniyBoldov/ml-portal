"""Models API endpoints (New Architecture)

CRUD operations for LLM and Embedding models.
No file system scanning - models are added manually.
"""
from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import db_uow, get_current_user, require_admin
from app.core.security import UserCtx
from app.services.model_service import ModelService
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
            "items": [
                {
                    "id": str(m.id),
                    "alias": m.alias,
                    "name": m.name,
                    "type": m.type.value,
                    "provider": m.provider,
                    "provider_model_name": m.provider_model_name,
                    "base_url": m.base_url,
                    "api_key_ref": m.api_key_ref,
                    "extra_config": m.extra_config,
                    "status": m.status.value,
                    "enabled": m.enabled,
                    "default_for_type": m.default_for_type,
                    "model_version": m.model_version,
                    "description": m.description,
                    "last_health_check_at": m.last_health_check_at,
                    "health_status": m.health_status.value if m.health_status else None,
                    "health_error": m.health_error,
                    "health_latency_ms": m.health_latency_ms,
                    "created_at": m.created_at,
                    "updated_at": m.updated_at,
                    "deleted_at": m.deleted_at,
                }
                for m in items
            ],
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
        
        return {
            "id": str(model.id),
            "alias": model.alias,
            "name": model.name,
            "type": model.type.value,
            "provider": model.provider,
            "provider_model_name": model.provider_model_name,
            "base_url": model.base_url,
            "api_key_ref": model.api_key_ref,
            "extra_config": model.extra_config,
            "status": model.status.value,
            "enabled": model.enabled,
            "default_for_type": model.default_for_type,
            "model_version": model.model_version,
            "description": model.description,
            "last_health_check_at": model.last_health_check_at,
            "health_status": model.health_status.value if model.health_status else None,
            "health_error": model.health_error,
            "health_latency_ms": model.health_latency_ms,
            "created_at": model.created_at,
            "updated_at": model.updated_at,
            "deleted_at": model.deleted_at,
        }
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
        import uuid
        service = ModelService(session)
        model = await service.get_by_id(uuid.UUID(model_id))
        
        if not model:
            raise HTTPException(status_code=404, detail="Model not found")
        
        return {
            "id": str(model.id),
            "alias": model.alias,
            "name": model.name,
            "type": model.type.value,
            "provider": model.provider,
            "provider_model_name": model.provider_model_name,
            "base_url": model.base_url,
            "api_key_ref": model.api_key_ref,
            "extra_config": model.extra_config,
            "status": model.status.value,
            "enabled": model.enabled,
            "default_for_type": model.default_for_type,
            "model_version": model.model_version,
            "description": model.description,
            "last_health_check_at": model.last_health_check_at,
            "health_status": model.health_status.value if model.health_status else None,
            "health_error": model.health_error,
            "health_latency_ms": model.health_latency_ms,
            "created_at": model.created_at,
            "updated_at": model.updated_at,
            "deleted_at": model.deleted_at,
        }
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
        import uuid
        service = ModelService(session)
        data = payload.model_dump(exclude_unset=True)
        model = await service.update_model(uuid.UUID(model_id), data)
        
        if not model:
            raise HTTPException(status_code=404, detail="Model not found")
        
        return {
            "id": str(model.id),
            "alias": model.alias,
            "name": model.name,
            "type": model.type.value,
            "provider": model.provider,
            "provider_model_name": model.provider_model_name,
            "base_url": model.base_url,
            "api_key_ref": model.api_key_ref,
            "extra_config": model.extra_config,
            "status": model.status.value,
            "enabled": model.enabled,
            "default_for_type": model.default_for_type,
            "model_version": model.model_version,
            "description": model.description,
            "last_health_check_at": model.last_health_check_at,
            "health_status": model.health_status.value if model.health_status else None,
            "health_error": model.health_error,
            "health_latency_ms": model.health_latency_ms,
            "created_at": model.created_at,
            "updated_at": model.updated_at,
            "deleted_at": model.deleted_at,
        }
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
        import uuid
        service = ModelService(session)
        ok = await service.delete_model(uuid.UUID(model_id))
        
        if not ok:
            raise HTTPException(status_code=404, detail="Model not found")
        
        return None
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete model: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete model: {str(e)}")


@router.post("/{model_id}/health-check", response_model=HealthCheckResponse)
async def health_check_model(
    model_id: str,
    request: HealthCheckRequest,
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
    admin_user = Depends(require_admin),
):
    """Perform health check on model
    
    TODO: Implement actual provider health check
    """
    try:
        import uuid
        from datetime import datetime, timezone
        from app.models.model_registry import HealthStatus
        
        service = ModelService(session)
        model = await service.get_by_id(uuid.UUID(model_id))
        
        if not model:
            raise HTTPException(status_code=404, detail="Model not found")
        
        # TODO: Actually call provider to check health
        # For now, just mark as healthy
        await service.update_health_status(
            model.id,
            HealthStatus.HEALTHY,
            latency_ms=100,
            error=None
        )
        
        return {
            "model_id": str(model.id),
            "alias": model.alias,
            "status": HealthStatus.HEALTHY.value,
            "latency_ms": 100,
            "error": None,
            "checked_at": datetime.now(timezone.utc)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to health check model: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to health check model: {str(e)}")
