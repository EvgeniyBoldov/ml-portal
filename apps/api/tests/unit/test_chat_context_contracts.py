from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from app.services.chat_context_contracts import ChatContextOperation, TopicScopePayload


def test_context_contracts_import_in_fresh_process_and_keep_runtime_event_exports() -> None:
    result = subprocess.run(
        [sys.executable, "-c", (
            "from app.services.chat_context_contracts import ChatContextSnapshot; "
            "from app.agents.runtime.result_context import ResultObservation; "
            "from app.agents.runtime import RuntimeEvent; "
            "assert ChatContextSnapshot and ResultObservation and RuntimeEvent"
        )],
        cwd=Path(__file__).resolve().parents[2],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_context_operation_rejects_unknown_payload_fields() -> None:
    operation = ChatContextOperation(
        action="touch", kind="artifact_ref", item_key="artifact-1",
        payload={"artifact_id": "artifact-1", "unexpected": "raw tool output"},
        source_ids=["turn:00000000-0000-0000-0000-000000000001"], expected_revision=0,
    )

    with pytest.raises(ValueError):
        operation.validated_payload()


def test_close_requires_provenance_and_no_payload() -> None:
    operation = ChatContextOperation(
        action="close", kind="artifact_ref", item_key="artifact-1",
        source_ids=[], expected_revision=0,
    )

    with pytest.raises(ValueError):
        operation.validated_payload()


def test_inferred_topic_scope_cannot_carry_project_identity() -> None:
    with pytest.raises(ValueError):
        TopicScopePayload.model_validate({
            "topic": "обновление отчёта", "source": "inferred", "project_keys": ["forbidden"],
        })


def test_scope_carries_trust_per_identity_field() -> None:
    operation = ChatContextOperation(
        action="update", kind="scope", item_key="current_scope",
        payload={"project_keys": ["ml-portal"], "topic": "weekly report"},
        source_ids=["turn:00000000-0000-0000-0000-000000000001"], expected_revision=0,
    )

    payload = operation.validated_payload()

    assert payload["project_keys_trust_class"] == "application_verified"
    assert payload["topic_trust_class"] == "runtime_normalized"
