"""Admin dashboard read contract."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class UsageSummary(BaseModel):
    requests: int = 0
    chat_requests: int = 0
    shadow_requests: int = 0
    active_users: int = 0
    active_agents: int = 0
    failed_requests: int = 0
    completed_requests: int = 0
    error_rate: float | None = None


class UsageBucket(BaseModel):
    at: datetime
    requests: int
    errors: int


class DashboardModel(BaseModel):
    alias: str
    id: str | None = None
    name: str
    type: str
    enabled: bool
    health: str
    checked_at: datetime | None = None
    assignments: list[str] = Field(default_factory=list)
    calls: int = 0
    errors: int = 0
    tokens_in: int | None = None
    tokens_out: int | None = None
    estimated_calls: int = 0
    metered_calls: int = 0
    avg_duration_ms: float | None = None


class DashboardAgent(BaseModel):
    slug: str
    id: str | None = None
    name: str
    origin: str
    executions: int
    users: int
    errors: int
    avg_duration_ms: float | None = None


class DashboardCollection(BaseModel):
    id: str
    slug: str
    name: str
    documents: int
    source_bytes: int
    unknown_sizes: int
    chunks: int
    ready: int
    processing: int
    partial: int
    failed: int
    embedding_models: list[str] = Field(default_factory=list)


class DashboardMemoryScope(BaseModel):
    key: str
    name: str
    documents: int
    pending: int
    failed: int
    status: str = "unknown"
    nodes: int | None = None
    edges: int | None = None
    indexed_at: datetime | None = None


class DashboardProblem(BaseModel):
    key: str
    severity: Literal["warning", "danger"]
    title: str
    detail: str
    count: int = 1
    last_at: datetime | None = None
    href: str


class DashboardResponse(BaseModel):
    days: Literal[1, 7, 30]
    generated_at: datetime
    period_start: datetime
    coverage_started_at: datetime
    current: UsageSummary
    previous: UsageSummary
    timeline: list[UsageBucket]
    models: list[DashboardModel]
    agents: list[DashboardAgent]
    collections: list[DashboardCollection]
    memory_scopes: list[DashboardMemoryScope]
    memory_available: bool
    problems: list[DashboardProblem]
