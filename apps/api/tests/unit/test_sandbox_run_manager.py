from types import SimpleNamespace
from uuid import uuid4

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


@pytest.mark.asyncio
async def test_get_next_run_step_order_appends_after_existing_steps():
    run_id = uuid4()

    class _StepsRepo:
        async def get_max_order_num(self, _rid):
            assert _rid == run_id
            return 7

    host = SimpleNamespace(steps=_StepsRepo())
    manager = SandboxRunManager(host)

    assert await manager.get_next_run_step_order(run_id) == 8
