from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from sqlalchemy.orm import Session
import hashlib

from app.api.deps import db_session, rate_limit, get_current_user
from app.core.security import get_bearer_token
from app.services.auth_service import login as do_login, refresh as do_refresh, revoke_refresh as do_revoke
from app.repositories.users_repo import UsersRepo

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/login")
async def login(request: Request, payload: dict, session: Session = Depends(db_session)):
    # payload: {"login":"...", "password":"..."}
    await rate_limit(request, "auth_login", limit=10, window_sec=60)
    login_ = (payload or {}).get("login", "").strip()
    password = (payload or {}).get("password", "")
    if not login_ or not password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="missing_credentials")
    try:
        access, refresh, user_id = do_login(session, login_, password)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_credentials")
    # enrich with user for convenience (per OpenAPI)
    u = UsersRepo(session).get(user_id)
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "expires_in": 3600,
        "user": {"id": str(u.id), "fio": getattr(u, "fio", None), "login": u.login, "role": u.role} if u else None,
    }

@router.post("/refresh")
def refresh(payload: dict, session: Session = Depends(db_session)):
    rt = (payload or {}).get("refresh_token")
    if not rt:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="missing_refresh_token")
    try:
        access, maybe_new_refresh = do_refresh(session, rt)
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
def logout(payload: dict | None = None, session: Session = Depends(db_session)) -> Response:
    # Best-effort: revoke provided refresh token; if absent, just return 204 (contract allows empty body).
    rt = (payload or {}).get("refresh_token") if isinstance(payload, dict) else None
    if rt:
        do_revoke(session, rt)
    return Response(status_code=204)
