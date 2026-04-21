"""
CredentialService v2 - owner-based credentials for ToolInstance.
"""
from dataclasses import dataclass
from typing import List, Optional, Dict, Any, Tuple
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import CredentialNotFoundError, AppError as CredentialError
from app.core.logging import get_logger
from app.core.crypto import CryptoError, get_crypto_service
from app.models.credential_set import Credential, AuthType
from app.repositories.credential_set_repository import CredentialRepository
from app.repositories.tool_instance_repository import ToolInstanceRepository

logger = get_logger(__name__)


@dataclass
class DecryptedCredentials:
    """Decrypted credentials with metadata"""
    auth_type: str
    payload: Dict[str, Any]
    credential_id: UUID
    owner_type: str  # "user" | "tenant" | "platform"


@dataclass
class CredentialReference:
    """Credential metadata without secret payload."""
    auth_type: str
    credential_id: UUID
    owner_type: str  # "user" | "tenant" | "platform"


class CredentialService:
    """
    Сервис для управления credentials v2 (owner-based).

    Отвечает за:
    - CRUD операции с credentials
    - Шифрование/дешифрование payload
    - Резолв credentials по стратегии (credential_strategy)
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = CredentialRepository(session)
        self.instance_repo = ToolInstanceRepository(session)
        self.crypto = get_crypto_service()

    async def create_credentials(
        self,
        instance_id: UUID,
        auth_type: str,
        payload: Dict[str, Any],
        owner_user_id: Optional[UUID] = None,
        owner_tenant_id: Optional[UUID] = None,
        owner_platform: bool = False,
    ) -> Credential:
        """Create new credential for a tool instance."""
        instance = await self.instance_repo.get_by_id(instance_id)
        if not instance:
            raise CredentialError(f"Tool instance '{instance_id}' not found")

        self._validate_owner(owner_user_id, owner_tenant_id, owner_platform)
        self._validate_auth_type(auth_type)
        self._validate_payload(auth_type, payload)

        try:
            encrypted_payload = self.crypto.encrypt(payload)
        except CryptoError as e:
            raise CredentialError(f"Failed to encrypt credentials: {e}")

        credential = Credential(
            instance_id=instance_id,
            owner_user_id=owner_user_id,
            owner_tenant_id=owner_tenant_id,
            owner_platform=owner_platform,
            auth_type=auth_type,
            encrypted_payload=encrypted_payload,
            is_active=True,
        )

        return await self.repo.create(credential)

    async def get_credentials(self, credential_id: UUID) -> Credential:
        """Get credential by ID (without decryption)"""
        cred = await self.repo.get_by_id(credential_id)
        if not cred:
            raise CredentialNotFoundError(f"Credentials '{credential_id}' not found")
        return cred

    async def get_decrypted_credentials(
        self,
        credential_id: UUID,
    ) -> DecryptedCredentials:
        """Get and decrypt credentials"""
        cred = await self.get_credentials(credential_id)
        return await self._decrypt(cred)

    async def update_credentials(
        self,
        credential_id: UUID,
        auth_type: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
        is_active: Optional[bool] = None,
    ) -> Credential:
        """Update existing credentials"""
        cred = await self.get_credentials(credential_id)

        if auth_type is not None:
            self._validate_auth_type(auth_type)
            cred.auth_type = auth_type

        if payload is not None:
            self._validate_payload(cred.auth_type, payload)
            try:
                cred.encrypted_payload = self.crypto.encrypt(payload)
            except CryptoError as e:
                raise CredentialError(f"Failed to encrypt credentials: {e}")

        if is_active is not None:
            cred.is_active = is_active

        return await self.repo.update(cred)

    async def delete_credentials(self, credential_id: UUID) -> None:
        """Delete credentials"""
        cred = await self.get_credentials(credential_id)
        await self.repo.delete(cred)

    async def list_credentials(
        self,
        skip: int = 0,
        limit: int = 100,
        instance_id: Optional[UUID] = None,
        owner_user_id: Optional[UUID] = None,
        owner_tenant_id: Optional[UUID] = None,
        owner_platform: Optional[bool] = None,
        is_active: Optional[bool] = None,
    ) -> Tuple[List[Credential], int]:
        """List credentials with filters (without decryption)"""
        return await self.repo.list_credentials(
            skip=skip,
            limit=limit,
            instance_id=instance_id,
            owner_user_id=owner_user_id,
            owner_tenant_id=owner_tenant_id,
            owner_platform=owner_platform,
            is_active=is_active,
        )

    async def resolve_credentials(
        self,
        instance_id: UUID,
        strategy: str = "PLATFORM_FIRST",
        user_id: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
    ) -> Optional[DecryptedCredentials]:
        """
        Resolve and decrypt credentials using strategy.

        Returns None if no credentials found.
        """
        cred = await self.repo.resolve_for_instance(
            instance_id=instance_id,
            strategy=strategy,
            user_id=user_id,
            tenant_id=tenant_id,
        )
        if not cred:
            return None
        return await self._decrypt(cred)

    async def resolve_credential_reference(
        self,
        instance_id: UUID,
        strategy: str = "PLATFORM_FIRST",
        user_id: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
    ) -> Optional[CredentialReference]:
        """Resolve credential metadata without decrypting secret payload."""
        cred = await self.repo.resolve_for_instance(
            instance_id=instance_id,
            strategy=strategy,
            user_id=user_id,
            tenant_id=tenant_id,
        )
        if not cred:
            return None
        owner_type = "platform" if cred.owner_platform else ("user" if cred.owner_user_id else "tenant")
        return CredentialReference(
            auth_type=cred.auth_type,
            credential_id=cred.id,
            owner_type=owner_type,
        )

    async def has_credentials(
        self,
        tool_instance_id: UUID,
        user_id: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
    ) -> bool:
        """Check if credentials exist for a tool instance."""
        return await self.repo.has_credentials(
            instance_id=tool_instance_id,
            user_id=user_id,
            tenant_id=tenant_id,
        )

    async def _decrypt(self, cred: Credential) -> DecryptedCredentials:
        """Helper to decrypt credentials"""
        try:
            payload = self.crypto.decrypt(cred.encrypted_payload)
        except CryptoError as e:
            logger.error(f"Failed to decrypt credentials {cred.id}: {e}")
            raise CredentialError(f"Failed to decrypt credentials: {e}")

        owner_type = "platform" if cred.owner_platform else (
            "user" if cred.owner_user_id else "tenant"
        )

        return DecryptedCredentials(
            auth_type=cred.auth_type,
            payload=payload,
            credential_id=cred.id,
            owner_type=owner_type,
        )

    def _validate_owner(
        self,
        owner_user_id: Optional[UUID],
        owner_tenant_id: Optional[UUID],
        owner_platform: bool,
    ) -> None:
        """Validate exactly one owner is set"""
        count = sum([
            owner_platform,
            owner_user_id is not None,
            owner_tenant_id is not None,
        ])
        if count != 1:
            raise CredentialError("Exactly one owner must be set (user, tenant, or platform)")

    def _validate_auth_type(self, auth_type: str) -> None:
        valid_types = [t.value for t in AuthType]
        if auth_type not in valid_types:
            raise CredentialError(f"Invalid auth_type: {auth_type}. Must be one of: {valid_types}")

    def _validate_payload(self, auth_type: str, payload: Dict[str, Any]) -> None:
        if auth_type == AuthType.TOKEN.value:
            if "token" not in payload:
                raise CredentialError("Token auth requires 'token' in payload")
        elif auth_type == AuthType.BASIC.value:
            if "username" not in payload or "password" not in payload:
                raise CredentialError("Basic auth requires 'username' and 'password' in payload")
        elif auth_type == AuthType.API_KEY.value:
            if "api_key" not in payload:
                raise CredentialError("API key auth requires 'api_key' in payload")
