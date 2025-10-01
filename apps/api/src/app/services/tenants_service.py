"""
Tenants service for tenant management business logic
"""
from __future__ import annotations
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from app.repositories.tenants_repo import TenantsRepository, TenantModel
from app.core.logging import get_logger

logger = get_logger(__name__)

class TenantsService:
    """Service for tenant operations"""
    
    def __init__(self, session: Session):
        self.repo = TenantsRepository(session)
    
    def get_tenant(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Get tenant by ID"""
        tenant = self.repo.get_by_id(tenant_id)
        if not tenant:
            return None
        
        return self._format_tenant_response(tenant)
    
    def list_tenants(
        self, 
        limit: int = 20, 
        cursor: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """List tenants with cursor pagination"""
        tenants, next_cursor = self.repo.list_tenants(limit, cursor, filters)
        
        return {
            "items": [self._format_tenant_response(tenant) for tenant in tenants],
            "next_cursor": next_cursor,
            "total": len(tenants)  # TODO: Get actual total count
        }
    
    def create_tenant(self, tenant_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create new tenant"""
        # Validate required fields
        if not tenant_data.get("name"):
            raise ValueError("Tenant name is required")
        
        # Validate isolation level
        valid_levels = ["standard", "premium", "enterprise"]
        isolation_level = tenant_data.get("isolation_level", "standard")
        if isolation_level not in valid_levels:
            raise ValueError(f"Invalid isolation level. Must be one of: {', '.join(valid_levels)}")
        
        tenant = self.repo.create_tenant(tenant_data)
        if not tenant:
            return None
        
        return self._format_tenant_response(tenant)
    
    def update_tenant(self, tenant_id: str, update_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update tenant"""
        tenant = self.repo.update_tenant(tenant_id, update_data)
        if not tenant:
            return None
        
        return self._format_tenant_response(tenant)
    
    def delete_tenant(self, tenant_id: str) -> bool:
        """Delete tenant"""
        return self.repo.delete_tenant(tenant_id)
    
    def _format_tenant_response(self, tenant: TenantModel) -> Dict[str, Any]:
        """Format tenant model for API response"""
        return {
            "id": tenant.id,
            "name": tenant.name,
            "isolation_level": tenant.isolation_level,
            "settings": tenant.settings,
            "is_active": tenant.is_active,
            "created_at": tenant.created_at,
            "updated_at": tenant.updated_at,
            "user_count": tenant.settings.get("max_users", 0),  # Simulated
            "storage_used": tenant.settings.get("storage_limit", "0GB")  # Simulated
        }
