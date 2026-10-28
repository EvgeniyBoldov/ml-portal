from __future__ import annotations

import asyncio
from typing import Any, AsyncGenerator, Dict, Optional
import uuid

from app.agents import ToolContext
from app.core.logging import get_logger
from app.core.config import get_settings
from app.services.chat_context_service import ChatContextService
from app.services.chat_context_contracts import ChatContextSnapshot
from app.services.chat_persistence_service import ChatPersistenceService
from app.services.chat_turn_service import ChatTurnService
from app.services.chat_turn_state import ChatTurnState, TurnPhase
from app.services.runtime_hitl_protocol_service import RuntimeHitlProtocolService

logger = get_logger(__name__)

class ChatTurnOrchestrator:
    """Orchestrates a single chat turn while preserving current chat contract."""

    def __init__(
        self,
        *,
        context_service: ChatContextService,
        persistence_service: ChatPersistenceService,
        turn_service: ChatTurnService,
    ) -> None:
        self.context_service = context_service
        self.persistence_service = persistence_service
        self.turn_service = turn_service

    async def execute_turn(
        self,
        *,
        chat,
        chat_id: str,
        user_id: str,
        tenant_id: Optional[str] = None,
        content: str,
        artifact_ids: list[str],
        confirmation_tokens: Optional[list[str]] = None,
        attachment_meta: list[dict[str, Any]],
        attachment_contexts: list[dict[str, Any]],
        idempotency_key: Optional[str],
        continuation_meta: Optional[Dict[str, Any]],
        persist_user_message: bool,
        run_with_router,
        store_idempotency,
        bind_attachments,
        preloaded_context: Optional[list[dict[str, Any]]] = None,
        preloaded_context_snapshot: Optional[ChatContextSnapshot] = None,
        resumed_turn_id: Optional[str] = None,
        requested_runtime_run_id: Optional[str] = None,
        cancellation_reason: str = "Client disconnected",
    ) -> AsyncGenerator[Dict[str, Any], None]:
        turn = ChatTurnState(chat_id=chat_id, request_id=idempotency_key)
        continuation_run_id = (continuation_meta or {}).get("resumed_from_run_id")
        try:
            supplied_run_id = requested_runtime_run_id or continuation_run_id
            runtime_run_id = str(uuid.UUID(str(supplied_run_id))) if supplied_run_id else str(uuid.uuid4())
        except (TypeError, ValueError):
            runtime_run_id = str(uuid.uuid4())
        hash_payload = content if not artifact_ids else f"{content}||artifacts:{','.join(sorted(artifact_ids))}"
        if resumed_turn_id:
            # A clarification/confirmation is the continuation of the same
            # logical chat turn.  The router has atomically moved this row
            # from paused to resumed before opening the stream; do not create
            # a second row for the same root runtime run.
            turn_id = uuid.UUID(str(resumed_turn_id))
        else:
            persisted_turn = await self.turn_service.start_turn(
                chat_id=chat_id,
                user_id=user_id,
                idempotency_key=idempotency_key,
                request_hash=self.turn_service.build_request_hash(hash_payload),
                runtime_run_id=runtime_run_id,
            )
            turn_id = persisted_turn.id  # cache scalar to survive ORM expiry

        user_message_id: Optional[str] = None
        try:
            if persist_user_message:
                yield {"type": "stage", "activity": {
                    "run_id": runtime_run_id, "stage": "preparing",
                    "action": "saving_user_message", "description": "Сохраняю сообщение",
                }}
                user_meta = {"attachments": attachment_meta} if attachment_meta else None
                user_message = await self.persistence_service.create_user_message(
                    chat_id=chat_id,
                    content=content,
                    meta=user_meta,
                )
                user_message_id = user_message.message_id  # cache scalar to survive ORM expiry
                user_message_created_at = user_message.created_at
                if artifact_ids:
                    await bind_attachments(
                        chat_id=chat_id,
                        owner_id=user_id,
                        artifact_ids=artifact_ids,
                        message_id=user_message_id,
                    )
                if not resumed_turn_id:
                    await self.turn_service.attach_user_message(turn_id, user_message_id)
                else:
                    # Claim the paused turn only once the SSE consumer has
                    # actually started execution, in the same transaction as
                    # persisting the resume input.
                    await self.turn_service.resume_turn(turn_id)
                # Persist the request/turn before a potentially long stream. The
                # terminal assistant, turn status and deterministic context share
                # a later transaction boundary.
                await self.turn_service.session.commit()
                turn.transition(TurnPhase.USER_PERSISTED)
                yield {
                    "type": "user_message",
                    "message_id": user_message_id,
                    "created_at": user_message_created_at,
                }
            else:
                turn.transition(TurnPhase.USER_PERSISTED)
                if resumed_turn_id:
                    await self.turn_service.resume_turn(turn_id)
                    await self.turn_service.session.commit()

            turn.transition(TurnPhase.CONTEXT_LOADED)
            yield {"type": "stage", "activity": {
                "run_id": runtime_run_id, "stage": "preparing",
                "action": "loading_context", "description": "Загружаю контекст",
            }}
            # RuntimePipeline builds cross-turn memory from the new Fact/Summary
            # stores. Injecting legacy chat summary duplicates context.
            # An explicit empty preloaded value is meaningful for a new chat.
            context = (
                list(preloaded_context)
                if preloaded_context is not None
                else await self.context_service.load_chat_context(chat_id, limit=get_settings().CHAT_CONTEXT_HISTORY_LIMIT)
            )
            # Keep the pre-turn history immutable for the runtime input.
            llm_messages = [*context, {"role": "user", "content": str(content)}]
            loaded_snapshot = preloaded_context_snapshot or await self.context_service.load_snapshot(
                chat_id=chat_id, owner_id=user_id, tenant_id=tenant_id,
            )
            context_snapshot = loaded_snapshot if isinstance(loaded_snapshot, ChatContextSnapshot) else ChatContextSnapshot(chat_id=chat_id)

            post_final_tail_ready = asyncio.Event()
            tool_ctx = ToolContext(
                tenant_id=tenant_id or "",
                user_id=user_id,
                chat_id=chat_id,
                request_id=idempotency_key or str(uuid.uuid4()),
                extra={
                    "continuation_meta": continuation_meta or {},
                    "confirmation_tokens": list(confirmation_tokens or []),
                    "chat_post_final_tail_ready": post_final_tail_ready,
                },
            )

            turn.transition(TurnPhase.EXECUTION_STARTED)
            yield {"type": "stage", "activity": {
                "run_id": runtime_run_id, "stage": "planning",
                "action": "routing_request", "description": "Определяю способ выполнения",
            }}
        except (asyncio.CancelledError, GeneratorExit):
            turn.force_cancel()
            import anyio
            with anyio.CancelScope(shield=True):
                await self.turn_service.session.rollback()
                await self.turn_service.cancel_turn(
                    turn_id, error_message=f"{cancellation_reason} during chat setup",
                )
                await self.turn_service.session.commit()
            raise
        except Exception:
            await self.turn_service.session.rollback()
            await self.turn_service.fail_turn(turn_id, error_message="Chat context preparation failed")
            await self.turn_service.session.commit()
            raise

        assistant_content = ""
        rag_sources = []
        final_attachments: list[dict[str, Any]] = []
        llm_error: Optional[dict[str, str]] = None
        runtime_event_types: list[str] = []
        final_stop_reason: Optional[str] = None
        final_content_received = False
        run_paused = False
        paused_run_id: Optional[str] = None
        last_run_id: Optional[str] = None
        paused_reason: Optional[str] = None
        paused_action: Optional[dict] = None
        paused_context: Optional[dict] = None
        terminal_event_emitted = False

        try:
            async for event_data in run_with_router(
                user_id=user_id,
                tenant_id=tenant_id or "",
                llm_messages=llm_messages,
                attachment_contexts=[item.model_dump(mode="json") if hasattr(item, "model_dump") else dict(item) for item in (attachment_contexts or [])],
                tool_ctx=tool_ctx,
                content=content,
                runtime_run_id=runtime_run_id,
                chat_turn_id=str(turn_id),
                expected_context_revision=context_snapshot.revision,
                chat_context_snapshot=context_snapshot,
                chat_user_message_id=user_message_id,
            ):
                runtime_event_types.append(str(event_data.get("type") or "unknown"))
                if isinstance(event_data.get("run_id"), str):
                    last_run_id = str(event_data.get("run_id"))
                elif event_data.get("type") == "final_content" and event_data.get("run_id"):
                    last_run_id = str(event_data["run_id"])
                if event_data.get("type") == "delta":
                    if turn.phase != TurnPhase.DELTA_STREAMING:
                        turn.transition(TurnPhase.DELTA_STREAMING)
                    assistant_content += event_data.get("content", "")
                elif event_data.get("type") == "final_content":
                    final_content_received = True
                    assistant_content = event_data.get("content", assistant_content)
                    rag_sources = event_data.get("sources", [])
                    final_attachments = (
                        event_data.get("attachments", [])
                        if isinstance(event_data.get("attachments"), list)
                        else []
                    )
                    final_stop_reason = str(event_data.get("stop_reason") or "").strip() or None
                elif event_data.get("type") == "run_paused":
                    run_paused = True
                    paused_run_id = event_data.get("run_id")
                    paused_reason = event_data.get("reason")
                    paused_action = event_data.get("action")
                    paused_context = event_data.get("context")
                    turn.transition(TurnPhase.PAUSED)
                elif event_data.get("type") == "error":
                    llm_error = self._normalize_runtime_error(
                        code=str(event_data.get("code") or "runtime_error"),
                        raw_message=str(event_data.get("error") or "Runtime error"),
                    )

                if event_data.get("type") not in ("final_content", "run_paused", "error"):
                    yield event_data
        except (asyncio.CancelledError, GeneratorExit):
            # The execution owner cancels this generator only after an explicit
            # Stop. Persist the terminal turn under a shield before unwinding.
            turn.force_cancel()
            import anyio
            with anyio.CancelScope(shield=True):
                await self.turn_service.session.rollback()
                if assistant_content.strip():
                    partial = await self.persistence_service.create_assistant_message(
                        chat_id=chat_id, content=assistant_content,
                        extra_meta={"runtime_status": "cancelled", "runtime_run_id": last_run_id},
                    )
                    await self.turn_service.attach_assistant_message(turn_id, partial.message_id)
                await self.turn_service.cancel_turn(turn_id, error_message=cancellation_reason)
                await self.turn_service.session.commit()
            raise
        except Exception as runtime_exc:
            llm_error = self._normalize_runtime_error(
                code="unknown_runtime_error",
                raw_message=str(runtime_exc),
            )
            logger.error("AgentRuntime error: %s", llm_error["operator_message"], exc_info=True)
            turn.force_error()
            await self.turn_service.fail_turn(turn_id, error_message=llm_error["operator_message"])
            yield {"type": "error", "error": llm_error["user_message"], "code": llm_error["code"]}

        if assistant_content and not llm_error and final_content_received:
            execution_failed = final_stop_reason == "failed"
            try:
                yield {"type": "stage", "activity": {
                    "run_id": runtime_run_id, "stage": "finalizing",
                    "action": "persisting_answer", "description": "Сохраняю ответ",
                }}
                assistant_message = await self.persistence_service.create_assistant_message(
                    chat_id=chat_id,
                    content=assistant_content,
                    rag_sources=rag_sources,
                    attachments=final_attachments,
                    extra_meta={
                        **({"runtime_run_id": last_run_id} if last_run_id else {}),
                        **({"runtime_stop_reason": final_stop_reason} if final_stop_reason else {}),
                        **(
                            {"runtime_status": final_stop_reason}
                            if final_stop_reason and final_stop_reason not in {"completed", "stopped"}
                            else {}
                        ),
                    } or None,
                )

                output_artifact_ids = [str(item["artifact_id"]) for item in final_attachments if item.get("artifact_id")]
                if output_artifact_ids:
                    await bind_attachments(chat_id=chat_id, owner_id=user_id, artifact_ids=output_artifact_ids,
                                           message_id=str(assistant_message.message_id))

                if execution_failed:
                    await self.turn_service.attach_assistant_message(turn_id, assistant_message.message_id)
                    await self.turn_service.fail_turn(turn_id, error_message="runtime_execution_failed")
                else:
                    await self.turn_service.complete_turn(
                        turn_id,
                        assistant_message_id=assistant_message.message_id,
                    )
                # The optional worker must observe the same committed deterministic
                # context and assistant message as the immediately following turn.
                await self.turn_service.session.commit()
            except asyncio.CancelledError:
                turn.force_cancel()
                import anyio
                with anyio.CancelScope(shield=True):
                    await self.turn_service.session.rollback()
                    await self.turn_service.cancel_turn(
                        turn_id, error_message=f"{cancellation_reason} while saving assistant response",
                    )
                    await self.turn_service.session.commit()
                raise
            except Exception:
                logger.exception("chat_turn_finalization_failed", extra={"chat_id": chat_id, "turn_id": str(turn_id)})
                turn.force_error()
                await self.turn_service.session.rollback()
                await self.turn_service.fail_turn(turn_id, error_message="chat_finalization_failed")
                await self.turn_service.session.commit()
                yield {"type": "error", "code": "chat_finalization_failed",
                       "error": "Не удалось сохранить ответ. Повторите запрос."}
                return
            # The database commit is authoritative. Cache population is
            # best-effort and outside the turn-finalization cancellation path.
            if idempotency_key and user_message_id:
                try:
                    await store_idempotency(
                        idempotency_key, user_message_id, assistant_message.message_id,
                        chat_id=chat_id, user_id=user_id,
                        request_hash=self.turn_service.build_request_hash(hash_payload),
                    )
                except Exception:
                    logger.warning("chat_idempotency_cache_write_failed", exc_info=True,
                                   extra={"chat_id": chat_id, "turn_id": str(turn_id)})
            post_final_tail_ready.set()
            await self._dispatch_context_compaction(
                chat_id=chat_id, turn_id=str(turn_id), user_id=user_id, tenant_id=tenant_id,
                recent_dialogue=llm_messages, user_message_id=user_message_id, assistant_content=assistant_content,
                assistant_message_id=str(assistant_message.message_id), run_id=last_run_id,
                terminal_state="failed" if execution_failed else "completed",
            )
            turn.transition(TurnPhase.FINAL_PERSISTED)
            yield {"type": "state", "run_id": runtime_run_id,
                   "status": "failed" if execution_failed else "completed"}
            yield {
                "type": "final",
                "message_id": assistant_message.message_id,
                "content": assistant_content,
                "created_at": assistant_message.created_at,
                "sources": rag_sources,
                "attachments": final_attachments,
                **({"stop_reason": final_stop_reason} if final_stop_reason else {}),
            }
            if execution_failed:
                turn.force_error()
            else:
                turn.transition(TurnPhase.COMPLETED)
            terminal_event_emitted = True
        elif not llm_error and not run_paused:
            turn.force_error()
            logger.error(
                "chat_turn_empty_agent_response",
                extra={
                    "chat_id": chat_id,
                    "turn_id": str(turn_id),
                    "runtime_run_id": runtime_run_id,
                    "last_run_id": last_run_id,
                    "runtime_event_types": runtime_event_types,
                },
            )
            await self.turn_service.fail_turn(turn_id, error_message="Empty response from agent")
            await self.turn_service.session.commit()
            yield {"type": "state", "run_id": runtime_run_id, "status": "failed"}
            yield {"type": "error", "error": "Empty response from agent"}
            terminal_event_emitted = True
        elif run_paused:
            from app.runtime.interaction import interaction_from_context
            active_interaction = interaction_from_context(paused_context)
            pause_id = active_interaction.id if active_interaction else str(uuid.uuid4())
            paused_action = {**(paused_action or {}), "pause_id": pause_id}
            paused_context = {**(paused_context or {}), "pause_id": pause_id}
            await self.turn_service.pause_turn(
                turn_id,
                pause_status=paused_reason or "paused",
                runtime_run_id=paused_run_id,
                paused_action=paused_action,
                paused_context=paused_context,
            )
            # The browser receives the pause over SSE and resumes through a
            # new HTTP request. Persist the checkpoint before emitting that
            # frame; a flush alone is rolled back when the streaming request
            # dependency closes its session.
            await self.turn_service.session.commit()
            yield {"type": "state", "run_id": runtime_run_id,
                   "status": paused_reason if paused_reason in {"waiting_input", "waiting_confirmation"} else "waiting_input",
                   "pause_reason": paused_reason or "waiting_input"}
            question = ""
            message = ""
            if isinstance(paused_context, dict):
                question = str(paused_context.get("question") or "").strip()
                message = str(paused_context.get("message") or "").strip()
            if not question and isinstance(paused_action, dict):
                question = str(paused_action.get("question") or "").strip()
            if not message and isinstance(paused_action, dict):
                message = str(paused_action.get("message") or "").strip()
            await self._dispatch_context_compaction(
                chat_id=chat_id, turn_id=str(turn_id), user_id=user_id, tenant_id=tenant_id,
                recent_dialogue=llm_messages, user_message_id=user_message_id, assistant_content=message or question,
                assistant_message_id=None, run_id=paused_run_id,
                terminal_state=str(paused_reason or "waiting_input"),
            )
            # Emit stop with run_id so UI can resume paused run.
            yield {
                "type": "stop",
                "reason": paused_reason or "paused",
                "question": question or None,
                "message": message or None,
                "run_id": paused_run_id,
                "action": paused_action if isinstance(paused_action, dict) else {},
                "context": paused_context if isinstance(paused_context, dict) else {},
                "contract_version": RuntimeHitlProtocolService.CONTRACT_VERSION,
            }
            terminal_event_emitted = True
        elif llm_error:
            turn.force_error()
            yield {"type": "stage", "activity": {
                "run_id": runtime_run_id, "stage": "finalizing",
                "action": "persisting_failure", "description": "Сохраняю результат выполнения",
            }}
            await self.turn_service.fail_turn(turn_id, error_message=llm_error["operator_message"])
            if assistant_content.strip():
                partial_message = await self.persistence_service.create_assistant_message(
                    chat_id=chat_id,
                    content=assistant_content.strip(),
                    rag_sources=rag_sources,
                    extra_meta={
                        "runtime_status": "partial",
                        "runtime_error_code": llm_error["code"],
                        "runtime_error_message": llm_error["user_message"],
                        "runtime_run_id": last_run_id,
                    },
                )
                await self.turn_service.attach_assistant_message(turn_id, partial_message.message_id)
            else:
                failed_message = await self.persistence_service.create_assistant_message(
                    chat_id=chat_id,
                    content=llm_error["user_message"],
                    rag_sources=rag_sources,
                    extra_meta={
                        "runtime_status": "failed",
                        "runtime_error_code": llm_error["code"],
                        "runtime_run_id": last_run_id,
                    },
                )
                await self.turn_service.attach_assistant_message(turn_id, failed_message.message_id)
            await self.turn_service.session.commit()
            yield {"type": "state", "run_id": runtime_run_id, "status": "failed"}
            if not terminal_event_emitted:
                yield {"type": "error", "error": llm_error["user_message"], "code": llm_error["code"]}
            terminal_event_emitted = True

    @staticmethod
    def _normalize_runtime_error(*, code: str, raw_message: str) -> dict[str, str]:
        normalized_code = (code or "unknown_runtime_error").strip().lower()
        message_lc = (raw_message or "").lower()
        if "budget" in normalized_code or "budget" in message_lc:
            normalized_code = "budget_exceeded"
            user_message = "Достигнут лимит выполнения запроса. Попробуйте сузить запрос."
        elif "retry" in normalized_code or "retry" in message_lc:
            normalized_code = "max_retries_exceeded"
            user_message = "Не удалось завершить запрос после нескольких попыток. Попробуйте позже."
        elif "tool" in normalized_code and "unavailable" in message_lc:
            normalized_code = "tool_unavailable"
            user_message = "Один из инструментов сейчас недоступен. Попробуйте позже."
        elif "timeout" in normalized_code or "timeout" in message_lc:
            normalized_code = "tool_timeout"
            user_message = "Превышено время ожидания инструмента. Попробуйте позже."
        elif "planner" in normalized_code or "planner" in message_lc:
            normalized_code = "planner_failed"
            user_message = "Не удалось построить план выполнения запроса. Попробуйте переформулировать вопрос."
        elif "policy" in normalized_code or "denied" in message_lc:
            normalized_code = "policy_blocked"
            user_message = "Запрос заблокирован политикой доступа."
        elif "agent" in normalized_code or "runtime_failed" in normalized_code:
            normalized_code = "agent_failed"
            user_message = "Не удалось завершить выполнение агентом. Попробуйте позже."
        else:
            normalized_code = "unknown_runtime_error"
            user_message = "Произошла внутренняя ошибка выполнения. Попробуйте позже."
        return {
            "code": normalized_code,
            "user_message": user_message,
            "operator_message": raw_message or normalized_code,
        }

    async def _dispatch_context_compaction(
        self,
        *,
        chat_id: str,
        turn_id: str,
        user_id: str,
        tenant_id: Optional[str],
        recent_dialogue: list[dict[str, Any]],
        user_message_id: Optional[str],
        assistant_content: str,
        assistant_message_id: Optional[str],
        run_id: Optional[str],
        terminal_state: str,
    ) -> None:
        """Queue optional semantic compaction after deterministic state exists."""
        if not tenant_id:
            return
        try:
            snapshot = await self.context_service.load_snapshot(
                chat_id=chat_id, owner_id=user_id, tenant_id=tenant_id,
            )
            if not isinstance(snapshot, ChatContextSnapshot):
                return
            from app.runtime.redactor import RuntimeRedactor
            redactor = RuntimeRedactor()
            dialogue = [
                {"role": str(item.get("role")), "content": str(redactor.redact(item.get("content") or ""))[:1200]}
                for item in recent_dialogue[-7:]
                if isinstance(item, dict) and item.get("role") in {"user", "assistant"} and item.get("content")
            ]
            if assistant_content:
                dialogue.append({"role": "assistant", "content": str(redactor.redact(assistant_content))[:1200]})
            sources = [f"turn:{turn_id}"]
            if user_message_id:
                sources.append(f"message:{user_message_id}")
            if assistant_message_id:
                sources.append(f"message:{assistant_message_id}")
            if run_id:
                sources.append(f"run:{run_id}")
            for item in recent_dialogue[-7:]:
                if isinstance(item, dict) and item.get("message_id"):
                    sources.append(f"message:{item['message_id']}")
            from app.workers.tasks_memory import compact_chat_context

            compact_chat_context.delay({
                "chat_id": chat_id, "chat_turn_id": turn_id, "user_id": user_id, "tenant_id": tenant_id,
                "expected_revision": snapshot.revision, "snapshot": snapshot.model_dump(mode="json"),
                "recent_dialogue": dialogue[-8:],
                "outcome": {"terminal_state": terminal_state, "assistant_summary": assistant_content[:600]},
                "valid_source_ids": list(dict.fromkeys(sources))[:20],
            })
        except Exception:
            logger.warning("chat_context_compaction_dispatch_failed", exc_info=True, extra={"chat_id": chat_id, "turn_id": turn_id})
