"""End-to-end durable timer pause/wake through the real runtime pipeline.

Covers the full worker path over real PostgreSQL: claim a queued segment,
execute it through ChatStreamService/ChatTurnOrchestrator/RuntimePipeline with
the real SqlPlanStore, pause on a planner timer request, accept the due timer,
and re-execute the follow-up segment. The planner is replaced with a
deterministic SleepingPlanner that always raises TimerPauseRequired and
TurnPreflight is replaced with a fixed planner-route decision, so no LLM is
required.

The invariant under test: DurableRuntimePause.id equals the GraphPause.id
persisted by plan_store.pause_timer (no fallback identity), and the wake
segment receives that same pause identity through the trusted timer
continuation.

Run with DURABLE_RUNTIME_PG=1 on migrated PostgreSQL.
"""
import os
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.models  # noqa: F401  — registers every mapped model
from app.core import db as core_db
from app.core.db import _db_url
from app.models.chat import ChatMessages, Chats
from app.models.chat_turn import ChatTurn
from app.models.durable_runtime import (
    DurableRuntimePause,
    DurableRuntimeRun,
    DurableRuntimeSegment,
)
from app.models.runtime_plan import RuntimePause as GraphPause
from app.models.runtime_plan import RuntimePlan
from app.models.tenant import Tenants, UserTenants
from app.models.user import Users
from app.runtime.assembler import PipelineAssembler
from app.runtime.orchestrator import GraphOrchestrator
from app.runtime.plan_store import SqlPlanStore
from app.runtime.planner.graph_planner import TimerPauseRequired
from app.runtime.stages.graph_planning_stage import GraphPlanningStage
from app.runtime.turn_preflight import TurnPreflight, TurnPreflightDecision
from app.services.durable_runtime_execution import execute_claimed_segment
from app.services.durable_runtime_service import DurableRuntimeService

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(os.getenv("DURABLE_RUNTIME_PG") != "1", reason="requires local PostgreSQL"),
]


@pytest_asyncio.fixture
async def database():
    url = _db_url()
    engine = create_async_engine(url)
    schema = "durable_runtime_exec_test_" + uuid4().hex
    async with engine.begin() as connection:
        await connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
    try:
        # The migrated public schema is the authoritative DDL: metadata
        # create_all trips over legacy model quirks (the duplicated users
        # login index, raw-string server defaults). Clone it instead.
        # Foreign keys are generated on the admin connection (search_path
        # includes public) so pg_get_constraintdef prints unqualified
        # references, then restored inside the clone where search_path
        # resolves them to the test schema.
        async with engine.connect() as connection:
            foreign_keys = list(
                (
                    await connection.exec_driver_sql(
                        f"""
                        SELECT format('ALTER TABLE %I.%I ADD CONSTRAINT %I %s',
                                      '{schema}', c.relname, con.conname,
                                      pg_get_constraintdef(con.oid))
                        FROM pg_constraint con
                        JOIN pg_class c ON c.oid = con.conrelid
                        JOIN pg_namespace n ON n.oid = c.relnamespace
                        WHERE con.contype = 'f' AND n.nspname = 'public'
                        """
                    )
                ).scalars()
            )
        scoped = create_async_engine(
            # public stays in the path: asyncpg resolves unqualified type names
            # (chat_role_enum and friends) at prepare time, and unqualified
            # tables still resolve to the clone because it comes first.
            url, connect_args={"server_settings": {"search_path": f"{schema},public"}}
        )
        async with scoped.begin() as connection:
            table_names = list(
                (
                    await connection.exec_driver_sql(
                        "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
                    )
                ).scalars()
            )
            for name in table_names:
                await connection.exec_driver_sql(
                    f'CREATE TABLE "{name}" (LIKE public."{name}" INCLUDING ALL)'
                )
            for statement in foreign_keys:
                await connection.exec_driver_sql(statement)
        yield scoped
    finally:
        if "scoped" in locals():
            await scoped.dispose()
        async with engine.begin() as connection:
            await connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
        await engine.dispose()


class SleepingPlanner:
    """Deterministic planner: every iteration requests a timer pause.

    Wake offsets make the first pause immediately due (so accept_due_timers
    picks it up) and the second one far in the future, which ends the scenario
    in a fresh waiting state.
    """

    def __init__(self, wake_offsets: list[timedelta]) -> None:
        self.requests: list[Any] = []
        self._wake_offsets = list(wake_offsets)

    async def plan(self, *, request: Any, **kwargs: Any) -> Any:
        self.requests.append(request)
        wake_at = (
            datetime.now(timezone.utc) + self._wake_offsets[len(self.requests) - 1]
        ).isoformat()
        raise TimerPauseRequired(
            {
                "wake_at": wake_at,
                "reason": "Check the application again",
                "next_check": "Read the current application status",
                "user_update": "I will check again later.",
            },
            {"request": request.model_dump(mode="json"), "tool_results": []},
        )


