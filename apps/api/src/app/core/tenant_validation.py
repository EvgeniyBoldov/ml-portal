"""
Tenant validation utilities
"""
from __future__ import annotations
from typing import Optional
import uuid
from fastapi import HTTPException, status

from app.core.security import UserCtx
from app.schemas.common import Problem


class TenantRequiredError(HTTPException):
    """Exception raised when tenant_id is required but missing"""
    
    def __init__(self, operation: str = "operation"):
        problem = Problem(
            type="https://example.com/problems/tenant-required",
            title="Tenant Required",
            status=status.HTTP_400_BAD_REQUEST,
            code="TENANT_REQUIRED",
            detail=f"Tenant ID is required for {operation}",
            instance={"operation": operation}
        )
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=problem.model_dump()
        )


def require_tenant_id(user: UserCtx, operation: str = "operation") -> uuid.UUID:
    """
    Strictly require tenant_id from user context.
    
    Args:
        user: User context
        operation: Operation name for error message
        
    Returns:
        Valid tenant_id
        
    Raises:
        TenantRequiredError: If tenant_id is missing
    """
    if not user:
        raise TenantRequiredError(operation)
    
    tenant_id = getattr(user, 'tenant_id', None)
    if not tenant_id:
        raise TenantRequiredError(operation)
    
    return tenant_id


def get_tenant_id_safe(user: UserCtx, operation: str = "operation") -> Optional[uuid.UUID]:
    """
    Safely get tenant_id from user context without raising exceptions.
    
    Args:
        user: User context
        operation: Operation name for logging
        
    Returns:
        tenant_id if present, None otherwise
    """
    if not user:
        return None
    
    return getattr(user, 'tenant_id', None)


def validate_tenant_access(user: UserCtx, required_tenant_id: uuid.UUID, operation: str = "operation") -> None:
    """
    Validate that user has access to the specified tenant.
    
    Args:
        user: User context
        required_tenant_id: Required tenant ID
        operation: Operation name for error message
        
    Raises:
        TenantRequiredError: If tenant_id is missing
        HTTPException: If tenant access is denied
    """
    user_tenant_id = require_tenant_id(user, operation)
    
    if user_tenant_id != required_tenant_id:
        problem = Problem(
            type="https://example.com/problems/tenant-access-denied",
            title="Tenant Access Denied",
            status=status.HTTP_403_FORBIDDEN,
            code="TENANT_ACCESS_DENIED",
            detail=f"Access denied to tenant {required_tenant_id}",
            instance={
                "required_tenant_id": str(required_tenant_id),
                "user_tenant_id": str(user_tenant_id),
                "operation": operation
            }
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=problem.model_dump()
        )


def require_editor_or_admin(user: UserCtx) -> UserCtx:
    """
    Require user to have editor or admin role.
    
    Args:
        user: User context
        
    Returns:
        User context if authorized
        
    Raises:
        HTTPException: If user is not authorized
    """
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    
    # Check if user has editor or admin role
    user_role = getattr(user, 'role', None)
    if user_role not in ['editor', 'admin']:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Editor or admin role required"
        )
    
    return user


def require_reader_or_above(user: UserCtx) -> UserCtx:
    """
    Require user to have reader, editor or admin role.
    
    Args:
        user: User context
        
    Returns:
        User context if authorized
        
    Raises:
        HTTPException: If user is not authorized
    """
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    
    # Check if user has reader, editor or admin role
    user_role = getattr(user, 'role', None)
    if user_role not in ['reader', 'editor', 'admin']:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Reader, editor or admin role required"
        )
    
    return user
