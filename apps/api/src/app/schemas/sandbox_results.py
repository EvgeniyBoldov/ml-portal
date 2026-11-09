"""Read-only sandbox Result Store browser responses."""
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class SandboxResultDescriptor(BaseModel):
    result_id: str
    operation: str
    call_id: str
    task_id: str | None
    agent_execution_id: str | None
    row_count: int
    source_total: int | None
    source_complete: bool
    revision: int
    observed_schema: dict[str, Any]
    created_at: datetime
    expires_at: datetime


class SandboxResultList(BaseModel):
    items: list[SandboxResultDescriptor]
    next_offset: int | None


class SandboxResultPage(SandboxResultDescriptor):
    rows: list[Any]
    offset: int
    next_offset: int | None
