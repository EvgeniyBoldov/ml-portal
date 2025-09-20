from __future__ import annotations
import json, os
from typing import List

def as_bool(val: str | None, default: bool=False) -> bool:
    if val is None:
        return default
    return str(val).strip().lower() in {"1","true","yes","on"}

def as_int(val: str | None, default: int) -> int:
    try:
        return int(val) if val is not None else default
    except Exception:
        return default

def as_list(val: str | None, default: list[str] | None=None) -> list[str]:
    if val is None:
        return list(default or [])
    s = val.strip()
    if s.startswith("["):
        try:
            arr = json.loads(s)
            return [str(x).strip() for x in arr]
        except Exception:
            pass
    return [x.strip() for x in s.split(",") if x.strip()]
