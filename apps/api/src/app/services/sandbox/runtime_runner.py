"""In-process owner for sandbox runtime execution.

The HTTP/SSE response observes a run; it must never own or cancel it.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Optional
from uuid import UUID

from app.agents.context import ToolContext
from app.core.http.clients import LLMClientProtocol
from app.core.logging import get_logger
from app.runtime import OrchestrationPhase, PipelineRequest, RuntimeEvent, RuntimeEventType, RuntimePipeline
from app.services.runtime_event_logger import RuntimeEventJournalFactory, RuntimeLogContext, RuntimeLoggingLevel
from app.services.runtime_terminal_status import planner_terminal_from_event
from app.services.runtime_tail_event_bus import RuntimeRunControlSubscriber, RuntimeTailEventBus
from app.services.sandbox_service import SandboxService
from app.services.runtime_hitl_protocol_service import RuntimeHitlProtocolService
from app.services.chat_context_service import ChatContextService
from app.services.chat_turn_service import CHAT_TURN_HEARTBEAT_SECONDS, ChatTurnService

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class SandboxRuntimeCommand:
    run_id: UUID
    user_id: UUID
    tenant_id: UUID
    pipeline_request: PipelineRequest
    tool_context: ToolContext


class SandboxRuntimeRunner:
    """Runs a sandbox pipeline independently of a particular HTTP connection."""

    def __init__(self) -> None:
        self._tasks: dict[UUID, asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()

    async def start(
        self,
        *,
        command: SandboxRuntimeCommand,
        llm_client: LLMClientProtocol,
        session_factory: Any,
    ) -> asyncio.Task[None]:
        async with self._lock:
            existing = self._tasks.get(command.run_id)
            if existing is not None and not existing.done():
                return existing
            task = asyncio.create_task(
                self._run(command=command, llm_client=llm_client, session_factory=session_factory),
                name=f"sandbox-runtime:{command.run_id}",
            )
            self._tasks[command.run_id] = task

            def clear_finished(finished: asyncio.Task[None]) -> None:
                if self._tasks.get(command.run_id) is finished:
                    self._tasks.pop(command.run_id, None)

            task.add_done_callback(clear_finished)
            return task

    async def cancel_local(self, run_id: UUID) -> bool:
        """Interrupt the local owner promptly; Redis covers other API processes."""
        async with self._lock:
            task = self._tasks.get(run_id)
            if task is None or task.done():
                return False
            task.cancel()
            return True

    async def _run(
        self,
        *,
        command: SandboxRuntimeCommand,
        llm_client: LLMClientProtocol,
        session_factory: Any,
    ) -> None:
        final_status = "completed"
        final_error: Optional[str] = None
        paused_payload: Optional[dict[str, Any]] = None
        cancelled = False
        control = RuntimeRunControlSubscriber(run_id=str(command.run_id))
        heartbeat_task = asyncio.create_task(
            self._heartbeat(command.run_id, session_factory),
            name=f"sandbox-chat-turn-heartbeat:{command.run_id}",
        )

        try:
            await control.subscribe()
            async with session_factory() as execution_db:
                run = await SandboxService(execution_db).get_run(command.run_id)
                if run is None:
                    return
                if run.status == "cancelling":
                    cancelled = True
                else:
                    pipeline = RuntimePipeline(session=execution_db, llm_client=llm_client)
                    iterator = pipeline.execute(command.pipeline_request, command.tool_context).__aiter__()
                    next_event = asyncio.create_task(anext(iterator))
                    cancel_signal = asyncio.create_task(control.wait_for_cancel())
                    try:
                        while next_event is not None:
                            done, _ = await asyncio.wait(
                                {next_event, cancel_signal},
                                return_when=asyncio.FIRST_COMPLETED,
                            )
                            if cancel_signal in done:
                                cancelled = True
                                next_event.cancel()
                                await asyncio.gather(next_event, return_exceptions=True)
                                break
                            try:
                                event = next_event.result()
                            except StopAsyncIteration:
                                break

                            if event.type == RuntimeEventType.STOP:
                                terminal = self._terminal_state_for_event(event)
                                if terminal is not None:
                                    final_status, final_error, paused_payload = terminal
                                    if paused_payload is not None:
                                        await RuntimeTailEventBus().publish(
                                            stream_key=str(command.run_id),
                                            payload={"type": "pause", "run_id": str(command.run_id), **paused_payload},
                                        )
                            elif event.type == RuntimeEventType.DELTA:
                                content = str(event.data.get("content") or "")
                                if content:
                                    await RuntimeTailEventBus().publish(
                                        stream_key=str(command.run_id),
                                        payload={"type": "delta", "run_id": str(command.run_id), "content": content},
                                    )
                            elif event.type == RuntimeEventType.FINAL:
                                terminal = self._terminal_state_for_event(event)
                                if terminal is not None:
                                    final_status, final_error, paused_payload = terminal
                                if final_status == "completed":
                                    await RuntimeTailEventBus().publish(
                                        stream_key=str(command.run_id),
                                        payload={
                                            "type": "final",
                                            "run_id": str(command.run_id),
                                            "content": str(event.data.get("content") or ""),
                                            "sources": event.data.get("sources") or [],
                                            "attachments": event.data.get("attachments") or [],
                                        },
                                    )
                            else:
                                terminal = planner_terminal_from_event(event)
                                if terminal is not None:
                                    final_status = terminal[0].value
                                    final_error = terminal[1]
                                    paused_payload = None
                            if await self._is_cancelling(execution_db, command.run_id):
                                cancelled = True
                                break
                            next_event = asyncio.create_task(anext(iterator))
                    finally:
                        if next_event is not None and not next_event.done():
                            next_event.cancel()
                            await asyncio.gather(next_event, return_exceptions=True)
                        if not cancel_signal.done():
                            cancel_signal.cancel()
                            await asyncio.gather(cancel_signal, return_exceptions=True)
                    if not cancelled:
                        await execution_db.commit()
        except asyncio.CancelledError:
            cancelled = True
        except Exception as exc:  # noqa: BLE001
            logger.exception("sandbox_runtime_runner_failed run_id=%s", command.run_id)
            final_status = "failed"
            final_error = "Sandbox runtime execution failed"
            # A pause is provisional until the runner reaches its normal
            # terminal write. Any later exception fails that same turn.
            paused_payload = None
            try:
                await self._emit_error(command=command, session_factory=session_factory, exc=exc)
            except Exception:  # noqa: BLE001
                logger.exception("sandbox_runtime_error_journal_failed run_id=%s", command.run_id)
        finally:
            if not heartbeat_task.done():
                heartbeat_task.cancel()
            await asyncio.gather(heartbeat_task, return_exceptions=True)
            # Closing the pub/sub connection is best-effort cleanup. It must
            # never prevent the durable run/chat-turn terminal write below.
            try:
                await control.unsubscribe()
            except Exception:  # noqa: BLE001
                logger.exception("sandbox_runtime_control_unsubscribe_failed run_id=%s", command.run_id)
            if cancelled:
                final_status = "cancelled"
                final_error = "Cancelled by user"
                paused_payload = None
            await self._persist_terminal(
                command=command,
                session_factory=session_factory,
                status=final_status,
                error=final_error,
                paused_payload=paused_payload,
            )

    @staticmethod
    async def _heartbeat(run_id: UUID, session_factory: Any) -> None:
        """Keep the companion turn lease fresh while sandbox owns execution."""
        while True:
            await asyncio.sleep(CHAT_TURN_HEARTBEAT_SECONDS)
            try:
                async with session_factory() as session:
                    active = await ChatTurnService(session).heartbeat_turn(run_id)
                    if active is False:
                        return
                    if active is True:
                        await session.commit()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                logger.warning("sandbox_chat_turn_heartbeat_failed run_id=%s", run_id, exc_info=True)

    @staticmethod
    def _terminal_state_for_event(
        event: RuntimeEvent,
    ) -> Optional[tuple[str, Optional[str], Optional[dict[str, Any]]]]:
        """Map only HITL STOP events to a waiting turn; terminal STOPs close it."""
        if event.type == RuntimeEventType.STOP:
            paused_payload = RuntimeHitlProtocolService.build_paused_from_stop(dict(event.data or {}))
            if paused_payload["reason"] in {"waiting_input", "waiting_confirmation"}:
                return str(paused_payload["reason"]), None, paused_payload
            if paused_payload["reason"] != "completed":
                message = str((event.data or {}).get("message") or paused_payload["reason"])
                return "failed", message, None
        elif event.type == RuntimeEventType.FINAL:
            stop_reason = str((event.data or {}).get("stop_reason") or "").strip()
            if stop_reason and stop_reason not in {"completed", "failed"}:
                return "failed", stop_reason, None

        terminal = planner_terminal_from_event(event)
        if terminal is None:
            return None
        if terminal[0].value == "stopped":
            return "failed", terminal[1] or "Sandbox runtime stopped", None
        return terminal[0].value, terminal[1], None

    @staticmethod
    async def _is_cancelling(session: Any, run_id: UUID) -> bool:
        run = await SandboxService(session).get_run(run_id)
        return run is not None and run.status == "cancelling"

    async def _persist_terminal(
        self,
        *,
        command: SandboxRuntimeCommand,
        session_factory: Any,
        status: str,
        error: Optional[str],
        paused_payload: Optional[dict[str, Any]],
    ) -> None:
        """Persist with a fresh session: a cancelled execution session is unsafe."""
        try:
            async with session_factory() as terminal_db:
                service = SandboxService(terminal_db)
                if paused_payload is not None:
                    await service.pause_run(
                        run_id=command.run_id,
                        status=str(paused_payload["reason"]),
                        paused_action=paused_payload["action"],
                        paused_context=paused_payload["context"],
                    )
                else:
                    await service.finish_run(command.run_id, status, error)
                await self._persist_chat_turn_terminal(
                    terminal_db=terminal_db, command=command, status=status,
                    error=error, paused_payload=paused_payload,
                )
                await terminal_db.commit()
        except Exception:  # noqa: BLE001
            logger.exception("sandbox_runtime_terminal_persist_failed run_id=%s", command.run_id)
            return

        # Pipeline journals its terminal event before yielding it, including
        # cancellation/error paths that never yield RUN_END to this runner.
        root_logger = getattr(command.tool_context, "extra", {}).get("runtime_root_event_logger")
        pipeline_status = getattr(root_logger, "run_terminal_status", None)
        if status in {"cancelled", "failed"} and pipeline_status != status:
            terminal_logger = RuntimeEventJournalFactory.create(
                context=RuntimeLogContext(
                    run_id=command.run_id,
                    level=RuntimeLoggingLevel.FULL,
                    origin="sandbox",
                    tenant_id=command.tenant_id,
                    user_id=command.user_id,
                    stream_logs=True,
                    stream_progress=True,
                ),
                session_factory=session_factory,
            )
            await terminal_logger.emit(
                RuntimeEvent.run_end(run_id=str(command.run_id), status=status),
                phase=OrchestrationPhase.PIPELINE,
            )

    @staticmethod
    async def _persist_chat_turn_terminal(
        *, terminal_db: Any, command: SandboxRuntimeCommand, status: str,
        error: Optional[str], paused_payload: Optional[dict[str, Any]],
    ) -> None:
        """Keep the hidden sandbox chat turn in the same lifecycle state.

        The sandbox run is the execution owner, but chat-context provenance
        requires its companion turn to be a real lifecycle record as well.
        """
        turn_id = command.pipeline_request.chat_turn_id
        if not turn_id:
            return
        turns = ChatTurnService(terminal_db)
        if paused_payload is not None:
            await turns.pause_turn(
                turn_id, pause_status=str(paused_payload["reason"]),
                runtime_run_id=command.run_id,
                paused_action=paused_payload["action"], paused_context=paused_payload["context"],
            )
            return
        if status == "completed":
            await turns.complete_turn(turn_id)
            return
        if status == "cancelled":
            turn = await turns.cancel_turn(turn_id, error_message=error or "Cancelled by user")
            branch_id = (command.pipeline_request.sandbox_overrides or {}).get("sandbox_branch_id")
            if turn is not None and branch_id:
                await ChatContextService(terminal_db, None, None).cancel_turn_context(
                    chat_id=str(turn.chat_id), chat_turn_id=str(turn.id), branch_id=str(branch_id),
                )
            return
        await turns.fail_turn(turn_id, error_message=error or "Sandbox runtime failed")

    async def _emit_error(self, *, command: SandboxRuntimeCommand, session_factory: Any, exc: Exception) -> None:
        error_logger = RuntimeEventJournalFactory.create(
            context=RuntimeLogContext(
                run_id=command.run_id,
                level=RuntimeLoggingLevel.FULL,
                origin="sandbox",
                tenant_id=command.tenant_id,
                user_id=command.user_id,
                stream_logs=True,
                stream_progress=True,
            ),
            session_factory=session_factory,
        )
        await error_logger.error(exc, payload={"stage": "sandbox_runtime_runner"})


sandbox_runtime_runner = SandboxRuntimeRunner()
