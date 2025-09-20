from __future__ import annotations
import hashlib
from typing import Optional

def safe_ext(filename: str) -> str:
    parts = filename.rsplit(".", 1)
    if len(parts) == 2 and len(parts[1]) <= 8:
        return parts[1].lower()
    return "bin"

def content_key(owner_id: str, filename: str, *, content_hash: Optional[str] = None, kind: str = "raw") -> str:
    # /{owner_id}/{kind}/{sha256[:2]}/{sha256}{.ext}
    ext = safe_ext(filename)
    h = content_hash or hashlib.sha256(filename.encode("utf-8")).hexdigest()
    return f"{owner_id}/{kind}/{h[:2]}/{h}.{ext}"
