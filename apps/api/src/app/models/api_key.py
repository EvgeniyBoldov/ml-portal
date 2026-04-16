"""
API Key model for IDE plugin authentication.

Provides secure API key management for MCP clients.
"""
import uuid
import secrets
import hashlib
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import String, DateTime, Text, Boolean, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


def generate_api_key() -> str:
    """Generate a secure API key with prefix for identification."""
    # Format: mlp_<random_32_chars>
    return f"mlp_{secrets.token_urlsafe(32)}"


def hash_api_key(key: str) -> str:
    """Hash API key for secure storage."""
    return hashlib.sha256(key.encode()).hexdigest()


class APIKey(Base):
    """
    API Key for authenticating IDE plugins and external integrations.
    
    Security:
    - Only the hash is stored, not the actual key
    - Key is shown once on creation, then never again
    - Keys can be scoped to specific tools/prompts
    - Keys can have expiration dates
    """
    __tablename__ = "api_keys"
    __table_args__ = (
        Index("ix_api_keys_key_hash", "key_hash"),
        Index("ix_api_keys_user_id", "user_id"),
        Index("ix_api_keys_tenant_id", "tenant_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    
    # Human-readable name for the key
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Key prefix for identification (first 8 chars, e.g., "mlp_abc1")
    key_prefix: Mapped[str] = mapped_column(String(12), nullable=False)
    
    # SHA-256 hash of the full key
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    
    # Owner
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    tenant_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    
    # Permissions
    scopes: Mapped[List[str]] = mapped_column(JSONB, default=list)  # e.g., ["tools:read", "tools:execute", "prompts:read"]
    allowed_tools: Mapped[Optional[List[str]]] = mapped_column(JSONB, nullable=True)  # null = all tools
    allowed_prompts: Mapped[Optional[List[str]]] = mapped_column(JSONB, nullable=True)  # null = all prompts
    
    # Rate limiting overrides (null = use defaults)
    rate_limit_rpm: Mapped[Optional[int]] = mapped_column(nullable=True)  # requests per minute
    rate_limit_rph: Mapped[Optional[int]] = mapped_column(nullable=True)  # requests per hour
    
    # Lifecycle
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    
    def __repr__(self):
        return f"<APIKey {self.name} ({self.key_prefix}...)>"
    
    @classmethod
    def create(
        cls,
        name: str,
        user_id: uuid.UUID,
        tenant_id: Optional[uuid.UUID] = None,
        description: Optional[str] = None,
        scopes: Optional[List[str]] = None,
        allowed_tools: Optional[List[str]] = None,
        allowed_prompts: Optional[List[str]] = None,
        expires_at: Optional[datetime] = None,
    ) -> tuple["APIKey", str]:
        """
        Create a new API key.
        
        Returns:
            Tuple of (APIKey instance, raw key string)
            
        Note: The raw key is only available at creation time!
        """
        raw_key = generate_api_key()
        key_hash = hash_api_key(raw_key)
        key_prefix = raw_key[:12]  # "mlp_" + first 8 chars
        
        api_key = cls(
            name=name,
            description=description,
            key_prefix=key_prefix,
            key_hash=key_hash,
            user_id=user_id,
            tenant_id=tenant_id,
            scopes=scopes or ["tools:read", "tools:execute", "prompts:read", "llm:proxy"],
            allowed_tools=allowed_tools,
            allowed_prompts=allowed_prompts,
            expires_at=expires_at,
        )
        
        return api_key, raw_key
    
    def verify(self, raw_key: str) -> bool:
        """Verify a raw key against this API key's hash."""
        return hash_api_key(raw_key) == self.key_hash
    
    def is_valid(self) -> bool:
        """Check if key is active and not expired."""
        if not self.is_active:
            return False
        if self.expires_at and self.expires_at < datetime.now(timezone.utc):
            return False
        return True
    
    def has_scope(self, scope: str) -> bool:
        """Check if key has a specific scope."""
        return scope in (self.scopes or [])
    
    def can_use_tool(self, tool_slug: str) -> bool:
        """Check if key can use a specific tool."""
        if self.allowed_tools is None:
            return True  # null = all tools allowed
        return tool_slug in self.allowed_tools
    
    def can_use_prompt(self, prompt_slug: str) -> bool:
        """Check if key can use a specific prompt."""
        if self.allowed_prompts is None:
            return True  # null = all prompts allowed
        return prompt_slug in self.allowed_prompts
