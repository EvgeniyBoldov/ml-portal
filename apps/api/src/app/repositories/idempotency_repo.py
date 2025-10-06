"""
Idempotency repository for managing idempotency keys
"""
from __future__ import annotations
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, delete
from datetime import datetime, timezone, timedelta
import uuid
import hashlib
import json

from repositories.base import TenantRepository, AsyncTenantRepository
from core.logging import get_logger

logger = get_logger(__name__)

# Idempotency model (would be defined in models)
class IdempotencyKey:
    """Idempotency key model"""
    def __init__(self, **kwargs):
        self.id = kwargs.get('id')
        self.tenant_id = kwargs.get('tenant_id')
        self.user_id = kwargs.get('user_id')
        self.key = kwargs.get('key')
        self.req_hash = kwargs.get('req_hash')
        self.response_status = kwargs.get('response_status')
        self.response_body = kwargs.get('response_body')
        self.response_headers = kwargs.get('response_headers')
        self.ttl_at = kwargs.get('ttl_at')
        self.created_at = kwargs.get('created_at')


class IdempotencyRepository(TenantRepository[IdempotencyKey]):
    """Idempotency repository with tenant isolation"""
    
    def __init__(self, session: Session, tenant_id: uuid.UUID, user_id: Optional[uuid.UUID] = None):
        super().__init__(session, IdempotencyKey, tenant_id, user_id)
    
    def _hash_request(self, method: str, path: str, body: Optional[Dict[str, Any]] = None) -> str:
        """Generate hash for request"""
        request_data = {
            'method': method,
            'path': path,
            'body': body or {}
        }
        request_str = json.dumps(request_data, sort_keys=True)
        return hashlib.sha256(request_str.encode()).hexdigest()
    
    def store_response(self, tenant_id: uuid.UUID, user_id: Optional[uuid.UUID], 
                      key: str, method: str, path: str, body: Optional[Dict[str, Any]],
                      response_status: int, response_body: Optional[Dict[str, Any]] = None,
                      response_headers: Optional[Dict[str, str]] = None,
                      ttl_at: Optional[datetime] = None) -> IdempotencyKey:
        """Store idempotency response with proper TTL calculation"""
        req_hash = self._hash_request(method, path, body)
        
        # Use provided ttl_at or calculate with proper timedelta
        if ttl_at is None:
            ttl_at = datetime.now(timezone.utc) + timedelta(minutes=15)
        
        return self.create(
            tenant_id=self.tenant_id,
            user_id=user_id,
            key=key,
            req_hash=req_hash,
            response_status=response_status,
            response_body=response_body,
            response_headers=response_headers,
            ttl_at=ttl_at
        )
    
    def get_response(self, tenant_id: uuid.UUID, user_id: Optional[uuid.UUID], 
                    key: str, method: str, path: str, body: Optional[Dict[str, Any]]) -> Optional[IdempotencyKey]:
        """Get cached response for idempotency key"""
        req_hash = self._hash_request(method, path, body)
        
        filters = {
            'user_id': user_id,
            'key': key,
            'req_hash': req_hash,
            'ttl_at': {'gte': datetime.now(timezone.utc)}
        }
        
        entities, _ = self.list(filters=filters, limit=1)
        return entities[0] if entities else None
    
    def cleanup_expired(self, tenant_id: uuid.UUID) -> int:
        """Clean up expired idempotency keys"""
        delete_stmt = delete(self.model).where(
            and_(
                self.model.tenant_id == tenant_id,
                self.model.ttl_at < datetime.now(timezone.utc)
            )
        )
        result = self.session.execute(delete_stmt)
        return result.rowcount
    
    def get_stats(self, tenant_id: uuid.UUID) -> Dict[str, int]:
        """Get idempotency statistics"""
        total = self.count(tenant_id)
        
        # Count active (not expired)
        active_filters = {'ttl_at': {'gte': datetime.now(timezone.utc)}}
        active = self.count(filters=active_filters)
        
        return {
            'total': total,
            'active': active,
            'expired': total - active
        }


class AsyncIdempotencyRepository(AsyncTenantRepository[IdempotencyKey]):
    """Async idempotency repository with tenant isolation"""
    
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID, user_id: Optional[uuid.UUID] = None):
        super().__init__(session, IdempotencyKey, tenant_id, user_id)
    
    def _hash_request(self, method: str, path: str, body: Optional[Dict[str, Any]] = None) -> str:
        """Generate hash for request"""
        request_data = {
            'method': method,
            'path': path,
            'body': body or {}
        }
        request_str = json.dumps(request_data, sort_keys=True)
        return hashlib.sha256(request_str.encode()).hexdigest()
    
    async def store_response(self, tenant_id: uuid.UUID, user_id: Optional[uuid.UUID], 
                            key: str, method: str, path: str, body: Optional[Dict[str, Any]],
                            response_status: int, response_body: Optional[Dict[str, Any]] = None,
                            response_headers: Optional[Dict[str, str]] = None,
                            ttl_at: Optional[datetime] = None) -> IdempotencyKey:
        """Store idempotency response with proper TTL calculation"""
        req_hash = self._hash_request(method, path, body)
        
        # Use provided ttl_at or calculate with proper timedelta
        if ttl_at is None:
            ttl_at = datetime.now(timezone.utc) + timedelta(minutes=15)
        
        return await self.create(
            tenant_id=self.tenant_id,
            user_id=user_id,
            key=key,
            req_hash=req_hash,
            response_status=response_status,
            response_body=response_body,
            response_headers=response_headers,
            ttl_at=ttl_at
        )
    
    async def get_response(self, tenant_id: uuid.UUID, user_id: Optional[uuid.UUID], 
                          key: str, method: str, path: str, body: Optional[Dict[str, Any]]) -> Optional[IdempotencyKey]:
        """Get cached response for idempotency key"""
        req_hash = self._hash_request(method, path, body)
        
        filters = {
            'user_id': user_id,
            'key': key,
            'req_hash': req_hash,
            'ttl_at': {'gte': datetime.now(timezone.utc)}
        }
        
        entities, _ = await self.list(filters=filters, limit=1)
        return entities[0] if entities else None
    
    async def cleanup_expired(self, tenant_id: uuid.UUID) -> int:
        """Clean up expired idempotency keys"""
        from sqlalchemy import delete
        
        delete_stmt = delete(self.model).where(
            and_(
                self.model.tenant_id == tenant_id,
                self.model.ttl_at < datetime.now(timezone.utc)
            )
        )
        result = await self.session.execute(delete_stmt)
        return result.rowcount


# Factory functions
def create_idempotency_repository(session: Session) -> IdempotencyRepository:
    """Create idempotency repository"""
    return IdempotencyRepository(session)

def create_async_idempotency_repository(session: AsyncSession) -> AsyncIdempotencyRepository:
    """Create async idempotency repository"""
    return AsyncIdempotencyRepository(session)
