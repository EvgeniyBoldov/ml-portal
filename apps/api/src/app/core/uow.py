"""
Unit of Work pattern for managing transactions
"""
from __future__ import annotations
from typing import Optional, Dict, Any, TypeVar, Generic
from contextlib import contextmanager, asynccontextmanager
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import uuid

from app.core.logging import get_logger

logger = get_logger(__name__)

T = TypeVar('T')


class UnitOfWork:
    """Unit of Work for managing transactions"""
    
    def __init__(self, session: Session):
        self.session = session
        self._repositories: Dict[str, Any] = {}
    
    def __enter__(self):
        """Enter transaction context"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit transaction context"""
        if exc_type is not None:
            logger.error(f"Transaction failed: {exc_val}")
            self.session.rollback()
        else:
            self.session.commit()
    
    def get_repository(self, repo_type: type, *args, **kwargs):
        """Get or create repository instance"""
        repo_name = repo_type.__name__
        if repo_name not in self._repositories:
            self._repositories[repo_name] = repo_type(self.session, *args, **kwargs)
        return self._repositories[repo_name]
    
    def commit(self):
        """Commit transaction"""
        self.session.commit()
    
    def rollback(self):
        """Rollback transaction"""
        self.session.rollback()
    
    def flush(self):
        """Flush pending changes"""
        self.session.flush()


class AsyncUnitOfWork:
    """Async Unit of Work for managing transactions"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self._repositories: Dict[str, Any] = {}
    
    async def __aenter__(self):
        """Enter async transaction context"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit async transaction context"""
        if exc_type is not None:
            logger.error(f"Async transaction failed: {exc_val}")
            await self.session.rollback()
        else:
            await self.session.commit()
    
    def get_repository(self, repo_type: type, *args, **kwargs):
        """Get or create repository instance"""
        repo_name = repo_type.__name__
        if repo_name not in self._repositories:
            self._repositories[repo_name] = repo_type(self.session, *args, **kwargs)
        return self._repositories[repo_name]
    
    async def commit(self):
        """Commit transaction"""
        await self.session.commit()
    
    async def rollback(self):
        """Rollback transaction"""
        await self.session.rollback()
    
    async def flush(self):
        """Flush pending changes"""
        await self.session.flush()


# Example usage patterns
class ChatService:
    """Example service using Unit of Work"""
    
    def __init__(self, uow: UnitOfWork):
        self.uow = uow
    
    def create_chat_with_message(self, tenant_id: uuid.UUID, owner_id: uuid.UUID, 
                                chat_name: str, initial_message: str) -> Dict[str, Any]:
        """Create chat and initial message in single transaction"""
        with self.uow:
            # Get repositories
            chats_repo = self.uow.get_repository(ChatsRepository)
            messages_repo = self.uow.get_repository(ChatMessagesRepository)
            
            # Create chat
            chat = chats_repo.create_chat(tenant_id, owner_id, chat_name)
            
            # Create initial message
            message = messages_repo.create_message(
                tenant_id=tenant_id,
                chat_id=chat.id,
                role="user",
                content={"text": initial_message}
            )
            
            # Update chat's last_message_at
            chats_repo.update_last_message_at(tenant_id, chat.id, message.created_at)
            
            return {
                "chat_id": str(chat.id),
                "message_id": str(message.id),
                "created_at": chat.created_at.isoformat()
            }


class AsyncChatService:
    """Example async service using Unit of Work"""
    
    def __init__(self, uow: AsyncUnitOfWork):
        self.uow = uow
    
    async def create_chat_with_message(self, tenant_id: uuid.UUID, owner_id: uuid.UUID, 
                                     chat_name: str, initial_message: str) -> Dict[str, Any]:
        """Create chat and initial message in single transaction"""
        async with self.uow:
            # Get repositories
            chats_repo = self.uow.get_repository(AsyncChatsRepository)
            messages_repo = self.uow.get_repository(AsyncChatMessagesRepository)
            
            # Create chat
            chat = await chats_repo.create_chat(tenant_id, owner_id, chat_name)
            
            # Create initial message
            message = await messages_repo.create_message(
                tenant_id=tenant_id,
                chat_id=chat.id,
                role="user",
                content={"text": initial_message}
            )
            
            return {
                "chat_id": str(chat.id),
                "message_id": str(message.id),
                "created_at": chat.created_at.isoformat()
            }


# Import the repository classes (would be imported from actual modules)
class ChatsRepository:
    def __init__(self, session: Session):
        self.session = session
    
    def create_chat(self, tenant_id: uuid.UUID, owner_id: uuid.UUID, name: str):
        # Implementation would go here
        pass
    
    def update_last_message_at(self, tenant_id: uuid.UUID, chat_id: uuid.UUID, timestamp):
        # Implementation would go here
        pass


class ChatMessagesRepository:
    def __init__(self, session: Session):
        self.session = session
    
    def create_message(self, tenant_id: uuid.UUID, chat_id: uuid.UUID, role: str, content: dict):
        # Implementation would go here
        pass


class AsyncChatsRepository:
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create_chat(self, tenant_id: uuid.UUID, owner_id: uuid.UUID, name: str):
        # Implementation would go here
        pass


class AsyncChatMessagesRepository:
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create_message(self, tenant_id: uuid.UUID, chat_id: uuid.UUID, role: str, content: dict):
        # Implementation would go here
        pass
