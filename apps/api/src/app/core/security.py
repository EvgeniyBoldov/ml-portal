from __future__ import annotations
import time
import uuid
from dataclasses import dataclass
from typing import Optional, Any, Dict, List
import jwt
from argon2 import PasswordHasher
from fastapi import HTTPException, status
from .config import get_settings

ph = PasswordHasher()

@dataclass
class UserCtx:
    id: str
    email: str | None = None
    role: str = "reader"
    tenant_ids: List[str] | None = None
    scopes: List[str] | None = None

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

def create_access_token(user_id: str, email: str, role: str, tenant_ids: List[str], scopes: List[str]) -> str:
    """Create JWT access token"""
    s = get_settings()
    now = int(time.time())
    
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "tenant_ids": tenant_ids,
        "scopes": scopes,
        "iss": s.JWT_ISSUER,
        "aud": s.JWT_AUDIENCE,
        "iat": now,
        "exp": now + (s.JWT_ACCESS_TTL_MINUTES * 60),
        "jti": str(uuid.uuid4()),  # JWT ID for token tracking
        "type": "access"
    }
    
    headers = {"kid": s.JWT_KID} if s.JWT_KID else None
    return jwt.encode(payload, s.JWT_SECRET, algorithm=s.JWT_ALGORITHM, headers=headers)

def create_refresh_token(user_id: str) -> str:
    """Create JWT refresh token"""
    s = get_settings()
    now = int(time.time())
    
    payload = {
        "sub": user_id,
        "iss": s.JWT_ISSUER,
        "aud": s.JWT_AUDIENCE,
        "iat": now,
        "exp": now + (s.JWT_REFRESH_TTL_DAYS * 24 * 60 * 60),
        "jti": str(uuid.uuid4()),
        "type": "refresh"
    }
    
    headers = {"kid": s.JWT_KID} if s.JWT_KID else None
    return jwt.encode(payload, s.JWT_SECRET, algorithm=s.JWT_ALGORITHM, headers=headers)

def decode_jwt(token: str) -> Dict[str, Any]:
    """Decode and validate JWT token"""
    s = get_settings()
    try:
        payload = jwt.decode(
            token, 
            s.JWT_SECRET, 
            algorithms=[s.JWT_ALGORITHM], 
            audience=s.JWT_AUDIENCE, 
            issuer=s.JWT_ISSUER
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"}
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"}
        )

def get_jwks() -> Dict[str, Any]:
    """Generate JWKS (JSON Web Key Set) for key rotation"""
    s = get_settings()
    # For now, we'll use symmetric key, but in production should use RSA keys
    return {
        "keys": [
            {
                "kty": "oct",  # symmetric key type
                "kid": s.JWT_KID or "default",
                "k": jwt.encode({"secret": s.JWT_SECRET}, "", algorithm="none").split('.')[2],  # base64 encoded secret
                "alg": s.JWT_ALGORITHM,
                "use": "sig"
            }
        ]
    }
