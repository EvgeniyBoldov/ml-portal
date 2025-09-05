from __future__ import annotations
import base64, json
from typing import Any, Dict, Optional, Tuple

def encode_cursor(payload: Dict[str, Any]) -> str:
    return base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()

def decode_cursor(cursor: Optional[str]) -> Optional[Dict[str, Any]]:
    if not cursor:
        return None
    try:
        data = base64.urlsafe_b64decode(cursor.encode()).decode()
        return json.loads(data)
    except Exception:
        return None

def page(items, next_cursor_payload: Optional[Dict[str, Any]]):
    return {"items": items, "next_cursor": encode_cursor(next_cursor_payload) if next_cursor_payload else None}
