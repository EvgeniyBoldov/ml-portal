"""
Agent Service v2 - business logic for versioned agents.

Architecture:
- Agent (container) - slug, name, description, current_version_id
- AgentVersion - prompt, policy_id, limit_id, version, status
- AgentBinding - tool bindings per version

Version workflow:
- Create → always draft
- Activate → draft → active (deprecates previous active)
- Deactivate → draft or active → deprecated
"""
import logging
from typing import List, Optional, Tuple, Dict, Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.agent import Agent
from app.models.agent_version import AgentVersion, AgentVersionStatus
from app.models.agent_binding import AgentBinding
from app.models.permission_set import PermissionSet
from app.repositories.agent_repository import AgentRepository, AgentVersionRepository

logger = logging.getLogger(__name__)


class AgentError(Exception):
    pass


class AgentNotFoundError(AgentError):
    pass


class AgentVersionNotFoundError(AgentError):
    pass


class AgentAlreadyExistsError(AgentError):
    pass


class AgentVersionNotEditableError(AgentError):
    pass


class AgentService:
    """Service for managing agents and their versions"""

    DEFAULT_AGENT = "chat-simple"
    RAG_AGENT = "chat-rag"

    def __init__(self, session: AsyncSession):
        self.session = session
        self.agent_repo = AgentRepository(session)
        self.version_repo = AgentVersionRepository(session)

    # ─────────────────────────────────────────────────────────────────────────
    # AGENT CONTAINER operations
    # ─────────────────────────────────────────────────────────────────────────

    async def create_agent(
        self,
        slug: str,
        name: str,
        description: Optional[str] = None,
    ) -> Agent:
        existing = await self.agent_repo.get_by_slug(slug)
        if existing:
            raise AgentAlreadyExistsError(f"Agent with slug '{slug}' already exists")

        agent = Agent(slug=slug, name=name, description=description)
        agent = await self.agent_repo.create(agent)

        await self._add_agent_to_default_permissions(agent.slug)

        return agent

    async def get_agent(self, agent_id: UUID) -> Agent:
        agent = await self.agent_repo.get_by_id(agent_id)
        if not agent:
            raise AgentNotFoundError(f"Agent '{agent_id}' not found")
        return agent

    async def get_agent_by_slug(self, slug: str) -> Agent:
        agent = await self.agent_repo.get_by_slug(slug)
        if not agent:
            raise AgentNotFoundError(f"Agent '{slug}' not found")
        return agent

    async def get_agent_with_versions(self, slug: str) -> Agent:
        agent = await self.agent_repo.get_by_slug_with_versions(slug)
        if not agent:
            raise AgentNotFoundError(f"Agent '{slug}' not found")
        return agent

    async def update_agent(
        self,
        agent_id: UUID,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Agent:
        agent = await self.get_agent(agent_id)
        update_data = {}
        if name is not None:
            update_data['name'] = name
        if description is not None:
            update_data['description'] = description
        if update_data:
            return await self.agent_repo.update(agent, update_data)
        return agent

    async def delete_agent(self, agent_id: UUID) -> None:
        agent = await self.get_agent(agent_id)
        await self.agent_repo.delete(agent)

    async def list_agents(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> Tuple[List[Agent], int]:
        return await self.agent_repo.list_agents(skip, limit)

    async def _add_agent_to_default_permissions(self, agent_slug: str):
        stmt = select(PermissionSet).where(
            PermissionSet.scope == "default",
            PermissionSet.tenant_id.is_(None),
            PermissionSet.user_id.is_(None)
        )
        result = await self.session.execute(stmt)
        default_perms = result.scalar_one_or_none()

        if not default_perms:
            logger.warning("Default permission set not found, skipping auto-add for agent")
            return

        agent_permissions = dict(default_perms.agent_permissions or {})
        if agent_slug in agent_permissions:
            return

        agent_permissions[agent_slug] = "denied"
        default_perms.agent_permissions = agent_permissions
        self.session.add(default_perms)
        await self.session.flush()
        logger.info(f"Added agent '{agent_slug}' to default permissions (status: denied)")

    # ─────────────────────────────────────────────────────────────────────────
    # AGENT VERSION operations
    # ─────────────────────────────────────────────────────────────────────────

    async def create_version(
        self,
        agent_slug: str,
        prompt: Optional[str] = None,
        policy_id: Optional[UUID] = None,
        limit_id: Optional[UUID] = None,
        notes: Optional[str] = None,
        parent_version_id: Optional[UUID] = None,
    ) -> AgentVersion:
        """
        Create a new agent version (always draft).

        If parent_version_id is provided, inherits prompt/policy_id/limit_id
        from the parent version. Explicit values override inherited ones.
        """
        agent = await self.get_agent_by_slug(agent_slug)
        next_version = await self.version_repo.get_next_version(agent.id)

        # Inherit from parent version if specified
        inherited_prompt = ""
        inherited_policy_id = None
        inherited_limit_id = None

        if parent_version_id:
            parent = await self.version_repo.get_by_id(parent_version_id)
            if parent and parent.agent_id == agent.id:
                inherited_prompt = parent.prompt
                inherited_policy_id = parent.policy_id
                inherited_limit_id = parent.limit_id
                logger.info(
                    f"Inheriting from v{parent.version} for agent '{agent_slug}'"
                )
            else:
                logger.warning(
                    f"Parent version {parent_version_id} not found or belongs to another agent"
                )

        version = AgentVersion(
            agent_id=agent.id,
            version=next_version,
            status=AgentVersionStatus.DRAFT.value,
            prompt=prompt if prompt is not None else inherited_prompt,
            policy_id=policy_id if policy_id is not None else inherited_policy_id,
            limit_id=limit_id if limit_id is not None else inherited_limit_id,
            notes=notes,
            parent_version_id=parent_version_id,
        )
        return await self.version_repo.create(version)

    async def get_version(self, version_id: UUID) -> AgentVersion:
        version = await self.version_repo.get_by_id(version_id)
        if not version:
            raise AgentVersionNotFoundError(f"Agent version '{version_id}' not found")
        return version

    async def get_version_by_number(
        self, agent_slug: str, version_number: int
    ) -> AgentVersion:
        agent = await self.get_agent_by_slug(agent_slug)
        version = await self.version_repo.get_by_agent_and_version(agent.id, version_number)
        if not version:
            raise AgentVersionNotFoundError(
                f"Version {version_number} not found for agent '{agent_slug}'"
            )
        return version

    async def list_versions(
        self, agent_slug: str, status_filter: Optional[str] = None
    ) -> List[AgentVersion]:
        agent = await self.get_agent_by_slug(agent_slug)
        return await self.version_repo.get_all_by_agent(agent.id, status_filter)

    async def update_version(
        self,
        version_id: UUID,
        prompt: Optional[str] = None,
        policy_id: Optional[UUID] = None,
        limit_id: Optional[UUID] = None,
        notes: Optional[str] = None,
    ) -> AgentVersion:
        version = await self.get_version(version_id)
        if not version.is_editable:
            raise AgentVersionNotEditableError(
                f"Version {version.version} is not editable (status: {version.status})"
            )

        update_data: Dict[str, Any] = {}
        if prompt is not None:
            update_data['prompt'] = prompt
        if policy_id is not None:
            update_data['policy_id'] = policy_id
        if limit_id is not None:
            update_data['limit_id'] = limit_id
        if notes is not None:
            update_data['notes'] = notes

        if update_data:
            return await self.version_repo.update(version, update_data)
        return version

    async def delete_version(self, version_id: UUID) -> None:
        version = await self.get_version(version_id)
        if version.status == AgentVersionStatus.ACTIVE.value:
            raise AgentError("Cannot delete active version. Deactivate it first.")
        await self.version_repo.delete(version)

    async def activate_version(self, version_id: UUID) -> AgentVersion:
        version = await self.get_version(version_id)
        if not version.can_activate:
            raise AgentError(
                f"Version {version.version} cannot be activated (status: {version.status})"
            )

        await self.version_repo.deactivate_active_version(version.agent_id)
        await self.version_repo.update_status(version_id, AgentVersionStatus.ACTIVE.value)

        agent = await self.agent_repo.get_by_id(version.agent_id)
        await self.agent_repo.update(agent, {'current_version_id': version_id})

        return await self.get_version(version_id)

    async def deactivate_version(self, version_id: UUID) -> AgentVersion:
        version = await self.get_version(version_id)
        if not version.can_deactivate:
            raise AgentError(
                f"Version {version.version} cannot be deactivated (status: {version.status})"
            )

        await self.version_repo.update_status(version_id, AgentVersionStatus.DEPRECATED.value)

        agent = await self.agent_repo.get_by_id(version.agent_id)
        if agent.current_version_id == version_id:
            await self.agent_repo.update(agent, {'current_version_id': None})

        return await self.get_version(version_id)

    # ─────────────────────────────────────────────────────────────────────────
    # RUNTIME helpers
    # ─────────────────────────────────────────────────────────────────────────

    async def resolve_active_version(
        self, agent_slug: Optional[str] = None, use_rag: bool = False
    ) -> AgentVersion:
        """
        Resolve the active AgentVersion for runtime.
        Falls back to default agent if slug not found.
        """
        if agent_slug is None:
            agent_slug = self.RAG_AGENT if use_rag else self.DEFAULT_AGENT

        agent = await self.agent_repo.get_by_slug(agent_slug)
        if not agent:
            agent = await self.agent_repo.get_by_slug(self.DEFAULT_AGENT)
            if not agent:
                raise AgentNotFoundError(
                    f"Default agent '{self.DEFAULT_AGENT}' not found. Run migrations."
                )

        version = None
        if agent.current_version_id:
            version = await self.version_repo.get_by_id(agent.current_version_id)
        if not version:
            version = await self.version_repo.get_active_by_agent(agent.id)
        if not version:
            raise AgentVersionNotFoundError(
                f"No active version for agent '{agent.slug}'"
            )

        return version

    async def resolve_agent_for_chat(
        self,
        agent_slug: Optional[str] = None,
        use_rag: bool = False,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Convenience method for ChatStreamService.

        Returns:
            Tuple of (prompt_text, metadata_dict)
        """
        version = await self.resolve_active_version(agent_slug, use_rag)
        agent = await self.agent_repo.get_by_id(version.agent_id)

        return (
            version.prompt,
            {
                "agent_slug": agent.slug,
                "agent_version": version.version,
                "policy_id": str(version.policy_id) if version.policy_id else None,
                "limit_id": str(version.limit_id) if version.limit_id else None,
            }
        )
