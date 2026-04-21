from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ConfirmationIssueRequest(BaseModel):
    operation_fingerprint: str = Field(..., min_length=16)


class ConfirmationIssueResponse(BaseModel):
    token: str
    expires_at: datetime
