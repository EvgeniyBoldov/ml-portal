"""Persistence transition checks; run with DURABLE_RUNTIME_PG=1 on migrated PostgreSQL."""
import os
import asyncio
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.schema import CreateTable
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.db import _db_url
from app.models.assignment_integration import AssignmentIntegration, AssignmentIntegrationToken
from app.models.base import Base
from app.models.chat import ChatMessages, Chats
from app.models.chat_turn import ChatTurn
from app.models.durable_runtime import DurableRuntimeCommand, DurableRuntimeEvent, DurableRuntimePause, DurableRuntimeRun, DurableRuntimeSegment
from app.models.runtime_plan import (
    RuntimeNeedBinding, RuntimePause as GraphPause, RuntimePlan, RuntimePlanIteration,
    RuntimePlanTask, RuntimeTaskAttempt, RuntimeTaskDependency, RuntimeTaskNeed,
    RuntimeTaskResolution,
)
from app.runtime.plan_store import SqlPlanStore
from app.models.tool_instance import ToolInstance
from app.models.user import Users
from app.services.durable_runtime_service import DurableRuntimeConflict, DurableRuntimeService

pytestmark = [pytest.mark.asyncio, pytest.mark.skipif(os.getenv("DURABLE_RUNTIME_PG") != "1", reason="requires local PostgreSQL")]


@pytest_asyncio.fixture
async def database():
    url = _db_url()
    engine = create_async_engine(url)
    schema = "durable_runtime_test_" + uuid4().hex
    async with engine.begin() as connection:
        await connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
    scoped = create_async_engine(url, connect_args={"server_settings": {"search_path": schema}})
    tables = [model.__table__ for model in (
        ToolInstance, AssignmentIntegration, AssignmentIntegrationToken,
        Chats, ChatMessages, ChatTurn, RuntimePlan, RuntimePlanIteration,
        RuntimePlanTask, RuntimeTaskDependency, RuntimeTaskNeed, RuntimeNeedBinding,
        RuntimeTaskResolution, RuntimeTaskAttempt, GraphPause,
        DurableRuntimeCommand, DurableRuntimeEvent, DurableRuntimePause,
        DurableRuntimeRun, DurableRuntimeSegment,
    )]
    try:
        async with scoped.begin() as connection:
            await connection.run_sync(lambda sync: sync.execute(CreateTable(Users.__table__)))
            await connection.run_sync(lambda sync: Base.metadata.create_all(sync, tables=tables))
        yield scoped
    finally:
        await scoped.dispose()
        async with engine.begin() as connection:
            await connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
        await engine.dispose()


async def _fixture(session):
    user_id, chat_id, turn_id = uuid4(), uuid4(), uuid4()
    session.add(Users(id=user_id, login=f"durable-{user_id}"))
    await session.flush()
    session.add(Chats(id=chat_id, owner_id=user_id, name="durable runtime test"))
    await session.flush()
    session.add(ChatTurn(id=turn_id, chat_id=chat_id, user_id=user_id, status="running"))
    await session.flush()
    return user_id, turn_id


