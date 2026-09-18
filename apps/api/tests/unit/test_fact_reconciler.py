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
        scope=FactScope.TENANT,
        subject="department.standard_db",
        value="PostgreSQL",
        source=FactSource.TOOL_RESULT,
        metadata={
            "compaction_action": "mark_conflict",
            "evidence": [{"source_type": "tool_result", "source_ref": "call-1"}],
        },
    )

    result = await reconciler.apply_with_decisions(
        candidates=[candidate], user_id=uuid4(), tenant_id=uuid4(),
    )

    reconciler._demote_conflicts.assert_awaited_once()
    demoted = reconciler._demote_conflicts.await_args.args[0]
    assert demoted.status == FactStatus.UNCONFIRMED.value
    assert result.changes[0].status_after == FactStatus.UNCONFIRMED.value
