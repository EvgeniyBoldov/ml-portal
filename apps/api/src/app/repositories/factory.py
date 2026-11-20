"""
Repository factory with tenant isolation and dependency injection
"""
from __future__ import annotations
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends, HTTPException
from sqlalchemy import select
import uuid

from app.repositories.chats_repo import AsyncChatsRepository, AsyncChatMessagesRepository
from app.repositories.documents_repo import AsyncRAGDocumentsRepository
from app.repositories.rag_ingest_repos import AsyncSourceRepository
from app.repositories.rag_status_repo import AsyncRAGStatusRepository
from app.api.deps import db_uow, get_current_user
from app.core.security import UserCtx
from app.core.logging import get_logger
from app.core.config import is_local
from app.models.tenant import UserTenants, Tenants

logger = get_logger(__name__)


class AsyncRepositoryFactory:
    """Async factory for creating repositories with tenant isolation"""
    
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID, user_id: Optional[uuid.UUID] = None):
        self.session = session
        self.tenant_id = tenant_id
        if user_id is None:
            self.user_id = None
        elif isinstance(user_id, uuid.UUID):
            self.user_id = user_id
        else:
            self.user_id = uuid.UUID(str(user_id))
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
    
    
    def get_source_repository(self) -> AsyncSourceRepository:
        """Get async source repository with tenant isolation"""
        if 'source' not in self._repositories:
            self._repositories['source'] = AsyncSourceRepository(self.session, self.tenant_id, self.user_id)
        return self._repositories['source']
    
    
    
    
    async def create_chat(self, owner_id: uuid.UUID, name: Optional[str] = None, tags: Optional[list] = None):
        """Create chat with tenant isolation"""
        chats_repo = self.get_chats_repository()
        return await chats_repo.create_chat(owner_id, name, tags)
    
    
    async def get_rag_document_by_id(self, doc_id: uuid.UUID) -> Optional[Any]:
        """Get RAG document by ID with tenant isolation"""
        rag_repo = self.get_rag_documents_repository()
        # AsyncTenantRepository.get_by_id expects (tenant_id, id)
        return await rag_repo.get_by_id(tenant_id=self.tenant_id, id=doc_id)
    
    async def delete_rag_document(self, doc_id: uuid.UUID) -> bool:
        """Delete RAG document and clean up all related data"""
        try:
            # First, clean up status nodes
            status_repo = self.get_rag_status_repository()
            await status_repo.delete_nodes_by_doc_id(doc_id)
            
            # Then delete the document itself
            rag_repo = self.get_rag_documents_repository()
            success = await rag_repo.delete(tenant_id=self.tenant_id, id=doc_id)
            
            return success
        except Exception as e:
            logger.error(f"Failed to delete RAG document {doc_id}: {e}")
            raise
    
    
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
async def get_async_repository_factory(
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user)
) -> AsyncRepositoryFactory:
    """Get async repository factory with tenant isolation from current user"""
    # Extract tenant_id from user context - CRITICAL: no defaults in production
    tenant_id = await _extract_tenant_id_from_user(session, user)
    
    return AsyncRepositoryFactory(session, tenant_id, user.id)


async def _extract_tenant_id_from_user(session: AsyncSession, user: UserCtx) -> uuid.UUID:
    """Extract tenant_id from user context with validation"""
    # 1) Try tenant IDs from token first.
    for raw_tenant_id in (user.tenant_ids or []):
        try:
            return uuid.UUID(str(raw_tenant_id))
        except (TypeError, ValueError):
            continue

    # 2) Fallback: load tenant mapping from DB (handles stale JWT without tenant_ids).
    try:
        user_id = uuid.UUID(str(user.id))
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid user id in token")

    tenant_result = await session.execute(
        select(UserTenants.tenant_id)
        .join(Tenants, Tenants.id == UserTenants.tenant_id)
        .where(
            UserTenants.user_id == user_id,
            Tenants.is_active.is_(True),
            Tenants.lifecycle_status != "deprecated",
        )
        .order_by(UserTenants.is_default.desc(), Tenants.created_at.asc())
        .limit(1)
    )
    mapped_tenant_id = tenant_result.scalar_one_or_none()
    if mapped_tenant_id:
        user.tenant_ids = [str(mapped_tenant_id)]
        return mapped_tenant_id

    # 3) Local/dev fallback only: pick first active tenant.
    if is_local():
        fallback_result = await session.execute(
            select(Tenants.id)
            .where(
                Tenants.is_active.is_(True),
                Tenants.lifecycle_status != "deprecated",
            )
            .order_by(Tenants.created_at.asc())
            .limit(1)
        )
        fallback_tenant_id = fallback_result.scalar_one_or_none()
        if fallback_tenant_id:
            logger.warning(
                "User %s has no tenant mapping; using fallback tenant %s in local mode",
                user.id,
                fallback_tenant_id,
            )
            user.tenant_ids = [str(fallback_tenant_id)]
            return fallback_tenant_id

    raise HTTPException(
        status_code=400,
        detail=f"User {user.id} has no tenant assigned. Re-login or assign a tenant.",
    )
