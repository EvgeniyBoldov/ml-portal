from __future__ import annotations

from uuid import UUID, uuid4

from app.runtime.entity_ids import (
    memory_recall_orchestrator_id,
    turn_preflight_orchestrator_id,
)
from app.services.runtime_event_logger import _validate_runtime_identity


def test_preflight_orchestrator_identities_are_uuid_compatible() -> None:
    run_id = str(uuid4())

    preflight_id = turn_preflight_orchestrator_id(run_id)
    recall_id = memory_recall_orchestrator_id(run_id)

    UUID(preflight_id)
    UUID(recall_id)
    _validate_runtime_identity("orchestrator", preflight_id, "run", run_id)
    _validate_runtime_identity("orchestrator", recall_id, "orchestrator", preflight_id)
    assert preflight_id != recall_id
    assert preflight_id == turn_preflight_orchestrator_id(run_id)
