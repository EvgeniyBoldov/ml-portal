from __future__ import annotations
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc, asc, cast, String
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime, timezone
import uuid

from app.models.chat import Chats, ChatMessages
from app.repositories.base import AsyncTenantRepository
from app.core.logging import get_logger
from app.services.chat_visibility import is_sandbox_upload_chat, visible_chat_clause

logger = get_logger(__name__)


class AsyncChatsRepository(AsyncTenantRepository[Chats]):
    """Async chats repository"""
    
    def __init__(self, session: AsyncSession, tenant_id: Optional[uuid.UUID], user_id: Optional[uuid.UUID] = None):
        super().__init__(session, Chats, tenant_id, user_id)
    
    async def create_chat(self, owner_id: str, name: Optional[str] = None,
                         tags: Optional[List[str]] = None) -> Chats:
        """Create a new chat"""
        chat = Chats(owner_id=owner_id, name=name, tags=tags or [])
        self.session.add(chat)
        await self.session.flush()
        return chat
    
    async def get_user_chats(
        self,
        user_id: str,
        query: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        include_internal: bool = False,
    ) -> List[Chats]:
        """Get chats for a user with optional search"""
        stmt = select(Chats).where(
            Chats.owner_id == user_id
        ).order_by(desc(Chats.created_at))
        if not include_internal:
            stmt = stmt.where(visible_chat_clause(Chats))
        
        if query:
            search_term = f"%{query}%"
            stmt = stmt.where(
                or_(
                    Chats.name.ilike(search_term),
                    Chats.tags.op('?')(query)
                )
            )
        
        stmt = stmt.offset(offset).limit(limit)
        
        result = await self.session.execute(stmt)
        chats = list(result.scalars().all())
        if include_internal:
            return chats
        return [chat for chat in chats if not is_sandbox_upload_chat(chat)]
    
    async def get_chat_by_id(self, chat_id: str, include_internal: bool = False) -> Optional[Chats]:
        """Get chat by ID"""
        result = await self.session.execute(
            select(Chats).where(Chats.id == chat_id)
        )
        chat = result.scalar_one_or_none()
        if not chat:
            return None
        if self.user_id and chat.owner_id != self.user_id:
            return None
        if not include_internal and is_sandbox_upload_chat(chat):
            return None
        return chat
    
    async def update_chat(self, chat_id: str, **kwargs) -> Optional[Chats]:
        """Update chat"""
        chat = await self.get_chat_by_id(chat_id)
        if chat:
            for key, value in kwargs.items():
                if hasattr(chat, key):
                    setattr(chat, key, value)
            chat.updated_at = datetime.now(timezone.utc)
            await self.session.flush()
        return chat
    
    async def delete_chat(self, chat_id: str) -> bool:
        """Delete chat"""
        chat = await self.get_chat_by_id(chat_id)
        if chat:
            await self.session.delete(chat)
            await self.session.flush()
            return True
        return False


class AsyncChatMessagesRepository(AsyncTenantRepository[ChatMessages]):
    """Async chat messages repository"""
    
    def __init__(self, session: AsyncSession, tenant_id: Optional[uuid.UUID], user_id: Optional[uuid.UUID] = None):
        super().__init__(session, ChatMessages, tenant_id, user_id)
    
    async def create_message(self, chat_id: str, role: str, content: Dict[str, Any], 
                           meta: Optional[Dict[str, Any]] = None, **kwargs) -> ChatMessages:
        """Create a new chat message"""
        message = ChatMessages(
            chat_id=chat_id,
            role=role,
            content=content,
            meta=meta or {},
            **kwargs,
        )
        self.session.add(message)
        await self.session.flush()
        return message
    
    async def get_chat_messages(
        self, 
        chat_id: str, 
        limit: int = 100, 
        offset: int = 0,
        cursor: Optional[str] = None
    ) -> List[ChatMessages]:
        """
        Get messages for a chat with keyset pagination
        
        Args:
            chat_id: Chat ID
            limit: Max number of messages to return
            offset: Offset for backward compatibility (deprecated)
            cursor: ISO timestamp cursor for keyset pagination
        """
        query = select(ChatMessages).where(
            ChatMessages.chat_id == chat_id
        )
        
        # Use keyset pagination if cursor provided
        if cursor:
            try:
                cursor_dt = datetime.fromisoformat(cursor.replace('Z', '+00:00'))
                query = query.where(ChatMessages.created_at > cursor_dt)
            except (ValueError, AttributeError):
                # Fallback to offset if cursor is invalid
                query = query.offset(offset)
        else:
            query = query.offset(offset)
        
        query = query.order_by(asc(ChatMessages.created_at)).limit(limit)
        
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_recent_chat_messages(
        self,
        chat_id: str,
        limit: int = 20,
    ) -> List[ChatMessages]:
        """Get most recent messages in chronological order (oldest->newest within the tail)."""
        query = (
            select(ChatMessages)
            .where(ChatMessages.chat_id == chat_id)
            .order_by(desc(ChatMessages.created_at))
            .limit(limit)
        )
        result = await self.session.execute(query)
        latest_desc = list(result.scalars().all())
        latest_desc.reverse()
        return latest_desc
    
    async def get_message_by_id(self, message_id: str) -> Optional[ChatMessages]:
        """Get message by ID"""
        result = await self.session.execute(
            select(ChatMessages).where(ChatMessages.id == message_id)
        )
        message = result.scalar_one_or_none()
        if not message:
            return None
        return message
    
    async def update_message(self, message_id: str, **kwargs) -> Optional[ChatMessages]:
        """Update message"""
        message = await self.get_message_by_id(message_id)
        if message:
            for key, value in kwargs.items():
                if hasattr(message, key):
                    setattr(message, key, value)
            message.updated_at = datetime.now(timezone.utc)
            await self.session.flush()
        return message
    
    async def delete_message(self, message_id: str) -> bool:
        """Delete message"""
        message = await self.get_message_by_id(message_id)
        if message:
            await self.session.delete(message)
            await self.session.flush()
            return True
        return False