async def _fake_preflight_decide(self: TurnPreflight, **kwargs: Any) -> TurnPreflightDecision:
    return TurnPreflightDecision.model_validate(
        {
            "route": "planner",
            "task_brief": {
                "goal": "Monitor the application",
                "direction": "Check for future status changes",
                "expected_result": "Report a status change",
            },
        }
    )


async def _seed(
    sessions: async_sessionmaker,
) -> tuple[UUID, UUID, UUID, UUID, UUID]:
    """User/tenant/chat/turn rows plus one queued durable run; returns ids."""
    user_id, tenant_id, chat_id, turn_id = uuid4(), uuid4(), uuid4(), uuid4()
    async with sessions() as session:
        # Flush per row: without mapped relationships the unit of work does
        # not order these INSERTs by foreign keys (service-test pattern).
        session.add(Users(id=user_id, login=f"exec-{user_id}"))
        await session.flush()
        session.add(Tenants(id=tenant_id, name=f"exec-{tenant_id}", is_active=True))
        await session.flush()
        session.add(UserTenants(user_id=user_id, tenant_id=tenant_id, is_default=True))
        await session.flush()
        session.add(Chats(id=chat_id, owner_id=user_id, name="durable runtime exec test"))
        await session.flush()
        session.add(ChatTurn(id=turn_id, chat_id=chat_id, user_id=user_id, status="running"))
        await session.flush()
        run = await DurableRuntimeService(session).create_run(
            chat_turn_id=turn_id,
            owner_user_id=user_id,
            request_payload={
                "tenant_id": str(tenant_id),
                "content": "Watch the application status and tell me when it changes.",
            },
            idempotency_key=f"idem-{uuid4()}",
        )
        await session.commit()
        return user_id, tenant_id, chat_id, turn_id, run.id


def _install_pipeline_stubs(
    monkeypatch: pytest.MonkeyPatch,
    database: Any,
    planner: SleepingPlanner,
) -> None:
    """Swap the LLM planner for the sleeping one and pin session globals."""

    def build_graph_planning_stage(self: PipelineAssembler, *, max_steps: int) -> GraphPlanningStage:
        store = SqlPlanStore(self._session)
        return GraphPlanningStage(
            store=store,
            orchestrator=GraphOrchestrator(
                store=store,
                planner=planner,
                executor=Mock(),
                synthesizer=Mock(),
            ),
            max_steps=max_steps,
        )

    # The assembler's session is the worker session passed to
    # execute_claimed_segment, so the plan store shares the pipeline
    # transaction: GraphPause, DurableRuntimePause, turn state and the
    # assistant message commit together in the pause branch.
    monkeypatch.setattr(PipelineAssembler, "build_graph_planning_stage", build_graph_planning_stage)
    monkeypatch.setattr(TurnPreflight, "decide", _fake_preflight_decide)
    # fence_effect() and the journal writers open their own sessions through
    # the app-level factory/engine globals; point them at the test schema.
    monkeypatch.setattr(core_db, "_session_factory", async_sessionmaker(database, expire_on_commit=False))
    monkeypatch.setattr(core_db, "_engine", database)


