"""
Idempotency repository for handling duplicate request prevention
"""
from __future__ import annotations
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from datetime import datetime, timezone
import uuid
import hashlib
import json

from app.repositories.base import AsyncTenantRepository
from app.core.logging import get_logger

logger = get_logger(__name__)

# Idempotency model (would be defined in models)
class IdempotencyKey:
    """Idempotency key model"""


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
    
