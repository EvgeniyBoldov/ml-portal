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
from app.agents import AgentRuntime, ToolContext, RuntimeEvent, RuntimeEventType
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
    """
    
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
        self.agent_service = AgentService(session)
        self.runtime = AgentRuntime(llm_client)
    
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
            logger.info(f"User message created: {user_message_id}")
            yield {"type": "user_message", "message_id": user_message_id}
            
            # 5. Load agent profile
            yield {"type": "status", "stage": "loading_agent"}
            agent_profile = await self.agent_service.get_agent_profile(
                agent_slug=agent_slug,
                use_rag=use_rag
            )
            logger.info(
                f"Using agent: {agent_profile.agent.slug}, "
                f"tools: {agent_profile.tools}"
            )
            
            # 6. Load context
            yield {"type": "status", "stage": "loading_context"}
            context = await self.load_chat_context(chat_id, limit=20)
            llm_messages = context + [{"role": "user", "content": content}]
            
            # 7. Create tool context
            tool_ctx = ToolContext(
                tenant_id=tenant_id,
                user_id=user_id,
                chat_id=chat_id,
                request_id=idempotency_key or str(uuid.uuid4())
            )
            
            # 8. Run agent via AgentRuntime
            yield {"type": "status", "stage": "agent_running"}
            
            assistant_content = ""
            rag_sources = []
            llm_error = None
            
            try:
                async for event in self.runtime.run(
                    profile=agent_profile,
                    messages=llm_messages,
                    ctx=tool_ctx,
                    model=model
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
            
            # 9. Save assistant message
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
                logger.info(f"Assistant message saved: {assistant_message_id}")
                
                # 10. Store idempotency
                if idempotency_key:
                    await self.store_idempotency(
                        idempotency_key,
                        user_message_id,
                        assistant_message_id
                    )
                
                yield {
                    "type": "final", 
                    "message_id": assistant_message_id,
                    "sources": rag_sources
                }
                yield {"type": "status", "stage": "completed"}
            elif not llm_error:
                yield {"type": "error", "error": "Empty response from agent"}
        
        except Exception as e:
            logger.error(f"Error in send_message_stream: {e}", exc_info=True)
            yield {"type": "error", "error": str(e)}
    
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