async def test_execute_claimed_segment_pauses_on_timer_and_resumes_after_wake(
    database, monkeypatch
):
    sessions = async_sessionmaker(database, expire_on_commit=False)
    user_id, tenant_id, chat_id, turn_id, run_id = await _seed(sessions)
    planner = SleepingPlanner([timedelta(minutes=-1), timedelta(hours=2)])
    _install_pipeline_stubs(monkeypatch, database, planner)

    # --- Initial segment: claim, execute through the real pipeline, pause. ---
    async with sessions() as session:
        claim = await DurableRuntimeService(session).claim_next(
            worker_id="worker-a", lease_seconds=300
        )
        assert claim is not None
        assert claim.run_id == run_id
        assert claim.reason == "initial"
        assert claim.attempt == 1
        await session.commit()

    async with sessions() as session:
        await execute_claimed_segment(
            claim, session=session, llm_client=Mock(), redis_client=Mock()
        )

    async with sessions() as check:
        run = await check.get(DurableRuntimeRun, run_id)
        assert run is not None
        assert run.status == "waiting_timer"

        plan = await check.scalar(
            select(RuntimePlan).where(RuntimePlan.root_run_id == run_id)
        )
        assert plan is not None
        assert plan.status == "waiting_timer"

        pauses = list(
            await check.scalars(select(GraphPause).where(GraphPause.plan_id == plan.id))
        )
        assert len(pauses) == 1
        graph_pause = pauses[0]
        assert graph_pause.kind == "timer"
        assert graph_pause.status == "waiting"
        payload = graph_pause.payload
        assert payload["user_update"] == "I will check again later."
        assert payload["paused_iteration_sequence"] == 0
        assert payload["checkpoint"]
        assert datetime.fromisoformat(payload["wake_at"]) <= datetime.now(timezone.utc)

        # Invariant: the durable pause is the planner pause, not a new one.
        durable_pause = await check.get(DurableRuntimePause, graph_pause.id)
        assert durable_pause is not None
        assert durable_pause.kind == "waiting_timer"
        assert durable_pause.status == "active"
        assert durable_pause.id == graph_pause.id
        assert durable_pause.wake_at == datetime.fromisoformat(payload["wake_at"])
        assert durable_pause.wake_at <= datetime.now(timezone.utc)
        assert durable_pause.requester == {"user_id": str(user_id)}

        turn = await check.get(ChatTurn, turn_id)
        assert turn is not None
        assert turn.status == "waiting_timer"
        assert turn.pause_status == "waiting_timer"
        assert str((turn.paused_context or {}).get("pause_id")) == str(graph_pause.id)

        assistant_messages = list(
            await check.scalars(
                select(ChatMessages)
                .where(ChatMessages.chat_id == chat_id, ChatMessages.role == "assistant")
                .order_by(ChatMessages.created_at)
            )
        )
        assert [message.content for message in assistant_messages] == [
            {"text": "I will check again later."}
        ]

        segments = list(
            await check.scalars(
                select(DurableRuntimeSegment)
                .where(DurableRuntimeSegment.run_id == run_id)
                .order_by(DurableRuntimeSegment.sequence)
            )
        )
        assert [(s.sequence, s.reason, s.status) for s in segments] == [
            (1, "initial", "completed")
        ]

    # --- Wake: the due timer becomes a queued timer_elapsed segment. ---
    async with sessions() as session:
        due = await DurableRuntimeService(session).accept_due_timers()
        await session.commit()
    assert due == [run_id]

    async with sessions() as session:
        wake_claim = await DurableRuntimeService(session).claim_next(
            worker_id="worker-b", lease_seconds=300
        )
        assert wake_claim is not None
        assert wake_claim.run_id == run_id
        assert wake_claim.reason == "timer_elapsed"
        resume = (wake_claim.context or {}).get("resume") or {}
        assert resume.get("signal_type") == "timer_elapsed"
        assert str(resume.get("pause_id")) == str(graph_pause.id)
        await session.commit()

    async with sessions() as session:
        await execute_claimed_segment(
            wake_claim, session=session, llm_client=Mock(), redis_client=Mock()
        )

    async with sessions() as check:
        run = await check.get(DurableRuntimeRun, run_id)
        assert run is not None
        assert run.status == "waiting_timer"

        plan = await check.scalar(
            select(RuntimePlan).where(RuntimePlan.root_run_id == run_id)
        )
        assert plan is not None
        assert plan.status == "waiting_timer"

        pauses = list(
            await check.scalars(select(GraphPause).where(GraphPause.plan_id == plan.id))
        )
        assert sorted(pause.status for pause in pauses) == ["elapsed", "waiting"]
        resumed_pause = next(p for p in pauses if p.id == graph_pause.id)
        second_pause = next(p for p in pauses if p.id != graph_pause.id)
        assert resumed_pause.status == "elapsed"
        assert resumed_pause.resolved_at is not None
        assert second_pause.status == "waiting"
        assert (
            datetime.fromisoformat(second_pause.payload["wake_at"])
            >= datetime.now(timezone.utc)
        )

        durable_pauses = list(
            await check.scalars(
                select(DurableRuntimePause)
                .where(DurableRuntimePause.run_id == run_id)
                .order_by(DurableRuntimePause.wake_at)
            )
        )
        assert [pause.status for pause in durable_pauses] == ["resolved", "active"]
        assert durable_pauses[0].id == graph_pause.id
        assert durable_pauses[1].id == second_pause.id
        assert durable_pauses[1].wake_at >= datetime.now(timezone.utc)

        # The wake segment continued the same plan and received the trusted
        # timer continuation carrying the original pause identity.
        assert len(planner.requests) == 2
        timer_resume = planner.requests[1].context.timer_resume
        assert str(timer_resume["pause_id"]) == str(graph_pause.id)
        assert timer_resume["planned_wake_at"] == payload["wake_at"]

        segments = list(
            await check.scalars(
                select(DurableRuntimeSegment)
                .where(DurableRuntimeSegment.run_id == run_id)
                .order_by(DurableRuntimeSegment.sequence)
            )
        )
        assert [(s.sequence, s.reason, s.status) for s in segments] == [
            (1, "initial", "completed"),
            (2, "timer_elapsed", "completed"),
        ]

        assistant_messages = list(
            await check.scalars(
                select(ChatMessages)
                .where(ChatMessages.chat_id == chat_id, ChatMessages.role == "assistant")
                .order_by(ChatMessages.created_at)
            )
        )
        assert [message.content for message in assistant_messages] == [
            {"text": "I will check again later."},
            {"text": "I will check again later."},
        ]
