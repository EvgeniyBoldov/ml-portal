"""
Policy Service - business logic for execution policies.

Architecture:
- Policy (container) - holds metadata: slug, name, description
- PolicyVersion - holds versioned data: limits, timeouts, budgets
- recommended_version_id - points to the version that should be used by default

Version workflow:
- Create → always draft
- Activate → draft → active (deactivates previous active)
- Deactivate → draft or active → inactive
"""
import logging
from typing import List, Optional, Tuple, Dict, Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.policy import Policy, PolicyVersion, PolicyStatus
from app.repositories.policy_repository import PolicyRepository, PolicyVersionRepository

logger = logging.getLogger(__name__)


class PolicyError(Exception):
    """Base exception for policy operations"""
    pass


class PolicyNotFoundError(PolicyError):
    """Policy not found"""
    pass


class PolicyVersionNotFoundError(PolicyError):
    """Policy version not found"""
    pass


class PolicyAlreadyExistsError(PolicyError):
    """Policy with this slug already exists"""
    pass


class PolicyVersionNotEditableError(PolicyError):
    """Policy version cannot be edited (not in draft status)"""
    pass


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
        """Create a new policy container (without version)"""
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
        """Get policy by ID"""
        policy = await self.policy_repo.get_by_id(policy_id)
        if not policy:
            raise PolicyNotFoundError(f"Policy '{policy_id}' not found")
        return policy

    async def get_policy_by_slug(self, slug: str) -> Policy:
        """Get policy by slug"""
        policy = await self.policy_repo.get_by_slug(slug)
        if not policy:
            raise PolicyNotFoundError(f"Policy '{slug}' not found")
        return policy

    async def get_policy_with_versions(self, slug: str) -> Policy:
        """Get policy by slug with all versions loaded"""
        policy = await self.policy_repo.get_by_slug_with_versions(slug)
        if not policy:
            raise PolicyNotFoundError(f"Policy '{slug}' not found")
        return policy

    async def update_policy(
        self,
        policy_id: UUID,
        name: Optional[str] = None,
        description: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> Policy:
        """Update policy container metadata (not versioned data)"""
        policy = await self.get_policy(policy_id)
        
        update_data = {}
        if name is not None:
            update_data['name'] = name
        if description is not None:
            update_data['description'] = description
        if is_active is not None:
            update_data['is_active'] = is_active
        
        if update_data:
            return await self.policy_repo.update(policy, update_data)
        return policy

    async def delete_policy(self, policy_id: UUID) -> None:
        """Delete a policy and all its versions"""
        policy = await self.get_policy(policy_id)
        
        # Don't allow deleting the default policy
        if policy.slug == "default":
            raise PolicyError("Cannot delete the default policy")
        
        await self.policy_repo.delete(policy)

    async def list_policies(
        self,
        skip: int = 0,
        limit: int = 100,
        is_active: Optional[bool] = None,
    ) -> Tuple[List[Policy], int]:
        """List policies with filters"""
        return await self.policy_repo.list_policies(skip, limit, is_active)

    async def get_default_policy(self) -> Optional[Policy]:
        """Get the default policy"""
        return await self.policy_repo.get_default()

    # ─────────────────────────────────────────────────────────────────────────
    # POLICY VERSION operations
    # ─────────────────────────────────────────────────────────────────────────

    async def create_version(
        self,
        policy_slug: str,
        max_steps: Optional[int] = None,
        max_tool_calls: Optional[int] = None,
        max_wall_time_ms: Optional[int] = None,
        tool_timeout_ms: Optional[int] = None,
        max_retries: Optional[int] = None,
        budget_tokens: Optional[int] = None,
        budget_cost_cents: Optional[int] = None,
        extra_config: Optional[Dict[str, Any]] = None,
        notes: Optional[str] = None,
        parent_version_id: Optional[UUID] = None,
    ) -> PolicyVersion:
        """Create a new version for a policy (always in draft status)"""
        policy = await self.get_policy_by_slug(policy_slug)
        
        next_version = await self.version_repo.get_next_version(policy.id)
        
        version = PolicyVersion(
            policy_id=policy.id,
            version=next_version,
            status=PolicyStatus.DRAFT.value,
            max_steps=max_steps,
            max_tool_calls=max_tool_calls,
            max_wall_time_ms=max_wall_time_ms,
            tool_timeout_ms=tool_timeout_ms,
            max_retries=max_retries,
            budget_tokens=budget_tokens,
            budget_cost_cents=budget_cost_cents,
            extra_config=extra_config or {},
            notes=notes,
            parent_version_id=parent_version_id,
        )
        
        return await self.version_repo.create(version)

    async def get_version(self, version_id: UUID) -> PolicyVersion:
        """Get version by ID"""
        version = await self.version_repo.get_by_id(version_id)
        if not version:
            raise PolicyVersionNotFoundError(f"Policy version '{version_id}' not found")
        return version

    async def get_version_by_number(
        self, 
        policy_slug: str, 
        version_number: int
    ) -> PolicyVersion:
        """Get specific version of a policy by version number"""
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
        """List all versions of a policy"""
        policy = await self.get_policy_by_slug(policy_slug)
        return await self.version_repo.get_all_by_policy(policy.id, status_filter)

    async def update_version(
        self,
        version_id: UUID,
        max_steps: Optional[int] = None,
        max_tool_calls: Optional[int] = None,
        max_wall_time_ms: Optional[int] = None,
        tool_timeout_ms: Optional[int] = None,
        max_retries: Optional[int] = None,
        budget_tokens: Optional[int] = None,
        budget_cost_cents: Optional[int] = None,
        extra_config: Optional[Dict[str, Any]] = None,
        notes: Optional[str] = None,
    ) -> PolicyVersion:
        """Update a version (only draft versions can be edited)"""
        version = await self.get_version(version_id)
        
        if not version.is_editable:
            raise PolicyVersionNotEditableError(
                f"Version {version.version} is not editable (status: {version.status})"
            )
        
        update_data = {}
        if max_steps is not None:
            update_data['max_steps'] = max_steps
        if max_tool_calls is not None:
            update_data['max_tool_calls'] = max_tool_calls
        if max_wall_time_ms is not None:
            update_data['max_wall_time_ms'] = max_wall_time_ms
        if tool_timeout_ms is not None:
            update_data['tool_timeout_ms'] = tool_timeout_ms
        if max_retries is not None:
            update_data['max_retries'] = max_retries
        if budget_tokens is not None:
            update_data['budget_tokens'] = budget_tokens
        if budget_cost_cents is not None:
            update_data['budget_cost_cents'] = budget_cost_cents
        if extra_config is not None:
            update_data['extra_config'] = extra_config
        if notes is not None:
            update_data['notes'] = notes
        
        if update_data:
            return await self.version_repo.update(version, update_data)
        return version

    async def delete_version(self, version_id: UUID) -> None:
        """Delete a version (only draft versions can be deleted)"""
        version = await self.get_version(version_id)
        
        if version.status == PolicyStatus.ACTIVE.value:
            raise PolicyError("Cannot delete active version. Deactivate it first.")
        
        await self.version_repo.delete(version)

    async def activate_version(self, version_id: UUID) -> PolicyVersion:
        """
        Activate a version (draft → active).
        Deactivates the currently active version (active → inactive).
        Updates recommended_version_id on the policy.
        """
        version = await self.get_version(version_id)
        
        if not version.can_activate:
            raise PolicyError(
                f"Version {version.version} cannot be activated (status: {version.status})"
            )
        
        # Deactivate currently active version
        await self.version_repo.deactivate_active_version(version.policy_id)
        
        # Activate this version
        await self.version_repo.update_status(version_id, PolicyStatus.ACTIVE.value)
        
        # Update recommended_version_id on policy
        policy = await self.policy_repo.get_by_id(version.policy_id)
        await self.policy_repo.update(policy, {'recommended_version_id': version_id})
        
        # Refresh and return
        return await self.get_version(version_id)

    async def deactivate_version(self, version_id: UUID) -> PolicyVersion:
        """Deactivate a version (draft or active → inactive)"""
        version = await self.get_version(version_id)
        
        if not version.can_deactivate:
            raise PolicyError(
                f"Version {version.version} cannot be deactivated (status: {version.status})"
            )
        
        await self.version_repo.update_status(version_id, PolicyStatus.INACTIVE.value)
        
        # If this was the recommended version, clear it
        policy = await self.policy_repo.get_by_id(version.policy_id)
        if policy.recommended_version_id == version_id:
            await self.policy_repo.update(policy, {'recommended_version_id': None})
        
        return await self.get_version(version_id)

    async def get_recommended_version(self, policy_slug: str) -> Optional[PolicyVersion]:
        """Get the recommended version for a policy"""
        policy = await self.get_policy_by_slug(policy_slug)
        
        if policy.recommended_version_id:
            return await self.version_repo.get_by_id(policy.recommended_version_id)
        
        # Fallback to active version
        return await self.version_repo.get_active_by_policy(policy.id)

    async def update_recommended_version(
        self, 
        policy_slug: str, 
        version_id: UUID
    ) -> Policy:
        """Update the recommended version for a policy"""
        # Use eager loading to avoid MissingGreenlet error
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        
        stmt = select(Policy).where(Policy.slug == policy_slug).options(
            selectinload(Policy.versions),
            selectinload(Policy.recommended_version)
        )
        result = await self.session.execute(stmt)
        policy = result.scalar_one_or_none()
        
        if not policy:
            raise PolicyError(f"Policy '{policy_slug}' not found")
            
        version = await self.get_version(version_id)
        
        # Verify version belongs to this policy
        if version.policy_id != policy.id:
            raise PolicyError("Version does not belong to this policy")
        
        # Verify version is not inactive
        if version.status == PolicyStatus.INACTIVE.value:
            raise PolicyError("Cannot set inactive version as recommended")
        
        await self.policy_repo.update(policy, {'recommended_version_id': version_id})
        
        # Return the policy with eager loaded relationships
        stmt = select(Policy).where(Policy.slug == policy_slug).options(
            selectinload(Policy.versions),
            selectinload(Policy.recommended_version)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    # ─────────────────────────────────────────────────────────────────────────
    # EFFECTIVE LIMITS (for runtime)
    # ─────────────────────────────────────────────────────────────────────────

    async def get_effective_limits(self, policy_id: Optional[UUID]) -> Dict[str, Any]:
        """
        Get effective limits from a policy's recommended version.
        Falls back to default policy if policy_id is None.
        """
        policy = None
        if policy_id:
            policy = await self.policy_repo.get_by_id(policy_id)
        
        if not policy:
            policy = await self.policy_repo.get_default()
        
        if not policy:
            # Hardcoded fallback if no policy exists
            return self._get_fallback_limits()
        
        # Get recommended version
        version = None
        if policy.recommended_version_id:
            version = await self.version_repo.get_by_id(policy.recommended_version_id)
        
        if not version:
            # Fallback to active version
            version = await self.version_repo.get_active_by_policy(policy.id)
        
        if not version:
            return self._get_fallback_limits()
        
        return {
            "max_steps": version.max_steps,
            "max_tool_calls": version.max_tool_calls,
            "max_wall_time_ms": version.max_wall_time_ms,
            "tool_timeout_ms": version.tool_timeout_ms,
            "max_retries": version.max_retries,
            "budget_tokens": version.budget_tokens,
            "budget_cost_cents": version.budget_cost_cents,
            **version.extra_config,
        }

    def _get_fallback_limits(self) -> Dict[str, Any]:
        """Hardcoded fallback limits if no policy exists"""
        return {
            "max_steps": 20,
            "max_tool_calls": 50,
            "max_wall_time_ms": 300000,
            "tool_timeout_ms": 30000,
            "max_retries": 3,
            "budget_tokens": None,
            "budget_cost_cents": None,
        }
