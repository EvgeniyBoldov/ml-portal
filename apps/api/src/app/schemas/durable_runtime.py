"""Public, provider-neutral contracts for durable runtime integrations."""
from __future__ import annotations

import json
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator

MAX_DURABLE_MESSAGE_CHARS = 20_000


class ThreadAddress(BaseModel):
    model_config = ConfigDict(extra="forbid")
    integration_id: str = Field(min_length=1, max_length=100)
    workspace_id: str = Field(min_length=1, max_length=255)
    conversation_id: str = Field(min_length=1, max_length=255)
    thread_id: str = Field(min_length=1, max_length=255)
    source_message_id: str = Field(min_length=1, max_length=255)

    @field_validator("integration_id", "workspace_id", "conversation_id", "thread_id", "source_message_id")
    @classmethod
    def nonblank_address_part(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("address fields must not be blank")
        return value


class AdmitRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: str = Field(min_length=1, max_length=255)
    text: str = Field(min_length=1, max_length=MAX_DURABLE_MESSAGE_CHARS)
    address: ThreadAddress
    timezone: str | None = Field(default=None, max_length=100)
    referenced_context: dict[str, Any] | None = None

    @field_validator("text")
    @classmethod
    def nonblank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text must not be blank")
        return value

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                ZoneInfo(value)
            except (ValueError, ZoneInfoNotFoundError) as exc:
                raise ValueError("timezone must be a valid IANA timezone") from exc
        return value

    @model_validator(mode="after")
    def bound_referenced_context(self) -> "AdmitRunRequest":
        if self.referenced_context is not None:
            try:
                encoded = json.dumps(self.referenced_context, ensure_ascii=False, separators=(",", ":"))
            except (TypeError, ValueError) as exc:
                raise ValueError("referenced_context must be JSON serializable") from exc
            if len(encoded.encode("utf-8")) > 8192:
                raise ValueError("referenced_context must be at most 8192 bytes")
        return self


class AcceptedRun(BaseModel):
    chat_id: UUID
    run_id: UUID
    event_id: str
    status: str = "queued"


class RunResponseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: str = Field(min_length=1, max_length=255)
    pause_id: UUID
    value: str | StrictBool

    @field_validator("value")
    @classmethod
    def bounded_answer(cls, value: str | bool) -> str | bool:
        if isinstance(value, str) and (not value.strip() or len(value) > MAX_DURABLE_MESSAGE_CHARS):
            raise ValueError("Text response must contain 1 to 20000 characters")
        return value


class CancelRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: str = Field(min_length=1, max_length=255)


class AckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    external_message_id: str | None = Field(default=None, max_length=255)
