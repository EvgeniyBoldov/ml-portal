from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from sqlalchemy.orm import Session
import hashlib

from app.api.deps import db_session, rate_limit, get_current_user
from app.core.security import get_bearer_token
from app.services.users_service_enhanced import UsersService
from app.repositories.users_repo_enhanced import UsersRepository

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/login")
async def login(request: Request, payload: dict, session: Session = Depends(db_session)):
    # payload: {"login":"...", "password":"..."}
    login_ = (payload or {}).get("login", "").strip()
    password = (payload or {}).get("password", "")
    
    # Rate limit by IP + login
    await rate_limit(request, "auth_login", limit=10, window_sec=60, login=login_)
    if not login_ or not password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="missing_credentials")
    try:
        users_repo = UsersRepository(session)
        users_service = UsersService(users_repo)
        user = users_service.authenticate_user(login_, password)
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_credentials")
        
        # Generate tokens
        from app.core.security import encode_jwt
        from datetime import datetime, timedelta
        
        access_payload = {
            "sub": str(user.id),
            "user_id": str(user.id),
            "role": user.role,
            "exp": datetime.utcnow() + timedelta(hours=1)
        }
        access = encode_jwt(access_payload, ttl_seconds=3600)
        
        refresh_payload = {
            "sub": str(user.id),
            "user_id": str(user.id),
            "role": user.role,
            "exp": datetime.utcnow() + timedelta(days=30)
        }
        refresh = encode_jwt(refresh_payload, ttl_seconds=30*24*3600)
        
        user_id = str(user.id)
        u = user
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_credentials")
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "expires_in": 3600,
        "user": {"id": str(u.id), "fio": getattr(u, "fio", None), "login": u.login, "role": u.role} if u else None,
    }

@router.post("/refresh")
async def refresh(payload: dict, session: Session = Depends(db_session)):
    rt = (payload or {}).get("refresh_token")
    if not rt:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="missing_refresh_token")
    try:
        from app.core.security import decode_jwt
        from datetime import datetime, timedelta
        
        # Decode refresh token
        payload = decode_jwt(rt)
        user_id = payload.get("sub") or payload.get("user_id")
        if not user_id:
            raise ValueError("Invalid refresh token")
        
        # Get user
        users_repo = UsersRepository(session)
        user = users_repo.get_by_id(user_id)
        if not user or not user.is_active:
            raise ValueError("User not found or inactive")
        
        # Generate new access token
        access_payload = {
            "sub": str(user.id),
            "user_id": str(user.id),
            "role": user.role,
            "exp": datetime.utcnow() + timedelta(hours=1)
        }
        from app.core.security import encode_jwt
        access = encode_jwt(access_payload, ttl_seconds=3600)
        maybe_new_refresh = rt  # Keep the same refresh token
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    return {
        "access_token": access,
        "refresh_token": maybe_new_refresh,
        "token_type": "bearer",
        "expires_in": 3600,
    }

@router.get("/me")
def me(user = Depends(get_current_user)):
    return user

@router.post("/logout", status_code=204)
async def logout(payload: dict | None = None, session: Session = Depends(db_session)) -> Response:
    # Best-effort: revoke provided refresh token; if absent, just return 204 (contract allows empty body).
    rt = (payload or {}).get("refresh_token") if isinstance(payload, dict) else None
    if rt:
        users_repo = UsersRepository(session)
        users_service = UsersService(users_repo)
        await users_service.revoke_token(rt)
    return Response(status_code=204)
