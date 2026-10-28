"""In-process owner for chat execution, independent of any SSE subscriber.

The runner is intentionally an API-process execution owner for now. A lost SSE
subscriber only stops delivery; an explicit control signal cancels execution.
Moving ownership to Celery is a later reliability step.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from app.core.http.clients import LLMClientProtocol
from app.core.logging import get_logger
from app.repositories.factory import AsyncRepositoryFactory
from app.services.chat_stream_service import ChatStreamService
from app.services.chat_turn_service import CHAT_TURN_HEARTBEAT_SECONDS, ChatTurnService
from app.core.chat_lifecycle import ACTIVE_STATUSES, ChatTurnStatus
from app.services.runtime_tail_event_bus import (
    RuntimeRunControlSubscriber,
    RuntimeTailEventBus,
)

logger = get_logger(__name__)
CHAT_RUN_OWNER_TTL_SECONDS = 2 * 60 * 60


def chat_event_stream_key(run_id: str) -> str:
    return f"chat:{run_id}"


def chat_run_owner_key(run_id: str) -> str:
    return f"chat:run-owner:{run_id}"


def chat_stage_snapshot_key(run_id: str) -> str:
    return f"chat:run-stage:{run_id}"


async def read_chat_stage_snapshot(redis_client: Any, run_id: str) -> dict[str, Any] | None:
    raw = await redis_client.get(chat_stage_snapshot_key(run_id))
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


@dataclass(frozen=True, slots=True)
class ChatRuntimeCommand:
    run_id: uuid.UUID
    chat_id: uuid.UUID
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    content: str
    artifact_ids: list[str]
    idempotency_key: Optional[str] = None
    confirmation_tokens: Optional[list[str]] = None
    continuation_meta: Optional[dict[str, Any]] = None
    resumed_turn_id: Optional[uuid.UUID] = None
    persist_user_message: bool = True


class ChatRuntimeRunner:
    """Own a chat turn task and publish its public events to Redis."""

    def __init__(self) -> None:
        self._tasks: dict[uuid.UUID, asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()
        self._event_bus = RuntimeTailEventBus()

    async def start(
        self,
        *,
        command: ChatRuntimeCommand,
        llm_client: LLMClientProtocol,
        redis_client: Any,
        session_factory: Any,
    ) -> asyncio.Task[None]:
        async with self._lock:
            existing = self._tasks.get(command.run_id)
            if existing is not None and not existing.done():
                return existing

            # Subscribe before starting execution so a Stop request cannot be
            # lost between returning the run id and beginning the pipeline.
            control = RuntimeRunControlSubscriber(
                run_id=str(command.run_id), persist_cancel_marker=True,
            )
            await control.subscribe()
            try:
                await redis_client.set(
                    chat_run_owner_key(str(command.run_id)),
                    json.dumps({
                        "chat_id": str(command.chat_id),
                        "user_id": str(command.user_id),
                    }),
                    ex=CHAT_RUN_OWNER_TTL_SECONDS,
                )
            except Exception:
                await control.unsubscribe()
                raise
            ready = asyncio.Event()
            task = asyncio.create_task(
                self._run(
                    command=command,
                    llm_client=llm_client,
                    redis_client=redis_client,
                    session_factory=session_factory,
                    control=control,
                    ready=ready,
                ),
                name=f"chat-runtime:{command.run_id}",
            )
            self._tasks[command.run_id] = task

            def clear_finished(finished: asyncio.Task[None]) -> None:
                if self._tasks.get(command.run_id) is finished:
                    self._tasks.pop(command.run_id, None)

            task.add_done_callback(clear_finished)
        ready_wait = asyncio.create_task(ready.wait())
        await asyncio.wait({task, ready_wait}, return_when=asyncio.FIRST_COMPLETED)
        if not ready_wait.done():
            ready_wait.cancel()
            await asyncio.gather(ready_wait, return_exceptions=True)
        else:
            await ready_wait
        if task.done():
            await task
        return task

    async def _run(
        self,
        *,
        command: ChatRuntimeCommand,
        llm_client: LLMClientProtocol,
        redis_client: Any,
        session_factory: Any,
        control: RuntimeRunControlSubscriber,
        ready: asyncio.Event,
    ) -> None:
        async def execute() -> None:
            async with session_factory() as session:
                repositories = AsyncRepositoryFactory(
                    session, command.tenant_id, command.user_id,
                )
                service = ChatStreamService(
                    session=session,
                    redis=redis_client,
                    llm_client=llm_client,
                    chats_repo=repositories.get_chats_repository(),
                    messages_repo=repositories.get_chat_messages_repository(),
                )
                async for event in service.send_message_stream(
                    chat_id=str(command.chat_id),
                    user_id=str(command.user_id),
                    tenant_id=str(command.tenant_id),
                    content=command.content,
                    artifact_ids=command.artifact_ids,
                    confirmation_tokens=command.confirmation_tokens,
                    idempotency_key=command.idempotency_key,
                    continuation_meta=command.continuation_meta,
                    resumed_turn_id=str(command.resumed_turn_id) if command.resumed_turn_id else None,
                    persist_user_message=command.persist_user_message,
                    runtime_run_id=str(command.run_id),
                    cancellation_reason="Cancelled by user",
                ):
                    event = self._normalize_service_event(event, command.run_id)
                    if event.get("type") in {"user_message", "cached", "error", "state"} or (
                        event.get("type") == "stage"
                        and isinstance(event.get("activity"), dict)
                        and event["activity"].get("stage") in {"preparing", "planning"}
                    ):
                        ready.set()
                    if event.get("type") == "stage":
                        activity = event.get("activity")
                        if isinstance(activity, dict):
                            try:
                                activity.setdefault("updated_at", datetime.now(timezone.utc).isoformat())
                                await redis_client.set(
                                    chat_stage_snapshot_key(str(command.run_id)),
                                    json.dumps(activity, ensure_ascii=False),
                                    ex=CHAT_RUN_OWNER_TTL_SECONDS,
                                )
                            except Exception:
                                logger.warning("chat_runtime_stage_snapshot_failed run_id=%s", command.run_id, exc_info=True)
                    if event.get("type") == "state":
                        event.setdefault("run_id", str(command.run_id))
                        activity = await read_chat_stage_snapshot(redis_client, str(command.run_id))
                        if activity:
                            event.setdefault("stage", activity.get("stage"))
                    await self._event_bus.publish(
                        stream_key=chat_event_stream_key(str(command.run_id)),
                        payload={"type": "service_event", "event": event},
                    )

        execution = asyncio.create_task(execute(), name=f"chat-turn:{command.run_id}")
        cancel_wait = asyncio.create_task(control.wait_for_cancel())
        heartbeat_task = asyncio.create_task(
            self._heartbeat(command.run_id, session_factory),
            name=f"chat-turn-heartbeat:{command.run_id}",
        )
        cancelled = False
        try:
            done, _ = await asyncio.wait(
                {execution, cancel_wait}, return_when=asyncio.FIRST_COMPLETED,
            )
            if cancel_wait in done and not execution.done():
                cancelled = True
                execution.cancel()
                await asyncio.gather(execution, return_exceptions=True)
            else:
                await execution
        except asyncio.CancelledError:
            cancelled = True
            execution.cancel()
            await asyncio.gather(execution, return_exceptions=True)
            raise
        except Exception:
            logger.exception("chat_runtime_runner_failed run_id=%s", command.run_id)
            await self._fail_turn(command, session_factory)
            await self._publish(command.run_id, {
                "type": "service_event", "event": {
                    "type": "state", "run_id": str(command.run_id),
                    "status": ChatTurnStatus.FAILED.value,
                },
            })
            await self._publish(
                command.run_id,
                {"type": "service_event", "event": {
                    "type": "error", "code": "chat_runtime_failed",
                    "error": "Не удалось обработать запрос. Попробуйте позже.",
                }},
            )
        finally:
            ready.set()
            if not cancel_wait.done():
                cancel_wait.cancel()
                await asyncio.gather(cancel_wait, return_exceptions=True)
            if not heartbeat_task.done():
                heartbeat_task.cancel()
            await asyncio.gather(heartbeat_task, return_exceptions=True)
            await control.unsubscribe()
            # The nested orchestrator persists cancellation when the explicit
            # control signal cancels its generator. Keep this fallback for a
            # cancellation during setup, before that handler owns the turn.
            if cancelled:
                await self._cancel_turn_if_active(command, session_factory)
                await self._publish(command.run_id, {
                    "type": "service_event", "event": {
                        "type": "state", "run_id": str(command.run_id),
                        "status": ChatTurnStatus.CANCELLED.value,
                    },
                })
                await self._publish(command.run_id, {
                    "type": "service_event",
                    "event": {"type": "cancelled", "run_id": str(command.run_id)},
                })
            await self._publish(command.run_id, {"type": "done"})
            try:
                await redis_client.delete(chat_run_owner_key(str(command.run_id)))
                await redis_client.delete(chat_stage_snapshot_key(str(command.run_id)))
            except Exception:
                logger.warning("chat_runtime_owner_key_delete_failed run_id=%s", command.run_id, exc_info=True)

    async def _publish(self, run_id: uuid.UUID, payload: dict[str, Any]) -> None:
        try:
            await self._event_bus.publish(
                stream_key=chat_event_stream_key(str(run_id)), payload=payload,
            )
        except Exception:
            logger.warning("chat_runtime_event_publish_failed run_id=%s", run_id, exc_info=True)

    @staticmethod
    async def _fail_turn(command: ChatRuntimeCommand, session_factory: Any) -> None:
        try:
            async with session_factory() as session:
                turns = ChatTurnService(session)
                turn = await turns.get_by_runtime_run_id(command.run_id)
                if turn is not None and turn.status in ACTIVE_STATUSES:
                    await turns.fail_turn(turn.id, error_message="chat_runtime_failed")
                    await session.commit()
        except Exception:
            logger.exception("chat_runtime_failure_persist_failed run_id=%s", command.run_id)

    @staticmethod
    async def _heartbeat(run_id: uuid.UUID, session_factory: Any) -> None:
        while True:
            await asyncio.sleep(CHAT_TURN_HEARTBEAT_SECONDS)
            try:
                async with session_factory() as session:
                    turns = ChatTurnService(session)
                    active = await turns.heartbeat_turn(run_id)
                    if active is False:
                        return
                    if active is True:
                        await session.commit()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("chat_runtime_heartbeat_failed run_id=%s", run_id, exc_info=True)

    @staticmethod
    def _normalize_service_event(event: dict[str, Any], run_id: uuid.UUID) -> dict[str, Any]:
        if event.get("type") == "status":
            legacy_stage = event.get("stage")
            stage_map = {
                "saving_user_message": ("preparing", "Сохраняю сообщение"),
                "loading_context": ("preparing", "Загружаю контекст"),
                "agent_running": ("planning", "Определяю способ выполнения"),
            }
            mapped = stage_map.get(str(legacy_stage))
            if mapped:
                stage, description = mapped
                return {"type": "stage", "activity": {
                    "run_id": str(run_id), "stage": stage,
                    "action": str(legacy_stage), "description": description,
                }}
            return event
        if event.get("type") == "final":
            event = dict(event)
            event["status"] = (
                ChatTurnStatus.FAILED.value
                if event.get("stop_reason") == "failed"
                else ChatTurnStatus.COMPLETED.value
            )
        return event

    @staticmethod
    async def _cancel_turn_if_active(command: ChatRuntimeCommand, session_factory: Any) -> None:
        try:
            async with session_factory() as session:
                turns = ChatTurnService(session)
                turn = await turns.get_by_runtime_run_id(command.run_id)
                if turn is not None and turn.status in ACTIVE_STATUSES:
                    await turns.cancel_turn(turn.id, error_message="Cancelled by user")
                    await session.commit()
        except Exception:
            logger.exception("chat_runtime_cancel_persist_failed run_id=%s", command.run_id)


chat_runtime_runner = ChatRuntimeRunner()
