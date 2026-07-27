"""Canonical public representation of persisted runtime journal rows."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


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
