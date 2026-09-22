from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services.chat_context_contracts import ChatContextOperation
from app.services.chat_context_reconciler import ChatContextReconciler


@pytest.mark.asyncio
async def test_reconciler_skips_operation_when_scoped_provenance_does_not_resolve() -> None:
    repository = AsyncMock()
    repository.get_or_create_head = AsyncMock(return_value=SimpleNamespace(
        revision=3, updated_through_turn_order=0,
    ))
    repository.validate_provenance = AsyncMock(side_effect=ValueError("outside chat"))
    reconciler = ChatContextReconciler(repository)
    turn_id = str(uuid4())
    operation = ChatContextOperation(
        action="update", kind="goal", item_key="active_goal",
        payload={"text": "continue"}, source_ids=[f"turn:{turn_id}"], expected_revision=3,
    )

    receipt = await reconciler.apply(
        chat_id=str(uuid4()), branch_id=None, chat_turn_id=turn_id,
        expected_revision=3, operations=[operation],
    )

    assert receipt.applied_count == 0
    assert receipt.skipped_count == 1
    repository.add_item.assert_not_called()


@pytest.mark.asyncio
async def test_reconciler_rejects_artifact_payload_without_matching_registry_source() -> None:
    repository = AsyncMock()
    repository.get_or_create_head = AsyncMock(return_value=SimpleNamespace(revision=0, updated_through_turn_order=0))
    operation = ChatContextOperation(
        action="touch", kind="artifact_ref", item_key=str(uuid4()),
        payload={"artifact_id": str(uuid4())}, source_ids=[f"turn:{uuid4()}"], expected_revision=0,
    )

    receipt = await ChatContextReconciler(repository).apply(
        chat_id=str(uuid4()), branch_id=None, chat_turn_id=str(uuid4()),
        expected_revision=0, operations=[operation],
    )

    assert receipt.skipped_count == 1
    repository.validate_provenance.assert_not_awaited()


@pytest.mark.asyncio
async def test_reconciler_closes_existing_artifact_after_registry_deletion() -> None:
    turn_id = str(uuid4())
    artifact_id = str(uuid4())
    existing = SimpleNamespace(expires_at=None, status="active")
    repository = AsyncMock()
    repository.get_or_create_head = AsyncMock(return_value=SimpleNamespace(
        revision=2, updated_through_turn_order=0, updated_through_turn_id=None,
    ))
    repository.active_item = AsyncMock(return_value=existing)
    repository.validate_provenance = AsyncMock(return_value={
        "source_turn_id": uuid4(), "source_message_id": None, "source_run_id": None,
    })
    repository.flush = AsyncMock()
    operation = ChatContextOperation(
        action="close", kind="artifact_ref", item_key=artifact_id,
        source_ids=[f"turn:{turn_id}", f"artifact:{artifact_id}"], expected_revision=2,
    )

    receipt = await ChatContextReconciler(repository).apply(
        chat_id=str(uuid4()), branch_id=None, chat_turn_id=turn_id,
        expected_revision=2, operations=[operation],
    )

    assert receipt.applied_count == 1
    assert existing.status == "closed"
    assert repository.validate_provenance.await_args.kwargs["allow_missing_artifact_ids"] == {artifact_id}


@pytest.mark.asyncio
async def test_inferred_topic_preserves_verified_scope_field_trust() -> None:
    turn_id = str(uuid4())
    existing = SimpleNamespace(
        expires_at=None,
        payload={
            "project_keys": ["ml-portal"], "project_keys_trust_class": "application_verified",
            "entity_refs": [], "trust_class": "application_verified", "source": "explicit",
        },
        confidence=1.0,
    )
    repository = AsyncMock()
    repository.get_or_create_head = AsyncMock(return_value=SimpleNamespace(
        revision=1, updated_through_turn_order=0, updated_through_turn_id=None,
    ))
    repository.validate_provenance = AsyncMock(return_value={
        "source_turn_id": uuid4(), "source_message_id": None, "source_run_id": None,
    })
    repository.active_item = AsyncMock(return_value=existing)
    repository.flush = AsyncMock()
    operation = ChatContextOperation(
        action="update", kind="scope", item_key="current_scope",
        payload={"topic": "weekly reports", "source": "inferred", "trust_class": "model_inferred"},
        source_ids=[f"turn:{turn_id}"], expected_revision=1,
    )

    receipt = await ChatContextReconciler(repository).apply(
        chat_id=str(uuid4()), branch_id=None, chat_turn_id=turn_id,
        expected_revision=1, operations=[operation],
    )

    assert receipt.applied_count == 1
    assert existing.payload["project_keys"] == ["ml-portal"]
    assert existing.payload["project_keys_trust_class"] == "application_verified"
    assert existing.payload["topic_trust_class"] == "model_inferred"
    assert existing.payload["trust_class"] == "application_verified"


@pytest.mark.asyncio
async def test_inferred_goal_cannot_replace_deterministic_goal() -> None:
    turn_id = str(uuid4())
    existing = SimpleNamespace(
        expires_at=None, payload={"text": "ship", "status": "active", "trust_class": "runtime_normalized"},
    )
    repository = AsyncMock()
    repository.get_or_create_head = AsyncMock(return_value=SimpleNamespace(revision=1, updated_through_turn_order=0))
    repository.active_item = AsyncMock(return_value=existing)
    repository.validate_provenance = AsyncMock(return_value={
        "source_turn_id": uuid4(), "source_message_id": None, "source_run_id": None,
    })
    operation = ChatContextOperation(
        action="update", kind="goal", item_key="active_goal",
        payload={"text": "hallucinated", "status": "active", "trust_class": "model_inferred"},
        source_ids=[f"turn:{turn_id}"], expected_revision=1,
    )

    receipt = await ChatContextReconciler(repository).apply(
        chat_id=str(uuid4()), branch_id=None, chat_turn_id=turn_id, expected_revision=1, operations=[operation],
    )

    assert receipt.skipped_count == 1
    assert existing.payload["text"] == "ship"


@pytest.mark.asyncio
async def test_reconciler_rejects_noncanonical_singleton_key() -> None:
    repository = AsyncMock()
    repository.get_or_create_head = AsyncMock(return_value=SimpleNamespace(revision=0, updated_through_turn_order=0))
    operation = ChatContextOperation(
        action="add", kind="goal", item_key="another-goal", payload={"text": "x"},
        source_ids=[f"turn:{uuid4()}"], expected_revision=0,
    )
    receipt = await ChatContextReconciler(repository).apply(
        chat_id=str(uuid4()), branch_id=None, chat_turn_id=str(uuid4()), expected_revision=0, operations=[operation],
    )
    assert receipt.skipped_count == 1
    repository.validate_provenance.assert_not_awaited()
