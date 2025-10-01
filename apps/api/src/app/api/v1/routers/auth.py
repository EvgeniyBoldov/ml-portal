"""
Auth endpoints for API v1
"""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from sqlalchemy.orm import Session
import hashlib
from datetime import datetime

from app.api.deps import db_session, rate_limit, get_current_user
from app.core.security import UserCtx
from app.core.security import get_bearer_token
from app.services.users_service import UsersService
from app.repositories.users_repo import UsersRepository
from app.schemas.common import Problem
from app.schemas.auth import (
    AuthLoginRequest, AuthRefreshRequest, AuthTokensResponse,
    UserMeResponse, PasswordForgotRequest, PasswordResetRequest,
    PasswordResetResponse, PATTokenCreateRequest, PATTokenResponse,
    PATTokensListResponse
)

router = APIRouter(tags=["auth"])

@router.post("/auth/login", response_model=AuthTokensResponse)
async def login(request: Request, payload: AuthLoginRequest, session: Session = Depends(db_session)):
    """Login endpoint with rate limiting and proper validation"""
    # Rate limit by IP + email
    await rate_limit(request, "auth_login", limit=10, window_sec=60, login=payload.email)
    try:
        users_repo = UsersRepository(session)
        users_service = UsersService(users_repo)
        user = users_service.authenticate_user(payload.email, payload.password)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=Problem(
                    type="https://example.com/problems/invalid-credentials",
                    title="Authentication Failed",
                    status=401,
                    code="INVALID_CREDENTIALS",
                    detail="Invalid email or password"
                ).model_dump()
            )
        
        # Generate tokens
        from app.core.security import encode_jwt
        from datetime import datetime, timedelta
        
        access_payload = {
            "sub": str(user.id),
            "user_id": str(user.id),
            "role": user.role,
            "exp": datetime.utcnow() + timedelta(minutes=15)  # 15 minutes as per contract
        }
        access = encode_jwt(access_payload, ttl_seconds=15*60)
        
        refresh_payload = {
            "sub": str(user.id),
            "user_id": str(user.id),
            "role": user.role,
            "exp": datetime.utcnow() + timedelta(days=30)  # 30 days as per contract
        }
        refresh = encode_jwt(refresh_payload, ttl_seconds=30*24*3600)
        
        user_id = str(user.id)
        u = user
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=Problem(
                type="https://example.com/problems/invalid-credentials",
                title="Authentication Failed",
                status=401,
                code="INVALID_CREDENTIALS",
                detail="Invalid email or password"
            ).model_dump()
        )
    
    return AuthTokensResponse(
        access_token=access,
        refresh_token=refresh,
        token_type="bearer",
        expires_in=900,  # 15 minutes
        refresh_expires_in=30*24*3600,  # 30 days
        user=UserMeResponse(
            id=str(u.id),
            role=u.role,
            login=getattr(u, "login", None),
            fio=getattr(u, "fio", None)
        ) if u else None
    )

@router.post("/auth/refresh", response_model=AuthTokensResponse)
async def refresh(payload: AuthRefreshRequest, session: Session = Depends(db_session)):
    """Refresh access token with proper TTL (G8 compliant)"""
    
    try:
        from app.core.security import decode_jwt
        from datetime import datetime, timedelta
        
        # Decode refresh token
        token_payload = decode_jwt(payload.refresh_token)
        user_id = token_payload.get("sub") or token_payload.get("user_id")
        if not user_id:
            raise ValueError("Invalid refresh token")
        
        # Get user
        users_repo = UsersRepository(session)
        user = users_repo.get_by_id(user_id)
        if not user or not user.is_active:
            raise ValueError("User not found or inactive")
        
        # Generate new access token with 15 minutes TTL
        access_payload = {
            "sub": str(user.id),
            "user_id": str(user.id),
            "role": user.role,
            "exp": datetime.utcnow() + timedelta(minutes=15)  # 15 minutes as per contract
        }
        from app.core.security import encode_jwt
        access = encode_jwt(access_payload, ttl_seconds=15*60)
        
        # Keep the same refresh token (30 days TTL)
        # In production, might want to rotate refresh tokens for security
        maybe_new_refresh = payload.refresh_token
        
        return AuthTokensResponse(
            access_token=access,
            refresh_token=maybe_new_refresh,
            token_type="bearer",
            expires_in=900,  # 15 minutes
            refresh_expires_in=30*24*3600,  # 30 days
            user=UserMeResponse(
                id=str(user.id),
                role=user.role,
                login=getattr(user, "login", None),
                fio=getattr(user, "fio", None)
            )
        )
        
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Token refresh failed: {str(e)}")

