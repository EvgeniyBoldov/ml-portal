"""
Users endpoints for API v1
"""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import db_session, db_uow, get_current_user, require_admin
from app.repositories.users_repo import AsyncUsersRepository
from app.services.users_service import AsyncUsersService
from app.schemas.common import ProblemDetails
from app.schemas.users import UserResponse

router = APIRouter(tags=["users"])

@router.get("")
async def list_users(
    limit: int = Query(20, ge=1, le=100),
    cursor: str | None = None,
    query: str | None = None,
    role: str | None = None,
    is_active: bool | None = None,
    session: AsyncSession = Depends(db_uow),
    admin_user = Depends(require_admin),
):
    """List users (admin only)"""
    repo = AsyncUsersRepository(session)
    users, next_cursor, has_more, total = await repo.list_users(
        limit=limit,
        cursor=cursor,
        query=query,
        role=role,
        is_active=is_active,
    )
    items = []
    for u in users:
        try:
            default_tid = await repo.get_default_tenant(u.id)
        except Exception:
            default_tid = None
        items.append({
            "id": u.id,
            "login": u.login,
            "email": u.email,
            "role": u.role,
            "is_active": getattr(u, "is_active", True),
            "tenant_id": default_tid,
            "created_at": u.created_at.isoformat() if getattr(u, "created_at", None) else "",
            "updated_at": getattr(u, "updated_at", None).isoformat() if getattr(u, "updated_at", None) else None,
        })
    return {
        "users": items,
        "has_more": has_more,
        "next_cursor": next_cursor,
        "total": total,
    }

@router.post("")
async def create_user(
    user_data: dict,
    session: AsyncSession = Depends(db_uow),
    admin_user = Depends(require_admin),
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
    
    repo = AsyncUsersRepository(session)
    service = AsyncUsersService(repo)
    
    # Extract user data
    login = user_data.get("login")
    email = user_data.get("email")
    role = user_data.get("role", "reader")
    password = user_data.get("password")
    tenant_ids = user_data.get("tenant_ids", [])
    
    if not login:
        raise HTTPException(
            status_code=422, 
            detail=ProblemDetails(
                title="Validation Error",
                status=422,
                detail="login_required"
            ).model_dump()
        )
    
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
        user = await service.create_user(login, email, password, role, tenant_ids)
        return {
            "user": {
                "id": user.id,
                "login": user.login,
                "email": user.email,
                "role": user.role,
                "is_active": getattr(user, "is_active", True),
                "created_at": user.created_at.isoformat() if getattr(user, "created_at", None) else "",
                "updated_at": user.updated_at.isoformat() if getattr(user, "updated_at", None) else None,
            }
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

@router.get("/{user_id}", response_model=UserResponse)
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
        "id": user.id,
        "login": user.login,
        "email": user.email,
        "role": user.role,
        "is_active": getattr(user, "is_active", True),
        "created_at": user.created_at.isoformat() if getattr(user, "created_at", None) else "",
        "updated_at": getattr(user, "updated_at", None).isoformat() if getattr(user, "updated_at", None) else None,
    }

@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    user_data: dict,
    session: AsyncSession = Depends(db_uow),
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
            "id": updated_user.id,
            "login": updated_user.login,
            "email": updated_user.email,
            "full_name": getattr(updated_user, "full_name", None),
            "role": updated_user.role,
            "is_active": getattr(updated_user, "is_active", True),
            "created_at": updated_user.created_at.isoformat() if getattr(updated_user, "created_at", None) else "",
            "updated_at": getattr(updated_user, "updated_at", None).isoformat() if getattr(updated_user, "updated_at", None) else None,
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

@router.delete("/{user_id}")
async def delete_user(
    user_id: str,
    session: AsyncSession = Depends(db_uow),
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
    from fastapi import Response
    return Response(status_code=204)
