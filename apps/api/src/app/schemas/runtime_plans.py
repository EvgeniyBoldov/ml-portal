from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class RuntimeTaskView(BaseModel):
    id: UUID
    task_id: str
    title: str
    objective: str
    agent_slug: str
    status: str
    inputs: Dict[str, Any]
    expected_outputs: List[Dict[str, Any]]
    checkpoint: Dict[str, Any]
    result: Optional[Dict[str, Any]] = None
    attempts: int
    next_retry_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


class RuntimePlanView(BaseModel):
    id: UUID
    tenant_id: UUID
    chat_id: Optional[UUID]
    root_run_id: UUID
    goal: str
    status: str
    revision: int
    answer_brief: Optional[str]
    created_at: datetime
    updated_at: datetime
    tasks: List[RuntimeTaskView] = []
    model_config = ConfigDict(from_attributes=True)


class RuntimeEventView(BaseModel):
    id: UUID
    run_id: UUID
    sequence: int
    event_type: str
    tenant_id: Optional[UUID] = None
    user_id: Optional[UUID] = None
    chat_id: Optional[UUID] = None
    origin: str
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    parent_entity_type: Optional[str] = None
    parent_entity_id: Optional[str] = None
    trigger: Optional[str] = None
    caused_by_event_id: Optional[UUID] = None
    logging_level: str
    schema_version: int
    payload_hash: Optional[str] = None
    payload: Dict[str, Any]
    duration_ms: Optional[int] = None
    occurred_at: datetime
    model_config = ConfigDict(from_attributes=True)


class RuntimeTimelineView(BaseModel):
    """Canonical read model consumed by the sandbox timeline renderer."""

    run_id: UUID
    plan: Optional[RuntimePlanView] = None
    events: List[RuntimeEventView] = []
