"""Connector-neutral envelope for durable assignments."""
import json
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.schemas.durable_runtime import AdmitRunRequest, CancelRunRequest, RunResponseRequest

ConnectorPart = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9_-]{0,47}$")]


class Connector(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: ConnectorPart
    id: ConnectorPart

    @property
    def key(self) -> str:
        return f"{self.type}:{self.id}"


class DeliveryConnector(Connector):
    data: dict[str, Any]

    @field_validator("data")
    @classmethod
    def bounded_destination(cls, value: dict[str, Any]) -> dict[str, Any]:
        if not value or len(json.dumps(value, ensure_ascii=False).encode()) > 2048:
            raise ValueError("Delivery data must contain a destination and fit in 2048 bytes")
        return value


class ExternalUser(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mail: str | None = Field(default=None, max_length=320)
    clouds: UUID | None = None
    telegram: int | None = Field(default=None, strict=True, gt=0)
    tel: str | None = Field(default=None, pattern=r"^\+[1-9][0-9]{1,14}$")


class AssignmentData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    timezone: str | None = None
    referenced_context: dict[str, Any] | None = None


class AssignmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: Connector
    reply_to: DeliveryConnector
    user: ExternalUser
    event_id: str = Field(min_length=1, max_length=255)
    data: AssignmentData

    def to_admission(self) -> AdmitRunRequest:
        destination = self.reply_to.data
        return AdmitRunRequest(
            event_id=self.event_id, text=self.data.text, timezone=self.data.timezone,
            referenced_context=self.data.referenced_context,
            address={
                "integration_id": self.source.key,
                "workspace_id": self.source.id,
                "conversation_id": str(destination.get("chat_id") or self.reply_to.key),
                "thread_id": str(destination.get("message_id") or self.event_id),
                "source_message_id": self.event_id,
            },
        )


class AssignmentAnswer(RunResponseRequest):
    user: ExternalUser


class AssignmentCancel(CancelRunRequest):
    user: ExternalUser
