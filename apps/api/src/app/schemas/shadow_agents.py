"""Strict JSON envelopes for machine-to-machine agent invocation."""
from datetime import datetime
from uuid import UUID
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, JsonValue


class ShadowAgentRequest(BaseModel):
    agent: str = Field(min_length=1)
    data: dict[str, JsonValue]
    async_: bool = Field(default=False, alias="async")
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class ShadowAgentResponse(BaseModel):
    agent: str = Field(min_length=1)
    result: dict[str, JsonValue]
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class ShadowAgentAccepted(BaseModel):
    id: UUID


class ShadowAgentTask(BaseModel):
    id: UUID
    agent: str
    status: Literal["queued", "running", "completed", "failed"]
    result: dict[str, JsonValue] | None = None
    error: str | None = None
    created_at: datetime
    delivered_at: datetime | None = None
