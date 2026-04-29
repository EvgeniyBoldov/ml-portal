"""
Chat streaming service with idempotency, context loading, and Agent Runtime integration.

This service acts as a thin transport layer:
- Handles idempotency
- Manages message persistence
- Delegates agent execution to the v3 RuntimePipeline
"""
from __future__ import annotations
from typing import Optional, Dict, Any, List, AsyncGenerator
from datetime import datetime, timezone
import uuid
from types import SimpleNamespace

from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis

from app.repositories.chats_repo import AsyncChatsRepository, AsyncChatMessagesRepository
from app.core.http.clients import LLMClientProtocol
from app.services.run_store import RunStore
from app.agents import ToolContext
from app.runtime import RuntimePipeline, PipelineRequest, RuntimeEvent, RuntimeEventType
from app.agents.execution_preflight import AgentUnavailableError
from app.core.logging import get_logger
from app.core.idempotency import IdempotencyManager
from app.services.chat_context_service import ChatContextService
from app.services.chat_event_mapper import ChatEventMapper
from app.services.chat_persistence_service import ChatPersistenceService
from app.services.chat_title_service import ChatTitleService
from app.services.chat_turn_orchestrator import ChatTurnOrchestrator
from app.services.chat_turn_service import ChatTurnService
from app.services.chat_attachment_service import ChatAttachmentService, ChatAttachmentNotFoundError
from app.services.chat_generated_file_service import ChatGeneratedFileService
from app.core.db import get_session_factory

logger = get_logger(__name__)


