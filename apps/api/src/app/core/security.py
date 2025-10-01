from __future__ import annotations
import time
import jwt
import re
from typing import Any, Dict, Optional, Literal
from pydantic import BaseModel
from argon2 import PasswordHasher
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.config import get_settings
import uuid

class UserCtx(BaseModel):
    id: str
    role: Literal["admin","editor","reader"] = "reader"
    tenant_id: Optional[uuid.UUID] = None

ph = PasswordHasher()
http_bearer = HTTPBearer(auto_error=False)

def hash_password(password: str) -> str:
    """Hash password with Argon2id and pepper"""
    # Add pepper if configured
    s = get_settings()
    if hasattr(s, 'PASSWORD_PEPPER') and s.PASSWORD_PEPPER:
        password = password + s.PASSWORD_PEPPER
    return ph.hash(password)

def verify_password(password: str, password_hash: str) -> bool:
    """Verify password with Argon2id and pepper"""
    try:
        # Add pepper if configured
        s = get_settings()
        if hasattr(s, 'PASSWORD_PEPPER') and s.PASSWORD_PEPPER:
            password = password + s.PASSWORD_PEPPER
        return ph.verify(password_hash, password)
    except Exception:
        return False

def validate_password_strength(password: str) -> tuple[bool, str]:
    """Validate password strength according to policy"""
    errors = []
    s = get_settings()
    
    if len(password) < s.PASSWORD_MIN_LENGTH:
        errors.append(f"Password must be at least {s.PASSWORD_MIN_LENGTH} characters long")
    
    if s.PASSWORD_REQUIRE_UPPERCASE and not re.search(r'[A-Z]', password):
        errors.append("Password must contain at least one uppercase letter")
    
    if s.PASSWORD_REQUIRE_LOWERCASE and not re.search(r'[a-z]', password):
        errors.append("Password must contain at least one lowercase letter")
    
    if s.PASSWORD_REQUIRE_DIGITS and not re.search(r'\d', password):
        errors.append("Password must contain at least one digit")
    
    if s.PASSWORD_REQUIRE_SPECIAL and not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        errors.append("Password must contain at least one special character")
    
    if errors:
        return False, "; ".join(errors)
    
    return True, ""

def encode_jwt(payload: Dict[str, Any], *, ttl_seconds: int) -> str:
    now = int(time.time())
    to_encode = {"iat": now, "exp": now + ttl_seconds, **payload}
    s = get_settings()
    return jwt.encode(to_encode, s.JWT_SECRET, algorithm=s.JWT_ALGORITHM)

def decode_jwt(token: str) -> Dict[str, Any]:
    try:
        s = get_settings()
        return jwt.decode(token, s.JWT_SECRET, algorithms=[s.JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token_expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_token")

# JWT Key Rotation Support
def get_jwt_secret() -> str:
    """Get current JWT secret with rotation support"""
    # TODO: Implement key rotation logic
    # For now, return the configured secret
    s = get_settings()
    return s.JWT_SECRET

def get_jwt_secret_with_rotation(token_payload: Dict[str, Any]) -> str:
    """Get JWT secret considering key rotation based on token timestamp"""
    # TODO: Implement key rotation based on token iat/exp
    # For now, return the configured secret
    s = get_settings()
    return s.JWT_SECRET

# FastAPI dependency
def get_bearer_token(credentials: HTTPAuthorizationCredentials | None = Depends(http_bearer)) -> str:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing_bearer")
    return credentials.credentials

def get_bearer_token_from_request(req) -> str:
    """Extract bearer token from request headers (alternative method)"""
    auth = req.headers.get("Authorization") or ""
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    token = auth.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    return token

def decode_token(token: str) -> dict:
    """Decode JWT token (alias for decode_jwt)"""
    return decode_jwt(token)

def get_current_user_from_token(token: str) -> UserCtx:
    """Get current user from JWT token"""
    payload = decode_token(token)
    uid = str(payload.get("sub") or payload.get("user_id") or "")
    role = payload.get("role") or "reader"
    tenant_id_str = payload.get("tenant_id")
    tenant_id = None
    if tenant_id_str:
        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except ValueError:
            # Invalid UUID format, keep tenant_id as None
            pass
    
    if not uid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return UserCtx(id=uid, role=role, tenant_id=tenant_id)
