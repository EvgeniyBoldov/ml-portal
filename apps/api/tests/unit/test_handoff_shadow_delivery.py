from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.core.exceptions import ConflictError
from app.schemas.shadow_agents import ShadowAgentRequest
from app.services.shadow_invocation_service import ShadowInvocationService


class MemoryInvocationRepository:
    def __init__(self) -> None:
        self.rows: dict[tuple[object, object, str], object] = {}

    async def by_idempotency_key(self, *, user_id, tenant_id, idempotency_key):
        return self.rows.get((user_id, tenant_id, idempotency_key))

    async def add(self, invocation):
        if invocation.id is None:
            invocation.id = uuid4()
        if invocation.idempotency_key is not None:
            key = (invocation.user_id, invocation.tenant_id, invocation.idempotency_key)
            if key in self.rows:
                raise RuntimeError("fake unique race should use database test")
            self.rows[key] = invocation
        else:
            self.rows[(invocation.user_id, invocation.tenant_id, str(uuid4()))] = invocation


def service(monkeypatch):
    from app.workers import tasks_shadow_invocations

    session = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())
    agent_service = SimpleNamespace(validate=AsyncMock())
    instance = ShadowInvocationService(session, agent_service)
    instance.repo = MemoryInvocationRepository()
    dispatch = Mock()
    monkeypatch.setattr(tasks_shadow_invocations.execute_shadow_invocation, "delay", dispatch)
    return instance, session, agent_service, dispatch


@pytest.mark.asyncio
async def test_same_owner_tenant_key_replays_without_second_dispatch(monkeypatch):
    instance, session, agent, dispatch = service(monkeypatch)
    owner, tenant = uuid4(), uuid4()
    payload = ShadowAgentRequest(agent="shadow-a", data={"value": 1}, **{"async": True})

    first = await instance.enqueue(payload, user_id=owner, tenant_id=tenant, scopes=[],
                                   request_id="request-1", idempotency_key=" key-1 ")
    second = await instance.enqueue(payload, user_id=owner, tenant_id=tenant, scopes=[],
                                    request_id="request-2", idempotency_key="key-1")

    assert first == second
    assert session.commit.await_count == 1
    assert agent.validate.await_count == 2  # replay still rechecks current access
    dispatch.assert_called_once_with(str(first))


@pytest.mark.asyncio
async def test_key_validation_rejects_blank_and_overlong_values(monkeypatch):
    instance, _, agent, dispatch = service(monkeypatch)
    payload = ShadowAgentRequest(agent="shadow-a", data={}, **{"async": True})

    for key in ("   ", "x" * 256):
        with pytest.raises(ValueError, match="Idempotency-Key"):
            await instance.enqueue(payload, user_id=uuid4(), tenant_id=uuid4(), scopes=[],
                                   request_id="r", idempotency_key=key)
    agent.validate.assert_not_awaited()
    dispatch.assert_not_called()


@pytest.mark.asyncio
async def test_same_key_with_different_agent_or_data_conflicts(monkeypatch):
    instance, _, _, dispatch = service(monkeypatch)
    owner, tenant = uuid4(), uuid4()
    first = ShadowAgentRequest(agent="shadow-a", data={"value": 1}, **{"async": True})
    await instance.enqueue(first, user_id=owner, tenant_id=tenant, scopes=[], request_id="r1",
                           idempotency_key="key")

    for payload in (
        ShadowAgentRequest(agent="shadow-b", data={"value": 1}, **{"async": True}),
        ShadowAgentRequest(agent="shadow-a", data={"value": 2}, **{"async": True}),
    ):
        with pytest.raises(ConflictError):
            await instance.enqueue(payload, user_id=owner, tenant_id=tenant, scopes=[], request_id="r2",
                                   idempotency_key="key")
    dispatch.assert_called_once()


@pytest.mark.asyncio
async def test_key_is_scoped_to_owner_and_effective_tenant_and_no_key_is_new_intent(monkeypatch):
    instance, session, _, dispatch = service(monkeypatch)
    owner, other, tenant, other_tenant = uuid4(), uuid4(), uuid4(), uuid4()
    payload = ShadowAgentRequest(agent="shadow-a", data={"value": 1}, **{"async": True})

    owner_id = await instance.enqueue(payload, user_id=owner, tenant_id=tenant, scopes=[], request_id="r1",
                                      idempotency_key="key")
    assert await instance.enqueue(payload, user_id=other, tenant_id=tenant, scopes=[], request_id="r2",
                                  idempotency_key="key") != owner_id
    assert await instance.enqueue(payload, user_id=owner, tenant_id=other_tenant, scopes=[], request_id="r3",
                                  idempotency_key="key") != owner_id
    first = await instance.enqueue(payload, user_id=owner, tenant_id=tenant, scopes=[], request_id="r4")
    second = await instance.enqueue(payload, user_id=owner, tenant_id=tenant, scopes=[], request_id="r5")
    assert first != second and first != owner_id
    assert session.commit.await_count == 5
    assert dispatch.call_count == 5


@pytest.mark.asyncio
async def test_worker_heartbeat_keeps_slow_claim_and_stops_on_cancellation(monkeypatch):
    from app.workers import tasks_shadow_invocations as worker

    monkeypatch.setattr(worker, "_heartbeat_period", lambda: 0.005)
    refresh = AsyncMock(return_value=True)
    monkeypatch.setattr(worker, "_refresh_claim", refresh)
    stop = asyncio.Event()
    heartbeat = asyncio.create_task(worker._heartbeat(uuid4(), uuid4(), stop))
    await asyncio.sleep(0.025)
    stop.set()

    assert await heartbeat is True
    assert refresh.await_count >= 2


@pytest.mark.asyncio
async def test_lost_lease_cancels_inflight_invocation(monkeypatch):
    from app.workers import tasks_shadow_invocations as worker

    started, cancelled = asyncio.Event(), asyncio.Event()

    async def lost_claim(_invocation_id, _claim_id, _stop):
        await started.wait()
        return False

    monkeypatch.setattr(worker, "_heartbeat", lost_claim)

    async def invoke():
        started.set()
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    with pytest.raises(RuntimeError, match="claim was superseded"):
        await worker._invoke_under_lease(uuid4(), uuid4(), invoke)
    assert cancelled.is_set()
