"""In-process owner for chat execution, independent of any SSE subscriber.

The runner is intentionally an API-process execution owner for now. A lost SSE
subscriber only stops delivery; an explicit control signal cancels execution.
Moving ownership to Celery is a later reliability step.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
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
CHAT_EVENT_REDIS_TIMEOUT_SECONDS = 2.0
CHAT_RESUME_HANDOFF_TIMEOUT_SECONDS = 2.0


def chat_event_stream_key(run_id: str) -> str:
    return f"chat:{run_id}"


def chat_run_owner_key(run_id: str) -> str:
    return f"chat:run-owner:{run_id}"


def chat_stage_snapshot_key(run_id: str) -> str:
    return f"chat:run-stage:{run_id}"


async def read_chat_stage_snapshot(redis_client: Any, run_id: str) -> dict[str, Any] | None:
    try:
        async with asyncio.timeout(CHAT_EVENT_REDIS_TIMEOUT_SECONDS):
            raw = await redis_client.get(chat_stage_snapshot_key(run_id))
    except Exception:
        logger.warning("chat_runtime_stage_snapshot_read_failed run_id=%s", run_id, exc_info=True)
        return None
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
    execution_id: uuid.UUID = field(default_factory=uuid.uuid4)


class ChatRunConflictError(Exception):
    """The run id is already reserved by an execution."""


def _owner_record(command: ChatRuntimeCommand) -> str:
    return json.dumps({
        "chat_id": str(command.chat_id),
        "user_id": str(command.user_id),
        "execution_id": str(command.execution_id),
    })


async def claim_chat_run(redis_client: Any, command: ChatRuntimeCommand) -> None:
    if not await redis_client.set(
        chat_run_owner_key(str(command.run_id)), _owner_record(command),
        ex=CHAT_RUN_OWNER_TTL_SECONDS, nx=True,
    ):
        raise ChatRunConflictError("Run ID is already in use")


async def release_chat_run(redis_client: Any, command: ChatRuntimeCommand) -> None:
    try:
        await redis_client.eval(
            """
            if redis.call('get', KEYS[1]) == ARGV[1] then
                return redis.call('del', KEYS[1], KEYS[2])
            end
            return 0
            """,
            2, chat_run_owner_key(str(command.run_id)),
            chat_stage_snapshot_key(str(command.run_id)), _owner_record(command),
        )
    except Exception:
        logger.warning("chat_runtime_owner_release_failed run_id=%s", command.run_id, exc_info=True)


class ChatRuntimeRunner:
    """Own a chat turn task and publish its public events to Redis."""

    def __init__(self) -> None:
        self._tasks: dict[uuid.UUID, asyncio.Task[None]] = {}
        self._event_bus: RuntimeTailEventBus | None = None

    def is_running(self, run_id: uuid.UUID) -> bool:
        task = self._tasks.get(run_id)
        return task is not None and not task.done()

    async def start(
        self,
        *,
        command: ChatRuntimeCommand,
        llm_client: LLMClientProtocol,
        redis_client: Any,
        session_factory: Any,
        already_claimed: bool = False,
    ) -> asyncio.Task[None]:
        existing = self._tasks.get(command.run_id)
        while existing is not None and not existing.done():
            if command.resumed_turn_id is None:
                raise ChatRunConflictError("Run ID is already in use")
            await asyncio.gather(asyncio.shield(existing), return_exceptions=True)
            existing = self._tasks.get(command.run_id)

        ready = asyncio.Event()

        async def run_owned() -> None:
            if not already_claimed:
                deadline = asyncio.get_running_loop().time() + CHAT_RESUME_HANDOFF_TIMEOUT_SECONDS
                while True:
                    try:
                        await claim_chat_run(redis_client, command)
                        break
                    except ChatRunConflictError:
                        if command.resumed_turn_id is None or asyncio.get_running_loop().time() >= deadline:
                            raise
                        raw = await redis_client.get(chat_run_owner_key(str(command.run_id)))
                        if raw:
                            owner = json.loads(raw)
                            if (not isinstance(owner, dict) or owner.get("chat_id") != str(command.chat_id)
                                    or owner.get("user_id") != str(command.user_id)):
                                raise
                        await asyncio.sleep(0.05)
            control = RuntimeRunControlSubscriber(
                run_id=str(command.run_id), persist_cancel_marker=True,
            )
            try:
                await control.subscribe()
            except BaseException:
                import anyio
                with anyio.CancelScope(shield=True):
                    try:
                        await control.unsubscribe()
                    except Exception:
                        logger.warning("chat_runtime_control_setup_cleanup_failed run_id=%s",
                                       command.run_id, exc_info=True)
                    await release_chat_run(redis_client, command)
                raise
            if already_claimed:
                ready.set()
            await self._run(
                command=command, llm_client=llm_client, redis_client=redis_client,
                session_factory=session_factory, control=control, ready=ready,
            )

        # The local registry check and insertion contain no await.
        task = asyncio.create_task(run_owned(), name=f"chat-runtime:{command.run_id}")
        self._tasks[command.run_id] = task

        def clear_finished(finished: asyncio.Task[None]) -> None:
            if self._tasks.get(command.run_id) is finished:
                self._tasks.pop(command.run_id, None)
            if not finished.cancelled():
                finished.exception()

        task.add_done_callback(clear_finished)
        ready_wait = asyncio.create_task(ready.wait())
        try:
            await asyncio.wait({task, ready_wait}, return_when=asyncio.FIRST_COMPLETED)
            if task.done():
                await task
        finally:
            ready_wait.cancel()
            await asyncio.gather(ready_wait, return_exceptions=True)
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
        terminal_result_produced = False

        bus = self._event_bus or RuntimeTailEventBus(redis_client=redis_client)

        async def publish(payload: dict[str, Any]) -> None:
            try:
                async with asyncio.timeout(CHAT_EVENT_REDIS_TIMEOUT_SECONDS):
                    await bus.publish(
                        stream_key=chat_event_stream_key(str(command.run_id)),
                        payload={**payload, "execution_id": str(command.execution_id)},
                    )
            except Exception:
                logger.warning("chat_runtime_event_publish_failed run_id=%s", command.run_id, exc_info=True)

        async def execute() -> None:
            nonlocal terminal_result_produced
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
                    if event.get("type") in {"final", "cached", "stop", "run_paused"} or (
                        event.get("type") == "state"
                        and event.get("status") in {
                            ChatTurnStatus.COMPLETED.value,
                            ChatTurnStatus.FAILED.value,
                            ChatTurnStatus.CANCELLED.value,
                            ChatTurnStatus.WAITING_INPUT.value,
                            ChatTurnStatus.WAITING_CONFIRMATION.value,
                        }
                    ):
                        terminal_result_produced = True
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
                                async with asyncio.timeout(CHAT_EVENT_REDIS_TIMEOUT_SECONDS):
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
                    await publish({"type": "service_event", "event": event})

        execution = asyncio.create_task(execute(), name=f"chat-turn:{command.run_id}")
        cancel_wait = asyncio.create_task(control.wait_for_cancel())
        heartbeat_task = asyncio.create_task(
            self._heartbeat(command.run_id, session_factory),
            name=f"chat-turn-heartbeat:{command.run_id}",
        )
        cancelled = False
        control_failed = False
        try:
            done, _ = await asyncio.wait(
                {execution, cancel_wait}, return_when=asyncio.FIRST_COMPLETED,
            )
            if cancel_wait in done:
                try:
                    cancel_wait.result()
                except asyncio.CancelledError as exc:
                    if execution.done() or terminal_result_produced:
                        await execution
                    else:
                        control_failed = True
                        execution.cancel("chat_runtime_control_failure")
                        await asyncio.gather(execution, return_exceptions=True)
                        raise RuntimeError("Chat run control waiter was cancelled unexpectedly") from exc
                except Exception as exc:
                    if execution.done() or terminal_result_produced:
                        logger.warning(
                            "chat_runtime_control_failed_after_terminal run_id=%s", command.run_id, exc_info=True,
                        )
                        await execution
                    else:
                        control_failed = True
                        execution.cancel("chat_runtime_control_failure")
                        await asyncio.gather(execution, return_exceptions=True)
                        raise RuntimeError("Chat run control channel failed") from exc
                if execution.done() or terminal_result_produced:
                    await execution
                else:
                    cancelled = True
                    execution.cancel()
                    await asyncio.gather(execution, return_exceptions=True)
            else:
                await execution
        except asyncio.CancelledError:
            cancelled = not terminal_result_produced
            execution.cancel()
            await asyncio.gather(execution, return_exceptions=True)
            raise
        except Exception:
            if terminal_result_produced:
                logger.warning("chat_runtime_terminal_tail_failed run_id=%s", command.run_id, exc_info=True)
                if not execution.done():
                    execution.cancel("chat_runtime_post_terminal_failure")
                    await asyncio.gather(execution, return_exceptions=True)
            else:
                logger.exception("chat_runtime_runner_failed run_id=%s", command.run_id)
                if not execution.done():
                    execution.cancel("chat_runtime_control_failure" if control_failed else "chat_runtime_owner_failure")
                    await asyncio.gather(execution, return_exceptions=True)
                await self._fail_turn(
                    command, session_factory, allow_cancelled=control_failed,
                )
                await publish({
                    "type": "service_event", "event": {
                        "type": "state", "run_id": str(command.run_id),
                        "status": ChatTurnStatus.FAILED.value,
                    },
                })
                await publish(
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
            try:
                await control.unsubscribe()
            except Exception:
                # Control-channel cleanup is best-effort; it must not prevent
                # persistence and terminal delivery for the owned chat turn.
                logger.warning("chat_runtime_control_unsubscribe_failed run_id=%s", command.run_id, exc_info=True)
            # The nested orchestrator persists cancellation when the explicit
            # control signal cancels its generator. Keep this fallback for a
            # cancellation during setup, before that handler owns the turn.
            if cancelled:
                await self._cancel_turn_if_active(command, session_factory)
                await publish({
                    "type": "service_event", "event": {
                        "type": "state", "run_id": str(command.run_id),
                        "status": ChatTurnStatus.CANCELLED.value,
                    },
                })
                await publish({
                    "type": "service_event",
                    "event": {"type": "cancelled", "run_id": str(command.run_id)},
                })
            await release_chat_run(redis_client, command)
            await publish({"type": "done"})

    @staticmethod
    async def _fail_turn(
        command: ChatRuntimeCommand,
        session_factory: Any,
        *,
        allow_cancelled: bool = False,
    ) -> None:
        try:
            async with session_factory() as session:
                turns = ChatTurnService(session)
                turn = await turns.get_by_runtime_run_id(command.run_id)
                if turn is not None and (
                    turn.status in ACTIVE_STATUSES
                    or (allow_cancelled and turn.status == ChatTurnStatus.CANCELLED.value)
                ):
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
