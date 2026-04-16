from __future__ import annotations
import time
import uuid
from dataclasses import dataclass
from typing import Optional, Any, Dict, List
import jwt
from argon2 import PasswordHasher
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

def _get_signing_key() -> str:
    """Get signing key based on algorithm"""
    s = get_settings()
    if s.JWT_ALGORITHM.startswith("RS") or s.JWT_ALGORITHM.startswith("ES"):
        if not s.JWT_PRIVATE_KEY:
            raise ValueError(f"JWT_PRIVATE_KEY required for {s.JWT_ALGORITHM}")
        return s.JWT_PRIVATE_KEY
    return s.JWT_SECRET

def _get_verification_key() -> str:
    """Get verification key based on algorithm"""
    s = get_settings()
    if s.JWT_ALGORITHM.startswith("RS") or s.JWT_ALGORITHM.startswith("ES"):
        if not s.JWT_PUBLIC_KEY:
            raise ValueError(f"JWT_PUBLIC_KEY required for {s.JWT_ALGORITHM}")
        return s.JWT_PUBLIC_KEY
    return s.JWT_SECRET

def create_access_token(user_id: str, email: str, role: str, tenant_ids: List[str], scopes: List[str]) -> str:
    """Create JWT access token with RSA (production) or HS256 (dev)"""
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
        "jti": str(uuid.uuid4()),
        "type": "access"
    }
    
    headers = {"kid": s.JWT_KID} if s.JWT_KID else None
    signing_key = _get_signing_key()
    return jwt.encode(payload, signing_key, algorithm=s.JWT_ALGORITHM, headers=headers)

def create_refresh_token(user_id: str) -> str:
    """Create JWT refresh token with RSA (production) or HS256 (dev)"""
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
    signing_key = _get_signing_key()
    return jwt.encode(payload, signing_key, algorithm=s.JWT_ALGORITHM, headers=headers)

def decode_jwt(token: str) -> Dict[str, Any]:
    """Decode and validate JWT token with RSA (production) or HS256 (dev)"""
    s = get_settings()
    from app.core.exceptions import UnauthorizedError
    try:
        verification_key = _get_verification_key()
        payload = jwt.decode(
            token, 
            verification_key, 
            algorithms=[s.JWT_ALGORITHM], 
            audience=s.JWT_AUDIENCE, 
            issuer=s.JWT_ISSUER
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise UnauthorizedError("Token has expired")
    except jwt.InvalidTokenError as e:
        raise UnauthorizedError(f"Invalid token: {str(e)}")

def get_jwks() -> Dict[str, Any]:
    """Generate JWKS (JSON Web Key Set) - only public keys for RSA"""
    s = get_settings()
    
    # For asymmetric algorithms (RS256, ES256), publish public key
    if s.JWT_ALGORITHM.startswith("RS") or s.JWT_ALGORITHM.startswith("ES"):
        if not s.JWT_PUBLIC_KEY:
            raise ValueError(f"JWT_PUBLIC_KEY required for JWKS with {s.JWT_ALGORITHM}")
        
        # Parse PEM public key and convert to JWK format
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.backends import default_backend
        import base64
        
        public_key_bytes = s.JWT_PUBLIC_KEY.encode('utf-8')
        public_key = serialization.load_pem_public_key(public_key_bytes, backend=default_backend())
        
        # Get public numbers for RSA
        if s.JWT_ALGORITHM.startswith("RS"):
            from cryptography.hazmat.primitives.asymmetric import rsa
            if isinstance(public_key, rsa.RSAPublicKey):
                public_numbers = public_key.public_numbers()
                
                # Convert to base64url without padding
                def int_to_base64url(n: int) -> str:
                    byte_length = (n.bit_length() + 7) // 8
                    return base64.urlsafe_b64encode(n.to_bytes(byte_length, 'big')).rstrip(b'=').decode('ascii')
                
                return {
                    "keys": [
                        {
                            "kty": "RSA",
                            "kid": s.JWT_KID or "default",
                            "use": "sig",
                            "alg": s.JWT_ALGORITHM,
                            "n": int_to_base64url(public_numbers.n),
                            "e": int_to_base64url(public_numbers.e)
                        }
                    ]
                }
    
    # For symmetric algorithms (HS256) - DO NOT publish secret!
    # Return minimal JWKS for compatibility, but warn
    return {
        "keys": [
            {
                "kty": "oct",
                "kid": s.JWT_KID or "default",
                "alg": s.JWT_ALGORITHM,
                "use": "sig",
                # NOTE: Secret is NOT included for security
            }
        ]
    }
