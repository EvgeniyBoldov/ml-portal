"""
Policy Service - business logic for behavioral policies (text-based rules).

Architecture:
- Policy (container) - holds metadata: slug, name, description
- PolicyVersion - holds versioned data: policy_text, policy_json
- current_version_id - points to the active version

Policy is NOT execution limits (those are in LimitService).
Policy defines behavioral rules, restrictions, and guidelines.

Version workflow:
- Create → always draft
- Activate → draft → active (deprecates previous active)
- Deactivate → draft or active → deprecated
"""
import hashlib
import logging
from typing import List, Optional, Tuple, Dict, Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    PolicyNotFoundError,
    PolicyVersionNotFoundError,
    PolicyAlreadyExistsError,
    PolicyVersionNotEditableError,
    AppError as PolicyError,
)
from app.models.policy import Policy, PolicyVersion, PolicyStatus
from app.repositories.policy_repository import PolicyRepository, PolicyVersionRepository

logger = logging.getLogger(__name__)


class PolicyService:
    """Service for managing policies and their versions"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.policy_repo = PolicyRepository(session)
        self.version_repo = PolicyVersionRepository(session)

    # ─────────────────────────────────────────────────────────────────────────
    # POLICY CONTAINER operations
    # ─────────────────────────────────────────────────────────────────────────

    async def create_policy(
        self,
        slug: str,
        name: str,
        description: Optional[str] = None,
    ) -> Policy:
        existing = await self.policy_repo.get_by_slug(slug)
        if existing:
            raise PolicyAlreadyExistsError(f"Policy with slug '{slug}' already exists")

        policy = Policy(
            slug=slug,
            name=name,
            description=description,
        )

        return await self.policy_repo.create(policy)

    async def get_policy(self, policy_id: UUID) -> Policy:
        policy = await self.policy_repo.get_by_id(policy_id)
        if not policy:
            raise PolicyNotFoundError(f"Policy '{policy_id}' not found")
        return policy

    async def get_policy_by_slug(self, slug: str) -> Policy:
        policy = await self.policy_repo.get_by_slug(slug)
        if not policy:
            raise PolicyNotFoundError(f"Policy '{slug}' not found")
        return policy

    async def get_policy_with_versions(self, slug: str) -> Policy:
        policy = await self.policy_repo.get_by_slug_with_versions(slug)
        if not policy:
            raise PolicyNotFoundError(f"Policy '{slug}' not found")
        return policy

    async def update_policy(
        self,
        policy_id: UUID,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Policy:
        policy = await self.get_policy(policy_id)

        update_data = {}
        if name is not None:
            update_data['name'] = name
        if description is not None:
            update_data['description'] = description

        if update_data:
            return await self.policy_repo.update(policy, update_data)
        return policy

    async def delete_policy(self, policy_id: UUID) -> None:
        policy = await self.get_policy(policy_id)
        await self.policy_repo.delete(policy)

    async def list_policies(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> Tuple[List[Policy], int]:
        return await self.policy_repo.list_policies(skip, limit)

    # ─────────────────────────────────────────────────────────────────────────
    # POLICY VERSION operations
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _compute_hash(policy_text: str) -> str:
        return hashlib.sha256(policy_text.encode()).hexdigest()[:16]

    async def create_version(
        self,
        policy_slug: str,
        policy_text: Optional[str] = None,
        policy_json: Optional[Dict[str, Any]] = None,
        notes: Optional[str] = None,
        parent_version_id: Optional[UUID] = None,
    ) -> PolicyVersion:
        """
        Create a new policy version (always draft).

        If parent_version_id is provided, inherits policy_text/policy_json
        from the parent version. Explicit values override inherited ones.
        """
        policy = await self.get_policy_by_slug(policy_slug)
        next_version = await self.version_repo.get_next_version(policy.id)

        # Inherit from parent version if specified
        inherited_text = ""
        inherited_json = None

        if parent_version_id:
            parent = await self.version_repo.get_by_id(parent_version_id)
            if parent and parent.policy_id == policy.id:
                inherited_text = parent.policy_text
                inherited_json = parent.policy_json
                logger.info(
                    f"Inheriting from v{parent.version} for policy '{policy_slug}'"
                )
            else:
                logger.warning(
                    f"Parent version {parent_version_id} not found or belongs to another policy"
                )

        final_text = policy_text if policy_text is not None else inherited_text
        final_json = policy_json if policy_json is not None else inherited_json

        version = PolicyVersion(
            policy_id=policy.id,
            version=next_version,
            status=PolicyStatus.DRAFT.value,
            hash=self._compute_hash(final_text),
            policy_text=final_text,
            policy_json=final_json,
            notes=notes,
            parent_version_id=parent_version_id,
        )

        return await self.version_repo.create(version)

    async def get_version(self, version_id: UUID) -> PolicyVersion:
        version = await self.version_repo.get_by_id(version_id)
        if not version:
            raise PolicyVersionNotFoundError(f"Policy version '{version_id}' not found")
        return version

    async def get_version_by_number(
        self,
        policy_slug: str,
        version_number: int
    ) -> PolicyVersion:
        policy = await self.get_policy_by_slug(policy_slug)
        version = await self.version_repo.get_by_policy_and_version(policy.id, version_number)
        if not version:
            raise PolicyVersionNotFoundError(
                f"Version {version_number} not found for policy '{policy_slug}'"
            )
        return version

    async def list_versions(
        self,
        policy_slug: str,
        status_filter: Optional[str] = None
    ) -> List[PolicyVersion]:
        policy = await self.get_policy_by_slug(policy_slug)
        return await self.version_repo.get_all_by_policy(policy.id, status_filter)

    async def update_version(
        self,
        version_id: UUID,
        policy_text: Optional[str] = None,
        policy_json: Optional[Dict[str, Any]] = None,
        notes: Optional[str] = None,
    ) -> PolicyVersion:
        version = await self.get_version(version_id)

        if not version.is_editable:
            raise PolicyVersionNotEditableError(
                f"Version {version.version} is not editable (status: {version.status})"
            )

        update_data = {}
        if policy_text is not None:
            update_data['policy_text'] = policy_text
            update_data['hash'] = self._compute_hash(policy_text)
        if policy_json is not None:
            update_data['policy_json'] = policy_json
        if notes is not None:
            update_data['notes'] = notes

        if update_data:
            return await self.version_repo.update(version, update_data)
        return version

    async def delete_version(self, version_id: UUID) -> None:
        version = await self.get_version(version_id)

        if version.status == PolicyStatus.ACTIVE.value:
            raise PolicyError("Cannot delete active version. Deactivate it first.")

        await self.version_repo.delete(version)

    async def activate_version(self, version_id: UUID) -> PolicyVersion:
        """
        Activate a version (draft → active).
        Deprecates the currently active version.
        Updates current_version_id on the policy.
        """
        version = await self.get_version(version_id)

        if not version.can_activate:
            raise PolicyError(
                f"Version {version.version} cannot be activated (status: {version.status})"
            )

        await self.version_repo.deactivate_active_version(version.policy_id)
        await self.version_repo.update_status(version_id, PolicyStatus.ACTIVE.value)

        policy = await self.policy_repo.get_by_id(version.policy_id)
        await self.policy_repo.update(policy, {'current_version_id': version_id})

        return await self.get_version(version_id)

    async def deactivate_version(self, version_id: UUID) -> PolicyVersion:
        version = await self.get_version(version_id)

        if not version.can_deactivate:
            raise PolicyError(
                f"Version {version.version} cannot be deactivated (status: {version.status})"
            )

        await self.version_repo.update_status(version_id, PolicyStatus.DEPRECATED.value)

        policy = await self.policy_repo.get_by_id(version.policy_id)
        if policy.current_version_id == version_id:
            await self.policy_repo.update(policy, {'current_version_id': None})

        return await self.get_version(version_id)

    # ─────────────────────────────────────────────────────────────────────────
    # EFFECTIVE POLICY (for runtime)
    # ─────────────────────────────────────────────────────────────────────────

    async def get_effective_policy_text(self, policy_id: Optional[UUID]) -> Optional[str]:
        """
        Get effective policy text from a policy's current version.
        Returns None if no policy or version exists.
        """
        if not policy_id:
            return None

        policy = await self.policy_repo.get_by_id(policy_id)
        if not policy:
            return None

        version = None
        if policy.current_version_id:
            version = await self.version_repo.get_by_id(policy.current_version_id)

        if not version:
            version = await self.version_repo.get_active_by_policy(policy.id)

        if not version:
            return None

        return version.policy_text
