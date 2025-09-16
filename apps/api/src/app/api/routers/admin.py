from __future__ import annotations
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from sqlalchemy.orm import Session
import secrets
import hashlib
from datetime import datetime, timedelta

from app.api.deps import (
    db_session, require_admin, get_request_id, get_client_ip, get_user_agent
)
from app.core.security import hash_password, verify_password, validate_password_strength
from app.core.pat_validation import validate_scopes, check_scope_permission
from app.repositories.users_repo import UsersRepo
from app.services.audit_service import AuditService
from app.schemas.admin import (
    UserCreate, UserUpdate, UserResponse, UserListResponse,
    PasswordResetRequest, PasswordResetConfirm, PasswordChange,
    TokenCreate, TokenResponse, TokenListResponse,
    AuditLogResponse, AuditLogListResponse,
    ErrorResponse, UserRole, AuditAction
)

router = APIRouter(prefix="/api/admin", tags=["admin"])


def create_error_response(code: str, message: str, request_id: str, 
                         details: Optional[dict] = None) -> dict:
    """Create standardized error response."""
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or {}
        },
        "request_id": request_id
    }


def user_to_response(user) -> UserResponse:
    """Convert User model to UserResponse schema."""
    return UserResponse(
        id=str(user.id),
        login=user.login,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
        updated_at=user.updated_at,
        require_password_change=getattr(user, 'require_password_change', False)
    )


# User Management Endpoints
@router.get("/users", response_model=UserListResponse)
def list_users(
    query: Optional[str] = None,
    role: Optional[str] = None,
    is_active: Optional[bool] = None,
    limit: int = 50,
    cursor: Optional[str] = None,
    session: Session = Depends(db_session),
    current_user: dict = Depends(require_admin),
    request: Request = None,
    request_id: str = Depends(get_request_id)
):
    """List users with pagination and filters."""
    if limit > 100:
        limit = 100
    
    repo = UsersRepo(session)
    users, has_more, next_cursor = repo.list_users(
        query=query, role=role, is_active=is_active, 
        limit=limit, cursor=cursor
    )
    
    total = repo.count_users(query=query, role=role, is_active=is_active)
    
    return UserListResponse(
        users=[user_to_response(user) for user in users],
        total=total,
        has_more=has_more,
        next_cursor=next_cursor
    )


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    user_data: UserCreate,
    session: Session = Depends(db_session),
    current_user: dict = Depends(require_admin),
    request: Request = None,
    request_id: str = Depends(get_request_id)
):
    """Create a new user."""
    repo = UsersRepo(session)
    audit = AuditService(session)
    
    # Check if user already exists
    existing_user = repo.by_login(user_data.login)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=create_error_response(
                "user_exists", 
                f"User with login '{user_data.login}' already exists",
                request_id
            ).dict()
        )
    
    # Generate password if not provided
    password = user_data.password
    if not password:
        password = secrets.token_urlsafe(16)
    else:
        # Validate password strength if provided
        is_valid, error_msg = validate_password_strength(password)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=create_error_response(
                    "invalid_password",
                    f"Password validation failed: {error_msg}",
                    request_id
                ).dict()
            )
    
    password_hash = hash_password(password)
    
    # Create user
    user = repo.create_user(
        login=user_data.login,
        password_hash=password_hash,
        role=user_data.role.value,
        email=user_data.email,
        is_active=user_data.is_active
    )
    
    # Log audit action
    audit.log_user_action(
        action=AuditAction.USER_CREATED,
        target_user_id=str(user.id),
        actor_user_id=current_user["id"],
        request=request,
        request_id=request_id,
        role=user_data.role.value,
        email=user_data.email
    )
    
    response = user_to_response(user)
    
    # Include generated password in response only if EMAIL_ENABLED=false
    if not user_data.password and not settings.EMAIL_ENABLED:
        response_dict = response.dict()
        response_dict["generated_password"] = password
        return response_dict
    
    return response


