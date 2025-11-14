"""
Idempotency repository for handling duplicate request prevention
"""
from __future__ import annotations
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc
from datetime import datetime, timezone, timedelta
import uuid
import hashlib
import json

from app.repositories.base import AsyncTenantRepository
from app.core.logging import get_logger

logger = get_logger(__name__)

# Idempotency model (would be defined in models)
class IdempotencyKey:
    """Idempotency key model"""
    pass


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
    
    async def create_key(self, key: str, method: str, path: str, 
                       body: Optional[Dict[str, Any]] = None, 
                       ttl_hours: int = 24) -> IdempotencyKey:
        """Create idempotency key"""
        expires_at = datetime.now(timezone.utc) + timedelta(hours=ttl_hours)
        request_hash = self._hash_request(method, path, body)
        
        return await self.create(
            self.tenant_id,
            key=key,
            method=method,
            path=path,
            request_hash=request_hash,
            expires_at=expires_at,
            created_at=datetime.now(timezone.utc)
        )
    
    async def get_key(self, key: str) -> Optional[IdempotencyKey]:
        """Get idempotency key"""
        result = await self.session.execute(
            select(IdempotencyKey).where(
                and_(
                    IdempotencyKey.key == key,
                    IdempotencyKey.tenant_id == self.tenant_id,
                    IdempotencyKey.expires_at > datetime.now(timezone.utc)
                )
            )
        )
        return result.scalar_one_or_none()
    
    async def is_key_active(self, key: str) -> bool:
        """Check if key is active"""
        key_obj = await self.get_key(key)
        return key_obj is not None
    
    async def delete_expired_keys(self) -> int:
        """Delete expired keys"""
        result = await self.session.execute(
            select(IdempotencyKey).where(
                and_(
                    IdempotencyKey.tenant_id == self.tenant_id,
                    IdempotencyKey.expires_at <= datetime.now(timezone.utc)
                )
            )
        )
        expired_keys = result.scalars().all()
        
        for key in expired_keys:
            await self.session.delete(key)
        
        await self.session.commit()
        return len(expired_keys)
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get idempotency statistics"""
        total_result = await self.session.execute(
            select(func.count(IdempotencyKey.id)).where(
                IdempotencyKey.tenant_id == self.tenant_id
            )
        )
        total = total_result.scalar()
        
        active_result = await self.session.execute(
            select(func.count(IdempotencyKey.id)).where(
                and_(
                    IdempotencyKey.tenant_id == self.tenant_id,
                    IdempotencyKey.expires_at > datetime.now(timezone.utc)
                )
            )
        )
        active = active_result.scalar()
        
        return {
            'total': total,
            'active': active,
            'expired': total - active
        }