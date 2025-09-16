from __future__ import annotations
import time
import jwt
import re
from typing import Any, Dict, Optional
from argon2 import PasswordHasher
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from .config import settings

ph = PasswordHasher()
http_bearer = HTTPBearer(auto_error=False)

def hash_password(password: str) -> str:
    """Hash password with Argon2id and pepper"""
    # Add pepper if configured
    if hasattr(settings, 'PASSWORD_PEPPER') and settings.PASSWORD_PEPPER:
        password = password + settings.PASSWORD_PEPPER
    return ph.hash(password)

def verify_password(password: str, password_hash: str) -> bool:
    """Verify password with Argon2id and pepper"""
    try:
        # Add pepper if configured
        if hasattr(settings, 'PASSWORD_PEPPER') and settings.PASSWORD_PEPPER:
            password = password + settings.PASSWORD_PEPPER
        return ph.verify(password_hash, password)
    except Exception:
        return False

def validate_password_strength(password: str) -> tuple[bool, str]:
    """Validate password strength according to policy"""
    errors = []
    
    if len(password) < settings.PASSWORD_MIN_LENGTH:
        errors.append(f"Password must be at least {settings.PASSWORD_MIN_LENGTH} characters long")
    
    if settings.PASSWORD_REQUIRE_UPPERCASE and not re.search(r'[A-Z]', password):
        errors.append("Password must contain at least one uppercase letter")
    
    if settings.PASSWORD_REQUIRE_LOWERCASE and not re.search(r'[a-z]', password):
        errors.append("Password must contain at least one lowercase letter")
    
    if settings.PASSWORD_REQUIRE_DIGITS and not re.search(r'\d', password):
        errors.append("Password must contain at least one digit")
    
    if settings.PASSWORD_REQUIRE_SPECIAL and not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        errors.append("Password must contain at least one special character")
    
    if errors:
        return False, "; ".join(errors)
    
    return True, ""

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
