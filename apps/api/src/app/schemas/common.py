from __future__ import annotations
from pydantic import BaseModel, Field

class ProblemDetails(BaseModel):
    type: str = "about:blank"
    title: str = "Error"
    status: int = Field(ge=400, le=599, default=500)
    detail: str | None = None
    instance: str | None = None
