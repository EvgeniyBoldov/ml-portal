# apps/api/src/app/api/routers/users.py
from __future__ import annotations
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

# Импортируем схемы и сервисы напрямую
from app.api.schemas.users import (
    UserCreateRequest, UserUpdateRequest, UserSearchRequest, UserResponse,
    UserListResponse, UserStatsResponse, PasswordChangeRequest, PasswordResetRequest,
    PasswordResetConfirmRequest, PATTokenCreateRequest, PATTokenCreateResponse,
    PATTokenListResponse, PATTokenResponse
)
from app.api.deps import db_session, get_current_user, require_admin
from app.services.users_service_enhanced import UsersService, create_users_service

router = APIRouter(prefix="/users", tags=["users"])

def get_users_service(session: Session = Depends(db_session)) -> UsersService:
    """Get users service"""
    return create_users_service(session)

@router.post("/", response_model=Dict[str, Any])
async def create_user(
    request: UserCreateRequest,
    current_user: Dict[str, Any] = Depends(require_admin),
    service: UsersService = Depends(get_users_service)
):
    """Create a new user"""
    user = service.create_user(
        login=request.login,
        password=request.password,
        role=request.role.value,
        email=request.email,
        is_active=request.is_active
    )
    return {
        "success": True,
        "data": UserResponse.from_orm(user).dict(),
        "message": "User created successfully"
    }

@router.get("/{user_id}", response_model=Dict[str, Any])
async def get_user(
    user_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: UsersService = Depends(get_users_service)
):
    """Get user by ID"""
    # Check permissions (admin or own user)
    if current_user.get("user_role") != "admin" and current_user.get("user_id") != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    
    user = service.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    return {
        "success": True,
        "data": UserResponse.from_orm(user).dict()
    }

@router.put("/{user_id}", response_model=Dict[str, Any])
async def update_user(
    user_id: str,
    request: UserUpdateRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: UsersService = Depends(get_users_service)
):
    """Update user"""
    # Check permissions (admin or own user)
    if current_user.get("user_role") != "admin" and current_user.get("user_id") != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    
    # Prepare update data
    update_data = {}
    if request.email is not None:
        update_data["email"] = request.email
    if request.role is not None:
        # Only admin can change roles
        if current_user.get("user_role") != "admin":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admin can change user roles")
        update_data["role"] = request.role.value
    if request.is_active is not None:
        # Only admin can change active status
        if current_user.get("user_role") != "admin":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admin can change user active status")
        update_data["is_active"] = request.is_active
    
    if not update_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update")
    
    user = service.update(user_id, **update_data)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    return {
        "success": True,
        "data": UserResponse.from_orm(user).dict(),
        "message": "User updated successfully"
    }

@router.delete("/{user_id}", response_model=Dict[str, Any])
async def delete_user(
    user_id: str,
    current_user: Dict[str, Any] = Depends(require_admin),
    service: UsersService = Depends(get_users_service)
):
    """Delete user"""
    # Prevent self-deletion
    if current_user.get("user_id") == user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete your own account")
    
    result = service.delete(user_id)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    return {
        "success": True,
        "data": {"deleted": True},
        "message": "User deleted successfully"
    }

@router.post("/search", response_model=Dict[str, Any])
async def search_users(
    request: UserSearchRequest,
    current_user: Dict[str, Any] = Depends(require_admin),
    service: UsersService = Depends(get_users_service)
):
    """Search users"""
    users = service.search_users(
        query=request.query or "",
        role=request.role.value if request.role else None,
        is_active=request.is_active,
        limit=request.limit
    )
    
    total = service.count()
    
    return {
        "success": True,
        "data": UserListResponse(
            users=[UserResponse.from_orm(user).dict() for user in users],
            total=total,
            limit=request.limit,
            offset=request.offset,
            has_more=request.offset + request.limit < total
        ).dict()
    }

@router.get("/{user_id}/stats", response_model=Dict[str, Any])
async def get_user_stats(
    user_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: UsersService = Depends(get_users_service)
):
    """Get user statistics"""
    # Check permissions (admin or own user)
    if current_user.get("user_role") != "admin" and current_user.get("user_id") != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    
    stats = service.get_user_stats(user_id)
    
    return {
        "success": True,
        "data": stats
    }

@router.post("/{user_id}/change-password", response_model=Dict[str, Any])
async def change_password(
    user_id: str,
    request: PasswordChangeRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: UsersService = Depends(get_users_service)
):
    """Change user password"""
    # Check permissions (admin or own user)
    if current_user.get("user_role") != "admin" and current_user.get("user_id") != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    
    result = service.change_password(
        user_id=user_id,
        old_password=request.current_password,
        new_password=request.new_password
    )
    
    if not result:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password change failed")
    
    return {
        "success": True,
        "data": {"changed": True},
        "message": "Password changed successfully"
    }

@router.post("/reset-password", response_model=Dict[str, Any])
async def reset_password_request(
    request: PasswordResetRequest,
    service: UsersService = Depends(get_users_service)
):
    """Request password reset"""
    result = service.reset_password_request(request.email)
    
    return {
        "success": True,
        "data": {"requested": True},
        "message": "Password reset email sent if account exists"
    }

@router.post("/reset-password/confirm", response_model=Dict[str, Any])
async def reset_password_confirm(
    request: PasswordResetConfirmRequest,
    service: UsersService = Depends(get_users_service)
):
    """Confirm password reset"""
    result = service.reset_password_confirm(
        token=request.token,
        new_password=request.new_password
    )
    
    if not result:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password reset failed")
    
    return {
        "success": True,
        "data": {"reset": True},
        "message": "Password reset successfully"
    }

@router.post("/pat-tokens", response_model=Dict[str, Any])
async def create_pat_token(
    request: PATTokenCreateRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: UsersService = Depends(get_users_service)
):
    """Create PAT token"""
    token_record, access_token = service.create_pat_token(
        user_id=current_user.get("user_id"),
        name=request.name,
        scopes=request.scopes,
        expires_at=request.expires_at
    )
    
    return {
        "success": True,
        "data": PATTokenCreateResponse(
            token=PATTokenResponse.from_orm(token_record).dict(),
            access_token=access_token
        ).dict(),
        "message": "PAT token created successfully"
    }

@router.get("/pat-tokens", response_model=Dict[str, Any])
async def get_pat_tokens(
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: UsersService = Depends(get_users_service)
):
    """Get user's PAT tokens"""
    tokens = service.get_user_tokens(current_user.get("user_id"))
    
    return {
        "success": True,
        "data": PATTokenListResponse(
            tokens=[PATTokenResponse.from_orm(token).dict() for token in tokens],
            total=len(tokens)
        ).dict()
    }

@router.delete("/pat-tokens/{token_id}", response_model=Dict[str, Any])
async def revoke_pat_token(
    token_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: UsersService = Depends(get_users_service)
):
    """Revoke PAT token"""
    result = service.revoke_pat_token(current_user.get("user_id"), token_id)
    
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found")
    
    return {
        "success": True,
        "data": {"revoked": True},
        "message": "PAT token revoked successfully"
    }