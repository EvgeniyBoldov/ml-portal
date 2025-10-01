from __future__ import annotations
import time, json
from typing import Any, Dict, List, Optional
from uuid import uuid4
import jwt  # PyJWT
from jwt import PyJWKClient
from app.core.config import get_settings

def _jwks_client() -> Optional[PyJWKClient]:
    s = get_settings()
    if s.JWT_JWKS_JSON:
        # local JWKS string; use PyJWT client workaround: load directly
        data = json.loads(s.JWT_JWKS_JSON)
        class _LocalJWKs:
            def get_signing_key_from_jwt(self, token):
                headers = jwt.get_unverified_header(token)
                kid = headers.get("kid")
                for k in data.get("keys", []):
                    if k.get("kid") == kid:
                        return type("obj", (), {"key": jwt.algorithms.get_default_algorithms()[k.get("alg","RS256")].from_jwk(json.dumps(k))})
                raise Exception("kid_not_found")
        return _LocalJWKs()  # type: ignore
    return None

def issue_access_token(sub: str, *, tenant_id: str, scopes: list[str] | None = None) -> str:
    s = get_settings()
    now = int(time.time())
    exp = now + s.JWT_ACCESS_TTL_MINUTES * 60
    payload = {
        "sub": sub,
        "iss": s.JWT_ISSUER,
        "aud": s.JWT_AUDIENCE,
        "iat": now,
        "exp": exp,
        "tid": tenant_id,
        "scp": scopes or [],
    }
    headers = {"kid": s.JWT_KID} if s.JWT_KID else {}
    if s.JWT_ALGORITHM.startswith("HS"):
        return jwt.encode(payload, s.JWT_SECRET, algorithm=s.JWT_ALGORITHM, headers=headers)
    # RS/PS dev fallback: use secret if no private key provided — in prod use AS
    return jwt.encode(payload, s.JWT_SECRET, algorithm=s.JWT_ALGORITHM, headers=headers)

def verify_token(token: str) -> Dict[str, Any]:
    s = get_settings()
    options = {"verify_aud": True, "require": ["exp", "iat", "iss", "aud", "sub"]}
    jwks = _jwks_client()
    if jwks:
        key = jwks.get_signing_key_from_jwt(token).key  # type: ignore
        return jwt.decode(token, key=key, algorithms=[s.JWT_ALGORITHM], audience=s.JWT_AUDIENCE, issuer=s.JWT_ISSUER, options=options)
    return jwt.decode(token, key=s.JWT_SECRET, algorithms=[s.JWT_ALGORITHM], audience=s.JWT_AUDIENCE, issuer=s.JWT_ISSUER, options=options)
