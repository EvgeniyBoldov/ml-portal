from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import AsyncMock

import pytest

from app.services.sandbox.run_manager import SandboxRunManager


@pytest.mark.asyncio
async def test_pause_run_uses_provided_status():
    run_id = uuid4()
    run_obj = SimpleNamespace(id=run_id)

    updated = {}

    class _RunsRepo:
        async def get_by_id(self, _rid):
            return run_obj

        async def update(self, obj, data):
            updated["obj"] = obj
            updated["data"] = data
            return obj

    host = SimpleNamespace(runs=_RunsRepo())
    manager = SandboxRunManager(host)

    await manager.pause_run(
        run_id=run_id,
        status="waiting_input",
        paused_action={"kind": "input"},
        paused_context={"question": "q"},
    )

    assert updated["obj"] is run_obj
    assert updated["data"]["status"] == "waiting_input"
    assert updated["data"]["paused_action"] == {"kind": "input"}
    assert updated["data"]["finished_at"] is None


@pytest.mark.asyncio
async def test_resume_run_reopens_paused_run_and_clears_checkpoint():
    run_id = uuid4()
    run_obj = SimpleNamespace(id=run_id)
    updated = {}

    class _RunsRepo:
        async def get_by_id(self, _rid):
            return run_obj

        async def update(self, obj, data):
            updated["obj"] = obj
            updated["data"] = data
            return obj

    manager = SandboxRunManager(SimpleNamespace(runs=_RunsRepo()))

    await manager.resume_run(run_id)

    assert updated["obj"] is run_obj
    assert updated["data"] == {
        "status": "running",
        "paused_action": None,
        "paused_context": None,
        "finished_at": None,
    }


@pytest.mark.asyncio
async def test_request_cancel_marks_only_running_run_as_cancelling():
    run_id = uuid4()
    run_obj = SimpleNamespace(id=run_id, status="cancelling")
    repo = SimpleNamespace(request_cancel=AsyncMock(return_value=run_obj))
    manager = SandboxRunManager(SimpleNamespace(runs=repo))

    result = await manager.request_cancel(run_id)

    assert result is run_obj
    repo.request_cancel.assert_awaited_once_with(run_id)


@pytest.mark.asyncio
async def test_request_cancel_is_idempotent_for_non_running_run():
    run_id = uuid4()
    repo = SimpleNamespace(request_cancel=AsyncMock(return_value=None))
    manager = SandboxRunManager(SimpleNamespace(runs=repo))

    assert await manager.request_cancel(run_id) is None
    repo.request_cancel.assert_awaited_once_with(run_id)


@pytest.mark.asyncio
async def test_claim_resume_rejects_non_waiting_status_before_repository():
    repo = SimpleNamespace(claim_resume=AsyncMock(return_value=True))
    manager = SandboxRunManager(SimpleNamespace(runs=repo))

    claimed = await manager.claim_resume_run(
        uuid4(),
        expected_status="running",
        expected_paused_action=None,
        expected_paused_context=None,
    )

    assert not claimed
    repo.claim_resume.assert_not_awaited()