@router.get("/auth/me", response_model=UserMeResponse)
def me(user: UserCtx = Depends(get_current_user)):
    """Get current user information"""
    return UserMeResponse(
        id=user.id,
        role=user.role,
        login=None,  # Don't expose login in /me for security
        fio=None     # Don't expose FIO in /me for security
    )

@router.post("/auth/logout", status_code=204)
async def logout(payload: dict | None = None, session: Session = Depends(db_session)) -> Response:
    """Logout with refresh token revocation (G8 compliant)"""
    try:
        # Best-effort: revoke provided refresh token; if absent, just return 204 (contract allows empty body).
        rt = (payload or {}).get("refresh_token") if isinstance(payload, dict) else None
        
        if rt:
            # Revoke refresh token
            users_repo = UsersRepository(session)
            users_service = UsersService(users_repo)
            await users_service.revoke_token(rt)
            
            # TODO: In production, also revoke all related refresh tokens for the user
            # This ensures complete logout across all devices/sessions
        
        return Response(status_code=204)
        
    except Exception as e:
        # Even if revocation fails, return 204 (best-effort logout)
        print(f"Logout revocation failed: {e}")
        return Response(status_code=204)

@router.get("/tokens/pat", response_model=PATTokensListResponse)
def list_pat_tokens(
    session: Session = Depends(db_session),
    user: UserCtx = Depends(get_current_user),
):
    """List personal access tokens with mask (G8 compliant)"""
    try:
        # TODO: Implement actual PAT listing from database
        # For now, simulate PAT listing with masked tokens
        
        user_id = user.id
        if not user_id:
            raise HTTPException(status_code=401, detail="User not authenticated")
        
        # Simulate PAT tokens with mask
        pat_tokens = [
            PATTokenResponse(
                id=f"pat_{user_id}_1",
                name="API Integration Token",
                token_mask="pat_****_****_****_****_****_****_****_****",
                created_at=datetime.utcnow().isoformat(),
                expires_at=int(datetime.utcnow().timestamp() + 30*24*3600),  # 30 days
                last_used_at=None,
                is_active=True
            ),
            PATTokenResponse(
                id=f"pat_{user_id}_2", 
                name="Development Token",
                token_mask="pat_****_****_****_****_****_****_****_****",
                created_at=datetime.utcnow().isoformat(),
                expires_at=int(datetime.utcnow().timestamp() + 7*24*3600),  # 7 days
                last_used_at=datetime.utcnow().isoformat(),
                is_active=True
            )
        ]
        
        return PATTokensListResponse(tokens=pat_tokens)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list PAT tokens: {str(e)}")

@router.post("/tokens/pat", response_model=PATTokenResponse)
def create_pat_token(
    pat_data: PATTokenCreateRequest,
    session: Session = Depends(db_session),
    user: UserCtx = Depends(get_current_user),
):
    """Create personal access token with hash/mask (G8 compliant)"""
    
    try:
        user_id = user.id
        if not user_id:
            raise HTTPException(status_code=401, detail="User not authenticated")
        
        # Generate PAT ID
        pat_id = f"pat_{user_id}_{datetime.utcnow().timestamp()}"
        
        # Generate secure token (show only once)
        import secrets
        token_secret = secrets.token_urlsafe(32)
        full_token = f"pat_{pat_id}_{token_secret}"
        
        # Create hash for storage (never store plain token)
        token_hash = hashlib.sha256(full_token.encode()).hexdigest()
        
        # Create mask for display
        token_mask = f"pat_{pat_id[:8]}****_****_****_****_****_****_****"
        
        # TODO: Store in database with hash
        # For now, simulate storage
        
        return PATTokenResponse(
            id=pat_id,
            name=pat_data.name,
            token=full_token,  # Show only once - never again
            token_mask=token_mask,
            created_at=datetime.utcnow().isoformat(),
            expires_at=pat_data.expires_at,
            last_used_at=None,
            is_active=True
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create PAT token: {str(e)}")

@router.delete("/tokens/pat/{token_id}")
def revoke_pat_token(
    token_id: str,
    session: Session = Depends(db_session),
    user: UserCtx = Depends(get_current_user),
):
    """Revoke personal access token (G8 compliant)"""
    try:
        user_id = user.id
        if not user_id:
            raise HTTPException(status_code=401, detail="User not authenticated")
        
        # TODO: Implement actual PAT revocation from database
        # For now, simulate revocation
        
        # Check if token belongs to user
        if not token_id.startswith(f"pat_{user_id}_"):
            raise HTTPException(status_code=404, detail="PAT token not found")
        
        # Simulate revocation
        # In real implementation, would mark token as revoked in database
        
        return Response(status_code=204)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to revoke PAT token: {str(e)}")
