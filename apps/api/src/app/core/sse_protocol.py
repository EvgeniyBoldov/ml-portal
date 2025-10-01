from __future__ import annotations
from typing import Any
from app.schemas.common import ProblemDetails
from app.core.sse import format_sse

EVENT_META = "meta"
EVENT_TOKEN = "token"
EVENT_DONE  = "done"
EVENT_ERROR = "error"
EVENT_PING  = "ping"

def sse_error(detail: str, status: int = 502, title: str = "Upstream error") -> str:
    pd = ProblemDetails(title=title, status=status, detail=detail).model_dump()
    return format_sse(pd, event=EVENT_ERROR)