@router.get("/users/{user_id}", response_model=UserResponse)
def get_user(
    user_id: str,
    session: Session = Depends(db_session),
    current_user: dict = Depends(require_admin),
    request: Request = None,
    request_id: str = Depends(get_request_id)
):
    """Get user by ID."""
    repo = UsersRepo(session)
    user = repo.get(user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=create_error_response(
                "user_not_found",
                f"User with ID '{user_id}' not found",
                request_id
            ).dict()
        )
    
    return user_to_response(user)


@router.patch("/users/{user_id}", response_model=UserResponse)
def update_user(
    user_id: str,
    user_data: UserUpdate,
    session: Session = Depends(db_session),
    current_user: dict = Depends(require_admin),
    request: Request = None,
    request_id: str = Depends(get_request_id)
):
    """Update user."""
    repo = UsersRepo(session)
    audit = AuditService(session)
    
    user = repo.get(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=create_error_response(
                "user_not_found",
                f"User with ID '{user_id}' not found",
                request_id
            ).dict()
        )
    
    # Prepare updates
    updates = {}
    if user_data.role is not None:
        updates["role"] = user_data.role.value
    if user_data.email is not None:
        updates["email"] = user_data.email
    if user_data.is_active is not None:
        updates["is_active"] = user_data.is_active
    if user_data.require_password_change is not None:
        updates["require_password_change"] = user_data.require_password_change
    
    # Update user
    updated_user = repo.update_user(user_id, **updates)
    
    # Log audit action
    audit.log_user_action(
        action=AuditAction.USER_UPDATED,
        target_user_id=user_id,
        actor_user_id=current_user["id"],
        request=request,
        request_id=request_id,
        changes=updates
    )
    
    return user_to_response(updated_user)


@router.post("/users/{user_id}/password", response_model=dict)
def reset_user_password(
    user_id: str,
    password_data: PasswordChange,
    session: Session = Depends(db_session),
    current_user: dict = Depends(require_admin),
    request: Request = None,
    request_id: str = Depends(get_request_id)
):
    """Reset user password."""
    repo = UsersRepo(session)
    audit = AuditService(session)
    
    user = repo.get(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=create_error_response(
                "user_not_found",
                f"User with ID '{user_id}' not found",
                request_id
            ).dict()
        )
    
    # Generate new password if not provided
    new_password = password_data.new_password
    if not new_password:
        new_password = secrets.token_urlsafe(16)
    
    password_hash = hash_password(new_password)
    
    # Update password
    repo.update_user(user_id, password_hash=password_hash)
    
    # Revoke all refresh tokens
    for token in user.refresh_tokens:
        if not token.revoked:
            token.revoked = True
    
    session.commit()
    
    # Log audit action
    audit.log_user_action(
        action=AuditAction.PASSWORD_RESET,
        target_user_id=user_id,
        actor_user_id=current_user["id"],
        request=request,
        request_id=request_id
    )
    
    response = {"message": "Password reset successfully"}
    
    # Include new password only if EMAIL_ENABLED=false
    if not settings.EMAIL_ENABLED:
        response["new_password"] = new_password
    
    return response


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: str,
    session: Session = Depends(db_session),
    current_user: dict = Depends(require_admin),
    request: Request = None,
    request_id: str = Depends(get_request_id)
):
    """Soft delete user (deactivate)."""
    repo = UsersRepo(session)
    audit = AuditService(session)
    
    user = repo.get(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=create_error_response(
                "user_not_found",
                f"User with ID '{user_id}' not found",
                request_id
            ).dict()
        )
    
    # Soft delete (deactivate)
    repo.update_user(user_id, is_active=False)
    
    # Log audit action
    audit.log_user_action(
        action=AuditAction.USER_DEACTIVATED,
        target_user_id=user_id,
        actor_user_id=current_user["id"],
        request=request,
        request_id=request_id
    )
    
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# PAT Token Management Endpoints
@router.get("/users/{user_id}/tokens", response_model=TokenListResponse)
def list_user_tokens(
    user_id: str,
    session: Session = Depends(db_session),
    current_user: dict = Depends(require_admin),
    request: Request = None,
    request_id: str = Depends(get_request_id)
):
    """List user's PAT tokens."""
    repo = UsersRepo(session)
    
    user = repo.get(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=create_error_response(
                "user_not_found",
                f"User with ID '{user_id}' not found",
                request_id
            ).dict()
        )
    
    tokens = repo.get_user_tokens(user_id)
    total = len(tokens)
    
    return TokenListResponse(
        tokens=[TokenResponse.from_orm(token) for token in tokens],
        total=total
    )


