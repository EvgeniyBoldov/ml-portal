"""Tests for the memory-finalization transport boundary."""
from __future__ import annotations

from uuid import uuid4

from app.workers.tasks_memory import (
    MemoryFinalizePayload,
    SummaryPayload,
    _deserialize_turn_memory,
)


def test_finalize_payload_preserves_preflight_candidates() -> None:
    chat_id = uuid4()
    candidates = [{
        "scope": "tenant",
        "kind": "fact",
        "subject": "department.reliability_target",
        "value": "99.9%",
        "evidence_source_ids": ["user_message"],
    }]
    payload = MemoryFinalizePayload(
        chat_id=str(chat_id),
        turn_number=1,
        user_message="Запомни целевой уровень надёжности отдела: 99.9%",
        assistant_final="Факт принят для проверки.",
        summary=SummaryPayload(chat_id=str(chat_id)),
        preflight_candidates=candidates,
    )

    memory = _deserialize_turn_memory(
        MemoryFinalizePayload.model_validate(payload.model_dump(mode="json"))
    )

    assert memory.preflight_candidates == candidates