async def test_run_claim_pause_signal_and_fencing_are_durable(database):
        sessions = async_sessionmaker(database, expire_on_commit=False)
        async with sessions() as session:
            user_id, turn_id = await _fixture(session)
            service = DurableRuntimeService(session)
            run = await service.create_run(
                chat_turn_id=turn_id, owner_user_id=user_id,
                request_payload={"text": "watch this"}, idempotency_key=f"idem-{uuid4()}",
            )
            claim = await service.claim_next(worker_id="worker-a")
            assert claim is not None and claim.run_id == run.id and claim.attempt == 1
            assert await service.fence_claim(claim.segment_id, claim.claim_id)
            paused = await service.complete_segment(
                claim, status="waiting_input", context={"checkpoint": 3},
                action={"question": "Which item?"}, public_payload={"text": "Which item?"},
            )
            assert paused.status == "waiting_input"
            pause = await session.scalar(select(DurableRuntimePause).where(DurableRuntimePause.run_id == run.id))
            assert pause is not None and pause.payload["context"] == {"checkpoint": 3}
            resumed = await service.accept_signal(
                run.id, event_key="reply-1", signal_type="user_reply",
                payload={"answer": "42"}, pause_id=pause.id, actor_user_id=user_id,
            )
            assert resumed.status == "queued"
            # The same external signal is idempotent and does not create another segment.
            await service.accept_signal(run.id, event_key="reply-1", signal_type="user_reply", payload={"answer": "42"}, pause_id=pause.id, actor_user_id=user_id)
            segments = (await session.scalars(select(DurableRuntimeSegment).where(DurableRuntimeSegment.run_id == run.id))).all()
            assert len(segments) == 2
            commands = (await session.scalars(select(DurableRuntimeCommand).where(DurableRuntimeCommand.run_id == run.id))).all()
            assert len(commands) == 1
            assert await service.fence_claim(claim.segment_id, claim.claim_id) is None
            events = await service.list_events(run.id, actor_user_id=user_id)
            assert [event.kind for event in events] == ["accepted", "waiting_input"]
            await session.rollback()


async def test_stale_claim_and_non_owner_signal_are_rejected(database):
        sessions = async_sessionmaker(database, expire_on_commit=False)
        async with sessions() as session:
            user_id, turn_id = await _fixture(session)
            service = DurableRuntimeService(session)
            run = await service.create_run(chat_turn_id=turn_id, owner_user_id=user_id, request_payload={}, idempotency_key=f"idem-{uuid4()}")
            claim = await service.claim_next(worker_id="worker-a")
            assert claim is not None
            await service.complete_segment(claim, status="waiting_input", pause_id=uuid4())
            with pytest.raises(DurableRuntimeConflict):
                await service.complete_segment(claim, status="completed")
            with pytest.raises(DurableRuntimeConflict):
                await service.accept_signal(run.id, event_key="bad", signal_type="user_reply", payload={}, actor_user_id=uuid4())
            await session.rollback()


