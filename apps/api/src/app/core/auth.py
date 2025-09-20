from __future__ import annotations
from typing import Optional, Literal
from fastapi import Depends, HTTPException, status, Request
from pydantic import BaseModel
import jwt
from .config import settings

class UserCtx(BaseModel):
    id: str
    role: Literal["admin","editor","reader"] = "reader"

def _unauthorized():
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

def _forbidden():
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

def get_bearer_token(req: Request) -> str:
    auth = req.headers.get("Authorization") or ""
    if not auth.lower().startswith("bearer "):
        _unauthorized()
    token = auth.split(" ", 1)[1].strip()
    if not token:
        _unauthorized()
    return token

def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except Exception:
        _unauthorized()

def get_current_user(req: Request) -> UserCtx:
    token = get_bearer_token(req)
    payload = decode_token(token)
    uid = str(payload.get("sub") or payload.get("user_id") or "")
    role = payload.get("role") or "reader"
    if not uid:
        _unauthorized()
    return UserCtx(id=uid, role=role)

def require_user(user: UserCtx = Depends(get_current_user)) -> UserCtx:
    return user

def require_admin(user: UserCtx = Depends(get_current_user)) -> UserCtx:
    if user.role != "admin":
        _forbidden()
    return user
