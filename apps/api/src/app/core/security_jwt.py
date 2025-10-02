from __future__ import annotations
from typing import Dict, Any
from .security import decode_jwt

def verify_token(token: str) -> Dict[str, Any]:
    return decode_jwt(token)
