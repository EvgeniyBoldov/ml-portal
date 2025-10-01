from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List
import json
from app.core.config import get_settings

@dataclass
class JwkKey:
    kid: str
    kty: str
    n: str | None = None
    e: str | None = None
    crv: str | None = None
    x: str | None = None
    y: str | None = None
    alg: str | None = None
    use: str | None = "sig"

def load_jwks() -> Dict[str, Any]:
    """Load JWKS from settings (JSON string or path)."""
    s = get_settings()
    jwks_raw = getattr(s, "JWT_JWKS_JSON", None)
    if jwks_raw:
        try:
            jwks = json.loads(jwks_raw)
            if isinstance(jwks, dict) and "keys" in jwks:
                return jwks
        except Exception:
            pass
    # Fallback empty set — not for production signing, only publishing
    return {"keys": []}
