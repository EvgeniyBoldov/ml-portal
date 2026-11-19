"""Canonical public representation of persisted runtime journal rows."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_serializer


class RuntimeJournalEventResponse(BaseModel):
    id: UUID
    run_id: UUID
    sequence: int
    event_type: str
    occurred_at: datetime
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    parent_entity_type: Optional[str] = None
    parent_entity_id: Optional[str] = None
    caused_by_event_id: Optional[UUID] = None
    duration_ms: Optional[int] = None
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_serializer("occurred_at", when_used="json")
    def _serialize_utc(self, value: datetime) -> datetime:
        # Historical naive rows were written in UTC.
        return value.astimezone(timezone.utc) if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
