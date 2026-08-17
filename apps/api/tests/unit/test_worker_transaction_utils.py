from unittest.mock import AsyncMock

import pytest

from app.workers.transaction_utils import checkpoint_commit


@pytest.mark.asyncio
async def test_checkpoint_commit_persists_a_completed_worker_boundary() -> None:
    session = AsyncMock()

    await checkpoint_commit(session, "finalize_memory", "facts_writeback")

    session.commit.assert_awaited_once()
