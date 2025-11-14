"""
Models endpoints for API v1 (Model Registry)
"""
from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import db_session, get_current_user, require_admin
from app.core.security import UserCtx
from app.services.model_registry_service import ModelRegistryService
from app.schemas.model_registry import (
    ModelRegistryListResponse,
    ScanResult,
    ModelRegistry as ModelRegistrySchema,
    ModelRegistryUpdate,
    RetireRequest,
    RetireResponse,
)
from app.repositories.model_registry_repo import AsyncModelRegistryRepository

router = APIRouter(tags=["models"])

@router.get("", response_model=ModelRegistryListResponse)
async def list_models(
    state: Optional[str] = Query(None, description="Filter by state"),
    modality: Optional[str] = Query(None, description="Filter by modality"),
    search: Optional[str] = Query(None, description="Search by model id or version"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(db_session),
    user: UserCtx = Depends(get_current_user),
    admin_user = Depends(require_admin),
):
    """List models from registry with filtering and pagination"""
    try:
        service = ModelRegistryService(session)
        filters = {k: v for k, v in {"state": state, "modality": modality, "search": search}.items() if v}
        models = await service.get_models(filters=filters)
        total = len(models)
        start = (page - 1) * size
        end = start + size
        items = models[start:end]
        return {
            "items": items,
            "total": total,
            "page": page,
            "size": size,
            "has_more": end < total,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list models: {str(e)}")

@router.post("/scan", response_model=ScanResult)
async def scan_models(
    session: AsyncSession = Depends(db_session),
    user: UserCtx = Depends(get_current_user),
    admin_user = Depends(require_admin),
):
    """Rescan MODELS_ROOT and synchronize model registry"""
    try:
        service = ModelRegistryService(session)
        result = await service.scan_models_directory()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to scan models: {str(e)}")

@router.get("/{model_id}", response_model=ModelRegistrySchema)
async def get_model(
    model_id: str,
    session: AsyncSession = Depends(db_session),
    user: UserCtx = Depends(get_current_user),
    admin_user = Depends(require_admin),
):
    """Get model by ID"""
    try:
        service = ModelRegistryService(session)
        details = await service.get_model_details(model_id)
        if not details:
            raise HTTPException(status_code=404, detail="Model not found")
        # Map details to basic schema fields; extra fields are ignored by response schema
        return {
            "id": details["id"],
            "model": details["model"],
            "version": details["version"],
            "modality": details["modality"],
            "state": details["state"],
            "vector_dim": details.get("vector_dim"),
            "path": details["path"],
            "default_for_new": details.get("default_for_new", False),
            "notes": details.get("notes"),
            "used_by_tenants": details.get("used_by_tenants", 0),
            "created_at": details["created_at"],
            "updated_at": details["updated_at"],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get model: {str(e)}")

@router.patch("/{model_id}", response_model=ModelRegistrySchema)
async def update_model(
    model_id: str,
    payload: ModelRegistryUpdate,
    session: AsyncSession = Depends(db_session),
    user: UserCtx = Depends(get_current_user),
    admin_user = Depends(require_admin),
):
    """Update model registry entry (state/default_for_new/notes)"""
    try:
        service = ModelRegistryService(session)
        data = payload.model_dump(exclude_unset=True)
        updated = await service.update_model(model_id, data)
        if not updated:
            raise HTTPException(status_code=404, detail="Model not found")
        return updated
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update model: {str(e)}")

@router.post("/{model_id}:retire", response_model=RetireResponse)
async def retire_model(
    model_id: str,
    request: RetireRequest,
    session: AsyncSession = Depends(db_session),
    user: UserCtx = Depends(get_current_user),
    admin_user = Depends(require_admin),
):
    """Retire a model and optionally remove from tenants and drop vectors"""
    try:
        service = ModelRegistryService(session)
        result = await service.retire_model(model_id, request)
        await session.commit()
        return result
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to retire model: {str(e)}")

@router.delete("/{model_id}")
async def delete_model(
    model_id: str,
    session: AsyncSession = Depends(db_session),
    user: UserCtx = Depends(get_current_user),
    admin_user = Depends(require_admin),
):
    """Delete model from registry"""
    try:
        import uuid
        repo = AsyncModelRegistryRepository(session)
        ok = await repo.delete(uuid.UUID(model_id))
        if not ok:
            raise HTTPException(status_code=404, detail="Model not found")
        await session.commit()
        return {"message": "Model deleted"}
    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete model: {str(e)}")

@router.get("/{model_id}/tenants")
async def get_model_tenants(
    model_id: str,
    session: AsyncSession = Depends(db_session),
    user: UserCtx = Depends(get_current_user),
    admin_user = Depends(require_admin),
):
    """Get tenants using a specific model"""
    try:
        service = ModelRegistryService(session)
        details = await service.get_model_details(model_id)
        if not details:
            raise HTTPException(status_code=404, detail="Model not found")
        return {"model": details["model"], "tenants": details.get("tenants", [])}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get model tenants: {str(e)}")
