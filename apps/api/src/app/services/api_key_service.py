"""
API Key Service for managing IDE plugin authentication.
"""
from __future__ import annotations
import logging
from datetime import datetime
from typing import Optional, List, Tuple
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_key import APIKey, hash_api_key

logger = logging.getLogger(__name__)


class APIKeyService:
    """Service for API key management."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create_key(
        self,
        name: str,
        user_id: UUID,
        tenant_id: Optional[UUID] = None,
        description: Optional[str] = None,
        scopes: Optional[List[str]] = None,
        allowed_tools: Optional[List[str]] = None,
        allowed_prompts: Optional[List[str]] = None,
        expires_at: Optional[datetime] = None,
    ) -> Tuple[APIKey, str]:
        """
        Create a new API key.
        
        Returns:
            Tuple of (APIKey, raw_key_string)
            
        Important: The raw key is only returned once!
        """
        api_key, raw_key = APIKey.create(
            name=name,
            user_id=user_id,
            tenant_id=tenant_id,
            description=description,
            scopes=scopes,
            allowed_tools=allowed_tools,
            allowed_prompts=allowed_prompts,
            expires_at=expires_at,
        )
        
        self.session.add(api_key)
        await self.session.flush()
        await self.session.refresh(api_key)
        
        logger.info(f"Created API key '{name}' for user {user_id}")
        
        return api_key, raw_key
    
    async def verify_key(self, raw_key: str) -> Optional[APIKey]:
        """
        Verify an API key and return the APIKey if valid.
        
        Also updates last_used_at timestamp.
        """
        if not raw_key or not raw_key.startswith("mlp_"):
            return None
        
        key_hash = hash_api_key(raw_key)
        
        result = await self.session.execute(
            select(APIKey).where(APIKey.key_hash == key_hash)
        )
        api_key = result.scalar_one_or_none()
        
        if not api_key:
            logger.warning(f"API key not found: {raw_key[:12]}...")
            return None
        
        if not api_key.is_valid():
            logger.warning(f"API key invalid or expired: {api_key.name}")
            return None
        
        # Update last_used_at
        await self.session.execute(
            update(APIKey)
            .where(APIKey.id == api_key.id)
            .values(last_used_at=datetime.utcnow())
        )
        
        return api_key
    
    async def get_key_by_id(self, key_id: UUID) -> Optional[APIKey]:
        """Get API key by ID."""
        result = await self.session.execute(
            select(APIKey).where(APIKey.id == key_id)
        )
        return result.scalar_one_or_none()
    
    async def list_keys(
        self,
        user_id: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
        include_inactive: bool = False,
    ) -> List[APIKey]:
        """List API keys with optional filters."""
        query = select(APIKey)
        
        if user_id:
            query = query.where(APIKey.user_id == user_id)
        if tenant_id:
            query = query.where(APIKey.tenant_id == tenant_id)
        if not include_inactive:
            query = query.where(APIKey.is_active == True)
        
        query = query.order_by(APIKey.created_at.desc())
        
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def revoke_key(self, key_id: UUID) -> bool:
        """Revoke (deactivate) an API key."""
        result = await self.session.execute(
            update(APIKey)
            .where(APIKey.id == key_id)
            .values(is_active=False)
        )
        await self.session.flush()
        
        if result.rowcount > 0:
            logger.info(f"Revoked API key {key_id}")
            return True
        return False
    
    async def delete_key(self, key_id: UUID) -> bool:
        """Permanently delete an API key."""
        api_key = await self.get_key_by_id(key_id)
        if api_key:
            await self.session.delete(api_key)
            await self.session.flush()
            logger.info(f"Deleted API key {key_id}")
            return True
        return False
