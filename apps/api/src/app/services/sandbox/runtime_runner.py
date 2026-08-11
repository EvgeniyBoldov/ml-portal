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
                                paused_payload = RuntimeHitlProtocolService.build_paused_from_stop(dict(event.data or {}))
                                final_status = str(paused_payload["reason"])
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
                                if not final_status.startswith("waiting_"):
                                    final_status = "completed"
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
            try:
                await self._emit_error(command=command, session_factory=session_factory, exc=exc)
            except Exception:  # noqa: BLE001
                logger.exception("sandbox_runtime_error_journal_failed run_id=%s", command.run_id)
        finally:
            await control.unsubscribe()
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
                await terminal_db.commit()
        except Exception:  # noqa: BLE001
            logger.exception("sandbox_runtime_terminal_persist_failed run_id=%s", command.run_id)
            return

        if status in {"cancelled", "failed"}:
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
