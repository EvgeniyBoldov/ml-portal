"""
Chat streaming service with idempotency, context loading, and RAG support
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
from app.services.rag_search_service import RagSearchService
from app.services.prompt_service import PromptService
from app.core.logging import get_logger
from app.core.idempotency import IdempotencyManager

logger = get_logger(__name__)


class ChatStreamService:
    """Service for streaming chat messages with idempotency and context"""
    
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
        self.prompt_service = PromptService(session)
    
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
        model: Optional[str] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Send message and stream LLM response
        
        Yields events:
        - {"type": "user_message", "message_id": "..."}
        - {"type": "delta", "content": "..."}
        - {"type": "final", "message_id": "..."}
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
            yield {"type": "status", "stage": "saving_user_message"}
            # 3. Save user message
            user_message = await self.messages_repo.create_message(
                chat_id=chat_id,
                role="user",
                content={"text": content}
            )
            await self.session.flush()  # Flush message
            # Commit to persist user message early so it is visible on reloads
            await self.session.commit()
            
            user_message_id = str(user_message.id)
            logger.info(f"User message created: {user_message_id}")
            
            yield {"type": "user_message", "message_id": user_message_id}
            
            # 4. Load context
            yield {"type": "status", "stage": "loading_context"}
            context = await self.load_chat_context(chat_id, limit=20)
            
            # Add current message to context
            llm_messages = context + [{"role": "user", "content": content}]
            
            # Metadata to save with assistant message
            rag_sources = []
            
            # Add RAG context if use_rag=True
            if use_rag:
                try:
                    yield {"type": "status", "stage": "rag_search_started"}
                    # Get tenant_id from chat
                    chat = await self.chats_repo.get_chat_by_id(chat_id)
                    if chat:
                        tenant_id = str(chat.tenant_id)
                        
                        logger.info(f"RAG search requested for tenant {tenant_id}, query: '{content[:100]}...'")
                        
                        # Search in RAG
                        rag_service = RagSearchService()
                        search_results = await rag_service.search(
                            tenant_id=tenant_id,
                            query=content,
                            k=5  # Top 5 results
                        )
                        
                        if search_results:
                            # Prepare sources for metadata and client
                            for result in search_results:
                                rag_sources.append({
                                    "source_id": result.source_id,
                                    "chunk_id": result.chunk_id,
                                    "text": result.text[:200], # snippet
                                    "page": result.page,
                                    "score": result.score,
                                    "meta": result.meta
                                })

                            yield {
                                "type": "status", 
                                "stage": "rag_search_done", 
                                "hits": len(search_results),
                                "sources": rag_sources
                            }
                            
                            # Format RAG context using PromptService
                            rag_context_items = []
                            for result in search_results:
                                # Truncate text to max 500 chars to avoid context overflow
                                text = result.text.strip()
                                if len(text) > 500:
                                    text = text[:497] + "..."
                                
                                item = {
                                    "text": text,
                                    "source_id": result.source_id,
                                    "page": result.page,
                                    "model_hits": None
                                }
                                if result.model_hits:
                                    item["model_hits"] = ", ".join([f"{hit['alias']}({hit['score']:.2f})" for hit in result.model_hits])
                                rag_context_items.append(item)

                            try:
                                rag_context = await self.prompt_service.render(
                                    "chat.rag.system", 
                                    {"results": rag_context_items}
                                )
                            except Exception as e:
                                logger.error(f"Failed to render RAG prompt template: {e}")
                                # Fallback to hardcoded minimal prompt
                                rag_context = "# Контекст из базы знаний\n\n"
                                for item in rag_context_items:
                                    rag_context += f"## Источник\n{item['text']}\n*Документ: {item['source_id']}*\n\n"

                            # Add system message with RAG context before user message
                            llm_messages.insert(-1, {
                                "role": "system",
                                "content": rag_context
                            })
                            
                            logger.info(f"✓ Added RAG context with {len(search_results)} results to LLM prompt")
                        else:
                            yield {"type": "status", "stage": "rag_no_results"}
                            logger.warning(f"RAG search returned no results for query: '{content[:100]}...'")
                            # Optionally notify user that RAG found nothing
                            yield {
                                "type": "rag_status",
                                "status": "no_results",
                                "message": "База знаний не содержит релевантной информации"
                            }
                except Exception as e:
                    yield {"type": "status", "stage": "rag_error"}
                    logger.error(f"✗ Error in RAG search: {e}", exc_info=True)
                    # Continue without RAG if search fails
                    yield {
                        "type": "rag_status",
                        "status": "error",
                        "message": f"Ошибка поиска в базе знаний: {str(e)}"
                    }
            
            # 6. Stream LLM response
            yield {"type": "status", "stage": "generating_answer_started"}
            assistant_content = ""
            llm_error = None
            try:
                async for chunk in self.llm_client.chat_stream(llm_messages, model=model):
                    assistant_content += chunk
                    yield {"type": "delta", "content": chunk}
            except Exception as llm_exc:
                llm_error = str(llm_exc)
                logger.error(f"Error in LLM streaming: {llm_error}", exc_info=True)
                yield {"type": "error", "error": llm_error}
            
            # 7. Save assistant message (if we got any content)
            if assistant_content:
                assistant_message = await self.messages_repo.create_message(
                    chat_id=chat_id,
                    role="assistant",
                    content={"text": assistant_content},
                    meta={"rag_sources": rag_sources} if rag_sources else None
                )
                await self.session.flush()  # Flush message
                # Commit to persist assistant message as soon as it is saved
                await self.session.commit()
                
                assistant_message_id = str(assistant_message.id)
                logger.info(f"Assistant message saved: {assistant_message_id}")
                
                # 8. Store idempotency
                if idempotency_key:
                    await self.store_idempotency(
                        idempotency_key,
                        user_message_id,
                        assistant_message_id
                    )
                
                yield {"type": "final", "message_id": assistant_message_id}
                yield {"type": "status", "stage": "generating_answer_finished"}
            elif not llm_error:
                # Only report empty response if there was no LLM error
                yield {"type": "error", "error": "Empty response from LLM"}
        
        except Exception as e:
            logger.error(f"Error in send_message_stream: {e}", exc_info=True)
            yield {"type": "error", "error": str(e)}
