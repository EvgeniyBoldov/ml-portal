"""Isolated PostgreSQL checks for async shadow idempotency and claim fencing."""
from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.exceptions import ConflictError, NotFoundError
from app.schemas.shadow_agents import ShadowAgentRequest
from app.services.shadow_invocation_service import ShadowInvocationService

pytestmark = pytest.mark.skipif(os.getenv("SHADOW_WORKFLOW_PG") != "1", reason="requires isolated PostgreSQL")


@asynccontextmanager
async def isolated_schema():
    schema = "shadow_delivery_" + uuid4().hex
    base = create_async_engine(get_settings().ASYNC_DB_URL)
    engine = None
    try:
        async with base.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_async_engine(get_settings().ASYNC_DB_URL,
            connect_args={"server_settings": {"search_path": schema}})
        async with engine.begin() as connection:
            await connection.execute(text("""
                CREATE TABLE shadow_invocations (
                    id uuid PRIMARY KEY, user_id uuid NOT NULL, tenant_id uuid NOT NULL,
                    agent varchar(255) NOT NULL, data jsonb NOT NULL, scopes jsonb NOT NULL,
                    request_id varchar(255) NOT NULL, idempotency_key varchar(255),
                    request_fingerprint varchar(64), status varchar(20) NOT NULL,
                    result jsonb, error varchar(255), claim_id uuid, delivered_at timestamptz,
                    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
                    CONSTRAINT uq_shadow_invocations_user_tenant_idempotency
                        UNIQUE (user_id, tenant_id, idempotency_key)
                )
            """))
            await connection.execute(text("""
                CREATE TABLE users (
                    id uuid PRIMARY KEY, login varchar(255) NOT NULL, password_hash text, email varchar(255),
                    role varchar(20) NOT NULL DEFAULT 'reader', is_admin boolean NOT NULL DEFAULT false,
                    memory_scope_keys varchar[] NOT NULL DEFAULT '{}', is_active boolean NOT NULL DEFAULT true,
                    require_password_change boolean DEFAULT false, created_at timestamptz NOT NULL DEFAULT now(),
                    updated_at timestamptz NOT NULL DEFAULT now(), auth_provider varchar(16) NOT NULL DEFAULT 'local',
                    external_id varchar(512), ldap_groups varchar[], last_login_at timestamptz,
                    full_name varchar(255), deactivated_at timestamptz, deactivated_reason varchar(64),
                    lifecycle_status varchar(20) NOT NULL DEFAULT 'active', deprecated_at timestamptz,
                    deprecated_by uuid, deprecated_reason text, retention_days integer NOT NULL DEFAULT 14,
                    delete_cascade boolean NOT NULL DEFAULT false, deprecated_root_kind varchar(32),
                    deprecated_root_id uuid
                )
            """))
        yield engine
    finally:
        if engine is not None:
            await engine.dispose()
        async with base.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await base.dispose()


def _session_context(engine):
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    @asynccontextmanager
    async def context():
        async with factory() as session:
            yield session

    return factory, context


@pytest.mark.asyncio
async def test_postgres_same_key_concurrent_replay_conflict_and_owner_tenant_scope(monkeypatch):
    from app.workers import tasks_shadow_invocations as worker

    async with isolated_schema() as engine:
        factory, _ = _session_context(engine)
        owner, other, tenant, other_tenant = uuid4(), uuid4(), uuid4(), uuid4()
        agent = SimpleNamespace(validate=AsyncMock())
        dispatch = Mock()
        monkeypatch.setattr(worker.execute_shadow_invocation, "delay", dispatch)
        payload = ShadowAgentRequest(agent="shadow-a", data={"value": 1}, **{"async": True})

        async def enqueue(user_id, tenant_id, key, body=payload):
            async with factory() as session:
                return await ShadowInvocationService(session, agent).enqueue(
                    body, user_id=user_id, tenant_id=tenant_id, scopes=[], request_id=str(uuid4()),
                    idempotency_key=key)

        first, replay = await asyncio.gather(
            enqueue(owner, tenant, "same-key"), enqueue(owner, tenant, "same-key"))
        assert first == replay
        assert dispatch.call_count == 1
        with pytest.raises(ConflictError):
            await enqueue(owner, tenant, "same-key",
                ShadowAgentRequest(agent="shadow-b", data={"value": 1}, **{"async": True}))
        assert await enqueue(other, tenant, "same-key") != first
        assert await enqueue(owner, other_tenant, "same-key") != first
        assert await enqueue(owner, tenant, None) != await enqueue(owner, tenant, None)

        async with factory() as session:
            service = ShadowInvocationService(session, agent)
            assert (await service.get(first, owner, tenant_id=tenant)).id == first
            assert first not in [row.id for row in await service.list_ready(owner, tenant_id=other_tenant)]
            with pytest.raises(NotFoundError):
                await service.get(first, other, tenant_id=tenant)
            assert await service.list_ready(other, tenant_id=tenant) == []
            await session.execute(text("UPDATE shadow_invocations SET status='completed', result='{}'::jsonb WHERE id=:id"),
                                  {"id": first})
            await session.commit()
            assert [item.id for item in await service.list_ready(owner, tenant_id=tenant)] == [first]
            assert [item.id for item in await service.list_ready(owner, tenant_id=tenant)] == [first]
            await service.acknowledge(first, owner, tenant_id=tenant)
            await service.acknowledge(first, owner, tenant_id=tenant)
            assert await service.list_ready(owner, tenant_id=tenant) == []


