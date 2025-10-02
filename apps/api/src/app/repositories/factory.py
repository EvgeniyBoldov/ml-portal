"""
Repository factory with tenant isolation and dependency injection
"""
from __future__ import annotations
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends
import uuid

from app.repositories.base import TenantRepository, AsyncTenantRepository
from app.repositories.chats_repo import ChatsRepository, ChatMessagesRepository, AsyncChatsRepository, AsyncChatMessagesRepository
from app.repositories.idempotency_repo import IdempotencyRepository, AsyncIdempotencyRepository
from app.repositories.rag_repo import RAGDocumentsRepository, RAGChunksRepository, AsyncRAGDocumentsRepository, AsyncRAGChunksRepository
from app.repositories.users_repo import UsersRepository
from app.repositories.analyze_repo import AnalyzeRepo
from app.core.security import UserCtx
from app.core.logging import get_logger

logger = get_logger(__name__)


class RepositoryFactory:
    """Factory for creating repositories with tenant isolation"""
    
    def __init__(self, session: Session, tenant_id: uuid.UUID, user_id: Optional[uuid.UUID] = None):
        self.session = session
        self.tenant_id = tenant_id
        self.user_id = user_id
        self._repositories: Dict[str, Any] = {}
    
    def get_chats_repository(self) -> ChatsRepository:
        """Get chats repository with tenant isolation"""
        if 'chats' not in self._repositories:
            self._repositories['chats'] = ChatsRepository(self.session, self.tenant_id, self.user_id)
        return self._repositories['chats']
    
    def get_chat_messages_repository(self) -> ChatMessagesRepository:
        """Get chat messages repository with tenant isolation"""
        if 'chat_messages' not in self._repositories:
            self._repositories['chat_messages'] = ChatMessagesRepository(self.session, self.tenant_id, self.user_id)
        return self._repositories['chat_messages']
    
    def get_rag_documents_repository(self) -> RAGDocumentsRepository:
        """Get RAG documents repository with tenant isolation"""
        if 'rag_documents' not in self._repositories:
            self._repositories['rag_documents'] = RAGDocumentsRepository(self.session, self.tenant_id, self.user_id)
        return self._repositories['rag_documents']
    
    def get_rag_chunks_repository(self) -> RAGChunksRepository:
        """Get RAG chunks repository with tenant isolation"""
        if 'rag_chunks' not in self._repositories:
            self._repositories['rag_chunks'] = RAGChunksRepository(self.session, self.tenant_id, self.user_id)
        return self._repositories['rag_chunks']
    
    def get_users_repository(self) -> UsersRepository:
        """Get users repository without tenant isolation"""
        if 'users' not in self._repositories:
            self._repositories['users'] = UsersRepository(self.session)
        return self._repositories['users']
    
    def get_analyze_repository(self) -> AnalyzeRepo:
        """Get analyze repository"""
        if 'analyze' not in self._repositories:
            self._repositories['analyze'] = AnalyzeRepo(self.session, self.tenant_id, self.user_id)
        return self._repositories['analyze']
    
    def get_idempotency_repository(self) -> IdempotencyRepository:
        """Get idempotency repository with tenant isolation"""
        if 'idempotency' not in self._repositories:
            self._repositories['idempotency'] = IdempotencyRepository(self.session, self.tenant_id, self.user_id)
        return self._repositories['idempotency']
    
    def create_chat(self, owner_id: uuid.UUID, name: Optional[str] = None, tags: Optional[list] = None):
        """Create chat with tenant isolation"""
        chats_repo = self.get_chats_repository()
        return chats_repo.create_chat(owner_id, name, tags)
    
    def create_chat_message(self, chat_id: uuid.UUID, role: str, content: Dict[str, Any], **kwargs):
        """Create chat message with tenant isolation"""
        messages_repo = self.get_chat_messages_repository()
        return messages_repo.create_message(chat_id, role, content, **kwargs)
    
    def create_rag_document(self, uploaded_by: uuid.UUID, name: str, **kwargs):
        """Create RAG document with tenant isolation"""
        rag_repo = self.get_rag_documents_repository()
        return rag_repo.create_document(
            user_id=uploaded_by,
            filename=name,
            **kwargs
        )
    
    def get_user_chats(self, owner_id: uuid.UUID, limit: int = 50, cursor: Optional[str] = None):
        """Get user chats with tenant isolation"""
        chats_repo = self.get_chats_repository()
        return chats_repo.get_user_chats(owner_id, limit, cursor)
    
    def get_chat_messages(self, chat_id: uuid.UUID, limit: int = 100, cursor: Optional[str] = None):
        """Get chat messages with tenant isolation"""
        messages_repo = self.get_chat_messages_repository()
        return messages_repo.get_chat_messages(chat_id, limit, cursor)


