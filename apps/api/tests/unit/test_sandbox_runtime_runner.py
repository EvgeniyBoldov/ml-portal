import asyncio
from uuid import uuid4

import pytest

from app.services.sandbox.runtime_runner import SandboxRuntimeRunner


@pytest.mark.asyncio
async def test_cancel_local_interrupts_only_registered_live_task():
    runner = SandboxRuntimeRunner()
    run_id = uuid4()
    task = asyncio.create_task(asyncio.sleep(60))
    runner._tasks[run_id] = task  # local registry state is the unit under test

    assert await runner.cancel_local(run_id) is True
    await asyncio.gather(task, return_exceptions=True)
    assert task.cancelled()


@pytest.mark.asyncio
async def test_cancel_local_is_idempotent_when_run_is_not_owned_here():
    assert await SandboxRuntimeRunner().cancel_local(uuid4()) is False
