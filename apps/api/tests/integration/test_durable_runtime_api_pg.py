"""HTTP to PostgreSQL workflow checks; run with DURABLE_RUNTIME_PG=1."""
from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.api.deps import db_session, db_uow, get_bearer_user
from app.api.v1.routers import durable_runtime as durable_api
from app.core.db import _db_url
from app.models.base import Base
from app.models.chat import ChatMessages, Chats
from app.models.chat_turn import ChatTurn
from app.models.durable_runtime import (
    DurableRuntimeCommand,
    DurableRuntimeEvent,
    DurableRuntimePause,
    DurableRuntimeRun,
    DurableRuntimeSegment,
)
from app.models.runtime_plan import (
    RuntimeNeedBinding, RuntimePause as GraphPause, RuntimePlan, RuntimePlanIteration,
    RuntimePlanTask, RuntimeTaskAttempt, RuntimeTaskDependency, RuntimeTaskNeed,
    RuntimeTaskResolution,
)
from app.runtime.interaction import InteractionQuestion, InteractionRequester, RuntimeInteraction
from app.services.durable_runtime_service import DurableRuntimeService

pytestmark = pytest.mark.skipif(os.getenv("DURABLE_RUNTIME_PG") != "1", reason="requires local PostgreSQL")


@pytest.fixture
def database():
    url = _db_url()
    admin_engine = create_async_engine(url, poolclass=NullPool)
    schema = "durable_runtime_api_" + uuid4().hex
    scoped_engine = create_async_engine(
        url,
        connect_args={"server_settings": {"search_path": schema}},
        poolclass=NullPool,
    )
    tables = [model.__table__ for model in (
        Chats, ChatMessages, ChatTurn, RuntimePlan, RuntimePlanIteration,
        RuntimePlanTask, RuntimeTaskDependency, RuntimeTaskNeed, RuntimeNeedBinding,
        RuntimeTaskResolution, RuntimeTaskAttempt, GraphPause,
        DurableRuntimeCommand, DurableRuntimeEvent, DurableRuntimePause,
        DurableRuntimeRun, DurableRuntimeSegment,
    )]

    async def create_schema():
        async with admin_engine.begin() as connection:
            await connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        async with scoped_engine.begin() as connection:
            await connection.exec_driver_sql("""
                CREATE TABLE users (
                    id uuid PRIMARY KEY,
                    login varchar(255) NOT NULL UNIQUE,
                    role varchar(20) NOT NULL DEFAULT 'reader',
                    is_admin boolean NOT NULL DEFAULT false,
                    memory_scope_keys varchar[] NOT NULL DEFAULT '{}',
                    is_active boolean NOT NULL DEFAULT true,
                    auth_provider varchar(16) NOT NULL DEFAULT 'local',
                    lifecycle_status varchar(20) NOT NULL DEFAULT 'active',
                    retention_days integer NOT NULL DEFAULT 14,
                    delete_cascade boolean NOT NULL DEFAULT false,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    updated_at timestamptz NOT NULL DEFAULT now()
                )
            """)
            await connection.run_sync(lambda sync: Base.metadata.create_all(sync, tables=tables))

    asyncio.run(create_schema())
    yield async_sessionmaker(scoped_engine, expire_on_commit=False), scoped_engine

    async def drop_schema():
        await scoped_engine.dispose()
        async with admin_engine.begin() as connection:
            await connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
        await admin_engine.dispose()

    asyncio.run(drop_schema())


