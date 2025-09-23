from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
import secrets
import hashlib
from datetime import datetime, timedelta

from app.api.deps import db_session, get_request_id, get_client_ip, get_user_agent, rate_limit
from app.core.security import hash_password, validate_password_strength
from app.repositories.users_repo_enhanced import UsersRepository
from app.services.audit_service import AuditService
from app.api.schemas.users import PasswordResetRequest, PasswordResetConfirm, ErrorResponse, AuditAction

router = APIRouter(prefix="/auth", tags=["password-reset"])


def create_error_response(code: str, message: str, request_id: str, 
                         details: Optional[dict] = None) -> ErrorResponse:
    """Create standardized error response."""
    return ErrorResponse(
        code=code,
        message=message,
        request_id=request_id,
        details=details
    )


@router.post("/password/forgot", status_code=status.HTTP_200_OK)
async def forgot_password(
    request_data: PasswordResetRequest,
    session: Session = Depends(db_session),
    request: Request = None,
    request_id: str = Depends(get_request_id)
):
    """Request password reset. Always returns 200 for security."""
    # Rate limiting for password reset requests
    await rate_limit(request, "password_reset", limit=5, window_sec=300)  # 5 attempts per 5 minutes
    
    repo = UsersRepository(session)
    audit = AuditService(session)
    
    # Find user by login or email
    user = repo.by_login(request_data.login_or_email)
    if not user and "@" in request_data.login_or_email:
        # Try to find by email
        users = repo.s.execute(
            repo.s.query(repo.Users).filter(repo.Users.email == request_data.login_or_email)
        ).scalars().all()
        if users:
            user = users[0]
    
    if not user or not user.is_active:
        # Always return 200 for security (don't reveal if user exists)
        return {"message": "If the account exists, a password reset link has been sent"}
    
    # Generate reset token
    token_plain = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token_plain.encode()).hexdigest()
    expires_at = datetime.utcnow() + timedelta(minutes=60)  # 1 hour expiry
    
    # Create reset token
    repo.create_password_reset_token(
        user_id=str(user.id),
        token_hash=token_hash,
        expires_at=expires_at
    )
    
    # Log audit action
    audit.log_auth_action(
        action=AuditAction.PASSWORD_RESET,
        user_id=str(user.id),
        request=request,
        request_id=request_id,
        method="email_request"
    )
    
    # TODO: Send email with reset link
    # For now, we'll just return the token in development
    # In production, this should be sent via email
    if not user.email:
        return {
            "message": "Password reset requested. Contact administrator for reset token.",
            "token": token_plain  # Only for development
        }
    
    # TODO: Implement email sending
    # send_password_reset_email(user.email, token_plain)
    
    return {"message": "If the account exists, a password reset link has been sent"}


@router.post("/password/reset", status_code=status.HTTP_200_OK)
async def reset_password(
    request_data: PasswordResetConfirm,
    session: Session = Depends(db_session),
    request: Request = None,
    request_id: str = Depends(get_request_id)
):
    """Reset password using token."""
    # Rate limiting for password reset attempts
    await rate_limit(request, "password_reset_confirm", limit=10, window_sec=300)  # 10 attempts per 5 minutes
    
    repo = UsersRepository(session)
    audit = AuditService(session)
    
    # Hash the provided token
    token_hash = hashlib.sha256(request_data.token.encode()).hexdigest()
    
    # Find valid reset token
    reset_token = repo.get_password_reset_token(token_hash)
    if not reset_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=create_error_response(
                "invalid_token",
                "Invalid or expired reset token",
                request_id
            ).dict()
        )
    
    # Validate new password
    is_valid, error_msg = validate_password_strength(request_data.new_password)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=create_error_response(
                "invalid_password",
                f"Password validation failed: {error_msg}",
                request_id
            ).dict()
        )
    
    # Update password
    password_hash = hash_password(request_data.new_password)
    repo.update_user(str(reset_token.user_id), password_hash=password_hash)
    
    # Mark token as used
    repo.use_password_reset_token(token_hash)
    
    # Revoke all refresh tokens for security
    user = repo.get(str(reset_token.user_id))
    if user:
        for token in user.refresh_tokens:
            if not token.revoked:
                token.revoked = True
        session.commit()
    
    # Log audit action
    audit.log_auth_action(
        action=AuditAction.PASSWORD_RESET,
        user_id=str(reset_token.user_id),
        request=request,
        request_id=request_id,
        method="email_reset"
    )
    
    return {"message": "Password reset successfully"}
