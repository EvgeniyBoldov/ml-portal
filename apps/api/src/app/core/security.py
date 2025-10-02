from __future__ import annotations
import time
from dataclasses import dataclass
from typing import Optional, Any, Dict
import jwt
from argon2 import PasswordHasher
from .config import get_settings

ph = PasswordHasher()

@dataclass
class UserCtx:
    id: str
    role: str = "reader"
    tenant_ids: list[str] | None = None

def hash_password(password: str) -> str:
    pepper = (get_settings().PASSWORD_PEPPER or "")
    return ph.hash(password + pepper)

def verify_password(password: str, password_hash: str) -> bool:
    try:
        pepper = (get_settings().PASSWORD_PEPPER or "")
        ph.verify(password_hash, password + pepper)
        return True
    except Exception:
        return False

def encode_jwt(payload: Dict[str, Any], *, ttl_seconds: int | None = None) -> str:
    s = get_settings()
    now = int(time.time())
    to_encode = {**payload, "iss": s.JWT_ISSUER, "aud": s.JWT_AUDIENCE, "iat": now}
    if ttl_seconds:
        to_encode["exp"] = now + ttl_seconds
    headers = {"kid": s.JWT_KID} if s.JWT_KID else None
    return jwt.encode(to_encode, s.JWT_SECRET, algorithm=s.JWT_ALGORITHM, headers=headers)

def decode_jwt(token: str) -> Dict[str, Any]:
    s = get_settings()
    return jwt.decode(token, s.JWT_SECRET, algorithms=[s.JWT_ALGORITHM], audience=s.JWT_AUDIENCE, issuer=s.JWT_ISSUER)