def test_http_admit_duplicate_answer_false_complete_replay_ack(database, monkeypatch):
    sessions, _engine = database
    owner_id, tenant_id = uuid4(), uuid4()

    async def seed_user():
        async with sessions() as session:
            await session.execute(text("INSERT INTO users (id, login) VALUES (:id, :login)"), {
                "id": owner_id,
                "login": f"durable-api-{owner_id}",
            })
            await session.commit()

    asyncio.run(seed_user())
    app = FastAPI()
    app.include_router(durable_api.router, prefix="/api/v1")
    app.dependency_overrides[get_bearer_user] = lambda: SimpleNamespace(id=owner_id)

    async def transaction_session():
        async with sessions() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[db_uow] = transaction_session
    app.dependency_overrides[db_session] = transaction_session

    async def active_tenants(_session, _user):
        return [tenant_id]

    monkeypatch.setattr(durable_api, "resolve_active_user_tenant_ids", active_tenants)
    monkeypatch.setattr(durable_api, "get_settings", lambda: SimpleNamespace(DURABLE_RUNTIME_ENABLED=True))
    monkeypatch.setattr(durable_api, "get_session_factory", lambda: sessions)
    body = {
        "event_id": "mention-1",
        "text": "Ask me to confirm before continuing",
        "timezone": "Europe/Moscow",
        "address": {
            "integration_id": "test-adapter",
            "workspace_id": "workspace-1",
            "conversation_id": "conversation-1",
            "thread_id": "thread-1",
            "source_message_id": "source-1",
        },
    }

    with TestClient(app) as client:
        accepted = client.post("/api/v1/integrations/durable-runs", json=body)
        assert accepted.status_code == 202, accepted.text
        accepted_data = accepted.json()
        duplicate = client.post("/api/v1/integrations/durable-runs", json=body)
        assert duplicate.status_code == 202, duplicate.text
        assert duplicate.json()["run_id"] == accepted_data["run_id"]
        assert duplicate.json()["chat_id"] == accepted_data["chat_id"]

    run_id = UUID(accepted_data["run_id"])
    async def add_boolean_pause():
        async with sessions() as session:
            service = DurableRuntimeService(session)
            requester = InteractionRequester(stage="turn_preflight", entity_id="turn_preflight")
            interaction = RuntimeInteraction.create(
                InteractionQuestion(question="Continue?", response_type="boolean"), requester,
            )
            pause_id = UUID(interaction.id)
            claim = await service.claim_next(worker_id="api-pg-pause")
            assert claim is not None and claim.run_id == run_id
            await service.complete_segment(
                claim,
                status="waiting_confirmation",
                context={"interaction": interaction.model_dump(mode="json")},
                action={"kind": "interaction"},
                public_payload={"pause_id": str(pause_id), "content": "Continue?"},
                pause_id=pause_id,
            )
            await session.commit()
            return pause_id

    pause_id = asyncio.run(add_boolean_pause())
    with TestClient(app) as client:
        stale = client.post(
            f"/api/v1/integrations/durable-runs/{run_id}/responses",
            json={"event_id": "reply-stale", "pause_id": str(uuid4()), "value": False},
        )
        assert stale.status_code == 409

        async def count_messages():
            async with sessions() as session:
                return await session.scalar(select(func.count()).select_from(ChatMessages))

        assert asyncio.run(count_messages()) == 1
        answer = client.post(
            f"/api/v1/integrations/durable-runs/{run_id}/responses",
            json={"event_id": "reply-1", "pause_id": str(pause_id), "value": False},
        )
        assert answer.status_code == 200, answer.text
        assert answer.json()["status"] == "queued"
        duplicate = client.post(
            f"/api/v1/integrations/durable-runs/{run_id}/responses",
            json={"event_id": "reply-1", "pause_id": str(pause_id), "value": False},
        )
        assert duplicate.status_code == 200, duplicate.text

        async def complete_run():
            async with sessions() as session:
                service = DurableRuntimeService(session)
                claim = await service.claim_next(worker_id="api-pg-test")
                assert claim is not None and claim.run_id == run_id
                await service.complete_segment(
                    claim, status="completed", public_payload={"content": "Completed"},
                )
                await session.commit()

        asyncio.run(complete_run())
        replay = client.get(f"/api/v1/integrations/durable-runs/{run_id}/events")
        assert replay.status_code == 200, replay.text
        items = replay.json()["items"]
        assert [item["kind"] for item in items] == ["accepted", "waiting_confirmation", "completed"]
        terminal_event_id = items[-1]["event_id"]
        stream = client.get(
            f"/api/v1/integrations/durable-runs/{run_id}/event-stream",
            headers={"Last-Event-ID": "1"},
        )
        assert stream.status_code == 200
        assert "id: 2\n" in stream.text and "id: 3\n" in stream.text
        assert "id: 1\n" not in stream.text
        ack = client.post(f"/api/v1/integrations/durable-runs/{run_id}/events/{terminal_event_id}/ack")
        assert ack.status_code == 204

    async def verify_rows():
        async with sessions() as session:
            assert await session.scalar(select(func.count()).select_from(Chats)) == 1
            assert await session.scalar(select(func.count()).select_from(ChatMessages)) == 2
            assert await session.scalar(select(func.count()).select_from(DurableRuntimeCommand)) == 1
            command = await session.scalar(select(DurableRuntimeCommand).where(DurableRuntimeCommand.run_id == run_id))
            assert command is not None and command.payload["response"] is False
            event = await session.get(DurableRuntimeEvent, UUID(terminal_event_id))
            assert event is not None and event.status == "delivered"

    asyncio.run(verify_rows())
