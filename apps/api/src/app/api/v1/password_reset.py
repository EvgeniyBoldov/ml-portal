from __future__ import annotations
from typing import Any
from fastapi import APIRouter, Depends, Request, HTTPException
from app.api.deps import db_session, rate_limit, get_client_ip
from app.core.middleware import get_request_id  # provided by your core middleware __init__
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/v1/password-reset", tags=["auth"])

def get_user_agent(request: Request) -> str:
    return request.headers.get("user-agent", "") or ""

@router.post("")
def start_reset(body: dict[str, Any], request: Request, session: Session = Depends(db_session)):
    _ = get_request_id(request)
    ip = get_client_ip(request)
    ua = get_user_agent(request)
    email = (body or {}).get("email")
    if not email:
        raise HTTPException(status_code=400, detail="email is required")
    # TODO: implement actual reset logic
    return {"ok": True, "email": email, "ip": ip, "ua": ua}