class AsyncRepositoryFactory:
    """Async factory for creating repositories with tenant isolation"""
    
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID, user_id: Optional[uuid.UUID] = None):
        self.session = session
        self.tenant_id = tenant_id
        self.user_id = user_id
        self._repositories: Dict[str, Any] = {}
    
    def get_chats_repository(self) -> AsyncChatsRepository:
        """Get async chats repository with tenant isolation"""
        if 'chats' not in self._repositories:
            self._repositories['chats'] = AsyncChatsRepository(self.session, self.tenant_id, self.user_id)
        return self._repositories['chats']
    
    def get_chat_messages_repository(self) -> AsyncChatMessagesRepository:
        """Get async chat messages repository with tenant isolation"""
        if 'chat_messages' not in self._repositories:
            self._repositories['chat_messages'] = AsyncChatMessagesRepository(self.session, self.tenant_id, self.user_id)
        return self._repositories['chat_messages']
    
    def get_rag_documents_repository(self) -> AsyncRAGDocumentsRepository:
        """Get async RAG documents repository with tenant isolation"""
        if 'rag_documents' not in self._repositories:
            self._repositories['rag_documents'] = AsyncRAGDocumentsRepository(self.session, self.tenant_id, self.user_id)
        return self._repositories['rag_documents']
    
    def get_rag_chunks_repository(self) -> AsyncRAGChunksRepository:
        """Get async RAG chunks repository with tenant isolation"""
        if 'rag_chunks' not in self._repositories:
            self._repositories['rag_chunks'] = AsyncRAGChunksRepository(self.session, self.tenant_id, self.user_id)
        return self._repositories['rag_chunks']
    
    def get_idempotency_repository(self) -> AsyncIdempotencyRepository:
        """Get async idempotency repository with tenant isolation"""
        if 'idempotency' not in self._repositories:
            self._repositories['idempotency'] = AsyncIdempotencyRepository(self.session, self.tenant_id, self.user_id)
        return self._repositories['idempotency']
    
    async def create_chat(self, owner_id: uuid.UUID, name: Optional[str] = None, tags: Optional[list] = None):
        """Create chat with tenant isolation"""
        chats_repo = self.get_chats_repository()
        return await chats_repo.create_chat(owner_id, name, tags)
    
    async def create_chat_message(self, chat_id: uuid.UUID, role: str, content: Dict[str, Any], **kwargs):
        """Create chat message with tenant isolation"""
        messages_repo = self.get_chat_messages_repository()
        return await messages_repo.create_message(chat_id, role, content, **kwargs)
    
    async def create_rag_document(self, uploaded_by: uuid.UUID, name: str, **kwargs):
        """Create RAG document with tenant isolation"""
        rag_repo = self.get_rag_documents_repository()
        return await rag_repo.create_document(
            user_id=uploaded_by,
            filename=name,
            **kwargs
        )


# Dependency injection functions
# def get_repository_factory(
#     session: Session = Depends(db_session),
#     user: UserCtx = Depends(get_current_user)
# ) -> RepositoryFactory:
#     """Get repository factory with tenant isolation from current user"""
#     # Extract tenant_id from user context - CRITICAL: no defaults in production
#     tenant_id = _extract_tenant_id_from_user(user)
#     
#     return RepositoryFactory(session, tenant_id, user.id)


# def get_async_repository_factory(
#     session: AsyncSession = Depends(get_async_db_session),
#     user: UserCtx = Depends(get_current_user)
# ) -> AsyncRepositoryFactory:
#     """Get async repository factory with tenant isolation from current user"""
#     # Extract tenant_id from user context - CRITICAL: no defaults in production
#     tenant_id = _extract_tenant_id_from_user(user)
#     
#     return AsyncRepositoryFactory(session, tenant_id, user.id)


def _extract_tenant_id_from_user(user: UserCtx) -> uuid.UUID:
    """Extract tenant_id from user context with validation"""
    # Check if user has tenant_id attribute
    if hasattr(user, 'tenant_id') and user.tenant_id is not None:
        return user.tenant_id
    
    # Check if user has tenant_ids list
    if hasattr(user, 'tenant_ids') and user.tenant_ids:
        if isinstance(user.tenant_ids, list) and len(user.tenant_ids) > 0:
            return user.tenant_ids[0]  # Use first tenant
    
    # CRITICAL: In production, this should never happen
    # All users must have a valid tenant_id
    raise ValueError(
        f"User {user.id} has no valid tenant_id. "
        "All users must be associated with at least one tenant."
    )


# Import dependencies
from fastapi import Depends
from app.api.deps import db_session, get_current_user
