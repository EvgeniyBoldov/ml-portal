from __future__ import annotations

from typing import Any, AsyncGenerator, Dict, Optional
import uuid

from app.agents import ToolContext
from app.core.logging import get_logger
from app.services.chat_context_service import ChatContextService
from app.services.chat_persistence_service import ChatPersistenceService
from app.services.chat_title_service import ChatTitleService
from app.services.chat_turn_service import ChatTurnService
from app.services.chat_turn_state import ChatTurnState, TurnPhase

logger = get_logger(__name__)

FILE_GENERATION_INSTRUCTION = (
    "When user asks to generate downloadable file, output file body in fenced block format:\n"
    "```file name=report.txt\n<content>\n```\n"
    "Supported formats: txt, md, csv, tsv, json. "
    "Do not generate executables, video, audio, or PDF."
)


class ChatTurnOrchestrator:
    """Orchestrates a single chat turn while preserving current chat contract."""

    def __init__(
        self,
        *,
        context_service: ChatContextService,
        persistence_service: ChatPersistenceService,
        title_service: ChatTitleService,
        turn_service: ChatTurnService,
    ) -> None:
        self.context_service = context_service
        self.persistence_service = persistence_service
        self.title_service = title_service
        self.turn_service = turn_service

    async def execute_turn(
        self,
        *,
        chat,
        chat_id: str,
        user_id: str,
        content: str,
        attachment_ids: list[str],
        confirmation_tokens: Optional[list[str]] = None,
        attachment_meta: list[dict[str, Any]],
        attachment_prompt_context: str,
        idempotency_key: Optional[str],
        model: Optional[str],
        agent_slug: Optional[str],
        continuation_meta: Optional[Dict[str, Any]],
        run_with_router,
        store_idempotency,
        bind_attachments,
        process_generated_files,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        turn = ChatTurnState(chat_id=chat_id, request_id=idempotency_key)
        tenant_id = str(chat.tenant_id)
        hash_payload = content if not attachment_ids else f"{content}||attachments:{','.join(sorted(attachment_ids))}"
        persisted_turn = await self.turn_service.start_turn(
            tenant_id=tenant_id,
            chat_id=chat_id,
            user_id=user_id,
            idempotency_key=idempotency_key,
            request_hash=self.turn_service.build_request_hash(hash_payload),
        )
        turn_id = persisted_turn.id  # cache scalar to survive ORM expiry

        yield {"type": "status", "stage": "saving_user_message"}
        user_meta = {"attachments": attachment_meta} if attachment_meta else None
        user_message = await self.persistence_service.create_user_message(
            chat_id=chat_id,
            content=content,
            meta=user_meta,
        )
        user_message_id = user_message.message_id  # cache scalar to survive ORM expiry
        user_message_created_at = user_message.created_at
        if attachment_ids:
            await bind_attachments(
                tenant_id=tenant_id,
                chat_id=chat_id,
                owner_id=user_id,
                attachment_ids=attachment_ids,
                message_id=user_message_id,
            )
        await self.turn_service.attach_user_message(turn_id, user_message_id)
        turn.transition(TurnPhase.USER_PERSISTED)
        yield {
            "type": "user_message",
            "message_id": user_message_id,
            "created_at": user_message_created_at,
        }

        turn.transition(TurnPhase.CONTEXT_LOADED)
        yield {"type": "status", "stage": "loading_context"}
        # RuntimePipeline already builds its own cross-turn memory from the
        # new Fact/Summary stores. Injecting legacy chat summary here duplicates
        # context and inflates token usage.
        context = await self.context_service.load_chat_context(chat_id, limit=12)
        llm_messages = context + [{"role": "system", "content": FILE_GENERATION_INSTRUCTION}]
        if attachment_prompt_context:
            llm_messages.append({"role": "system", "content": attachment_prompt_context})
        llm_messages.append({"role": "user", "content": str(content)})

        user_messages_count = sum(1 for msg in context if msg.get("role") == "user")
        is_first_message = user_messages_count == 0
        logger.info(
            f"Chat title check: user_messages_count={user_messages_count}, "
            f"is_first={is_first_message}, chat.name='{chat.name}'"
        )
        if is_first_message and chat.name in (None, "", "New Chat", "Новый чат"):
            logger.info(f"Generating chat title for first message: {content[:100]}")
            generated_title = await self.title_service.generate_chat_title(chat_id, content)
            if generated_title:
                logger.info(f"Generated title: {generated_title}")
                yield {"type": "chat_title", "title": generated_title}
            else:
                logger.warning("Failed to generate chat title")

        tool_ctx = ToolContext(
            tenant_id=tenant_id,
            user_id=user_id,
            chat_id=chat_id,
            request_id=idempotency_key or str(uuid.uuid4()),
            extra={
                "continuation_meta": continuation_meta or {},
                "confirmation_tokens": list(confirmation_tokens or []),
            },
        )

        turn.transition(TurnPhase.EXECUTION_STARTED)
        yield {"type": "status", "stage": "agent_running"}

        assistant_content = ""
        rag_sources = []
        llm_error: Optional[dict[str, str]] = None
        run_paused = False
        paused_run_id: Optional[str] = None
        last_run_id: Optional[str] = None
        paused_reason: Optional[str] = None
        paused_action: Optional[dict] = None
        paused_context: Optional[dict] = None
        terminal_event_emitted = False

        try:
            async for event_data in run_with_router(
                agent_slug=agent_slug,
                user_id=user_id,
                tenant_id=tenant_id,
                llm_messages=llm_messages,
                tool_ctx=tool_ctx,
                model=model,
                content=content,
            ):
                if isinstance(event_data.get("run_id"), str):
                    last_run_id = str(event_data.get("run_id"))
                if event_data.get("type") == "delta":
                    if turn.phase != TurnPhase.DELTA_STREAMING:
                        turn.transition(TurnPhase.DELTA_STREAMING)
                    assistant_content += event_data.get("content", "")
                elif event_data.get("type") == "final_content":
                    assistant_content = event_data.get("content", assistant_content)
                    rag_sources = event_data.get("sources", [])
                    _final_stop_reason = event_data.get("stop_reason")
                    if _final_stop_reason in ("failed", "loop_detected", "budget_exceeded", "aborted"):
                        llm_error = self._normalize_runtime_error(
                            code=f"runtime_{_final_stop_reason}",
                            raw_message=f"Agent run ended with status: {_final_stop_reason}",
                        )
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
                    terminal_event_emitted = True

                if event_data.get("type") not in ("final_content", "run_paused"):
                    yield event_data
        except Exception as runtime_exc:
            llm_error = self._normalize_runtime_error(
                code="unknown_runtime_error",
                raw_message=str(runtime_exc),
            )
            logger.error("AgentRuntime error: %s", llm_error["operator_message"], exc_info=True)
            turn.force_error()
            await self.turn_service.fail_turn(turn_id, error_message=llm_error["operator_message"])
            yield {"type": "error", "error": llm_error["user_message"], "code": llm_error["code"]}

        if assistant_content and not llm_error:
            generated_attachment_ids: list[str] = []
            generated_attachment_meta: list[dict[str, Any]] = []
            generated = await process_generated_files(
                tenant_id=tenant_id,
                chat_id=chat_id,
                owner_id=user_id,
                assistant_text=assistant_content,
            )
            assistant_content = generated.get("content", assistant_content)
            generated_attachment_meta = generated.get("attachments", [])
            generated_attachment_ids = [
                str(item.get("id"))
                for item in generated_attachment_meta
                if item.get("id")
            ]

            assistant_message = await self.persistence_service.create_assistant_message(
                chat_id=chat_id,
                content=assistant_content,
                rag_sources=rag_sources,
                attachments=generated_attachment_meta,
                extra_meta={"runtime_run_id": last_run_id} if last_run_id else None,
            )

            if generated_attachment_ids:
                await bind_attachments(
                    tenant_id=tenant_id,
                    chat_id=chat_id,
                    owner_id=user_id,
                    attachment_ids=generated_attachment_ids,
                    message_id=assistant_message.message_id,
                )

            if idempotency_key:
                await store_idempotency(
                    idempotency_key,
                    user_message_id,
                    assistant_message.message_id,
                )

            await self.turn_service.complete_turn(
                turn_id,
                assistant_message_id=assistant_message.message_id,
            )
            turn.transition(TurnPhase.FINAL_PERSISTED)
            yield {
                "type": "final",
                "message_id": assistant_message.message_id,
                "created_at": assistant_message.created_at,
                "sources": rag_sources,
            }
            turn.transition(TurnPhase.COMPLETED)
            yield {"type": "status", "stage": "completed"}
            terminal_event_emitted = True
        elif not llm_error and not run_paused:
            turn.force_error()
            await self.turn_service.fail_turn(turn_id, error_message="Empty response from agent")
            yield {"type": "error", "error": "Empty response from agent"}
            terminal_event_emitted = True
        elif run_paused:
            await self.turn_service.pause_turn(
                turn_id,
                pause_status=paused_reason or "paused",
                agent_run_id=paused_run_id,
                paused_action=paused_action,
                paused_context=paused_context,
            )
            question = ""
            message = ""
            if isinstance(paused_context, dict):
                question = str(paused_context.get("question") or "").strip()
                message = str(paused_context.get("message") or "").strip()
            if not question and isinstance(paused_action, dict):
                question = str(paused_action.get("question") or "").strip()
            if not message and isinstance(paused_action, dict):
                message = str(paused_action.get("message") or "").strip()
            # Emit stop with run_id so UI can resume paused run.
            yield {
                "type": "stop",
                "reason": paused_reason or "paused",
                "question": question or None,
                "message": message or None,
                "run_id": paused_run_id,
            }
            terminal_event_emitted = True
        elif llm_error:
            turn.force_error()
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
