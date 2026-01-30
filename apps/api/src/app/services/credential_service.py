"""
CredentialService - управление credentials для ToolInstance
"""
from dataclasses import dataclass
from typing import List, Optional, Dict, Any, Tuple
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.crypto import CryptoService, CryptoError, get_crypto_service
from app.models.credential_set import CredentialSet, AuthType, CredentialScope
from app.repositories.credential_set_repository import CredentialSetRepository
from app.repositories.tool_instance_repository import ToolInstanceRepository

logger = get_logger(__name__)


class CredentialError(Exception):
    """Base exception for credential operations"""
    pass


class CredentialNotFoundError(CredentialError):
    """Credential not found"""
    pass


class CredentialExistsError(CredentialError):
    """Credential already exists for this scope"""
    pass


@dataclass
class DecryptedCredentials:
    """Decrypted credentials with metadata"""
    auth_type: str
    payload: Dict[str, Any]
    scope: str
    credential_set_id: UUID


class CredentialService:
    """
    Сервис для управления credentials.
    
    Отвечает за:
    - CRUD операции с credentials
    - Шифрование/дешифрование payload
    - Резолв credentials по приоритету (User > Tenant)
    """
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = CredentialSetRepository(session)
        self.instance_repo = ToolInstanceRepository(session)
        self.crypto = get_crypto_service()
    
    async def create_credentials(
        self,
        tool_instance_id: UUID,
        auth_type: str,
        payload: Dict[str, Any],
        scope: str,
        tenant_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
        is_default: bool = True,
    ) -> CredentialSet:
        """
        Create new credentials for a tool instance.
        
        Args:
            tool_instance_id: ID of the tool instance
            auth_type: Type of authentication (token, basic, oauth, api_key)
            payload: Credentials payload (will be encrypted)
            scope: Scope level (tenant, user)
            tenant_id: Tenant ID (required for both scopes)
            user_id: User ID (required for user scope)
        """
        instance = await self.instance_repo.get_by_id(tool_instance_id)
        if not instance:
            raise CredentialError(f"Tool instance '{tool_instance_id}' not found")
        
        self._validate_scope(scope, tenant_id, user_id)
        self._validate_auth_type(auth_type)
        self._validate_payload(auth_type, payload)
        
        # If setting as default, unset other defaults for this scope
        if is_default:
            await self._unset_other_defaults(
                tool_instance_id=tool_instance_id,
                scope=scope,
                tenant_id=tenant_id,
                user_id=user_id,
            )
        
        try:
            encrypted_payload = self.crypto.encrypt(payload)
        except CryptoError as e:
            raise CredentialError(f"Failed to encrypt credentials: {e}")
        
        cred_set = CredentialSet(
            tool_instance_id=tool_instance_id,
            scope=scope,
            tenant_id=tenant_id,
            user_id=user_id,
            auth_type=auth_type,
            encrypted_payload=encrypted_payload,
            is_active=True,
            is_default=is_default,
        )
        
        return await self.repo.create(cred_set)
    
    async def get_credentials(self, credential_id: UUID) -> CredentialSet:
        """Get credential set by ID (without decryption)"""
        cred_set = await self.repo.get_by_id(credential_id)
        if not cred_set:
            raise CredentialNotFoundError(f"Credentials '{credential_id}' not found")
        return cred_set
    
    async def get_decrypted_credentials(
        self,
        credential_id: UUID,
    ) -> DecryptedCredentials:
        """Get and decrypt credentials"""
        cred_set = await self.get_credentials(credential_id)
        
        try:
            payload = self.crypto.decrypt(cred_set.encrypted_payload)
        except CryptoError as e:
            raise CredentialError(f"Failed to decrypt credentials: {e}")
        
        return DecryptedCredentials(
            auth_type=cred_set.auth_type,
            payload=payload,
            scope=cred_set.scope,
            credential_set_id=cred_set.id,
        )
    
    async def update_credentials(
        self,
        credential_id: UUID,
        auth_type: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
        is_active: Optional[bool] = None,
        is_default: Optional[bool] = None,
    ) -> CredentialSet:
        """Update existing credentials"""
        cred_set = await self.get_credentials(credential_id)
        
        if auth_type is not None:
            self._validate_auth_type(auth_type)
            cred_set.auth_type = auth_type
        
        if payload is not None:
            self._validate_payload(cred_set.auth_type, payload)
            try:
                cred_set.encrypted_payload = self.crypto.encrypt(payload)
            except CryptoError as e:
                raise CredentialError(f"Failed to encrypt credentials: {e}")
        
        if is_active is not None:
            cred_set.is_active = is_active
        
        if is_default is not None:
            if is_default:
                # Unset other defaults for this scope
                await self._unset_other_defaults(
                    tool_instance_id=cred_set.tool_instance_id,
                    scope=cred_set.scope,
                    tenant_id=cred_set.tenant_id,
                    user_id=cred_set.user_id,
                    exclude_id=credential_id,
                )
            cred_set.is_default = is_default
        
        return await self.repo.update(cred_set)
    
    async def delete_credentials(self, credential_id: UUID) -> None:
        """Delete credentials"""
        cred_set = await self.get_credentials(credential_id)
        await self.repo.delete(cred_set)
    
    async def list_credentials(
        self,
        skip: int = 0,
        limit: int = 100,
        tool_instance_id: Optional[UUID] = None,
        scope: Optional[str] = None,
        tenant_id: Optional[UUID] = None,
        is_active: Optional[bool] = None,
    ) -> Tuple[List[CredentialSet], int]:
        """List credentials with filters (without decryption)"""
        return await self.repo.list_credentials(
            skip=skip,
            limit=limit,
            tool_instance_id=tool_instance_id,
            scope=scope,
            tenant_id=tenant_id,
            is_active=is_active,
        )
    
    async def resolve_credentials(
        self,
        tool_instance_id: UUID,
        user_id: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
    ) -> Optional[DecryptedCredentials]:
        """
        Resolve and decrypt credentials for a tool instance.
        
        Priority: User > Tenant > Default
        
        If multiple credentials exist for a scope, uses is_default=true.
        If no default is set, raises error.
        
        Returns None if no credentials found.
        """
        # Try user scope first
        if user_id and tenant_id:
            cred_set = await self.repo.get_default_for_scope(
                tool_instance_id=tool_instance_id,
                scope="user",
                tenant_id=tenant_id,
                user_id=user_id,
            )
            if cred_set:
                return await self._decrypt_credentials(cred_set)
        
        # Try tenant scope
        if tenant_id:
            cred_set = await self.repo.get_default_for_scope(
                tool_instance_id=tool_instance_id,
                scope="tenant",
                tenant_id=tenant_id,
            )
            if cred_set:
                return await self._decrypt_credentials(cred_set)
        
        # Try default scope
        cred_set = await self.repo.get_default_for_scope(
            tool_instance_id=tool_instance_id,
            scope="default",
        )
        if cred_set:
            return await self._decrypt_credentials(cred_set)
        
        return None
    
    async def _decrypt_credentials(self, cred_set: CredentialSet) -> Optional[DecryptedCredentials]:
        """Helper to decrypt credentials"""
        try:
            payload = self.crypto.decrypt(cred_set.encrypted_payload)
        except CryptoError as e:
            logger.error(f"Failed to decrypt credentials {cred_set.id}: {e}")
            return None
        
        return DecryptedCredentials(
            auth_type=cred_set.auth_type,
            payload=payload,
            scope=cred_set.scope,
            credential_set_id=cred_set.id,
        )
    
    async def has_credentials(
        self,
        tool_instance_id: UUID,
        user_id: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
    ) -> bool:
        """Check if credentials exist for a tool instance"""
        cred_set = await self.repo.get_for_instance(
            tool_instance_id=tool_instance_id,
            user_id=user_id,
            tenant_id=tenant_id,
        )
        return cred_set is not None
    
    def _validate_scope(
        self,
        scope: str,
        tenant_id: Optional[UUID],
        user_id: Optional[UUID],
    ) -> None:
        """Validate scope and required IDs"""
        if scope == CredentialScope.DEFAULT.value:
            if tenant_id or user_id:
                raise CredentialError("Default scope cannot have tenant_id or user_id")
        elif scope == CredentialScope.TENANT.value:
            if not tenant_id:
                raise CredentialError("Tenant scope requires tenant_id")
            if user_id:
                raise CredentialError("Tenant scope cannot have user_id")
        elif scope == CredentialScope.USER.value:
            if not tenant_id or not user_id:
                raise CredentialError("User scope requires both tenant_id and user_id")
        else:
            raise CredentialError(f"Invalid scope: {scope}")
    
    def _validate_auth_type(self, auth_type: str) -> None:
        """Validate auth type"""
        valid_types = [t.value for t in AuthType]
        if auth_type not in valid_types:
            raise CredentialError(f"Invalid auth_type: {auth_type}. Must be one of: {valid_types}")
    
    def _validate_payload(self, auth_type: str, payload: Dict[str, Any]) -> None:
        """Validate payload structure based on auth type"""
        if auth_type == AuthType.TOKEN.value:
            if "token" not in payload:
                raise CredentialError("Token auth requires 'token' in payload")
        
        elif auth_type == AuthType.BASIC.value:
            if "username" not in payload or "password" not in payload:
                raise CredentialError("Basic auth requires 'username' and 'password' in payload")
        
        elif auth_type == AuthType.API_KEY.value:
            if "api_key" not in payload:
                raise CredentialError("API key auth requires 'api_key' in payload")
        
        elif auth_type == AuthType.OAUTH.value:
            pass
    
    async def _unset_other_defaults(
        self,
        tool_instance_id: UUID,
        scope: str,
        tenant_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
        exclude_id: Optional[UUID] = None,
    ) -> None:
        """Unset is_default for other credentials in the same scope"""
        from sqlalchemy import update
        
        stmt = (
            update(CredentialSet)
            .where(
                CredentialSet.tool_instance_id == tool_instance_id,
                CredentialSet.scope == scope,
                CredentialSet.is_default == True,
            )
        )
        
        if scope == "default":
            # Default scope has no tenant_id or user_id
            stmt = stmt.where(
                CredentialSet.tenant_id.is_(None),
                CredentialSet.user_id.is_(None),
            )
        elif scope == "tenant":
            stmt = stmt.where(CredentialSet.tenant_id == tenant_id)
        elif scope == "user":
            stmt = stmt.where(
                CredentialSet.tenant_id == tenant_id,
                CredentialSet.user_id == user_id,
            )
        
        if exclude_id:
            stmt = stmt.where(CredentialSet.id != exclude_id)
        
        stmt = stmt.values(is_default=False)
        
        await self.session.execute(stmt)
        await self.session.flush()
