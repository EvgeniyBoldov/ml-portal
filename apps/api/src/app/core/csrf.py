"""
CSRF protection module
"""
import secrets
import time
from fastapi import APIRouter, Response, Depends, Header, Cookie, HTTPException
from fastapi.responses import JSONResponse
from .redis import get_redis
from .error_handling import raise_bad_request, raise_forbidden

router = APIRouter()

CSRF_TTL = 60 * 30  # 30 minutes

@router.get("/csrf/token")
async def get_csrf_token(response: Response, redis=Depends(get_redis)):
    """Get CSRF token"""
    token = secrets.token_urlsafe(32)
    session_id = secrets.token_hex(16)
    await redis.setex(f"csrf:{session_id}", CSRF_TTL, token)
    response.set_cookie("csrf_session", session_id, httponly=True, samesite="strict")
    return {"message": "ok", "token": token}

async def validate_csrf(
    csrf_token: str | None = Header(None, alias="x-csrf-token"),
    session_id: str | None = Cookie(None, alias="csrf_session"),
    redis=Depends(get_redis),
):
    """Validate CSRF token"""
    if not csrf_token or not session_id:
        raise_bad_request("Missing CSRF", code="csrf_missing", status_code=403)
    
    stored = await redis.get(f"csrf:{session_id}")
    if not stored or stored != csrf_token:
        raise_forbidden("Invalid CSRF", code="csrf_invalid")
    
    return True
