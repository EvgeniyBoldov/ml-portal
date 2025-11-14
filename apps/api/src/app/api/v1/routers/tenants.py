#ПРОВЕРЕН
"""
Tenants API router with real database operations
"""
from __future__ import annotations
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import db_session, require_admin
from app.schemas.tenant import Tenant, TenantCreate, TenantUpdate, TenantListResponse
from app.services.tenants_service import AsyncTenantsService
import uuid
import logging

router = APIRouter(tags=["tenants"])

@router.get("", response_model=TenantListResponse)
async def list_tenants(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    session: AsyncSession = Depends(db_session),
    admin_user = Depends(require_admin),
):
    """List tenants with pagination and filtering (admin only)"""
    try:
        service = AsyncTenantsService(session)
        tenants = await service.list_tenants(limit=1000)  # Get all for filtering
        
        # Apply filters
        filtered_tenants = tenants
        if search:
            filtered_tenants = [
                t for t in filtered_tenants 
                if search.lower() in t["name"].lower()
            ]
        
        if is_active is not None:
            filtered_tenants = [t for t in filtered_tenants if t["is_active"] == is_active]
        
        # Calculate pagination
        total = len(filtered_tenants)
        start_idx = (page - 1) * size
        end_idx = start_idx + size
        items = filtered_tenants[start_idx:end_idx]
        
        return TenantListResponse(
            items=items,
            total=total,
            page=page,
            size=size,
            has_more=end_idx < total
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list tenants: {str(e)}")

@router.post("", response_model=Tenant)
async def create_tenant(
    tenant_data: TenantCreate,
    session: AsyncSession = Depends(db_session),
    admin_user = Depends(require_admin),
):
    """Create a new tenant (admin only)"""
    try:
        service = AsyncTenantsService(session)
        
        # Convert Pydantic model to dict
        tenant_dict = tenant_data.model_dump()
        
        tenant = await service.create_tenant(tenant_dict)
        if not tenant:
            raise HTTPException(status_code=500, detail="Failed to create tenant")
        
        await session.commit()
        
        return Tenant(**tenant)
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create tenant: {str(e)}")

@router.get("/{tenant_id}", response_model=Tenant)
async def get_tenant(
    tenant_id: str,
    session: AsyncSession = Depends(db_session),
    admin_user = Depends(require_admin),
):
    """Get tenant by ID (admin only)"""
    try:
        service = AsyncTenantsService(session)
        tenant = await service.get_tenant(tenant_id)
        
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")
        
        return Tenant(**tenant)
        
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid tenant ID format")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get tenant: {str(e)}")

@router.put("/{tenant_id}", response_model=Tenant)
async def update_tenant(
    tenant_id: str,
    tenant_data: TenantUpdate,
    session: AsyncSession = Depends(db_session),
    admin_user = Depends(require_admin),
):
    """Update tenant (admin only)"""
    try:
        service = AsyncTenantsService(session)
        
        # Convert Pydantic model to dict, excluding None values
        update_dict = tenant_data.model_dump(exclude_unset=True)
        
        tenant = await service.update_tenant(tenant_id, update_dict)
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")
        
        await session.commit()
        
        return Tenant(**tenant)
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update tenant: {str(e)}")

@router.get("/{tenant_id}/models/resolve")
async def get_tenant_active_models(
    tenant_id: str,
    session: AsyncSession = Depends(db_session),
    admin_user = Depends(require_admin),
):
    """Get active models for a tenant"""
    try:
        service = AsyncTenantsService(session)
        models = await service.get_tenant_active_models(tenant_id)
        return models
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get tenant models: {str(e)}")

@router.delete("/{tenant_id}")
async def delete_tenant(
    tenant_id: str,
    session: AsyncSession = Depends(db_session),
    admin_user = Depends(require_admin),
):
    """Delete tenant (admin only)"""
    try:
        service = AsyncTenantsService(session)
        
        success = await service.delete_tenant(tenant_id)
        if not success:
            raise HTTPException(status_code=404, detail="Tenant not found")
        
        await session.commit()
        
        return {"message": "Tenant deleted successfully"}
        
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid tenant ID format")
    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete tenant: {str(e)}")
