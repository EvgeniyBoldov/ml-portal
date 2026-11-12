"""Exercise delivery and ownership against PostgreSQL in a rolled-back transaction."""
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from app.core.config import get_settings
from app.core.exceptions import ConflictError, NotFoundError
from app.models.shadow_invocation import ShadowInvocation
from app.schemas.shadow_agents import ShadowAgentRequest
from app.services.shadow_invocation_service import ShadowInvocationService

pytestmark = pytest.mark.skipif(os.getenv("SHADOW_WORKFLOW_PG") != "1", reason="requires PostgreSQL")


@pytest.mark.asyncio
async def test_delivery_owner_ack_and_task_states(monkeypatch):
    from app.workers import tasks_shadow_invocations
    monkeypatch.setattr(tasks_shadow_invocations.execute_shadow_invocation, "delay", lambda *_: None)
    engine = create_async_engine(get_settings().ASYNC_DB_URL)
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                await connection.execute(text('''CREATE TEMP TABLE shadow_invocations (
                    id uuid primary key, user_id uuid not null, tenant_id uuid not null,
                    agent varchar(255) not null, data jsonb not null, scopes jsonb not null,
                    request_id varchar(255) not null, idempotency_key varchar(255),
                    request_fingerprint varchar(64), status varchar(20) not null,
                    result jsonb, error varchar(255), claim_id uuid, delivered_at timestamptz,
                    created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
                    UNIQUE (user_id, tenant_id, idempotency_key)
                ) ON COMMIT DROP'''))
                async with AsyncSession(bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint") as session:
                    owner, other, tenant = uuid4(), uuid4(), uuid4()
                    agent = SimpleNamespace(validate=AsyncMock())
                    service = ShadowInvocationService(session, agent)
                    task_id = await service.enqueue(ShadowAgentRequest(agent="test", data={}), user_id=owner,
                                                    tenant_id=tenant, scopes=[], request_id="test")
                    assert (await service.get(task_id, owner)).status == "queued"
                    assert await service.list_ready(owner) == []
                    with pytest.raises(ConflictError):
                        await service.acknowledge(task_id, owner)
                    with pytest.raises(NotFoundError):
                        await service.get(task_id, other)
                    with pytest.raises(NotFoundError):
                        await service.acknowledge(task_id, other)
                    row = await session.get(ShadowInvocation, task_id)
                    row.status, row.result = "completed", {"answer": 42}
                    await session.commit()
                    assert [item.id for item in await service.list_ready(owner)] == [task_id]
                    assert [item.id for item in await service.list_ready(owner)] == [task_id]
                    assert await service.list_ready(other) == []
                    await service.acknowledge(task_id, owner)
                    await service.acknowledge(task_id, owner)
                    assert await service.list_ready(owner) == []
                    result = await service.get(task_id, owner)
                    assert result.result == {"answer": 42} and result.delivered_at is not None
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_read_scope_keeps_owned_result_across_active_tenant_order_and_denies_revoked_membership():
    """Effective tenant ordering must not hide an owned result from another active tenant."""
    engine = create_async_engine(get_settings().ASYNC_DB_URL)
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                await connection.execute(text('''CREATE TEMP TABLE shadow_invocations (
                    id uuid primary key, user_id uuid not null, tenant_id uuid not null,
                    agent varchar(255) not null, data jsonb not null, scopes jsonb not null,
                    request_id varchar(255) not null, idempotency_key varchar(255),
                    request_fingerprint varchar(64), status varchar(20) not null,
                    result jsonb, error varchar(255), claim_id uuid, delivered_at timestamptz,
                    created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
                    UNIQUE (user_id, tenant_id, idempotency_key)
                ) ON COMMIT DROP'''))
                async with AsyncSession(bind=connection, expire_on_commit=False,
                                        join_transaction_mode="create_savepoint") as session:
                    from app.core.exceptions import NotFoundError
                    from app.models.shadow_invocation import ShadowInvocation
                    owner, source_tenant, current_default = uuid4(), uuid4(), uuid4()
                    source = ShadowInvocation(user_id=owner, tenant_id=source_tenant, agent="source",
                        data={}, scopes=[], request_id="source", status="completed", result={"source": True})
                    current = ShadowInvocation(user_id=owner, tenant_id=current_default, agent="current",
                        data={}, scopes=[], request_id="current", status="completed", result={"current": True})
                    session.add_all([source, current])
                    await session.commit()
                    service = ShadowInvocationService(session, SimpleNamespace())

                    # Source tenant is still an active membership, but resolver
                    # order now puts a different effective default first.
                    memberships = [current_default, source_tenant]
                    assert {item.id for item in await service.list_ready(owner, tenant_ids=memberships)} == {
                        source.id, current.id}
                    assert (await service.get(source.id, owner, tenant_ids=memberships)).result == {"source": True}
                    await service.acknowledge(source.id, owner, tenant_ids=memberships)
                    assert (await service.get(source.id, owner, tenant_ids=memberships)).delivered_at is not None

                    # Once source-tenant membership is revoked, other active
                    # memberships do not authorize the old tenant's result.
                    assert [item.id for item in await service.list_ready(owner, tenant_ids=[current_default])] == [current.id]
                    with pytest.raises(NotFoundError):
                        await service.get(source.id, owner, tenant_ids=[current_default])
                    with pytest.raises(NotFoundError):
                        await service.acknowledge(source.id, owner, tenant_ids=[current_default])
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("fails", [False, True])
async def test_worker_persists_completion_or_failure(monkeypatch, fails):
    from contextlib import asynccontextmanager
    from app.models.user import Users
    from app.workers import tasks_shadow_invocations as worker

    engine = create_async_engine(get_settings().ASYNC_DB_URL)
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                await connection.execute(text('''CREATE TEMP TABLE shadow_invocations (
                    id uuid primary key, user_id uuid not null, tenant_id uuid not null,
                    agent varchar(255) not null, data jsonb not null, scopes jsonb not null,
                    request_id varchar(255) not null, idempotency_key varchar(255),
                    request_fingerprint varchar(64), status varchar(20) not null,
                    result jsonb, error varchar(255), claim_id uuid, delivered_at timestamptz,
                    created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
                    UNIQUE (user_id, tenant_id, idempotency_key)
                ) ON COMMIT DROP'''))
                async with AsyncSession(bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint") as session:
                    user = Users(login="shadow-worker-" + uuid4().hex)
                    session.add(user)
                    await session.flush()
                    tenant = uuid4()
                    row = ShadowInvocation(user_id=user.id, tenant_id=tenant, agent="test", data={}, scopes=[], request_id="test", status="queued")
                    session.add(row)
                    await session.commit()
                    invocation_id = row.id
                    @asynccontextmanager
                    async def session_context():
                        yield session
                    monkeypatch.setattr(worker, "get_worker_session", session_context)
                    monkeypatch.setattr(worker, "ApiTokensRepository", lambda _: SimpleNamespace(active_tenant_ids=AsyncMock(return_value=[str(tenant)])))
                    invoke = AsyncMock(side_effect=RuntimeError("private detail") if fails else None,
                                       return_value=SimpleNamespace(result={"ok": True}))
                    monkeypatch.setattr(worker, "ShadowAgentService", lambda *_: SimpleNamespace(invoke=invoke))
                    monkeypatch.setattr(worker, "get_llm_client", lambda: None)
                    monkeypatch.setattr(worker, "reset_llm_client", lambda: None)
                    monkeypatch.setattr(worker, "cleanup_clients", AsyncMock())
                    await worker._execute(str(invocation_id))
                    session.expire_all()
                    row = await session.get(ShadowInvocation, invocation_id)
                    assert row.status == ("failed" if fails else "completed")
                    assert row.result == (None if fails else {"ok": True})
                    assert row.error == ("Shadow agent execution failed" if fails else None)
                    await worker._execute(str(invocation_id))
                    assert invoke.await_count == 1
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()
