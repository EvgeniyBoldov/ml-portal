"""
Tenants endpoints for API v1
"""
from __future__ import annotations
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession
from api.deps import db_session, require_admin, get_current_user
from services.tenants_service import TenantsService

router = APIRouter(tags=["tenants"])

@router.get("/tenants")
async def list_tenants(
    limit: int = Query(20, ge=1, le=100),
    cursor: str | None = Query(None, description="Cursor for pagination"),
    session: AsyncSession = Depends(db_session),
    admin_user = Depends(require_admin),
):
    """List tenants with cursor pagination (admin only) (G4/G5 compliant)"""
    try:
        service = TenantsService(session)
        return service.list_tenants(limit=limit, cursor=cursor)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list tenants: {str(e)}")

@router.post("/tenants")
async def create_tenant(
    tenant_data: dict,
    session: AsyncSession = Depends(db_session),
    admin_user = Depends(require_admin),
):
    """Create tenant with role isolation (admin only) (G4/G5 compliant)"""
    try:
        service = TenantsService(session)
        tenant = service.create_tenant(tenant_data)
        if not tenant:
            raise HTTPException(status_code=500, detail="Failed to create tenant")
        return tenant
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create tenant: {str(e)}")

@router.get("/tenants/{tenant_id}")
async def get_tenant(
    tenant_id: str,
    session: AsyncSession = Depends(db_session),
    admin_user = Depends(require_admin),
):
    """Get tenant by ID (admin only)"""
    try:
        service = TenantsService(session)
        tenant = service.get_tenant(tenant_id)
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")
        return tenant
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get tenant: {str(e)}")

@router.patch("/tenants/{tenant_id}")
async def update_tenant(
    tenant_id: str,
    tenant_data: dict,
    session: AsyncSession = Depends(db_session),
    admin_user = Depends(require_admin),
):
    """Update tenant (admin only)"""
    try:
        service = TenantsService(session)
        tenant = service.update_tenant(tenant_id, tenant_data)
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")
        return tenant
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update tenant: {str(e)}")

@router.delete("/tenants/{tenant_id}")
async def delete_tenant(
    tenant_id: str,
    session: AsyncSession = Depends(db_session),
    admin_user = Depends(require_admin),
):
    """Delete tenant (admin only)"""
    try:
        service = TenantsService(session)
        success = service.delete_tenant(tenant_id)
        if not success:
            raise HTTPException(status_code=404, detail="Tenant not found")
        return Response(status_code=204)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete tenant: {str(e)}")
