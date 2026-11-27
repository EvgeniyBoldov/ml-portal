from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ExternalRequestSummary(BaseModel):
    run_id: UUID
    source: str
    status: str
    user_name: str
    created_at: datetime
    updated_at: datetime


class ExternalRequestListItem(ExternalRequestSummary):
    text_preview: str


class ExternalRequestPage(BaseModel):
    items: list[ExternalRequestListItem]
    total: int


class ExternalRequestTimelineItem(BaseModel):
    id: UUID
    kind: str
    occurred_at: datetime
    text: str | None = None
    answer: str | bool | None = None
    wake_at: datetime | None = None
    resolved_at: datetime | None = None
    delivery_status: str | None = None
    delivered_at: datetime | None = None
    delivery_attempts: int = 0


class ExternalRequestDetail(ExternalRequestSummary):
    text: str
    completed_at: datetime | None
    timeline: list[ExternalRequestTimelineItem]
