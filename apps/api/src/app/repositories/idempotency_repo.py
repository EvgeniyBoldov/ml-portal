"""
Idempotency repository for handling duplicate request prevention
"""
from __future__ import annotations
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

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
    
    
    
    
