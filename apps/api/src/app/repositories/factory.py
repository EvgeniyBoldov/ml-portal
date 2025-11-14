"""
Repository factory with tenant isolation and dependency injection
"""
from __future__ import annotations
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends
import uuid

from app.repositories.base import AsyncTenantRepository
from app.repositories.chats_repo import AsyncChatsRepository, AsyncChatMessagesRepository
from app.repositories.idempotency_repo import AsyncIdempotencyRepository
from app.repositories.documents_repo import AsyncRAGDocumentsRepository, AsyncRAGChunksRepository
from app.repositories.users_repo import AsyncUsersRepository
from app.repositories.analyze_repo import AnalyzeRepo
from app.repositories.rag_ingest_repos import AsyncSourceRepository, AsyncChunkRepository, AsyncEmbStatusRepository, AsyncModelRegistryRepository
from app.repositories.rag_status_repo import AsyncRAGStatusRepository
from app.repositories.tenants_repo import AsyncTenantsRepository
from app.api.deps import db_uow, get_current_user
from app.core.security import UserCtx
from app.core.logging import get_logger

logger = get_logger(__name__)


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
    
    def get_users_repository(self) -> AsyncUsersRepository:
        """Get users repository without tenant isolation"""
        if 'users' not in self._repositories:
            self._repositories['users'] = AsyncUsersRepository(self.session)
        return self._repositories['users']
    
    def get_idempotency_repository(self) -> AsyncIdempotencyRepository:
        """Get async idempotency repository with tenant isolation"""
        if 'idempotency' not in self._repositories:
            self._repositories['idempotency'] = AsyncIdempotencyRepository(self.session, self.tenant_id, self.user_id)
        return self._repositories['idempotency']
    
    
    def get_source_repository(self) -> AsyncSourceRepository:
        """Get async source repository with tenant isolation"""
        if 'source' not in self._repositories:
            self._repositories['source'] = AsyncSourceRepository(self.session, self.tenant_id, self.user_id)
        return self._repositories['source']
    
    def get_chunk_repository(self) -> AsyncChunkRepository:
        """Get async chunk repository with tenant isolation"""
        if 'chunk' not in self._repositories:
            self._repositories['chunk'] = AsyncChunkRepository(self.session, self.tenant_id, self.user_id)
        return self._repositories['chunk']
    
    def get_emb_status_repository(self) -> AsyncEmbStatusRepository:
        """Get async embedding status repository with tenant isolation"""
        if 'emb_status' not in self._repositories:
            self._repositories['emb_status'] = AsyncEmbStatusRepository(self.session, self.tenant_id, self.user_id)
        return self._repositories['emb_status']
    
    def get_model_registry_repository(self) -> AsyncModelRegistryRepository:
        """Get async model registry repository with tenant isolation"""
        if 'model_registry' not in self._repositories:
            self._repositories['model_registry'] = AsyncModelRegistryRepository(self.session, self.tenant_id, self.user_id)
        return self._repositories['model_registry']
    
    async def get_emb_status_by_source_id(self, source_id: uuid.UUID):
        """Get embedding statuses by source ID"""
        emb_status_repo = self.get_emb_status_repository()
        return await emb_status_repo.get_by_source_id(source_id)
    
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
            filename=kwargs.get('filename', name),
            title=name,
            **{k: v for k, v in kwargs.items() if k != 'filename'}
        )
    
    async def get_rag_documents(self, user_id: uuid.UUID, status: Optional[str] = None, 
                              search: Optional[str] = None, limit: int = 50, offset: int = 0):
        """Get RAG documents with filtering"""
        rag_repo = self.get_rag_documents_repository()
        return await rag_repo.get_user_documents(
            self.tenant_id,
            user_id,
            status,
            search,
            limit,
            offset
        )
    
    async def count_rag_documents(self, user_id: uuid.UUID, status: Optional[str] = None, 
                                search: Optional[str] = None):
        """Count RAG documents with filtering"""
        rag_repo = self.get_rag_documents_repository()
        return await rag_repo.count_user_documents(
            self.tenant_id,
            user_id,
            status,
            search
        )
    
    async def get_rag_document_by_id(self, doc_id: uuid.UUID) -> Optional[Any]:
        """Get RAG document by ID with tenant isolation"""
        rag_repo = self.get_rag_documents_repository()
        return await rag_repo.get_by_id(self.tenant_id, doc_id)
    
    async def delete_rag_document(self, doc_id: uuid.UUID) -> bool:
        """Delete RAG document and clean up all related data"""
        try:
            # First, clean up status nodes
            status_repo = self.get_rag_status_repository()
            await status_repo.delete_nodes_by_doc_id(doc_id)
            
            # Then delete the document itself
            rag_repo = self.get_rag_documents_repository()
            success = await rag_repo.delete(self.tenant_id, doc_id)
            
            return success
        except Exception as e:
            logger.error(f"Failed to delete RAG document {doc_id}: {e}")
            raise
    
    def get_tenants_repository(self) -> AsyncTenantsRepository:
        """Get tenants repository"""
        if 'tenants' not in self._repositories:
            self._repositories['tenants'] = AsyncTenantsRepository(self.session)
        return self._repositories['tenants']
    
    def get_rag_status_repository(self) -> AsyncRAGStatusRepository:
        """Get RAG status repository"""
        if 'rag_status' not in self._repositories:
            self._repositories['rag_status'] = AsyncRAGStatusRepository(self.session, self.tenant_id, self.user_id)
        return self._repositories['rag_status']
    
    # def get_rag_ingest_repository(self) -> AsyncRAGIngestRepository:
    #     """Get RAG ingest run repository"""
    #     if "rag_ingest" not in self._repositories:
    #         self._repositories["rag_ingest"] = AsyncRAGIngestRepository(self.session, self.tenant_id)
    #     return self._repositories["rag_ingest"]


# Dependency injection functions
def get_async_repository_factory(
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user)
) -> AsyncRepositoryFactory:
    """Get async repository factory with tenant isolation from current user"""
    # Extract tenant_id from user context - CRITICAL: no defaults in production
    tenant_id = _extract_tenant_id_from_user(user)
    
    return AsyncRepositoryFactory(session, tenant_id, user.id)


def _extract_tenant_id_from_user(user: UserCtx) -> uuid.UUID:
    """Extract tenant_id from user context with validation"""
    from app.core.config import is_local, get_settings
    
    # Check if user has tenant_ids list
    if user.tenant_ids and len(user.tenant_ids) > 0:
        try:
            return uuid.UUID(user.tenant_ids[0])  # Use first tenant
        except ValueError:
            raise ValueError(f"Invalid tenant_id format: {user.tenant_ids[0]}")
    
    # CRITICAL: In non-local environments, users MUST have tenant_ids
    if not is_local():
        raise ValueError(f"User {user.id} has no tenant_ids. This is not allowed in {get_settings().ENV} environment.")
    
    # For local development only, create a default tenant_id
    logger.warning(f"User {user.id} has no valid tenant_id. Using default tenant for local development.")
    return uuid.UUID("fb983a10-c5f8-4840-a9d3-856eea0dc729")  # Use existing tenant for development