class ChatStreamService:
    """Compatibility façade for chat streaming built on smaller chat services."""
    
    def __init__(
        self,
        session: AsyncSession,
        redis: Redis,
        llm_client: LLMClientProtocol,
        chats_repo: AsyncChatsRepository,
        messages_repo: AsyncChatMessagesRepository,
    ):
        self.session = session
        self.redis = redis
        self.llm_client = llm_client
        self.chats_repo = chats_repo
        self.messages_repo = messages_repo
        self.idempotency = IdempotencyManager(redis)
        # Keep constructor test-friendly: RunStore resolves global factory lazily on first write.
        self.run_store = RunStore(session=session)
        self.context_service = ChatContextService(session, llm_client, messages_repo)
        self.title_service = ChatTitleService(session, llm_client, chats_repo)
        self.persistence_service = ChatPersistenceService(session, messages_repo)
        self.chat_turn_service = ChatTurnService(session)
        self.event_mapper = ChatEventMapper()
        self.attachment_service = ChatAttachmentService(session)
        self.generated_file_service = ChatGeneratedFileService(self.attachment_service)
        self.turn_orchestrator = ChatTurnOrchestrator(
            context_service=self.context_service,
            persistence_service=self.persistence_service,
            title_service=self.title_service,
            turn_service=self.chat_turn_service,
        )
        # Backward-compatible patch point for older unit tests.
        self.agent_service = SimpleNamespace(agent_repo=SimpleNamespace())
    
    async def verify_chat_access(self, chat_id: str, user_id: str) -> bool:
        """Verify that user has access to the chat"""
        chat = await self.chats_repo.get_chat_by_id(chat_id)
        if not chat:
            return False
        return str(chat.owner_id) == user_id
    
    async def load_chat_context(
        self,
        chat_id: str,
        limit: int = 20
    ) -> List[Dict[str, str]]:
        return await self.context_service.load_chat_context(chat_id, limit=limit)

    async def load_chat_context_with_summary(
        self,
        chat_id: str,
        recent_limit: int = 3,
    ) -> List[Dict[str, str]]:
        return await self.context_service.load_chat_context_with_summary(chat_id, recent_limit=recent_limit)
    
    async def generate_chat_title(self, chat_id: str, first_message: str) -> Optional[str]:
        return await self.title_service.generate_chat_title(chat_id, first_message)

    async def check_idempotency(
        self,
        idempotency_key: str,
        chat_id: str
    ) -> Optional[Dict[str, str]]:
        """Check if request with this idempotency key was already processed"""
        return await self.idempotency.get_cached_result(idempotency_key)

    async def check_turn_idempotency(
        self,
        *,
        idempotency_key: str,
        chat_id: str,
        user_id: str,
        content: str,
        attachment_ids: Optional[list[str]] = None,
    ) -> Optional[Dict[str, str]]:
        ids = attachment_ids or []
        hash_payload = content if not ids else f"{content}||attachments:{','.join(sorted(ids))}"
        request_hash = self.chat_turn_service.build_request_hash(hash_payload)
        payload_mismatch = await self.chat_turn_service.has_payload_mismatch(
            chat_id=chat_id,
            user_id=user_id,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
        if payload_mismatch:
            return {"state": "conflict"}

        turn = await self.chat_turn_service.get_latest_by_idempotency_key(
            chat_id=chat_id,
            user_id=user_id,
            idempotency_key=idempotency_key,
        )
        if not turn:
            return None

        if turn.status == "started":
            return {"state": "processing"}

        if turn.status == "completed" and turn.user_message_id and turn.assistant_message_id:
            return {
                "state": "completed",
                "user_message_id": str(turn.user_message_id),
                "assistant_message_id": str(turn.assistant_message_id),
            }

        return None
    
    async def store_idempotency(
        self,
        idempotency_key: str,
        user_message_id: str,
        assistant_message_id: str,
        ttl_hours: int = 24
    ) -> None:
        """Store idempotency result"""
        await self.idempotency.cache_result(idempotency_key, {
            "user_message_id": user_message_id,
            "assistant_message_id": assistant_message_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
    
    async def send_message_stream(
        self,
        chat_id: str,
        user_id: str,
        content: str,
        attachment_ids: Optional[list[str]] = None,
        confirmation_tokens: Optional[list[str]] = None,
        idempotency_key: Optional[str] = None,
        model: Optional[str] = None,
        agent_slug: Optional[str] = None,
        continuation_meta: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Send message and stream response while preserving current chat contract."""

        # 1. Check idempotency
        if idempotency_key:
            turn_cached = await self.check_turn_idempotency(
                idempotency_key=idempotency_key,
                chat_id=chat_id,
                user_id=user_id,
                content=content,
                attachment_ids=attachment_ids,
            )
            if turn_cached and turn_cached.get("state") == "conflict":
                yield {"type": "error", "error": "Idempotency key was already used with different request payload"}
                return

            if turn_cached and turn_cached.get("state") == "processing":
                yield {"type": "error", "error": "Request with this idempotency key is already in progress"}
                return

            if turn_cached and turn_cached.get("state") == "completed":
                logger.info(
                    "chat_idempotency_turn_hit",
                    extra={
                        "chat_id": chat_id,
                        "user_id": user_id,
                        "idempotency_key": idempotency_key,
                        "assistant_message_id": turn_cached.get("assistant_message_id"),
                        "user_message_id": turn_cached.get("user_message_id"),
                    },
                )
                yield {
                    "type": "cached",
                    "user_message_id": turn_cached["user_message_id"],
                    "assistant_message_id": turn_cached["assistant_message_id"],
                }
                return

            cached = await self.check_idempotency(idempotency_key, chat_id)
            if cached:
                logger.info(
                    "chat_idempotency_hit",
                    extra={
                        "chat_id": chat_id,
                        "user_id": user_id,
                        "idempotency_key": idempotency_key,
                        "assistant_message_id": cached.get("assistant_message_id"),
                        "user_message_id": cached.get("user_message_id"),
                    },
                )
                yield {
                    "type": "cached",
                    "user_message_id": cached["user_message_id"],
                    "assistant_message_id": cached["assistant_message_id"]
                }
                return
        
        # 2. Verify access
        if not await self.verify_chat_access(chat_id, user_id):
            yield {"type": "error", "error": "Access denied"}
            return

        try:
            chat = await self.chats_repo.get_chat_by_id(chat_id)
            if not chat:
                yield {"type": "error", "error": "Chat not found"}
                return

            attachment_rows = []
            attachment_prompt_context = ""
            attachment_ids = attachment_ids or []
            if attachment_ids:
                try:
                    attachment_rows = await self.attachment_service.get_owned_attachments(
                        tenant_id=str(chat.tenant_id),
                        chat_id=chat_id,
                        owner_id=user_id,
                        attachment_ids=attachment_ids,
                    )
                except ChatAttachmentNotFoundError as exc:
                    yield {"type": "error", "error": str(exc)}
                    return
                attachment_prompt_context = await self.attachment_service.build_prompt_context(
                    attachments=attachment_rows
                )

            async for event in self.turn_orchestrator.execute_turn(
                chat=chat,
                chat_id=chat_id,
                user_id=user_id,
                content=content,
                attachment_ids=attachment_ids,
                confirmation_tokens=confirmation_tokens or [],
                attachment_meta=self.attachment_service.to_meta(attachment_rows),
                attachment_prompt_context=attachment_prompt_context,
                idempotency_key=idempotency_key,
                model=model,
                agent_slug=agent_slug,
                continuation_meta=continuation_meta,
                run_with_router=self._run_with_router,
                store_idempotency=self.store_idempotency,
                bind_attachments=self.attachment_service.bind_to_message,
                process_generated_files=self._process_generated_files,
            ):
                yield event

        except Exception as e:
            logger.error(f"Error in send_message_stream: {e}", exc_info=True)
            yield {"type": "error", "error": str(e)}

    
    async def _run_with_router(
        self,
        agent_slug: str,
        user_id: str,
        tenant_id: str,
        llm_messages: List[Dict[str, str]],
        tool_ctx: ToolContext,
        model: Optional[str],
        content: str,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Run the turn via runtime v3 Pipeline, translating events to SSE payloads."""
        try:
            runtime_deps = tool_ctx.get_runtime_deps()
            runtime_deps.session_factory = get_session_factory()
            tool_ctx.set_runtime_deps(runtime_deps)

            pipeline = RuntimePipeline(
                session=self.session,
                llm_client=self.llm_client,
                run_store=self.run_store,
            )

            text_content = content.get("text", str(content)) if isinstance(content, dict) else str(content)

            pipeline_request = PipelineRequest(
                request_text=text_content,
                chat_id=str(tool_ctx.chat_id),
                user_id=user_id,
                tenant_id=tenant_id,
                messages=llm_messages,
                agent_slug=agent_slug,
                model=model,
                continuation_meta=(tool_ctx.extra or {}).get("continuation_meta", {}) if hasattr(tool_ctx, "extra") else {},
                confirmation_tokens=list((tool_ctx.extra or {}).get("confirmation_tokens") or []),
            )

            async for event in pipeline.execute(pipeline_request, tool_ctx):
                # FINAL and STOP are handled specially below — skip _map for them
                if event.type == RuntimeEventType.FINAL:
                    final_content = event.data.get("content", "")
                    final_sources = event.data.get("sources", [])
                    yield {
                        "type": "final_content",
                        "content": final_content,
                        "sources": final_sources,
                        "stop_reason": event.data.get("stop_reason"),
                    }
                    # Rolling dialogue summary is produced by the pipeline's
                    # TurnSummarizer (see app.runtime.summarizer_turn) right
                    # before FINAL is emitted; nothing to do here.

                elif event.type == RuntimeEventType.STOP:
                    stop_payload = dict(event.data or {})
                    reason = stop_payload.get("reason")
                    # Build paused_action preserving all confirmation details
                    # (operation_fingerprint, tool_slug, etc.) for resume token issuance.
                    paused_action_payload: dict = {
                        "type": "resume",
                        "reason": reason,
                        "question": stop_payload.get("question"),
                        "message": stop_payload.get("message"),
                    }
                    for _k in ("operation_fingerprint", "tool_slug", "operation", "risk_level", "args_preview", "summary"):
                        if stop_payload.get(_k) is not None:
                            paused_action_payload[_k] = stop_payload[_k]
                    yield {
                        "type": "run_paused",
                        "reason": reason,
                        "run_id": stop_payload.get("run_id"),
                        "action": paused_action_payload,
                        "context": stop_payload,
                    }

                else:
                    # Map all other events (status, delta, error, operation_call, etc.)
                    mapped = self.event_mapper.map_runtime_event(event)
                    if mapped:
                        yield mapped

        except AgentUnavailableError as e:
            reason_code = str(getattr(e, "reason_code", "") or "").strip() or None
            details = dict(getattr(e, "details", {}) or {})
            logger.warning(
                "Agent unavailable: %s",
                e,
                extra={
                    "reason_code": reason_code,
                    "details": details,
                },
            )
            if reason_code == "rbac_agent_invoke_denied":
                yield {
                    "type": "status",
                    "stage": "rbac_agent_invoke_denied",
                    "agent_slug": details.get("agent_slug"),
                }
            yield {
                "type": "error",
                "error": str(e),
                "code": reason_code,
                "details": details,
                "missing_tools": e.missing.tools if e.missing else [],
                "missing_collections": e.missing.collections if e.missing else [],
                "missing_credentials": e.missing.credentials if e.missing else [],
            }
        except Exception as e:
            logger.error(f"Router error: {e}", exc_info=True)
            yield {"type": "error", "error": f"Routing failed: {str(e)}"}

    async def _process_generated_files(
        self,
        *,
        tenant_id: str,
        chat_id: str,
        owner_id: str,
        assistant_text: str,
    ) -> Dict[str, Any]:
        try:
            result = await self.generated_file_service.extract_and_store(
                tenant_id=tenant_id,
                chat_id=chat_id,
                owner_id=owner_id,
                assistant_text=assistant_text,
            )
            return {
                "content": result.cleaned_content,
                "attachments": result.attachments,
            }
        except Exception as exc:
            logger.warning("Failed to process generated files: %s", exc)
            return {"content": assistant_text, "attachments": []}
