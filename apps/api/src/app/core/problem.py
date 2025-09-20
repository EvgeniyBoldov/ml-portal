from __future__ import annotations
from typing import Any, Optional
from fastapi.responses import JSONResponse

def problem(status: int, title: str, detail: Optional[str] = None, type_: str = "about:blank", extras: dict[str, Any] | None = None) -> JSONResponse:
    body = {
        "type": type_,
        "title": title,
        "status": status,
    }
    if detail:
        body["detail"] = detail
    if extras:
        body.update(extras)
    return JSONResponse(body, status_code=status, media_type="application/problem+json")