@pytest.mark.asyncio
async def test_postgres_heartbeat_and_expired_claim_takeover_fence_old_writer(monkeypatch):
    from app.models.shadow_invocation import ShadowInvocation
    from app.workers import tasks_shadow_invocations as worker

    async with isolated_schema() as engine:
        factory, session_context = _session_context(engine)
        user_id, tenant_id = uuid4(), uuid4()
        invocation_id = uuid4()
        async with factory() as session:
            await session.execute(text("INSERT INTO users (id, login) VALUES (:id, :login)"),
                                  {"id": user_id, "login": "worker-" + user_id.hex})
            session.add(ShadowInvocation(id=invocation_id, user_id=user_id, tenant_id=tenant_id,
                agent="shadow-a", data={}, scopes=[], request_id="r", status="queued"))
            await session.commit()

        monkeypatch.setattr(worker, "get_worker_session", session_context)
        monkeypatch.setattr(worker, "ApiTokensRepository", lambda _: SimpleNamespace(
            active_tenant_ids=AsyncMock(return_value=[str(tenant_id)])))
        monkeypatch.setattr(worker, "get_llm_client", lambda: None)
        monkeypatch.setattr(worker, "reset_llm_client", Mock())
        monkeypatch.setattr(worker, "cleanup_clients", AsyncMock())

        # A call longer than the configured lease remains running while heartbeats refresh it.
        monkeypatch.setattr(worker, "_lease", lambda: timedelta(seconds=0.12))
        started = asyncio.Event()
        calls = 0

        async def slow_invoke(*args, **kwargs):
            nonlocal calls
            calls += 1
            started.set()
            await asyncio.sleep(0.3)
            return SimpleNamespace(result={"answer": "first claim"})

        monkeypatch.setattr(worker, "ShadowAgentService", lambda *_: SimpleNamespace(invoke=slow_invoke))
        running = asyncio.create_task(worker._execute(str(invocation_id)))
        await started.wait()
        await asyncio.sleep(0.2)
        assert await worker._pending() == []
        await running
        assert calls == 1
        async with factory() as session:
            row = await session.get(ShadowInvocation, invocation_id)
            assert row.status == "completed" and row.result == {"answer": "first claim"}

        # Simulate worker death by withholding heartbeat; a fresh claim takes over.
        second_id = uuid4()
        async with factory() as session:
            session.add(ShadowInvocation(id=second_id, user_id=user_id, tenant_id=tenant_id,
                agent="shadow-a", data={}, scopes=[], request_id="r2", status="queued"))
            await session.commit()
        monkeypatch.setattr(worker, "_heartbeat_period", lambda: 60.0)
        old_started, release_old, new_started = asyncio.Event(), asyncio.Event(), asyncio.Event()
        invocation_count = 0

        async def takeover_invoke(*args, **kwargs):
            nonlocal invocation_count
            invocation_count += 1
            if invocation_count == 1:
                old_started.set()
                await release_old.wait()
                return SimpleNamespace(result={"answer": "stale worker"})
            new_started.set()
            return SimpleNamespace(result={"answer": "new claim"})

        monkeypatch.setattr(worker, "ShadowAgentService", lambda *_: SimpleNamespace(invoke=takeover_invoke))
        old_worker = asyncio.create_task(worker._execute(str(second_id)))
        await old_started.wait()
        async with factory() as session:
            await session.execute(text("UPDATE shadow_invocations SET updated_at = now() - interval '1 hour' WHERE id=:id"),
                                  {"id": second_id})
            await session.commit()
        new_worker = asyncio.create_task(worker._execute(str(second_id)))
        await new_started.wait()
        await new_worker
        release_old.set()
        await old_worker
        async with factory() as session:
            row = await session.get(ShadowInvocation, second_id)
            assert row.status == "completed" and row.result == {"answer": "new claim"}
