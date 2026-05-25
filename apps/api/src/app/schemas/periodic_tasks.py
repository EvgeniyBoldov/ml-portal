from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict


class PeriodicTaskItem(BaseModel):
    slug: str
    task_path: str
    name: str
    category: str
    default_schedule: Dict[str, Any]
    is_enabled: bool
    is_orphaned: bool
    last_run_at: Optional[datetime] = None
    last_status: Optional[str] = None
    last_duration_ms: Optional[int] = None
    last_error: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class PeriodicTaskToggleRequest(BaseModel):
    is_enabled: bool


class PeriodicTaskRunNowResponse(BaseModel):
    slug: str
    queued: bool = True
    task_id: Optional[str] = None


class PeriodicTaskListResponse(BaseModel):
    items: list[PeriodicTaskItem]
    total: int
