from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.models.memory import FactScope, FactSource, FactStatus
from app.runtime.memory.dto import FactDTO
from app.runtime.memory.fact_reconciler import FactReconciler


@pytest.mark.asyncio
async def test_mark_conflict_demotes_existing_confirmed_facts() -> None:
    session = MagicMock()
    session.flush = AsyncMock()
    reconciler = FactReconciler(session)
    reconciler._find_same = AsyncMock(return_value=None)
    reconciler._add_observations = AsyncMock(return_value=1)
    reconciler._demote_conflicts = AsyncMock()
    candidate = FactDTO(
        scope=FactScope.USER,
        subject="department.standard_db",
        value="PostgreSQL",
        source=FactSource.USER_UTTERANCE,
        metadata={
            "compaction_action": "mark_conflict",
            "evidence": [{"source_type": "user_message", "source_ref": "turn-1"}],
        },
    )

    result = await reconciler.apply_with_decisions(
        candidates=[candidate], user_id=uuid4(), tenant_id=uuid4(),
    )

    reconciler._demote_conflicts.assert_awaited_once()
    demoted = reconciler._demote_conflicts.await_args.args[0]
    assert demoted.status == FactStatus.UNCONFIRMED.value
    assert result.changes[0].status_after == FactStatus.UNCONFIRMED.value


@pytest.mark.asyncio
async def test_tenant_tool_evidence_cannot_enter_shared_facts() -> None:
    session = MagicMock()
    session.flush = AsyncMock()
    reconciler = FactReconciler(session)
    result = await reconciler.apply_with_decisions(
        candidates=[FactDTO(
            scope=FactScope.TENANT, subject="standard", value="PostgreSQL", source=FactSource.TOOL_RESULT,
            metadata={"evidence": [{"source_type": "tool_result", "source_ref": "call-1"}]},
        )],
        user_id=uuid4(), tenant_id=uuid4(),
    )
    assert result.decisions[0].reason_code == "no_admissible_evidence"
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_existing_replacement_can_supersede_after_new_evidence() -> None:
    session = MagicMock()
    session.flush = AsyncMock()
    reconciler = FactReconciler(session)
    candidate = FactDTO(
        scope=FactScope.USER, subject="role", value="Developer", source=FactSource.USER_UTTERANCE,
        metadata={"compaction_action": "supersede", "compaction_target_ids": [str(uuid4())],
                  "evidence": [{"source_type": "user_message", "source_ref": "turn-2"}]},
    )
    existing = MagicMock(observed_at=candidate.observed_at, status=FactStatus.CONFIRMED.value, support_count=1)
    reconciler._find_same = AsyncMock(return_value=existing)
    reconciler._add_observations = AsyncMock(return_value=1)
    reconciler._supersede_targets = AsyncMock()
    await reconciler.apply_with_decisions(candidates=[candidate], user_id=uuid4(), tenant_id=uuid4())
    reconciler._supersede_targets.assert_awaited_once_with(
        existing, candidate.metadata["compaction_target_ids"], observed_at=candidate.observed_at,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(("authors", "status"), [(1, "pending"), (3, "confirmed")])
async def test_tenant_confirmation_counts_authors_instead_of_observations(authors, status) -> None:
    session = MagicMock()
    session.flush = AsyncMock()
    reconciler = FactReconciler(session)
    candidate = FactDTO(
        scope=FactScope.TENANT, subject="standard", value="ITIL", source=FactSource.USER_UTTERANCE,
        metadata={"evidence": [{"source_type": "user_message", "source_ref": "turn-4"}]},
    )
    existing = MagicMock(observed_at=candidate.observed_at, status="pending", support_count=2)
    reconciler._find_same = AsyncMock(return_value=existing)
    reconciler._add_observations = AsyncMock(return_value=1)
    reconciler._tenant_author_count = AsyncMock(return_value=authors)

    result = await reconciler.apply_with_decisions(candidates=[candidate], user_id=uuid4(), tenant_id=uuid4())

    assert result.changes[0].status_after == status
    assert result.changes[0].support_after == authors
