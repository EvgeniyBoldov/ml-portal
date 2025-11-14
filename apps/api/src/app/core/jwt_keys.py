from __future__ import annotations
import json
from typing import Any, Dict
from .config import get_settings

def load_jwks() -> Dict[str, Any]:
    raw = get_settings().JWT_JWKS_JSON
    if not raw:
        return {"keys": []}
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and "keys" in data:
            return data
        return {"keys": []}
    except Exception:
        return {"keys": []}
