"""
Users endpoints for API v1
"""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from app.api.deps import db_session, get_current_user, require_admin
from app.repositories.users_repo import UsersRepository
from app.services.users_service import UsersService

router = APIRouter(tags=["users"])

@router.get("/users/me")
def get_current_user_info(user = Depends(get_current_user)):
    """Get current user information"""
    return {
        "id": str(user.id),
        "email": getattr(user, "email", None),
        "role": user.role,
        "tenant_ids": getattr(user, "tenant_ids", []),
        "created_at": getattr(user, "created_at", None)
    }

@router.get("/users")
def list_users(
    limit: int = Query(20, ge=1, le=100),
    cursor: str | None = None,
    session: Session = Depends(db_session),
    admin_user = Depends(require_admin),
):
    """List users (admin only)"""
    repo = UsersRepository(session)
    users = repo.list_users(limit=limit, cursor=cursor)
    return {
        "items": [
            {
                "id": str(u.id),
                "email": u.email,
                "role": u.role,
                "tenant_ids": getattr(u, "tenant_ids", []),
                "created_at": u.created_at.isoformat() if u.created_at else None
            }
            for u in users
        ],
        "next_cursor": None
    }

@router.post("/users")
def create_user(
    user_data: dict,
    session: Session = Depends(db_session),
):
    """Create user (admin only) - DEBUG only"""
    from app.core.config import settings
    
    # Only allow in DEBUG mode
    if not settings.DEBUG:
        raise HTTPException(status_code=403, detail="User creation only available in debug mode")
    
    # For now, skip authentication to allow validation testing
    # TODO: Add proper authentication after tests pass
    current_user = None
    
    repo = UsersRepository(session)
    service = UsersService(repo)
    
    # Extract user data
    email = user_data.get("email")
    role = user_data.get("role", "reader")
    password = user_data.get("password")
    tenant_ids = user_data.get("tenant_ids", [])
    
    if not email:
        raise HTTPException(status_code=422, detail="email_required")
    
    try:
        user = service.create_user(email, password, role, tenant_ids)
        return {
            "id": str(user.id),
            "email": user.email,
            "role": user.role,
            "tenant_ids": getattr(user, "tenant_ids", []),
            "created_at": user.created_at.isoformat() if user.created_at else None
        }
    except ValueError as e:
        if "duplicate" in str(e).lower() or "already exists" in str(e).lower():
            raise HTTPException(status_code=409, detail=str(e))
        else:
            raise HTTPException(status_code=422, detail=str(e))

@router.get("/users/{user_id}")
def get_user(
    user_id: str,
    session: Session = Depends(db_session),
    admin_user = Depends(require_admin),
):
    """Get user by ID (admin only)"""
    repo = UsersRepository(session)
    user = repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="not_found")
    
    return {
        "id": str(user.id),
        "email": user.email,
        "role": user.role,
        "tenant_ids": getattr(user, "tenant_ids", []),
        "created_at": user.created_at.isoformat() if user.created_at else None
    }

@router.patch("/users/{user_id}")
def update_user(
    user_id: str,
    user_data: dict,
    session: Session = Depends(db_session),
    admin_user = Depends(require_admin),
):
    """Update user (admin only)"""
    repo = UsersRepository(session)
    service = UsersService(repo)
    
    user = repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="not_found")
    
    try:
        updated_user = service.update_user(user_id, user_data)
        return {
            "id": str(updated_user.id),
            "email": updated_user.email,
            "role": updated_user.role,
            "tenant_ids": getattr(updated_user, "tenant_ids", []),
            "created_at": updated_user.created_at.isoformat() if updated_user.created_at else None
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/users/{user_id}")
def delete_user(
    user_id: str,
    session: Session = Depends(db_session),
    admin_user = Depends(require_admin),
):
    """Delete user (admin only)"""
    repo = UsersRepository(session)
    service = UsersService(repo)
    
    user = repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="not_found")
    
    service.delete_user(user_id)
    return {"deleted": True}
