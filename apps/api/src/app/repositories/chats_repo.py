from __future__ import annotations
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc, asc, cast, String
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime, timezone
import uuid

from app.models.chat import Chats, ChatMessages
from app.repositories.base import TenantRepository, AsyncTenantRepository
from app.core.logging import get_logger

logger = get_logger(__name__)

class ChatsRepository(TenantRepository[Chats]):
    """Enhanced chats repository with comprehensive chat management"""
    
    def __init__(self, session: Session, tenant_id: uuid.UUID, user_id: Optional[uuid.UUID] = None):
        super().__init__(session, Chats, tenant_id, user_id)
    
    def create_chat(self, owner_id: str, name: Optional[str] = None, 
                   tags: Optional[List[str]] = None) -> Chats:
        """Create a new chat"""
        return self.create(
            owner_id=owner_id,
            name=name,
            tags=tags or []
        )
    
    def get_user_chats(self, user_id: str, query: Optional[str] = None, 
                      limit: int = 100) -> List[Chats]:
        """Get chats for a user with optional search"""
        filters = {'owner_id': user_id}
        
        if query:
            # Search in chat names and tags
            chats = self.search(query, ['name'], limit)
            # Filter by owner
            return [chat for chat in chats if chat.owner_id == user_id]
        else:
            return self.list(filters=filters, order_by='-last_message_at', limit=limit)
    
    def get_rag_context(self, chat_id: str, query: str, top_k: int = 3) -> Optional[Dict[str, Any]]:
        """Get RAG context for chat (stub implementation)"""
        # TODO: Implement actual RAG context retrieval
        # This is a stub to prevent API crashes
        logger.debug(f"RAG context requested for chat {chat_id} with query: {query}")
        return None
    
    def update_chat_name(self, chat_id: str, name: str) -> Optional[Chats]:
        """Update chat name"""
        return self.update(chat_id, name=name)
    
    def update_chat_tags(self, chat_id: str, tags: List[str]) -> Optional[Chats]:
        """Update chat tags"""
        return self.update(chat_id, tags=tags)
    
    def update_last_message_at(self, chat_id: str) -> Optional[Chats]:
        """Update last message timestamp"""
        return self.update(chat_id, last_message_at=datetime.now(timezone.utc))
    
    def get_chats_by_tag(self, user_id: str, tag: str) -> List[Chats]:
        """Get chats by tag"""
        # This requires a more complex query for array contains
        stmt = select(Chats).where(
            and_(
                Chats.owner_id == user_id,
                Chats.tags.contains([tag])
            )
        ).order_by(desc(Chats.last_message_at))
        
        result = self.session.execute(stmt)
        return result.scalars().all()
    
    def search_chats(self, user_id: str, query: str, limit: int = 50) -> List[Chats]:
        """Search chats by name or tags"""
        stmt = select(Chats).where(
            and_(
                Chats.owner_id == user_id,
                or_(
                    Chats.name.ilike(f"%{query}%"),
                    Chats.tags.any(query)  # Search in tags array
                )
            )
        ).order_by(desc(Chats.last_message_at)).limit(limit)
        
        result = self.session.execute(stmt)
        return result.scalars().all()


class ChatMessagesRepository(TenantRepository[ChatMessages]):
    """Repository for chat messages"""
    
    def __init__(self, session: Session, tenant_id: uuid.UUID, user_id: Optional[uuid.UUID] = None):
        super().__init__(session, ChatMessages, tenant_id, user_id)
    
    def create_message(self, chat_id: str, role: str, content: Dict[str, Any],
                      model: Optional[str] = None, tokens_in: Optional[int] = None,
                      tokens_out: Optional[int] = None, meta: Optional[Dict[str, Any]] = None) -> ChatMessages:
        """Create a new chat message"""
        message = self.create(
            chat_id=chat_id,
            role=role,
            content=content,
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            meta=meta
        )
        
        # Update chat's last_message_at
        chat_repo = ChatsRepository(self.session)
        chat_repo.update_last_message_at(chat_id)
        
        return message
    
    def get_chat_messages(self, chat_id: str, limit: int = 50, 
                         cursor: Optional[str] = None) -> Tuple[List[ChatMessages], Optional[str]]:
        """Get messages for a chat with cursor-based pagination"""
        stmt = select(ChatMessages).where(ChatMessages.chat_id == chat_id)
        
        # Apply cursor pagination
        if cursor:
            try:
                cursor_id = uuid.UUID(cursor)
                stmt = stmt.where(ChatMessages.id > cursor_id)
            except (ValueError, TypeError):
                pass  # Invalid cursor, ignore
        
        stmt = stmt.order_by(asc(ChatMessages.created_at)).limit(limit + 1)
        
        result = self.session.execute(stmt)
        messages = result.scalars().all()
        
        has_more = len(messages) > limit
        if has_more:
            messages = messages[:-1]
            next_cursor = str(messages[-1].id) if messages else None
        else:
            next_cursor = None
        
        return messages, next_cursor
    
    def get_messages_by_role(self, chat_id: str, role: str, limit: int = 50) -> List[ChatMessages]:
        """Get messages by role"""
        return self.list(
            filters={'chat_id': chat_id, 'role': role},
            order_by='created_at',
            limit=limit
        )
    
    def get_latest_messages(self, chat_id: str, limit: int = 10) -> List[ChatMessages]:
        """Get latest messages for a chat"""
        return self.list(
            filters={'chat_id': chat_id},
            order_by='-created_at',
            limit=limit
        )
    
    def count_messages(self, chat_id: str) -> int:
        """Count messages in a chat"""
        return self.count(filters={'chat_id': chat_id})
    
    def delete_chat_messages(self, chat_id: str) -> int:
        """Delete all messages for a chat"""
        stmt = select(ChatMessages).where(ChatMessages.chat_id == chat_id)
        result = self.session.execute(stmt)
        messages = result.scalars().all()
        
        for message in messages:
            self.session.delete(message)
        
        self.session.flush()
        return len(messages)
    
    def search_messages(self, chat_id: str, query: str, limit: int = 50) -> List[ChatMessages]:
        """Search messages by content"""
        # This would require full-text search in JSON content
        # Search in JSONB content using proper cast to text
        stmt = select(ChatMessages).where(
            and_(
                ChatMessages.chat_id == chat_id,
                cast(ChatMessages.content, String).ilike(f"%{query}%")
            )
        ).order_by(desc(ChatMessages.created_at)).limit(limit)
        
        result = self.session.execute(stmt)
        return result.scalars().all()