@router.post("/users/{user_id}/tokens", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def create_user_token(
    user_id: str,
    token_data: TokenCreate,
    session: Session = Depends(db_session),
    current_user: dict = Depends(require_admin),
    request: Request = None,
    request_id: str = Depends(get_request_id)
):
    """Create a new PAT token for user."""
    repo = UsersRepo(session)
    audit = AuditService(session)
    
    user = repo.get(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=create_error_response(
                "user_not_found",
                f"User with ID '{user_id}' not found",
                request_id
            ).dict()
        )
    
    # Validate scopes
    scopes = [scope.value for scope in token_data.scopes] if token_data.scopes else []
    try:
        validated_scopes = validate_scopes(scopes)
    except HTTPException as e:
        raise e
    
    # Generate token
    token_plain = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token_plain.encode()).hexdigest()
    
    # Create token
    token = repo.create_token(
        user_id=user_id,
        token_hash=token_hash,
        name=token_data.name,
        scopes=validated_scopes,
        expires_at=token_data.expires_at
    )
    
    # Log audit action
    audit.log_token_action(
        action=AuditAction.TOKEN_CREATED,
        token_id=str(token.id),
        user_id=user_id,
        actor_user_id=current_user["id"],
        request=request,
        request_id=request_id,
        name=token_data.name
    )
    
    response = TokenResponse.from_orm(token)
    response.token_plain_once = token_plain
    
    return response


@router.delete("/tokens/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_token(
    token_id: str,
    session: Session = Depends(db_session),
    current_user: dict = Depends(require_admin),
    request: Request = None,
    request_id: str = Depends(get_request_id)
):
    """Revoke a PAT token."""
    repo = UsersRepo(session)
    audit = AuditService(session)
    
    token = repo.s.get(repo.UserTokens, token_id)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=create_error_response(
                "token_not_found",
                f"Token with ID '{token_id}' not found",
                request_id
            ).dict()
        )
    
    # Revoke token
    success = repo.revoke_token(token_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=create_error_response(
                "token_already_revoked",
                "Token is already revoked",
                request_id
            ).dict()
        )
    
    # Log audit action
    audit.log_token_action(
        action=AuditAction.TOKEN_REVOKED,
        token_id=token_id,
        user_id=str(token.user_id),
        actor_user_id=current_user["id"],
        request=request,
        request_id=request_id
    )
    
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# Audit Logs Endpoints
@router.get("/audit-logs", response_model=AuditLogListResponse)
def list_audit_logs(
    actor_user_id: Optional[str] = None,
    action: Optional[str] = None,
    object_type: Optional[str] = None,
    limit: int = 50,
    cursor: Optional[str] = None,
    session: Session = Depends(db_session),
    current_user: dict = Depends(require_admin),
    request: Request = None,
    request_id: str = Depends(get_request_id)
):
    """List audit logs with pagination and filters."""
    if limit > 100:
        limit = 100
    
    repo = UsersRepo(session)
    logs, has_more, next_cursor = repo.get_audit_logs(
        actor_user_id=actor_user_id,
        action=action,
        object_type=object_type,
        limit=limit,
        cursor=cursor
    )
    
    total = repo.count_audit_logs(
        actor_user_id=actor_user_id,
        action=action,
        object_type=object_type
    )
    
    return AuditLogListResponse(
        logs=[AuditLogResponse.from_orm(log) for log in logs],
        total=total,
        has_more=has_more,
        next_cursor=next_cursor
    )
