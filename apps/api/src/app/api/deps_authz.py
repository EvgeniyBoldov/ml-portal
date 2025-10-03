from __future__ import annotations
from typing import Iterable, Set, List
from fastapi import Depends, HTTPException, status
from app.api.deps import get_current_user
from app.core.security import UserCtx

def require_scopes(required: Iterable[str]):
    """Require specific scopes/permissions"""
    required_set: Set[str] = set(required)
    def _dep(user: UserCtx = Depends(get_current_user)):
        user_scopes: Set[str] = set(user.scopes or [])
        if not required_set.issubset(user_scopes):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, 
                detail=f"Insufficient scope. Required: {list(required_set)}, Available: {list(user_scopes)}"
            )
        return user
    return _dep

def require_role(required_role: str):
    """Require specific role"""
    def _dep(user: UserCtx = Depends(get_current_user)):
        if user.role != required_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{required_role}' required, got '{user.role}'"
            )
        return user
    return _dep

def require_any_role(required_roles: List[str]):
    """Require any of the specified roles"""
    def _dep(user: UserCtx = Depends(get_current_user)):
        if user.role not in required_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"One of roles {required_roles} required, got '{user.role}'"
            )
        return user
    return _dep

def require_tenant_access():
    """Require user to have tenant access (at least one tenant)"""
    def _dep(user: UserCtx = Depends(get_current_user)):
        if not user.tenant_ids or len(user.tenant_ids) == 0:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tenant access required"
            )
        return user
    return _dep
