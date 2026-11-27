"""Transactional PostgreSQL state transitions for durable runtime runs.

Callers own the transaction and commit. Every mutating method only flushes.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat_turn import ChatTurn
from app.models.durable_runtime import (
    DurableRuntimeCommand,
    DurableRuntimeEvent,
    DurableRuntimePause,
    DurableRuntimeRun,
    DurableRuntimeSegment,
)
from app.models.runtime_plan import RuntimePlan
from app.runtime.plan_store import SqlPlanStore


DURABLE_CHECKPOINT_VERSION = 1


@dataclass(frozen=True)
class DurableRuntimeClaim:
    run_id: uuid.UUID
    segment_id: uuid.UUID
    claim_id: uuid.UUID
    chat_turn_id: uuid.UUID
    attempt: int
    reason: str
    context: dict[str, Any] | None


class DurableRuntimeConflict(ValueError):
    """The requested transition conflicts with the persisted lifecycle."""


class DurableRuntimeService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _db_now(self) -> datetime:
        return await self.session.scalar(select(func.clock_timestamp()))

    async def lock_admission_key(self, key: str) -> None:
        # hashtextextended collisions only serialize unrelated admissions; they
        # cannot compromise correctness. The lock lasts until caller commit.
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": key}
        )

    async def get_run_by_admission_key(self, key: str) -> DurableRuntimeRun | None:
        return await self.session.scalar(
            select(DurableRuntimeRun).where(DurableRuntimeRun.admission_key == key)
        )

    async def get_run_by_idempotency_key(self, key: str) -> DurableRuntimeRun | None:
        return await self.session.scalar(
            select(DurableRuntimeRun).where(DurableRuntimeRun.idempotency_key == key)
        )

    async def get_run(self, run_id: uuid.UUID) -> DurableRuntimeRun | None:
        return await self.session.get(DurableRuntimeRun, run_id)

    async def get_event(self, run_id: uuid.UUID, event_id: uuid.UUID) -> DurableRuntimeEvent | None:
        return await self.session.scalar(select(DurableRuntimeEvent).where(
            DurableRuntimeEvent.run_id == run_id, DurableRuntimeEvent.id == event_id
        ))

    async def get_command(self, run_id: uuid.UUID, event_key: str) -> DurableRuntimeCommand | None:
        return await self.session.scalar(select(DurableRuntimeCommand).where(
            DurableRuntimeCommand.run_id == run_id, DurableRuntimeCommand.event_key == event_key
        ))

    async def create_run(
        self,
        *,
        chat_turn_id: uuid.UUID,
        owner_user_id: uuid.UUID,
        request_payload: dict[str, Any],
        idempotency_key: str,
        recipient: dict[str, Any] | None = None,
        root_run_id: uuid.UUID | None = None,
        admission_key: str | None = None,
    ) -> DurableRuntimeRun:
        existing = await self.get_run_by_idempotency_key(idempotency_key)
        if existing is not None:
            if existing.request_payload != request_payload:
                raise DurableRuntimeConflict("idempotency key already used for a different request")
            return existing
        turn = await self.session.scalar(
            select(ChatTurn).where(ChatTurn.id == chat_turn_id).with_for_update()
        )
        if turn is None:
            raise DurableRuntimeConflict("chat turn does not exist")
        run_id = root_run_id or turn.runtime_run_id or uuid.uuid4()
        turn.runtime_run_id = run_id
        turn.status = "queued"
        now = await self._db_now()
        run = DurableRuntimeRun(
            id=run_id,
            chat_turn_id=chat_turn_id,
            owner_user_id=owner_user_id,
            status="queued",
            idempotency_key=idempotency_key,
            admission_key=admission_key,
            request_payload=request_payload,
            recipient=recipient,
            context={"version": DURABLE_CHECKPOINT_VERSION, "action": None, "context": None, "resume": None},
        )
        self.session.add(run)
        self.session.add(DurableRuntimeSegment(run_id=run_id, sequence=1, reason="initial", status="queued", available_at=now))
        await self.session.flush()
        await self._append_event(run, "accepted", "accepted", {"status": "queued"})
        await self.session.flush()
        return run

    async def list_ready_segment_ids(self, limit: int = 100) -> list[uuid.UUID]:
        rows = await self.session.scalars(
            select(DurableRuntimeSegment)
            .where(
                or_(
                    (DurableRuntimeSegment.status == "queued") & (DurableRuntimeSegment.available_at <= func.clock_timestamp()),
                    (DurableRuntimeSegment.status == "running") & (DurableRuntimeSegment.lease_until <= func.clock_timestamp()),
                )
            )
            .order_by(DurableRuntimeSegment.available_at, DurableRuntimeSegment.created_at)
            .limit(max(1, min(limit, 1000)))
        )
        return [row.id for row in rows.all()]

    async def claim_segment(self, segment_id: uuid.UUID, *, worker_id: str, lease_seconds: int = 60) -> DurableRuntimeClaim | None:
        run_id = await self.session.scalar(select(DurableRuntimeSegment.run_id).where(DurableRuntimeSegment.id == segment_id))
        if run_id is None:
            return None
        run = await self.session.scalar(select(DurableRuntimeRun).where(DurableRuntimeRun.id == run_id).with_for_update().execution_options(populate_existing=True))
        segment = await self.session.scalar(select(DurableRuntimeSegment).where(
            DurableRuntimeSegment.id == segment_id,
            or_((DurableRuntimeSegment.status == "queued") & (DurableRuntimeSegment.available_at <= func.clock_timestamp()),
                (DurableRuntimeSegment.status == "running") & (DurableRuntimeSegment.lease_until <= func.clock_timestamp())),
        ).execution_options(populate_existing=True).with_for_update(skip_locked=True))
        if segment is None or run is None:
            return None
        if run is None or run.status in {"completed", "failed", "cancelled"}:
            now = await self._db_now()
            segment.status = "cancelled"
            segment.finished_at = now
            await self.session.flush()
            return None
        now = await self._db_now()
        if segment.attempt >= 8:
            segment.status = "failed"
            segment.finished_at = now
            segment.lease_until = None
            run.status = "failed"
            await self._finalize_plan(run.id, "failed", "durable_worker_lease_exhausted")
            turn = await self.session.get(ChatTurn, run.chat_turn_id)
            if turn is not None:
                turn.status = "failed"
                turn.error_message = "Execution could not be resumed after repeated worker failures."
                turn.completed_at = now
            await self._append_event(run, "lease-exhausted", "failed", {"error": "Execution could not be resumed after repeated worker failures."})
            await self.session.flush()
            return None
        segment.status = "running"
        segment.attempt += 1
        segment.claim_id = uuid.uuid4()
        segment.worker_id = worker_id
        segment.lease_until = now + timedelta(seconds=lease_seconds)
        run.status = "running"
        turn = await self.session.get(ChatTurn, run.chat_turn_id)
        if turn is not None:
            turn.status = "running"
            turn.heartbeat_at = now
        await self.session.flush()
        return DurableRuntimeClaim(run.id, segment.id, segment.claim_id, run.chat_turn_id, segment.attempt, segment.reason, run.context)

    async def claim_next(self, *, worker_id: str, lease_seconds: int = 60) -> DurableRuntimeClaim | None:
        """Compatibility helper for callers that claim and execute in one task."""
        candidates = await self.list_ready_segment_ids(1)
        if not candidates:
            return None
        return await self.claim_segment(candidates[0], worker_id=worker_id, lease_seconds=lease_seconds)

    async def get_claim(self, segment_id: uuid.UUID, claim_id: uuid.UUID) -> DurableRuntimeClaim | None:
        row = await self.session.execute(
            select(DurableRuntimeSegment, DurableRuntimeRun)
            .join(DurableRuntimeRun, DurableRuntimeRun.id == DurableRuntimeSegment.run_id)
            .where(DurableRuntimeSegment.id == segment_id, DurableRuntimeSegment.claim_id == claim_id,
                   DurableRuntimeSegment.status == "running", DurableRuntimeRun.status == "running",
                   DurableRuntimeSegment.lease_until > func.clock_timestamp())
        )
        pair = row.first()
        if pair is None:
            return None
        segment, run = pair
        return DurableRuntimeClaim(run.id, segment.id, claim_id, run.chat_turn_id, segment.attempt, segment.reason, run.context)

    async def fence_claim(self, segment_id: uuid.UUID, claim_id: uuid.UUID) -> DurableRuntimeClaim | None:
        segment_ref = await self.session.get(DurableRuntimeSegment, segment_id)
        if segment_ref is None:
            return None
        run = await self.session.scalar(select(DurableRuntimeRun).where(DurableRuntimeRun.id == segment_ref.run_id).with_for_update().execution_options(populate_existing=True))
        segment = await self.session.scalar(select(DurableRuntimeSegment).where(DurableRuntimeSegment.id == segment_id).with_for_update())
        if segment is None:
            return None
        lease_valid = await self.session.scalar(select(DurableRuntimeSegment.id).where(
            DurableRuntimeSegment.id == segment_id, DurableRuntimeSegment.claim_id == claim_id,
            DurableRuntimeSegment.status == "running", DurableRuntimeSegment.lease_until > func.clock_timestamp(),
        ))
        if run is None or run.status != "running" or segment.status != "running" or segment.claim_id != claim_id or lease_valid is None:
            return None
        return DurableRuntimeClaim(run.id, segment.id, claim_id, run.chat_turn_id, segment.attempt, segment.reason, run.context)

    async def heartbeat(self, claim: DurableRuntimeClaim, lease_seconds: int = 60) -> bool:
        fenced = await self.fence_claim(claim.segment_id, claim.claim_id)
        if fenced is None:
            return False
        now = await self._db_now()
        segment = await self.session.get(DurableRuntimeSegment, claim.segment_id)
        segment.lease_until = now + timedelta(seconds=lease_seconds)
        turn = await self.session.get(ChatTurn, fenced.chat_turn_id)
        if turn is not None:
            turn.heartbeat_at = now
        await self.session.flush()
        return True

    async def complete_segment(
        self,
        claim: DurableRuntimeClaim,
        *,
        status: str,
        context: dict[str, Any] | None = None,
        action: dict[str, Any] | None = None,
        public_payload: dict[str, Any] | None = None,
        wake_at: datetime | None = None,
        pause_id: uuid.UUID | None = None,
        event_key: str | None = None,
    ) -> DurableRuntimeRun:
        fenced = await self.fence_claim(claim.segment_id, claim.claim_id)
        if fenced is None:
            raise DurableRuntimeConflict("claim is stale or run is no longer active")
        if status not in {"waiting_input", "waiting_confirmation", "waiting_timer", "completed", "failed", "cancelled"}:
            raise ValueError(f"unsupported segment outcome: {status}")
        run = await self.session.scalar(select(DurableRuntimeRun).where(DurableRuntimeRun.id == claim.run_id).with_for_update().execution_options(populate_existing=True))
        segment = await self.session.get(DurableRuntimeSegment, claim.segment_id)
        turn = await self.session.get(ChatTurn, run.chat_turn_id)
        now = await self._db_now()
        if context is not None:
            run.context = {"version": DURABLE_CHECKPOINT_VERSION, "action": action, "context": context, "resume": None}
        segment.status = "completed"
        segment.finished_at = now
        segment.lease_until = None
        segment.claim_id = None
        run.status = status
        if status in {"failed", "cancelled"}:
            await self._finalize_plan(run.id, status, f"runtime_{status}")
        else:
            plan = await self.session.scalar(select(RuntimePlan).where(RuntimePlan.root_run_id == run.id).with_for_update())
            if plan is not None:
                plan.status = {
                    "waiting_input": "waiting_input", "waiting_confirmation": "waiting_input",
                    "waiting_timer": "waiting_timer", "completed": "completed",
                }[status]
        if turn is not None:
            turn.status = status
            turn.heartbeat_at = now
            if status in {"waiting_input", "waiting_confirmation", "waiting_timer"}:
                turn.paused_at = now
                turn.pause_status = status
                turn.paused_action = action
                turn.paused_context = context
            elif status in {"completed", "failed", "cancelled"}:
                turn.completed_at = now
                turn.error_message = (public_payload or {}).get("error") if status == "failed" else None
        if status in {"waiting_input", "waiting_confirmation", "waiting_timer"}:
            pause = DurableRuntimePause(
                id=pause_id or uuid.uuid4(), run_id=run.id,
                kind=status, requester={"user_id": str(run.owner_user_id)},
                payload={"version": DURABLE_CHECKPOINT_VERSION, "action": action, "context": context}, wake_at=wake_at,
            )
            self.session.add(pause)
            if public_payload:
                await self._append_event(run, event_key or f"pause:{pause.id}", status, public_payload)
        elif public_payload is not None:
            await self._append_event(run, event_key or f"terminal:{status}", status, public_payload)
        await self.session.flush()
        return run

    async def accept_signal(
        self, run_id: uuid.UUID, *, event_key: str, signal_type: str,
        payload: dict[str, Any], pause_id: uuid.UUID | None = None,
        actor_user_id: uuid.UUID | None = None,
    ) -> DurableRuntimeRun:
        run = await self.session.scalar(select(DurableRuntimeRun).where(DurableRuntimeRun.id == run_id).with_for_update().execution_options(populate_existing=True))
        if run is None:
            raise DurableRuntimeConflict("run does not exist")
        duplicate = await self.session.scalar(select(DurableRuntimeCommand).where(DurableRuntimeCommand.run_id == run_id, DurableRuntimeCommand.event_key == event_key))
        if duplicate is not None:
            if duplicate.kind != signal_type or duplicate.payload != payload or duplicate.actor_user_id != actor_user_id:
                raise DurableRuntimeConflict("event key already used for a different signal")
            return run
        pause = await self.session.scalar(select(DurableRuntimePause).where(DurableRuntimePause.run_id == run_id, DurableRuntimePause.status == "active").with_for_update())
        now = await self._db_now()
        if pause is None or (pause_id is not None and pause.id != pause_id):
            raise DurableRuntimeConflict("there is no matching active pause")
        if actor_user_id is not None and actor_user_id != run.owner_user_id:
            raise DurableRuntimeConflict("only the run owner may answer")
        if signal_type == "timer_elapsed" and (pause.kind != "waiting_timer" or (pause.wake_at and pause.wake_at > now)):
            raise DurableRuntimeConflict("timer is not due")
        self.session.add(DurableRuntimeCommand(run_id=run_id, event_key=event_key, kind=signal_type, actor_user_id=actor_user_id, payload=payload))
        pause.status = "resolved"
        pause.resolved_at = now
        run.context = {**(run.context or {}), "resume": {"pause_id": str(pause.id), "signal_type": signal_type, "payload": payload, "event_key": event_key, "received_at": now.isoformat()}}
        run.status = "queued"
        turn = await self.session.get(ChatTurn, run.chat_turn_id)
        if turn is not None:
            turn.status = "queued"
            turn.pause_status = None
            turn.paused_at = None
            turn.heartbeat_at = now
        max_seq = await self.session.scalar(select(func.max(DurableRuntimeSegment.sequence)).where(DurableRuntimeSegment.run_id == run_id)) or 0
        self.session.add(DurableRuntimeSegment(run_id=run_id, sequence=max_seq + 1, reason=signal_type, pause_id=pause.id, status="queued", available_at=now))
        await self.session.flush()
        return run

    async def accept_due_timers(self, limit: int = 100) -> list[uuid.UUID]:
        """Turn due active timer pauses into queued segments, once per pause."""
        pause_ids = await self.session.scalars(
            select(DurableRuntimePause.id)
            .where(
                DurableRuntimePause.status == "active",
                DurableRuntimePause.kind == "waiting_timer",
                DurableRuntimePause.wake_at <= func.clock_timestamp(),
            )
            .order_by(DurableRuntimePause.wake_at, DurableRuntimePause.created_at)
            .limit(max(1, min(limit, 1000)))
        )
        accepted: list[uuid.UUID] = []
        for pause_id in pause_ids.all():
            pause = await self.session.get(DurableRuntimePause, pause_id)
            if pause is None:
                continue
            try:
                run = await self.accept_signal(
                    pause.run_id,
                    event_key=f"timer:{pause.id}",
                    signal_type="timer_elapsed",
                    payload={},
                    pause_id=pause.id,
                )
            except DurableRuntimeConflict:
                # Another dispatcher or cancellation won after the candidate
                # read; the next sweep will evaluate any remaining due timer.
                continue
            accepted.append(run.id)
        return accepted

    async def cancel(self, run_id: uuid.UUID, *, event_key: str, actor_user_id: uuid.UUID) -> DurableRuntimeRun:
        run = await self.session.scalar(select(DurableRuntimeRun).where(DurableRuntimeRun.id == run_id).with_for_update().execution_options(populate_existing=True))
        if run is None:
            raise DurableRuntimeConflict("run does not exist")
        existing = await self.session.scalar(select(DurableRuntimeCommand).where(DurableRuntimeCommand.run_id == run_id, DurableRuntimeCommand.event_key == event_key))
        if existing is not None:
            if existing.kind != "cancel" or existing.actor_user_id != actor_user_id:
                raise DurableRuntimeConflict("event key already used for a different command")
            return run
        if actor_user_id != run.owner_user_id:
            raise DurableRuntimeConflict("only the run owner may cancel")
        self.session.add(DurableRuntimeCommand(run_id=run_id, event_key=event_key, kind="cancel", actor_user_id=actor_user_id, payload={}))
        if run.status not in {"completed", "failed", "cancelled"}:
            now = await self._db_now()
            run.status = "cancelled"
            await self._finalize_plan(run.id, "cancelled", "user_cancelled")
            for segment in (await self.session.scalars(select(DurableRuntimeSegment).where(DurableRuntimeSegment.run_id == run_id).with_for_update())).all():
                if segment.status in {"queued", "running"}:
                    segment.status = "cancelled"
                    segment.claim_id = None
                    segment.lease_until = None
                    segment.finished_at = now
            for pause in (await self.session.scalars(select(DurableRuntimePause).where(DurableRuntimePause.run_id == run_id, DurableRuntimePause.status == "active").with_for_update())).all():
                pause.status = "resolved"
                pause.resolved_at = now
            turn = await self.session.get(ChatTurn, run.chat_turn_id)
            if turn is not None:
                turn.status = "cancelled"
                turn.completed_at = now
                turn.pause_status = None
            await self._append_event(run, f"cancelled:{event_key}", "cancelled", {"status": "cancelled"})
        await self.session.flush()
        return run

    async def _finalize_plan(self, run_id: uuid.UUID, status: str, reason: str) -> None:
        """Close the graph ledger in the caller's transaction on terminal run state."""
        plan = await self.session.scalar(
            select(RuntimePlan).where(RuntimePlan.root_run_id == run_id).with_for_update()
        )
        if plan is None or plan.status in {"completed", "failed", "cancelled"}:
            return
        await SqlPlanStore(self.session).cancel_plan(plan.id, reason=reason, commit=False)
        if status == "failed":
            plan.status = "failed"
            plan.last_failure = {"code": reason, "message": "Durable runtime execution failed."}

    async def claim_outgoing(self, worker_id: str, limit: int = 20, lease_seconds: int = 60) -> list[DurableRuntimeEvent]:
        events = (await self.session.scalars(
            select(DurableRuntimeEvent).where(
                or_((DurableRuntimeEvent.status == "pending") & (DurableRuntimeEvent.available_at <= func.clock_timestamp()),
                    (DurableRuntimeEvent.status == "sending") & (DurableRuntimeEvent.lease_until <= func.clock_timestamp()))
            ).order_by(DurableRuntimeEvent.created_at).with_for_update(skip_locked=True).limit(limit)
        )).all()
        now = await self._db_now()
        for event in events:
            event.status = "sending"
            event.claim_id = uuid.uuid4()
            event.lease_until = now + timedelta(seconds=lease_seconds)
            event.attempts += 1
        await self.session.flush()
        return list(events)

    async def ack_outgoing(self, event_id: uuid.UUID, claim_id: uuid.UUID | None = None, external_message_id: str | None = None) -> bool:
        event = await self.session.scalar(select(DurableRuntimeEvent).where(DurableRuntimeEvent.id == event_id).with_for_update())
        if event is None:
            return False
        if event.status == "delivered":
            return True
        if claim_id is not None and (event.status != "sending" or event.claim_id != claim_id):
            return False
        event.status = "delivered"
        event.external_message_id = external_message_id
        event.delivered_at = await self._db_now()
        event.lease_until = None
        await self.session.flush()
        return True

    async def pending_assignment_deliveries(self, connector_type: str, connector_id: str, limit: int) -> list[uuid.UUID]:
        delivery = DurableRuntimeRun.recipient["assignment"]["reply_connector"]
        found = await self.session.scalars(
            select(DurableRuntimeRun.id).where(
                delivery["type"].as_string() == connector_type,
                delivery["id"].as_string() == connector_id,
                select(DurableRuntimeEvent.id).where(
                    DurableRuntimeEvent.run_id == DurableRuntimeRun.id,
                    DurableRuntimeEvent.status != "delivered",
                ).exists(),
            ).order_by(DurableRuntimeRun.created_at, DurableRuntimeRun.id).limit(limit),
        )
        return list(found.all())

    async def list_events(self, run_id: uuid.UUID, *, after_sequence: int = 0, actor_user_id: uuid.UUID, limit: int = 100) -> list[DurableRuntimeEvent]:
        run = await self.session.get(DurableRuntimeRun, run_id)
        if run is None or run.owner_user_id != actor_user_id:
            raise DurableRuntimeConflict("run is not available to this user")
        rows = await self.session.scalars(
            select(DurableRuntimeEvent).where(DurableRuntimeEvent.run_id == run_id, DurableRuntimeEvent.sequence > after_sequence)
            .order_by(DurableRuntimeEvent.sequence).limit(max(1, min(limit, 500)))
        )
        return list(rows.all())

    async def _append_event(self, run: DurableRuntimeRun, event_key: str, kind: str, payload: dict[str, Any]) -> DurableRuntimeEvent:
        existing = await self.session.scalar(select(DurableRuntimeEvent).where(DurableRuntimeEvent.run_id == run.id, DurableRuntimeEvent.event_key == event_key))
        if existing is not None:
            return existing
        seq = await self.session.scalar(select(func.max(DurableRuntimeEvent.sequence)).where(DurableRuntimeEvent.run_id == run.id)) or 0
        event = DurableRuntimeEvent(run_id=run.id, sequence=seq + 1, event_key=event_key, kind=kind, payload=payload, recipient=run.recipient)
        self.session.add(event)
        return event
