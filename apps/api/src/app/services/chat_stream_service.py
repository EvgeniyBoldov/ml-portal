"""
Chat streaming service with idempotency, context loading, and Agent Runtime integration.

This service acts as a thin transport layer:
- Handles idempotency
- Manages message persistence
- Delegates agent execution to AgentRuntime
"""
from __future__ import annotations
from typing import Optional, Dict, Any, List, AsyncGenerator
from datetime import datetime, timezone, timedelta
import json
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis

from app.repositories.chats_repo import AsyncChatsRepository, AsyncChatMessagesRepository
from app.core.http.clients import LLMClientProtocol
from app.services.agent_service import AgentService
from app.services.run_store import RunStore
from app.agents import AgentRuntime, ToolContext, RuntimeEvent, RuntimeEventType
from app.agents.router import AgentRouter, AgentUnavailableError, ExecutionMode
from app.core.logging import get_logger
from app.core.idempotency import IdempotencyManager

logger = get_logger(__name__)


class ChatStreamService:
    """
    Service for streaming chat messages with idempotency and context.
    
    Responsibilities:
    - Idempotency checking and storage
    - Access control
    - Message persistence (user and assistant)
    - Context loading
    - Delegating to AgentRuntime for actual agent execution
    - Auto-generating chat titles
    """
    
    TITLE_GENERATION_PROMPT = """Generate a short, descriptive title (3-6 words) for a chat that starts with this message. 
The title should capture the main topic or intent. Reply with ONLY the title, nothing else.
Language: use the same language as the user message.

User message: {message}"""
    
    def __init__(
        self,
        session: AsyncSession,
        redis: Redis,
        llm_client: LLMClientProtocol,
        chats_repo: AsyncChatsRepository,
        messages_repo: AsyncChatMessagesRepository,
        use_router: bool = True,
    ):
        self.session = session
        self.redis = redis
        self.llm_client = llm_client
        self.chats_repo = chats_repo
        self.messages_repo = messages_repo
        self.idempotency = IdempotencyManager(redis)
        self.agent_service = AgentService(session)
        self.run_store = RunStore(session)
        self.runtime = AgentRuntime(llm_client, run_store=self.run_store)
        self.use_router = use_router
        self.router = AgentRouter(session) if use_router else None
    
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
        """Load recent messages for LLM context"""
        messages = await self.messages_repo.get_chat_messages(
            chat_id=chat_id,
            limit=limit,
            offset=0
        )
        
        # Convert to LLM format
        context = []
        for msg in messages:
            # Extract text from content
            content_text = msg.content
            if isinstance(content_text, dict) and "text" in content_text:
                content_text = content_text["text"]
            elif isinstance(content_text, dict):
                content_text = json.dumps(content_text)
            
            context.append({
                "role": msg.role,
                "content": str(content_text)
            })
        
        return context
    
    async def generate_chat_title(self, chat_id: str, first_message: str) -> Optional[str]:
        """Generate a title for the chat based on the first message"""
        try:
            prompt = self.TITLE_GENERATION_PROMPT.format(message=first_message[:500])
            
            response = await self.llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
                model=None,  # Use default model
                stream=False,
                max_tokens=50,
                temperature=0.3,
            )
            
            title = response.get("content", "").strip()
            # Clean up title - remove quotes if present
            title = title.strip('"\'')
            
            if title and len(title) > 2:
                # Update chat name
                chat = await self.chats_repo.get_chat_by_id(chat_id)
                if chat:
                    chat.name = title[:100]  # Limit to 100 chars
                    await self.session.flush()
                    await self.session.commit()
                    logger.info(f"Generated chat title: {title}")
                    return title
        except Exception as e:
            logger.warning(f"Failed to generate chat title: {e}")
        return None
    
    async def check_idempotency(
        self,
        idempotency_key: str,
        chat_id: str
    ) -> Optional[Dict[str, str]]:
        """Check if request with this idempotency key was already processed"""
        cache_key = f"chat:message:{idempotency_key}"
        cached = await self.redis.get(cache_key)
        
        if cached:
            try:
                return json.loads(cached)
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON in idempotency cache: {cache_key}")
                return None
        
        return None
    
    async def store_idempotency(
        self,
        idempotency_key: str,
        user_message_id: str,
        assistant_message_id: str,
        ttl_hours: int = 24
    ) -> None:
        """Store idempotency result"""
        cache_key = f"chat:message:{idempotency_key}"
        value = json.dumps({
            "user_message_id": user_message_id,
            "assistant_message_id": assistant_message_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        await self.redis.setex(
            cache_key,
            timedelta(hours=ttl_hours),
            value
        )
    
    async def send_message_stream(
        self,
        chat_id: str,
        user_id: str,
        content: str,
        idempotency_key: Optional[str] = None,
        use_rag: bool = False,
        model: Optional[str] = None,
        agent_slug: Optional[str] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Send message and stream LLM response via AgentRuntime.
        
        Yields events:
        - {"type": "user_message", "message_id": "..."}
        - {"type": "status", "stage": "..."}
        - {"type": "tool_call", "tool": "...", "arguments": {...}}
        - {"type": "tool_result", "tool": "...", "success": bool, "data": ...}
        - {"type": "delta", "content": "..."}
        - {"type": "final", "message_id": "...", "sources": [...]}
        - {"type": "error", "error": "..."}
        """
        
        # 1. Check idempotency
        if idempotency_key:
            cached = await self.check_idempotency(idempotency_key, chat_id)
            if cached:
                logger.info(f"Idempotent request detected: {idempotency_key}")
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
            # 3. Get chat for tenant_id
            chat = await self.chats_repo.get_chat_by_id(chat_id)
            if not chat:
                yield {"type": "error", "error": "Chat not found"}
                return
            
            tenant_id = str(chat.tenant_id)
            
            # 4. Save user message
            yield {"type": "status", "stage": "saving_user_message"}
            user_message = await self.messages_repo.create_message(
                chat_id=chat_id,
                role="user",
                content={"text": content}
            )
            await self.session.flush()
            await self.session.commit()
            
            user_message_id = str(user_message.id)
            user_message_created_at = self._format_datetime(user_message.created_at)
            logger.info(f"User message created: {user_message_id}")
            yield {"type": "user_message", "message_id": user_message_id, "created_at": user_message_created_at}
            
            # 5. Load agent version (v2)
            yield {"type": "status", "stage": "loading_agent"}
            from app.agents.runtime import AgentProfile
            agent_version = await self.agent_service.resolve_active_version(
                agent_slug=agent_slug,
                use_rag=use_rag
            )
            agent_obj = await self.agent_service.agent_repo.get_by_id(agent_version.agent_id)
            resolved_agent_slug = agent_obj.slug if agent_obj else (agent_slug or "unknown")
            agent_profile = AgentProfile(
                agent_slug=resolved_agent_slug,
                prompt_text=agent_version.prompt,
            )
            logger.info(f"Using agent: {resolved_agent_slug}, version: {agent_version.version}")
            
            # 6. Load context
            yield {"type": "status", "stage": "loading_context"}
            context = await self.load_chat_context(chat_id, limit=8)
            llm_messages = context + [{"role": "user", "content": content}]
            
            # 6.1. Auto-generate chat title if this is the first user message
            # Context is loaded BEFORE current message, so for first message user_messages_count == 0
            user_messages_count = sum(1 for msg in context if msg.get("role") == "user")
            is_first_message = user_messages_count == 0
            logger.info(f"Chat title check: user_messages_count={user_messages_count}, is_first={is_first_message}, chat.name='{chat.name}'")
            if is_first_message and chat.name in (None, "", "New Chat", "Новый чат"):
                logger.info(f"Generating chat title for first message: {content[:100]}")
                generated_title = await self.generate_chat_title(chat_id, content)
                if generated_title:
                    logger.info(f"Generated title: {generated_title}")
                    yield {"type": "chat_title", "title": generated_title}
                else:
                    logger.warning("Failed to generate chat title")
            
            # 7. Create tool context
            tool_ctx = ToolContext(
                tenant_id=tenant_id,
                user_id=user_id,
                chat_id=chat_id,
                request_id=idempotency_key or str(uuid.uuid4())
            )
            
            # 8. Run agent via AgentRuntime (with optional Router)
            yield {"type": "status", "stage": "agent_running"}
            
            assistant_content = ""
            rag_sources = []
            llm_error = None
            
            try:
                # Use Router if enabled, otherwise use legacy flow
                if self.use_router and self.router:
                    async for event_data in self._run_with_router(
                        agent_slug=resolved_agent_slug,
                        user_id=user_id,
                        tenant_id=tenant_id,
                        llm_messages=llm_messages,
                        tool_ctx=tool_ctx,
                        model=model,
                        content=content,
                    ):
                        if event_data.get("type") == "delta":
                            assistant_content += event_data.get("content", "")
                        elif event_data.get("type") == "final_content":
                            assistant_content = event_data.get("content", assistant_content)
                            rag_sources = event_data.get("sources", [])
                        elif event_data.get("type") == "error":
                            llm_error = event_data.get("error")
                        
                        # Forward events to client (except internal ones)
                        if event_data.get("type") != "final_content":
                            yield event_data
                else:
                    # Legacy flow without Router
                    async for event in self.runtime.run(
                        profile=agent_profile,
                        messages=llm_messages,
                        ctx=tool_ctx,
                        model=model,
                        enable_logging=True,
                    ):
                        mapped = self._map_runtime_event(event)
                        if mapped:
                            yield mapped
                        
                        # Collect final content and sources
                        if event.type == RuntimeEventType.DELTA:
                            assistant_content += event.data.get("content", "")
                        elif event.type == RuntimeEventType.FINAL:
                            assistant_content = event.data.get("content", assistant_content)
                            rag_sources = event.data.get("sources", [])
                        elif event.type == RuntimeEventType.ERROR:
                            llm_error = event.data.get("error")
                        
            except Exception as runtime_exc:
                llm_error = str(runtime_exc)
                logger.error(f"AgentRuntime error: {llm_error}", exc_info=True)
                yield {"type": "error", "error": llm_error}
            
            # 9. Commit agent run data (steps, run record) regardless of outcome.
            # RunStore only does flush(), so we must commit here to persist runs.
            try:
                await self.session.commit()
                logger.info("Agent run data committed")
            except Exception as commit_exc:
                logger.error(f"Failed to commit agent run data: {commit_exc}", exc_info=True)
            
            # 10. Save assistant message
            if assistant_content:
                assistant_message = await self.messages_repo.create_message(
                    chat_id=chat_id,
                    role="assistant",
                    content={"text": assistant_content},
                    meta={"rag_sources": rag_sources} if rag_sources else None
                )
                await self.session.flush()
                await self.session.commit()
                
                assistant_message_id = str(assistant_message.id)
                assistant_message_created_at = self._format_datetime(assistant_message.created_at)
                logger.info(f"Assistant message saved: {assistant_message_id}")
                
                # 11. Store idempotency
                if idempotency_key:
                    await self.store_idempotency(
                        idempotency_key,
                        user_message_id,
                        assistant_message_id
                    )
                
                yield {
                    "type": "final", 
                    "message_id": assistant_message_id,
                    "created_at": assistant_message_created_at,
                    "sources": rag_sources
                }
                yield {"type": "status", "stage": "completed"}
            elif not llm_error:
                yield {"type": "error", "error": "Empty response from agent"}
        
        except Exception as e:
            logger.error(f"Error in send_message_stream: {e}", exc_info=True)
            yield {"type": "error", "error": str(e)}
    
    @staticmethod
    def _format_datetime(dt) -> Optional[str]:
        """Normalize datetime to ISO format with Z suffix for consistent API output."""
        if not dt:
            return None
        ts = dt.isoformat()
        if ts.endswith("+00:00"):
            ts = ts[:-6]
        elif ts.endswith("Z"):
            ts = ts[:-1]
        return ts + "Z"
    
    def _map_runtime_event(self, event: RuntimeEvent) -> Optional[Dict[str, Any]]:
        """Map AgentRuntime event to SSE event format"""
        if event.type == RuntimeEventType.STATUS:
            return {"type": "status", "stage": event.data.get("stage")}
        
        elif event.type == RuntimeEventType.THINKING:
            return {"type": "status", "stage": f"thinking_step_{event.data.get('step')}"}
        
        elif event.type == RuntimeEventType.TOOL_CALL:
            return {
                "type": "tool_call",
                "tool": event.data.get("tool"),
                "call_id": event.data.get("call_id"),
                "arguments": event.data.get("arguments")
            }
        
        elif event.type == RuntimeEventType.TOOL_RESULT:
            return {
                "type": "tool_result",
                "tool": event.data.get("tool"),
                "call_id": event.data.get("call_id"),
                "success": event.data.get("success"),
                "data": event.data.get("data")
            }
        
        elif event.type == RuntimeEventType.DELTA:
            return {"type": "delta", "content": event.data.get("content")}
        
        elif event.type == RuntimeEventType.ERROR:
            return {"type": "error", "error": event.data.get("error")}
        
        # FINAL is handled separately for message persistence
        return None
    
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
        """
        Run agent with Router for permission checking and policy enforcement.
        
        This method:
        1. Routes request through AgentRouter
        2. Checks permissions and prerequisites
        3. Runs agent with ExecutionRequest
        """
        try:
            # 1. Route request
            yield {"type": "status", "stage": "routing"}
            
            exec_request = await self.router.route(
                agent_slug=agent_slug,
                user_id=uuid.UUID(user_id),
                tenant_id=uuid.UUID(tenant_id),
                request_text=content[:500],
                allow_partial=False,
            )
            
            logger.info(
                f"Router decision: agent={exec_request.agent_slug}, "
                f"mode={exec_request.mode.value}, "
                f"tools={len(exec_request.available_tools)}"
            )
            
            # Emit routing info
            yield {
                "type": "routing_complete",
                "agent": exec_request.agent_slug,
                "mode": exec_request.mode.value,
                "available_tools": [t.tool_slug for t in exec_request.available_tools],
                "routing_duration_ms": exec_request.routing_duration_ms,
            }
            
            # 2. Enrich tool context with routing data
            if exec_request.tool_instances_map:
                tool_ctx.extra["tool_instances_map"] = exec_request.tool_instances_map
            
            if exec_request.effective_permissions:
                denied_reasons = exec_request.effective_permissions.denied_reasons or {}
                tool_ctx.denied_tools = list(denied_reasons.keys())
                tool_ctx.denied_reasons = denied_reasons
            
            # 3. Check if agent is available
            if exec_request.mode == ExecutionMode.UNAVAILABLE:
                missing = exec_request.missing_requirements
                error_msg = f"Agent unavailable: {missing.to_message()}" if missing else "Agent unavailable"
                yield {"type": "error", "error": error_msg}
                return
            
            # 3. Run agent with ExecutionRequest
            yield {"type": "status", "stage": "agent_executing"}
            
            async for event in self.runtime.run_with_request(
                exec_request=exec_request,
                messages=llm_messages,
                ctx=tool_ctx,
                model=model,
                enable_logging=True,
            ):
                mapped = self._map_runtime_event(event)
                if mapped:
                    yield mapped
                
                # Collect final content for internal use
                if event.type == RuntimeEventType.DELTA:
                    pass  # Handled by caller
                elif event.type == RuntimeEventType.FINAL:
                    yield {
                        "type": "final_content",
                        "content": event.data.get("content", ""),
                        "sources": event.data.get("sources", []),
                    }
                elif event.type == RuntimeEventType.ERROR:
                    yield {"type": "error", "error": event.data.get("error")}
                    
        except AgentUnavailableError as e:
            logger.warning(f"Agent unavailable: {e}")
            yield {
                "type": "error",
                "error": str(e),
                "missing_tools": e.missing.tools if e.missing else [],
                "missing_collections": e.missing.collections if e.missing else [],
                "missing_credentials": e.missing.credentials if e.missing else [],
            }
        except Exception as e:
            logger.error(f"Router error: {e}", exc_info=True)
            yield {"type": "error", "error": f"Routing failed: {str(e)}"}
