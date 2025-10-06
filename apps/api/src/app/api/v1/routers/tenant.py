# Tenant router

from __future__ import annotations
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from api.deps import db_session, require_admin
from schemas.tenant import Tenant, TenantCreate, TenantUpdate, TenantListResponse
import uuid
from datetime import datetime

router = APIRouter(tags=["tenants"])

# Mock data for development
MOCK_TENANTS = [
    {
        "id": "550e8400-e29b-41d4-a716-446655440001",
        "name": "Default Tenant",
        "description": "Default tenant for the system",
        "is_active": True,
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z"
    },
    {
        "id": "550e8400-e29b-41d4-a716-446655440002",
        "name": "Test Company",
        "description": "Test tenant for development",
        "is_active": True,
        "created_at": "2024-01-02T00:00:00Z",
        "updated_at": "2024-01-02T00:00:00Z"
    },
    {
        "id": "550e8400-e29b-41d4-a716-446655440003",
        "name": "Inactive Tenant",
        "description": "Inactive tenant for testing",
        "is_active": False,
        "created_at": "2024-01-03T00:00:00Z",
        "updated_at": "2024-01-03T00:00:00Z"
    }
]

@router.get("", response_model=TenantListResponse)
async def list_tenants(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    session: AsyncSession = Depends(db_session),
    admin_user = Depends(require_admin),
):
    """List tenants with pagination and filtering"""
    # Filter tenants
    filtered_tenants = MOCK_TENANTS.copy()
    
    if search:
        filtered_tenants = [
            t for t in filtered_tenants 
            if search.lower() in t["name"].lower() or 
               (t["description"] and search.lower() in t["description"].lower())
        ]
    
    if is_active is not None:
        filtered_tenants = [t for t in filtered_tenants if t["is_active"] == is_active]
    
    # Calculate pagination
    total = len(filtered_tenants)
    start_idx = (page - 1) * size
    end_idx = start_idx + size
    items = filtered_tenants[start_idx:end_idx]
    
    return TenantListResponse(
        tenants=items,
        total=total,
        page=page,
        size=size,
        has_more=end_idx < total
    )

@router.post("", response_model=Tenant)
async def create_tenant(
    tenant_data: TenantCreate,
    session: AsyncSession = Depends(db_session),
    admin_user = Depends(require_admin),
):
    """Create a new tenant"""
    # Check if tenant with same name already exists
    existing_tenant = next(
        (t for t in MOCK_TENANTS if t["name"].lower() == tenant_data.name.lower()),
        None
    )
    if existing_tenant:
        raise HTTPException(
            status_code=400,
            detail="Tenant with this name already exists"
        )
    
    # Create new tenant
    tenant_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat() + "Z"
    
    new_tenant = {
        "id": tenant_id,
        "name": tenant_data.name,
        "description": tenant_data.description,
        "is_active": tenant_data.is_active,
        "created_at": now,
        "updated_at": now
    }
    
    MOCK_TENANTS.append(new_tenant)
    return new_tenant

@router.get("/{tenant_id}", response_model=Tenant)
async def get_tenant(
    tenant_id: str,
    session: AsyncSession = Depends(db_session),
    admin_user = Depends(require_admin),
):
    """Get tenant by ID"""
    tenant = next((t for t in MOCK_TENANTS if t["id"] == tenant_id), None)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    return tenant

@router.put("/{tenant_id}", response_model=Tenant)
async def update_tenant(
    tenant_id: str,
    tenant_data: TenantUpdate,
    session: AsyncSession = Depends(db_session),
    admin_user = Depends(require_admin),
):
    """Update tenant"""
    tenant = next((t for t in MOCK_TENANTS if t["id"] == tenant_id), None)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    # Check if name is being changed and if it conflicts
    if tenant_data.name and tenant_data.name != tenant["name"]:
        existing_tenant = next(
            (t for t in MOCK_TENANTS 
             if t["id"] != tenant_id and t["name"].lower() == tenant_data.name.lower()),
            None
        )
        if existing_tenant:
            raise HTTPException(
                status_code=400,
                detail="Tenant with this name already exists"
            )
    
    # Update tenant
    now = datetime.utcnow().isoformat() + "Z"
    
    if tenant_data.name is not None:
        tenant["name"] = tenant_data.name
    if tenant_data.description is not None:
        tenant["description"] = tenant_data.description
    if tenant_data.is_active is not None:
        tenant["is_active"] = tenant_data.is_active
    
    tenant["updated_at"] = now
    
    return tenant

@router.delete("/{tenant_id}")
async def delete_tenant(
    tenant_id: str,
    session: AsyncSession = Depends(db_session),
    admin_user = Depends(require_admin),
):
    """Delete tenant"""
    tenant_index = next(
        (i for i, t in enumerate(MOCK_TENANTS) if t["id"] == tenant_id),
        None
    )
    if tenant_index is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    # Check if tenant has users (in real implementation)
    # For now, we'll allow deletion
    
    MOCK_TENANTS.pop(tenant_index)
    return {"message": "Tenant deleted successfully"}
