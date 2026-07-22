"""Single persisted writer for canonical runtime observations."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.runtime_observability import RuntimeExecutionEvent, RuntimeEventSequence
from app.runtime.redactor import RuntimeRedactor


class RuntimeObservationEvent(BaseModel):
    event_type: str = Field(min_length=1, max_length=80)
    run_id: UUID
    sequence: Optional[int] = None
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    parent_entity_type: Optional[str] = None
    parent_entity_id: Optional[str] = None
    trigger: Optional[str] = None
    caused_by_event_id: Optional[UUID] = None
    logging_level: str = "brief"
    payload: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RuntimeObservationWriter:
    """Level-aware append-only event writer.

    It is intentionally independent from chat/sandbox transport and can be
    used by planner, orchestrator, agents and memory components alike.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.redactor = RuntimeRedactor()

    async def append(self, event: RuntimeObservationEvent) -> RuntimeExecutionEvent:
        payload = self._filter_payload(event.payload, event.logging_level, event.event_type)
        payload = self.redactor.redact(payload)
        sequence = event.sequence
        if sequence is None:
            sequence_row = (await self.session.execute(select(RuntimeEventSequence).where(RuntimeEventSequence.run_id == event.run_id).with_for_update())).scalar_one_or_none()
            if sequence_row is None:
                sequence_row = RuntimeEventSequence(run_id=event.run_id, next_sequence=2)
                self.session.add(sequence_row)
                sequence = 1
            else:
                sequence = sequence_row.next_sequence
                sequence_row.next_sequence += 1
        row = RuntimeExecutionEvent(
            id=uuid4(), run_id=event.run_id, sequence=sequence,
            event_type=event.event_type, entity_type=event.entity_type, entity_id=event.entity_id,
            parent_entity_type=event.parent_entity_type, parent_entity_id=event.parent_entity_id,
            trigger=event.trigger, caused_by_event_id=event.caused_by_event_id,
            logging_level=self.normalize_level(event.logging_level), schema_version=1,
            payload_hash=hashlib.sha256(json.dumps(payload, ensure_ascii=False, default=str, sort_keys=True).encode()).hexdigest(),
            payload=payload, occurred_at=event.occurred_at,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    @staticmethod
    def normalize_level(value: str) -> str:
        return value if value in {"none", "errors", "brief", "full"} else "brief"

    @classmethod
    def _filter_payload(cls, payload: dict[str, Any], level: str, event_type: str) -> dict[str, Any]:
        level = cls.normalize_level(level)
        if level == "none":
            return {"event": event_type}
        if level == "full":
            return payload
        if level == "errors":
            error_keys = {"error", "error_code", "safe_message", "operator_message", "retryable", "status", "reason", "metric", "limit", "consumed"}
            return {key: value for key, value in payload.items() if key in error_keys}
        heavy = {"prompt", "system_prompt", "messages", "raw_response", "content", "arguments", "result", "output", "dependency_outputs"}
        result: dict[str, Any] = {}
        for key, value in payload.items():
            if key in heavy:
                raw = json.dumps(value, ensure_ascii=False, default=str)
                result[f"{key}_hash"] = hashlib.sha256(raw.encode()).hexdigest()
                result[f"{key}_length"] = len(raw)
            else:
                result[key] = value
        return result
