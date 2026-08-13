"""HTTP contracts for administrative memory facts."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class AdminFactCreate(BaseModel):
    subject: str = Field(min_length=1, max_length=200)
    value: str = Field(min_length=1, max_length=500)


class AdminFactUpdate(AdminFactCreate):
    pass


class AdminFactResponse(BaseModel):
    id: UUID
    owner_type: str
    owner_id: UUID
    scope: str
    subject: str
    value: str
    confidence: float
    source: str
    status: str
    support_count: int
    observed_at: datetime
    created_at: datetime

