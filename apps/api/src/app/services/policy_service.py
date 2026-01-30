"""
Policy Service - business logic for execution policies
"""
import logging
from typing import List, Optional, Tuple, Dict, Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.policy import Policy
from app.repositories.policy_repository import PolicyRepository

logger = logging.getLogger(__name__)


class PolicyError(Exception):
    """Base exception for policy operations"""
    pass


class PolicyNotFoundError(PolicyError):
    """Policy not found"""
    pass


class PolicyAlreadyExistsError(PolicyError):
    """Policy with this slug already exists"""
    pass


class PolicyService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = PolicyRepository(session)

    async def create_policy(
        self,
        slug: str,
        name: str,
        description: Optional[str] = None,
        max_steps: Optional[int] = None,
        max_tool_calls: Optional[int] = None,
        max_wall_time_ms: Optional[int] = None,
        tool_timeout_ms: Optional[int] = None,
        max_retries: Optional[int] = None,
        budget_tokens: Optional[int] = None,
        budget_cost_cents: Optional[int] = None,
        extra_config: Optional[Dict[str, Any]] = None,
    ) -> Policy:
        """Create a new policy"""
        existing = await self.repo.get_by_slug(slug)
        if existing:
            raise PolicyAlreadyExistsError(f"Policy with slug '{slug}' already exists")
        
        policy = Policy(
            slug=slug,
            name=name,
            description=description,
            max_steps=max_steps,
            max_tool_calls=max_tool_calls,
            max_wall_time_ms=max_wall_time_ms,
            tool_timeout_ms=tool_timeout_ms,
            max_retries=max_retries,
            budget_tokens=budget_tokens,
            budget_cost_cents=budget_cost_cents,
            extra_config=extra_config or {},
        )
        
        return await self.repo.create(policy)

    async def get_policy(self, policy_id: UUID) -> Policy:
        """Get policy by ID"""
        policy = await self.repo.get_by_id(policy_id)
        if not policy:
            raise PolicyNotFoundError(f"Policy '{policy_id}' not found")
        return policy

    async def get_policy_by_slug(self, slug: str) -> Policy:
        """Get policy by slug"""
        policy = await self.repo.get_by_slug(slug)
        if not policy:
            raise PolicyNotFoundError(f"Policy '{slug}' not found")
        return policy

    async def update_policy(
        self,
        policy_id: UUID,
        name: Optional[str] = None,
        description: Optional[str] = None,
        max_steps: Optional[int] = None,
        max_tool_calls: Optional[int] = None,
        max_wall_time_ms: Optional[int] = None,
        tool_timeout_ms: Optional[int] = None,
        max_retries: Optional[int] = None,
        budget_tokens: Optional[int] = None,
        budget_cost_cents: Optional[int] = None,
        extra_config: Optional[Dict[str, Any]] = None,
        is_active: Optional[bool] = None,
    ) -> Policy:
        """Update an existing policy"""
        policy = await self.get_policy(policy_id)
        
        if name is not None:
            policy.name = name
        if description is not None:
            policy.description = description
        if max_steps is not None:
            policy.max_steps = max_steps
        if max_tool_calls is not None:
            policy.max_tool_calls = max_tool_calls
        if max_wall_time_ms is not None:
            policy.max_wall_time_ms = max_wall_time_ms
        if tool_timeout_ms is not None:
            policy.tool_timeout_ms = tool_timeout_ms
        if max_retries is not None:
            policy.max_retries = max_retries
        if budget_tokens is not None:
            policy.budget_tokens = budget_tokens
        if budget_cost_cents is not None:
            policy.budget_cost_cents = budget_cost_cents
        if extra_config is not None:
            policy.extra_config = extra_config
        if is_active is not None:
            policy.is_active = is_active
        
        return await self.repo.update(policy)

    async def delete_policy(self, policy_id: UUID) -> None:
        """Delete a policy"""
        policy = await self.get_policy(policy_id)
        
        # Don't allow deleting the default policy
        if policy.slug == "default":
            raise PolicyError("Cannot delete the default policy")
        
        await self.repo.delete(policy)

    async def list_policies(
        self,
        skip: int = 0,
        limit: int = 100,
        is_active: Optional[bool] = None,
    ) -> Tuple[List[Policy], int]:
        """List policies with filters"""
        return await self.repo.list_policies(skip, limit, is_active)

    async def get_default_policy(self) -> Optional[Policy]:
        """Get the default policy"""
        return await self.repo.get_default()

    async def get_effective_limits(self, policy_id: Optional[UUID]) -> Dict[str, Any]:
        """
        Get effective limits from a policy.
        Falls back to default policy if policy_id is None.
        """
        policy = None
        if policy_id:
            policy = await self.repo.get_by_id(policy_id)
        
        if not policy:
            policy = await self.repo.get_default()
        
        if not policy:
            # Hardcoded fallback if no policy exists
            return {
                "max_steps": 20,
                "max_tool_calls": 50,
                "max_wall_time_ms": 300000,
                "tool_timeout_ms": 30000,
                "max_retries": 3,
                "budget_tokens": None,
                "budget_cost_cents": None,
            }
        
        return {
            "max_steps": policy.max_steps,
            "max_tool_calls": policy.max_tool_calls,
            "max_wall_time_ms": policy.max_wall_time_ms,
            "tool_timeout_ms": policy.tool_timeout_ms,
            "max_retries": policy.max_retries,
            "budget_tokens": policy.budget_tokens,
            "budget_cost_cents": policy.budget_cost_cents,
            **policy.extra_config,
        }
