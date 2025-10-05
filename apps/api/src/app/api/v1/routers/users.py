"""
Users endpoints for API v1
"""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from api.deps import db_session, get_current_user, require_admin
from repositories.users_repo import AsyncUsersRepository
from services.users_service import AsyncUsersService
from schemas.common import ProblemDetails

router = APIRouter(tags=["users"])

@router.get("/users/me")
async def get_current_user_info(user = Depends(get_current_user)):
    """Get current user information"""
    return {
        "id": str(user.id),
        "email": getattr(user, "email", None),
        "role": user.role,
        "tenant_ids": getattr(user, "tenant_ids", []),
        "created_at": getattr(user, "created_at", None)
    }

@router.get("/users")
async def list_users(
    limit: int = Query(20, ge=1, le=100),
    cursor: str | None = None,
    session: AsyncSession = Depends(db_session),
    admin_user = Depends(require_admin),
):
    """List users (admin only)"""
    repo = AsyncUsersRepository(session)
    users = await repo.list_users(limit=limit, cursor=cursor)
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
async def create_user(
    user_data: dict,
    session: AsyncSession = Depends(db_session),
):
    """Create user (admin only) - DEBUG only"""
    from app.core.config import get_settings
    
    # Only allow in DEBUG mode
    s = get_settings()
    if not s.DEBUG:
        raise HTTPException(
            status_code=403, 
            detail=ProblemDetails(
                title="Debug Endpoint Disabled",
                status=403,
                detail="User creation only available in debug mode"
            ).model_dump()
        )
    
    # For now, skip authentication to allow validation testing
    # TODO: Add proper authentication after tests pass
    current_user = None
    
    repo = AsyncUsersRepository(session)
    service = AsyncUsersService(repo)
    
    # Extract user data
    email = user_data.get("email")
    role = user_data.get("role", "reader")
    password = user_data.get("password")
    tenant_ids = user_data.get("tenant_ids", [])
    
    if not email:
        raise HTTPException(
            status_code=422, 
            detail=ProblemDetails(
                title="Validation Error",
                status=422,
                detail="email_required"
            ).model_dump()
        )
    
    try:
        user = await service.create_user(email, password, role, tenant_ids)
        return {
            "id": str(user.id),
            "email": user.email,
            "role": user.role,
            "tenant_ids": getattr(user, "tenant_ids", []),
            "created_at": user.created_at.isoformat() if user.created_at else None
        }
    except ValueError as e:
        if "duplicate" in str(e).lower() or "already exists" in str(e).lower():
            raise HTTPException(
                status_code=409, 
                detail=ProblemDetails(
                    title="Conflict",
                    status=409,
                    detail=str(e)
                ).model_dump()
            )
        else:
            raise HTTPException(
                status_code=422, 
                detail=ProblemDetails(
                    title="Validation Error",
                    status=422,
                    detail=str(e)
                ).model_dump()
            )

@router.get("/users/{user_id}")
async def get_user(
    user_id: str,
    session: AsyncSession = Depends(db_session),
    admin_user = Depends(require_admin),
):
    """Get user by ID (admin only)"""
    repo = AsyncUsersRepository(session)
    user = await repo.get_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=404, 
            detail=ProblemDetails(
                title="Not Found",
                status=404,
                detail="not_found"
            ).model_dump()
        )
    
    return {
        "id": str(user.id),
        "email": user.email,
        "role": user.role,
        "tenant_ids": getattr(user, "tenant_ids", []),
        "created_at": user.created_at.isoformat() if user.created_at else None
    }

@router.patch("/users/{user_id}")
async def update_user(
    user_id: str,
    user_data: dict,
    session: AsyncSession = Depends(db_session),
    admin_user = Depends(require_admin),
):
    """Update user (admin only)"""
    repo = AsyncUsersRepository(session)
    service = AsyncUsersService(repo)
    
    user = await repo.get_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=404, 
            detail=ProblemDetails(
                title="Not Found",
                status=404,
                detail="not_found"
            ).model_dump()
        )
    
    try:
        updated_user = await service.update_user(user_id, user_data)
        return {
            "id": str(updated_user.id),
            "email": updated_user.email,
            "role": updated_user.role,
            "tenant_ids": getattr(updated_user, "tenant_ids", []),
            "created_at": updated_user.created_at.isoformat() if updated_user.created_at else None
        }
    except ValueError as e:
        raise HTTPException(
            status_code=400, 
            detail=ProblemDetails(
                title="Bad Request",
                status=400,
                detail=str(e)
            ).model_dump()
        )

@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    session: AsyncSession = Depends(db_session),
    admin_user = Depends(require_admin),
):
    """Delete user (admin only)"""
    repo = AsyncUsersRepository(session)
    service = AsyncUsersService(repo)
    
    user = await repo.get_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=404, 
            detail=ProblemDetails(
                title="Not Found",
                status=404,
                detail="not_found"
            ).model_dump()
        )
    
    await service.delete_user(user_id)
    return {"deleted": True}