async def test_timer_resume_and_cancellation_survive_session_boundaries(database):
    sessions = async_sessionmaker(database, expire_on_commit=False)
    async with sessions() as session:
        user_id, turn_id = await _fixture(session)
        run = await DurableRuntimeService(session).create_run(
            chat_turn_id=turn_id, owner_user_id=user_id, request_payload={"content": "watch"},
            idempotency_key=f"idem-{uuid4()}",
        )
        run_id = run.id
        await session.commit()

    async with sessions() as session:
        service = DurableRuntimeService(session)
        claim = await service.claim_next(worker_id="worker-timer")
        assert claim is not None and claim.run_id == run_id
        await service.complete_segment(
            claim, status="waiting_timer", context={"wake_at": "already due"},
            wake_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        await session.commit()

    async with sessions() as session:
        service = DurableRuntimeService(session)
        run = await service.get_run(run_id)
        pause = await session.scalar(select(DurableRuntimePause).where(
            DurableRuntimePause.run_id == run_id, DurableRuntimePause.status == "active"
        ))
        assert run is not None and run.status == "waiting_timer" and pause is not None
        await service.accept_signal(run_id, event_key="timer-1", signal_type="timer_elapsed", payload={}, pause_id=pause.id)
        await session.commit()

    async with sessions() as session:
        claim = await DurableRuntimeService(session).claim_next(worker_id="worker-after-timer")
        assert claim is not None and claim.reason == "timer_elapsed"
        await session.commit()

    async with sessions() as session:
        service = DurableRuntimeService(session)
        run = await service.cancel(run_id, event_key="cancel-1", actor_user_id=user_id)
        assert run.status == "cancelled"
        await session.commit()

    async with sessions() as session:
        service = DurableRuntimeService(session)
        run = await service.get_run(run_id)
        assert run is not None and run.status == "cancelled"
        assert await service.fence_claim(claim.segment_id, claim.claim_id) is None


async def test_graph_timer_stays_paused_until_graph_resume(database):
    sessions = async_sessionmaker(database, expire_on_commit=False)
    planned_wake_at = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    async with sessions() as session:
        user_id, turn_id = await _fixture(session)
        run = await DurableRuntimeService(session).create_run(
            chat_turn_id=turn_id, owner_user_id=user_id, request_payload={"content": "watch"},
            idempotency_key=f"idem-{uuid4()}",
        )
        plan = await SqlPlanStore(session).create(
            goal="watch", root_run_id=run.id, tenant_id=uuid4(), scope_context={},
        )
        pause_id = await SqlPlanStore(session).pause_timer(
            plan.id, {"wake_at": planned_wake_at}, commit=False,
        )
        claim = await DurableRuntimeService(session).claim_next(worker_id="worker-before-timer")
        assert claim is not None
        await DurableRuntimeService(session).complete_segment(
            claim, status="waiting_timer", context={"wake_at": planned_wake_at},
            wake_at=datetime.fromisoformat(planned_wake_at), pause_id=UUID(pause_id),
        )
        await session.commit()
        plan_id, run_id = plan.id, run.id

    async with sessions() as session:
        service = DurableRuntimeService(session)
        await service.accept_due_timers()
        await session.commit()

    async with sessions() as session:
        plan = await session.get(RuntimePlan, plan_id)
        graph_pause = await session.get(GraphPause, UUID(pause_id))
        assert plan is not None and plan.status == "waiting_timer"
        assert graph_pause is not None and graph_pause.status == "waiting"
        claim = await DurableRuntimeService(session).claim_next(worker_id="worker-resume-graph")
        assert claim is not None and claim.run_id == run_id
        assert plan.status == "waiting_timer"
        await SqlPlanStore(session).resume_timer(
            plan_id, pause_id, planned_wake_at=planned_wake_at,
            actual_wake_at=datetime.now(timezone.utc).isoformat(), commit=False,
        )
        await session.commit()

    async with sessions() as session:
        plan = await session.get(RuntimePlan, plan_id)
        graph_pause = await session.get(GraphPause, UUID(pause_id))
        assert plan is not None and plan.status == "active"
        assert graph_pause is not None and graph_pause.status == "elapsed"


async def test_competing_workers_grant_one_claim(database):
    sessions = async_sessionmaker(database, expire_on_commit=False)
    async with sessions() as session:
        owner_id, turn_id = await _fixture(session)
        run = await DurableRuntimeService(session).create_run(
            chat_turn_id=turn_id, owner_user_id=owner_id, request_payload={},
            idempotency_key=f"idem-{uuid4()}",
        )
        run_id = run.id
        segment_id = (await session.scalar(select(DurableRuntimeSegment.id).where(
            DurableRuntimeSegment.run_id == run_id
        )))
        await session.commit()

    async def compete(worker_id: str):
        async with sessions() as session:
            claim = await DurableRuntimeService(session).claim_segment(
                segment_id, worker_id=worker_id,
            )
            await session.commit()
            return claim

    claims = await asyncio.gather(compete("worker-one"), compete("worker-two"))
    winners = [claim for claim in claims if claim is not None]
    assert len(winners) == 1
    async with sessions() as session:
        segment = await session.get(DurableRuntimeSegment, segment_id)
        assert segment is not None and segment.claim_id == winners[0].claim_id


async def test_timer_wake_racing_cancel_creates_at_most_one_continuation(database):
    sessions = async_sessionmaker(database, expire_on_commit=False)
    async with sessions() as session:
        owner_id, turn_id = await _fixture(session)
        service = DurableRuntimeService(session)
        run = await service.create_run(
            chat_turn_id=turn_id, owner_user_id=owner_id, request_payload={},
            idempotency_key=f"idem-{uuid4()}",
        )
        run_id = run.id
        claim = await service.claim_next(worker_id="worker-before-wake")
        assert claim is not None
        pause_id = uuid4()
        await service.complete_segment(
            claim, status="waiting_timer", pause_id=pause_id,
            context={"wake_at": "due"}, wake_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        await session.commit()

    async def wake():
        async with sessions() as session:
            accepted = await DurableRuntimeService(session).accept_due_timers()
            await session.commit()
            return accepted

    async def cancel():
        async with sessions() as session:
            result = await DurableRuntimeService(session).cancel(
                run_id, event_key="cancel-race", actor_user_id=owner_id,
            )
            await session.commit()
            return result.status

    await asyncio.gather(wake(), cancel())
    async with sessions() as session:
        run = await DurableRuntimeService(session).get_run(run_id)
        continuations = (await session.scalars(select(DurableRuntimeSegment).where(
            DurableRuntimeSegment.run_id == run_id, DurableRuntimeSegment.sequence > 1,
        ))).all()
        active_pause = await session.scalar(select(DurableRuntimePause).where(
            DurableRuntimePause.run_id == run_id, DurableRuntimePause.status == "active",
        ))
        assert run is not None and run.status == "cancelled"
        assert len(continuations) <= 1
        assert active_pause is None


async def test_assignment_identity_and_separate_reply_connector(database, monkeypatch):
    from importlib import import_module
    from types import SimpleNamespace

    import httpx
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from fastapi import FastAPI
    from pydantic import SecretStr

    from app.api.deps import db_session, db_uow, get_current_user
    from app.api.v1.routers import external_assignments as api
    from app.api.v1.routers.admin import agent_runs
    from app.models.tenant import UserTenants
    from app.schemas.external_assignment import AssignmentRequest
    from app.services.durable_runtime_integration_service import DurableRuntimeIntegrationService

    # Exercise the real tenant query without requiring the unrelated model catalog in this schema.
    async with database.begin() as connection:
        await connection.exec_driver_sql(
            "CREATE TABLE tenants (id uuid primary key, is_active boolean, lifecycle_status text, created_at timestamptz)"
        )
        await connection.run_sync(lambda sync: UserTenants.__table__.create(sync))
        def migrate(sync):
            migration = import_module("app.migrations.versions.0218_external_assignment_identities")
            with Operations.context(MigrationContext.configure(sync)):
                migration.upgrade()

        await connection.run_sync(migrate)

    sessions = async_sessionmaker(database, expire_on_commit=False)
    owner_id, tenant_id, huid = uuid4(), uuid4(), uuid4()
    async with sessions.begin() as session:
        session.add(Users(id=owner_id, login="ldap-user", email=" LDAP@example.org ",
                          auth_provider="ldap", last_login_at=datetime.now(timezone.utc)))
        await session.flush()
        await session.execute(
            text("INSERT INTO tenants VALUES (:id, true, 'active', now())"), {"id": tenant_id},
        )
        session.add(UserTenants(user_id=owner_id, tenant_id=tenant_id, is_default=True))

    async def transaction():
        async with sessions.begin() as session:
            yield session

    app = FastAPI()
    app.include_router(api.router)
    app.include_router(agent_runs.router, prefix="/admin/agent-runs")
    app.dependency_overrides[db_uow] = transaction
    app.dependency_overrides[db_session] = transaction
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(is_admin=False, role="reader")
    monkeypatch.setattr(api, "get_settings", lambda: SimpleNamespace(
        DURABLE_RUNTIME_ENABLED=True,
        ASSIGNMENT_CONNECTOR_TOKENS={
            "clouds:express": SecretStr("ingress"), "test:delivery": SecretStr("egress"),
            "test:other": SecretStr("other"),
        },
        ASSIGNMENT_REPLY_ROUTES={"clouds:express": ["test:delivery"]},
    ))
    source = {"type": "clouds", "id": "express"}
    destination = {"type": "test", "id": "delivery", "data": {"address": "thread-1"}}
    body = {
        "source": source, "reply_to": destination, "event_id": str(uuid4()),
        "data": {"text": "Check tomorrow"}, "user": {"clouds": str(huid), "telegram": 123},
    }
    ingress = {"Authorization": "Bearer ingress", "X-Assignment-Connector": "clouds:express"}
    egress = {"Authorization": "Bearer egress", "X-Assignment-Connector": "test:delivery"}
    other = {"Authorization": "Bearer other", "X-Assignment-Connector": "test:other"}
    base = "/integrations/assignments"

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        spoofed = {**ingress, "Authorization": egress["Authorization"]}
        assert (await client.post(base, json=body, headers=spoofed)).status_code == 401
        missing = await client.post(base, json=body, headers=ingress)
        assert missing.status_code == 403 and missing.json()["detail"]["code"] == "identity_not_linked"
        body["user"]["mail"] = "ldap@example.ORG"
        assert (await client.post(base, json={**body, "reply_to": {**destination, "id": "other"}},
                                  headers=ingress)).status_code == 403
        assert (await client.post(base, json=body, headers=egress)).status_code == 403
        response = await client.post(base, json=body, headers=ingress)
        assert response.status_code == 202, response.text
        run = response.json()["run_id"]
        del body["user"]["mail"]
        assert (await client.post(base, json=body, headers=ingress)).json()["run_id"] == run
        assert (await client.get(f"{base}/deliveries", headers=egress)).json()["run_ids"] == [run]
        assert (await client.get(f"{base}/{run}/events", headers=ingress)).status_code == 404
        assert (await client.get(f"{base}/{run}/events", headers=other)).status_code == 404
        feed = (await client.get(f"{base}/{run}/events", headers=egress)).json()
        assert feed["reply_to"] == destination and feed["user"] == {"clouds": str(huid)}
        ack = await client.post(f"{base}/{run}/events/{feed['items'][0]['event_id']}/ack",
                                headers=egress, json={"external_message_id": "sent"})
        assert ack.status_code == 204
        assert (await client.get(f"{base}/deliveries", headers=egress)).json()["run_ids"] == []
        async with sessions.begin() as session:
            runtime = DurableRuntimeService(session)
            claim = await runtime.claim_next(worker_id="admin-timeline")
            assert claim is not None and claim.run_id == UUID(run)
            wake_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            await runtime.complete_segment(claim, status="waiting_timer", wake_at=wake_at)
            assert await runtime.accept_due_timers() == [UUID(run)]

            claim = await runtime.claim_next(worker_id="admin-timeline")
            assert claim is not None and claim.run_id == UUID(run)
            pause_id = uuid4()
            await runtime.complete_segment(
                claim, status="waiting_confirmation", pause_id=pause_id,
                public_payload={"content": "Continue?", "pause_id": str(pause_id)},
            )
            await runtime.accept_signal(
                UUID(run), event_key="reply", signal_type="answer",
                pause_id=pause_id, actor_user_id=owner_id, payload={"response": False},
            )

        wrong_actor = {"event_id": str(uuid4()), "user": {"clouds": str(uuid4()), "mail": "ldap@example.org"}}
        assert (await client.post(f"{base}/{run}/cancel", json=wrong_actor, headers=ingress)).status_code == 404
        assert (await client.post(f"{base}/{run}/cancel", headers=ingress, json={
            "event_id": str(uuid4()), "user": {"clouds": str(huid)},
        })).json()["status"] == "cancelled"

        async with sessions.begin() as session:
            ordinary_request = AssignmentRequest.model_validate({**body, "event_id": str(uuid4())}).to_admission()
            ordinary = await DurableRuntimeIntegrationService(session).admit(
                ordinary_request, owner_user_id=owner_id, tenant_id=tenant_id,
            )
        listing = "/admin/agent-runs/external-requests"
        detail_url = f"{listing}/{run}"
        assert (await client.get(listing)).status_code == 403
        assert (await client.get(detail_url)).status_code == 403
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(is_admin=True, role="admin")
        response = await client.get(listing, params={"limit": 1})
        assert response.status_code == 200, response.text
        page = response.json()
        assert page["total"] == 1
        item = page["items"][0]
        assert item["run_id"] == run
        assert item["source"] == "clouds:express"
        assert item["status"] == "cancelled"
        assert item["user_name"] == "ldap-user"
        assert item["text_preview"] == "Check tomorrow"
        assert (await client.get(listing, params={"offset": 1})).json() == {"items": [], "total": 1}

        response = await client.get(detail_url)
        assert response.status_code == 200, response.text
        detail = response.json()
        assert detail["text"] == "Check tomorrow"
        assert detail["status"] == "cancelled" and detail["completed_at"]
        timeline = detail["timeline"]
        assert [step["kind"] for step in timeline] == [
            "accepted", "waiting_timer", "timer_elapsed", "waiting_confirmation", "answer", "cancelled",
        ]
        assert timeline[0]["delivery_status"] == "delivered"
        assert timeline[0]["delivered_at"]
        assert timeline[1]["delivery_status"] is None
        assert timeline[1]["wake_at"] and timeline[1]["resolved_at"]
        assert timeline[3]["text"] == "Continue?"
        assert timeline[3]["delivery_status"] == "pending"
        assert timeline[4]["answer"] is False
        assert (await client.get(f"{listing}/{ordinary.run_id}")).status_code == 404


async def test_admin_integration_tokens_control_assignment_access(database, monkeypatch):
    from types import SimpleNamespace

    import httpx
    from fastapi import Depends, FastAPI
    from pydantic import SecretStr

    from app.api.deps import db_uow, require_admin
    from app.api.v1.routers import external_assignments
    from app.api.v1.routers.admin import assignment_integrations

    sessions = async_sessionmaker(database, expire_on_commit=False)
    connector_id = uuid4()
    async with sessions.begin() as session:
        session.add(ToolInstance(
            id=connector_id, name="Clouds", slug="clouds", connector_type="integration",
            instance_kind="service", domain="integration", placement="remote", url="https://example.test/events",
        ))

    async def transaction():
        async with sessions.begin() as session:
            yield session

    app = FastAPI()
    app.include_router(assignment_integrations.router, prefix="/admin")
    app.dependency_overrides[db_uow] = transaction
    app.dependency_overrides[require_admin] = lambda: None
    monkeypatch.setattr(external_assignments, "get_settings", lambda: SimpleNamespace(
        ASSIGNMENT_CONNECTOR_TOKENS={"clouds:express": SecretStr("old-secret")},
    ))

    @app.get("/check")
    async def check_connector(principal=Depends(external_assignments.authenticate_connector)):
        return principal.key

    headers = {"X-Assignment-Connector": "clouds:express", "Authorization": "Bearer old-secret"}
    base = "/admin/integrations"
    data = {"name": "Clouds", "source": "clouds:express", "connector_id": str(connector_id)}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/check", headers=headers)).status_code == 200
        created = await client.post(base, json=data)
        assert created.status_code == 201, created.text
        assert (await client.post(base, json=data)).status_code == 409
        assert (await client.get("/check", headers=headers)).status_code == 401

        path = f"{base}/{created.json()['id']}"
        issued = await client.post(f"{path}/tokens", json={"name": "Clouds", "expires_days": 1})
        assert issued.status_code == 201, issued.text
        assert issued.headers["Cache-Control"] == "no-store"
        token = issued.json()
        headers["Authorization"] = f"Bearer {token['token']}"
        assert (await client.get("/check", headers=headers)).json() == "clouds:express"
        assert (await client.get("/check", headers={**headers, "X-Assignment-Connector": "clouds:other"})).status_code == 401
        listed = (await client.get(f"{path}/tokens")).json()[0]
        assert "token" not in listed and "token_hash" not in listed
        assert listed["last_used_at"]

        assert (await client.put(path, json={**data, "is_active": False})).status_code == 200
        assert (await client.get("/check", headers=headers)).status_code == 401
        assert (await client.put(path, json={**data, "is_active": True})).status_code == 200
        assert (await client.delete(f"{path}/tokens/{token['id']}")).status_code == 204
        assert (await client.get("/check", headers=headers)).status_code == 401
