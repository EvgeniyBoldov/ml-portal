"""
Users endpoints for API v1
"""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import db_session, db_uow, require_admin
from app.repositories.users_repo import AsyncUsersRepository
from app.services.users_service import AsyncUsersService
from app.schemas.common import ProblemDetails
from app.schemas.users import UserCreate, UserListResponse, UserPasswordUpdate, UserResponse, UserUpdate

router = APIRouter(tags=["users"])


async def _user_response(user, repo: AsyncUsersRepository) -> dict:
    default_tid = await repo.get_default_tenant(user.id)
    return {
        "id": user.id,
        "login": user.login,
        "email": user.email,
        "full_name": getattr(user, "full_name", None),
        "role": user.role,
        "is_admin": bool(user.is_admin),
        "memory_scope_keys": list(user.memory_scope_keys or []),
        "is_active": getattr(user, "is_active", True),
        "auth_provider": getattr(user, "auth_provider", "local"),
        "deactivated_reason": getattr(user, "deactivated_reason", None),
        "tenant_id": str(default_tid) if default_tid else None,
        "lifecycle_status": getattr(user, "lifecycle_status", "active"),
        "deprecated_at": getattr(user, "deprecated_at", None),
        "retention_days": getattr(user, "retention_days", None),
        "created_at": user.created_at.isoformat() if getattr(user, "created_at", None) else "",
        "updated_at": user.updated_at.isoformat() if getattr(user, "updated_at", None) else None,
        "last_login_at": user.last_login_at.isoformat() if getattr(user, "last_login_at", None) else None,
    }

@router.get("", response_model=UserListResponse)
async def list_users(
    limit: int = Query(20, ge=1, le=100),
    cursor: str | None = None,
    query: str | None = None,
    role: str | None = None,
    is_active: bool | None = None,
    include_deprecated: bool = Query(False),
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
        include_deprecated=include_deprecated,
    )
    items = []
    for u in users:
        default_tid = await repo.get_default_tenant(u.id)
        items.append({
            "id": u.id,
            "login": u.login,
            "email": u.email,
            "full_name": getattr(u, "full_name", None),
            "role": u.role,
            "is_admin": bool(u.is_admin),
            "is_active": getattr(u, "is_active", True),
            "auth_provider": getattr(u, "auth_provider", "local"),
            "deactivated_reason": getattr(u, "deactivated_reason", None),
            "tenant_id": default_tid,
            "lifecycle_status": getattr(u, "lifecycle_status", "active"),
            "deprecated_at": getattr(u, "deprecated_at", None),
            "retention_days": getattr(u, "retention_days", None),
            "created_at": u.created_at.isoformat() if getattr(u, "created_at", None) else "",
            "updated_at": getattr(u, "updated_at", None).isoformat() if getattr(u, "updated_at", None) else None,
            "last_login_at": getattr(u, "last_login_at", None).isoformat() if getattr(u, "last_login_at", None) else None,
        })
    return {
        "users": items,
        "has_more": has_more,
        "next_cursor": next_cursor,
        "total": total,
    }

@router.post("", response_model=UserResponse)
async def create_user(
    user_data: UserCreate,
    session: AsyncSession = Depends(db_uow),
    admin_user = Depends(require_admin),
):
    """Create a local user (admin only). LDAP users are provisioned on login."""
    repo = AsyncUsersRepository(session)
    service = AsyncUsersService(repo)
    
    # Extract user data
    try:
        user = await service.create_user(
            login=user_data.login,
            full_name=user_data.full_name,
            email=user_data.email,
            password=user_data.password,
            role=user_data.role.value,
            tenant_id=user_data.tenant_id,
            is_active=user_data.is_active,
            memory_scope_keys=user_data.memory_scope_keys,
            is_admin=user_data.is_admin or user_data.role.value == "admin",
        )
        return await _user_response(user, repo)
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
    
    return await _user_response(user, repo)

@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    user_data: UserUpdate,
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
        updated_user = await service.update_user(user_id, user_data.model_dump(exclude_unset=True))
        return await _user_response(updated_user, repo)
    except ValueError as e:
        if str(e) == "last_admin":
            raise HTTPException(
                status_code=409,
                detail=ProblemDetails(title="Conflict", status=409, detail="last_admin").model_dump(),
            ) from e
        if "already exists" in str(e).lower() or "already taken" in str(e).lower():
            raise HTTPException(
                status_code=409,
                detail=ProblemDetails(title="Conflict", status=409, detail=str(e)).model_dump(),
            ) from e
        raise HTTPException(
            status_code=400, 
            detail=ProblemDetails(
                title="Bad Request",
                status=400,
                detail=str(e)
            ).model_dump()
        )

@router.post("/{user_id}/password")
async def set_user_password(
    user_id: str,
    body: UserPasswordUpdate,
    session: AsyncSession = Depends(db_uow),
    admin_user = Depends(require_admin),
):
    """Set user password (admin only, local accounts only)"""
    repo = AsyncUsersRepository(session)
    service = AsyncUsersService(repo)

    user = await repo.get_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=404,
            detail=ProblemDetails(title="Not Found", status=404, detail="not_found").model_dump(),
        )

    auth_provider = getattr(user, "auth_provider", "local")
    if auth_provider != "local":
        raise HTTPException(
            status_code=400,
            detail=ProblemDetails(
                title="Bad Request",
                status=400,
                detail="password_change_not_allowed_for_non_local_accounts",
            ).model_dump(),
        )

    await service.update_user(user_id, {"password": body.new_password})
    return {"ok": True}
