"""
Audit Service for tracking operations and changes
"""
from typing import Optional, Dict, Any, List
from uuid import UUID
from datetime import datetime
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.user import AuditLogs, Users
from app.models.rag import DocumentScope

logger = logging.getLogger(__name__)


class AuditService:
    """Service for audit logging operations"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def log_action(
        self,
        actor_user_id: UUID,
        action: str,
        object_type: str,
        object_id: str,
        tenant_id: Optional[UUID] = None,
        scope_snapshot: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
        ip: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> AuditLogs:
        """
        Log an audit action
        
        Args:
            actor_user_id: User performing the action
            action: Type of action (create, update, delete, reindex, etc.)
            object_type: Type of object (document, chunk, user, etc.)
            object_id: ID of the object
            tenant_id: Tenant context (null for global operations)
            scope_snapshot: Document scope at time of action
            meta: Additional metadata
            request_id: Request correlation ID
            ip: Client IP address
            user_agent: Client user agent
        """
        
        audit_log = AuditLogs(
            actor_user_id=actor_user_id,
            tenant_id=tenant_id,
            action=action,
            object_type=object_type,
            object_id=object_id,
            scope_snapshot=scope_snapshot,
            meta=meta or {},
            request_id=request_id,
            ip=ip,
            user_agent=user_agent,
        )
        
        self.session.add(audit_log)
        await self.session.commit()
        await self.session.refresh(audit_log)
        
        logger.info(
            f"Audit logged: {action} {object_type} {object_id} "
            f"by user {actor_user_id} in tenant {tenant_id}"
        )
        
        return audit_log
    
    async def log_document_action(
        self,
        actor_user_id: UUID,
        action: str,
        document_id: UUID,
        document_scope: DocumentScope,
        document_tenant_id: Optional[UUID] = None,
        meta: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
        ip: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> AuditLogs:
        """
        Log document-related action
        """
        return await self.log_action(
            actor_user_id=actor_user_id,
            action=action,
            object_type="document",
            object_id=str(document_id),
            tenant_id=document_tenant_id,
            scope_snapshot=document_scope.value,
            meta=meta,
            request_id=request_id,
            ip=ip,
            user_agent=user_agent,
        )
    
    async def log_user_management_action(
        self,
        actor_user_id: UUID,
        action: str,
        target_user_id: UUID,
        tenant_id: Optional[UUID] = None,
        meta: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
        ip: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> AuditLogs:
        """
        Log user management action
        """
        return await self.log_action(
            actor_user_id=actor_user_id,
            action=action,
            object_type="user",
            object_id=str(target_user_id),
            tenant_id=tenant_id,
            meta=meta,
            request_id=request_id,
            ip=ip,
            user_agent=user_agent,
        )
    
    async def log_reindex_action(
        self,
        actor_user_id: UUID,
        action: str,
        trigger_type: str,
        tenant_id: Optional[UUID] = None,
        document_id: Optional[UUID] = None,
        scope: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
        ip: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> AuditLogs:
        """
        Log reindex operation
        """
        meta = meta or {}
        meta.update({
            "trigger_type": trigger_type,
            "document_id": str(document_id) if document_id else None,
            "scope": scope,
        })
        
        return await self.log_action(
            actor_user_id=actor_user_id,
            action=action,
            object_type="reindex",
            object_id=str(document_id) if document_id else trigger_type,
            tenant_id=tenant_id,
            meta=meta,
            request_id=request_id,
            ip=ip,
            user_agent=user_agent,
        )
    
    async def get_audit_history(
        self,
        actor_user_id: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
        object_type: Optional[str] = None,
        action: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[AuditLogs]:
        """
        Get audit history with filtering
        """
        query = select(AuditLogs)
        
        if actor_user_id:
            query = query.where(AuditLogs.actor_user_id == actor_user_id)
        
        if tenant_id:
            query = query.where(AuditLogs.tenant_id == tenant_id)
        
        if object_type:
            query = query.where(AuditLogs.object_type == object_type)
        
        if action:
            query = query.where(AuditLogs.action == action)
        
        query = query.order_by(AuditLogs.created_at.desc())
        query = query.offset(offset).limit(limit)
        
        result = await self.session.execute(query)
        return result.scalars().all()
    
    async def get_document_audit_history(
        self,
        document_id: UUID,
        limit: int = 50,
    ) -> List[AuditLogs]:
        """
        Get audit history for specific document
        """
        query = (
            select(AuditLogs)
            .where(AuditLogs.object_type == "document")
            .where(AuditLogs.object_id == str(document_id))
            .order_by(AuditLogs.created_at.desc())
            .limit(limit)
        )
        
        result = await self.session.execute(query)
        return result.scalars().all()
    
    async def get_user_audit_history(
        self,
        user_id: UUID,
        as_actor: bool = False,
        as_target: bool = False,
        limit: int = 100,
    ) -> List[AuditLogs]:
        """
        Get audit history for specific user
        
        Args:
            user_id: User ID to search for
            as_actor: Include actions performed by this user
            as_target: Include actions performed on this user
            limit: Maximum number of results
        """
        conditions = []
        
        if as_actor:
            conditions.append(AuditLogs.actor_user_id == user_id)
        
        if as_target:
            conditions.append(
                AuditLogs.object_id == str(user_id)
            ) & (AuditLogs.object_type == "user")
        
        if not conditions:
            return []
        
        query = (
            select(AuditLogs)
            .where(*conditions)
            .order_by(AuditLogs.created_at.desc())
            .limit(limit)
        )
        
        result = await self.session.execute(query)
        return result.scalars().all()