from __future__ import annotations
import time
import jwt
from typing import Any, Dict, Optional
from argon2 import PasswordHasher
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from .config import settings

ph = PasswordHasher()
http_bearer = HTTPBearer(auto_error=False)

def hash_password(password: str) -> str:
    return ph.hash(password)

def verify_password(password: str, password_hash: str) -> bool:
    try:
        return ph.verify(password_hash, password)
    except Exception:
        return False

def encode_jwt(payload: Dict[str, Any], *, ttl_seconds: int) -> str:
    now = int(time.time())
    to_encode = {"iat": now, "exp": now + ttl_seconds, **payload}
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm="HS256")

def decode_jwt(token: str) -> Dict[str, Any]:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token_expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_token")

# FastAPI dependency
def get_bearer_token(credentials: HTTPAuthorizationCredentials | None = Depends(http_bearer)) -> str:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing_bearer")
    return credentials.credentials
