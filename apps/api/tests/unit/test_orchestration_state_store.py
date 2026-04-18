from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.orchestration_state_store import OrchestrationStateStore


class _FakeSessionCtx:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_orchestration_state_store_update_and_snapshot(monkeypatch):
    run_id = uuid4()
    saved_state = {}

    class _FakeMemoryService:
        def __init__(self, session):
            pass

        async def snapshot(self, _run_id):
            return {"memory_state": {"orchestration_state_v2": saved_state}} if saved_state else {}

        async def update_context(self, run_id, **kwargs):
            state = (kwargs.get("state") or {}).get("orchestration_state_v2") or {}
            saved_state.clear()
            saved_state.update(state)

    class _FakeSession:
        async def commit(self):
            return None

    monkeypatch.setattr(
        "app.services.orchestration_state_store.ExecutionMemoryService",
        _FakeMemoryService,
    )

    store = OrchestrationStateStore(session_factory=lambda: _FakeSessionCtx(_FakeSession()))
    state = await store.update(
        run_id,
        chat_id=str(uuid4()),
        tenant_id=str(uuid4()),
        goal="resolve",
        patch={"intent_type": "orchestrate", "run_status": "running"},
    )
    assert state is not None
    snap = await store.snapshot(run_id)
    assert snap["intent_type"] == "orchestrate"
    assert snap["run_status"] == "running"
    assert snap["goal"] == "resolve"