# Async versions
class AsyncChatsRepository(AsyncTenantRepository[Chats]):
    """Async chats repository"""
    
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID, user_id: Optional[uuid.UUID] = None):
        super().__init__(session, Chats, tenant_id, user_id)
    
    async def create_chat(self, owner_id: str, name: Optional[str] = None, 
                         tags: Optional[List[str]] = None) -> Chats:
        """Create a new chat"""
        return await self.create(
            owner_id=owner_id,
            name=name,
            tags=tags or []
        )
    
    async def get_user_chats(self, user_id: str, query: Optional[str] = None, 
                            limit: int = 100) -> List[Chats]:
        """Get chats for a user with optional search"""
        filters = {'owner_id': user_id}
        
        if query:
            # Search in chat names
            chats = await self.search(query, ['name'], limit)
            # Filter by owner
            return [chat for chat in chats if chat.owner_id == user_id]
        else:
            return await self.list(filters=filters, order_by='-last_message_at', limit=limit)
    
    async def get_chat_with_messages(self, chat_id: str) -> Optional[Chats]:
        """Get chat with all messages loaded"""
        chat = await self.get_by_id(chat_id)
        if chat:
            # Load messages relationship
            await self.session.refresh(chat)
        return chat


class AsyncChatMessagesRepository(AsyncTenantRepository[ChatMessages]):
    """Async chat messages repository"""
    
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID, user_id: Optional[uuid.UUID] = None):
        super().__init__(session, ChatMessages, tenant_id, user_id)
    
    async def create_message(self, chat_id: str, role: str, content: Dict[str, Any],
                            model: Optional[str] = None, tokens_in: Optional[int] = None,
                            tokens_out: Optional[int] = None, meta: Optional[Dict[str, Any]] = None) -> ChatMessages:
        """Create a new chat message"""
        message = await self.create(
            chat_id=chat_id,
            role=role,
            content=content,
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            meta=meta
        )
        
        # Update chat's last_message_at
        chat_repo = AsyncChatsRepository(self.session)
        await chat_repo.update(chat_id, last_message_at=datetime.now(timezone.utc))
        
        return message
    
    async def get_chat_messages(self, chat_id: str, limit: int = 50, 
                               cursor: Optional[str] = None) -> Tuple[List[ChatMessages], Optional[str]]:
        """Get messages for a chat with cursor-based pagination"""
        stmt = select(ChatMessages).where(ChatMessages.chat_id == chat_id)
        
        # Apply cursor pagination
        if cursor:
            try:
                cursor_id = uuid.UUID(cursor)
                stmt = stmt.where(ChatMessages.id > cursor_id)
            except (ValueError, TypeError):
                pass  # Invalid cursor, ignore
        
        stmt = stmt.order_by(asc(ChatMessages.created_at)).limit(limit + 1)
        
        result = await self.session.execute(stmt)
        messages = result.scalars().all()
        
        has_more = len(messages) > limit
        if has_more:
            messages = messages[:-1]
            next_cursor = str(messages[-1].id) if messages else None
        else:
            next_cursor = None
        
        return messages, next_cursor


# Factory functions
def create_chats_repository(session: Session) -> ChatsRepository:
    """Create chats repository"""
    return ChatsRepository(session)

def create_chat_messages_repository(session: Session) -> ChatMessagesRepository:
    """Create chat messages repository"""
    return ChatMessagesRepository(session)

def create_async_chats_repository(session: AsyncSession) -> AsyncChatsRepository:
    """Create async chats repository"""
    return AsyncChatsRepository(session)

def create_async_chat_messages_repository(session: AsyncSession) -> AsyncChatMessagesRepository:
    """Create async chat messages repository"""
    return AsyncChatMessagesRepository(session)
