from __future__ import annotations

import pytest

from app.services.chat_context_contracts import ChatContextOperation, TopicScopePayload


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
