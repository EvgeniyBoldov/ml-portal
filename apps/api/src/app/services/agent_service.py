"""
Agent Service v2 - business logic for versioned agents.

Architecture:
- Agent (container) - human-readable metadata (name, slug, description, tags)
- AgentVersion - prompt parts, execution config, safety knobs, and routing fields
- Runtime routing uses version metadata + operation bindings.

Version workflow:
- Create → always draft
- Publish → draft → published (archives previous published)
- Archive → published → archived
"""
import logging
from typing import List, Optional, Tuple, Dict, Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import asc
from sqlalchemy.future import select

from app.core.exceptions import (
    AgentNotFoundError,
    AgentVersionNotFoundError,
    AgentAlreadyExistsError,
    AgentVersionNotEditableError,
    AppError as AgentError,
)
from app.models.agent import Agent
from app.models.agent_version import AgentVersion, AgentVersionStatus
from app.models.tool_instance import ToolInstance
from app.services.rbac_service import RbacService
from app.models.tenant import Tenants
from app.repositories.agent_repository import AgentRepository, AgentVersionRepository

logger = logging.getLogger(__name__)


LEGACY_AGENT_SLUG_ALIASES = {
    "rag-search": "knowledge-base-search",
}


class AgentService:
    """Service for managing agents and their versions"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.agent_repo = AgentRepository(session)
        self.version_repo = AgentVersionRepository(session)

    @staticmethod
    def _normalize_agent_slug(slug: Optional[str]) -> Optional[str]:
        if slug is None:
            return None
        return LEGACY_AGENT_SLUG_ALIASES.get(slug, slug)

    # ─────────────────────────────────────────────────────────────────────────
    # AGENT CONTAINER operations
    # ─────────────────────────────────────────────────────────────────────────

    async def create_agent(
        self,
        slug: str,
        name: str,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        logging_level: str = "brief",
        model: Optional[str] = None,
        allowed_collection_ids: Optional[List[UUID]] = None,
    ) -> Agent:
        existing = await self.agent_repo.get_by_slug(slug)
        if existing:
            raise AgentAlreadyExistsError(f"Agent with slug '{slug}' already exists")

        agent = Agent(
            slug=slug,
            name=name,
            description=description,
            tags=tags,
            logging_level=logging_level,
            model=model,
            allowed_collection_ids=allowed_collection_ids,
        )
        agent = await self.agent_repo.create(agent)

        rbac = RbacService(self.session)
        await rbac.ensure_platform_deny("agent", agent.id)

        return agent

    async def get_agent(self, agent_id: UUID) -> Agent:
        agent = await self.agent_repo.get_by_id(agent_id)
        if not agent:
            raise AgentNotFoundError(f"Agent '{agent_id}' not found")
        return agent

    async def get_agent_by_slug(self, slug: str) -> Agent:
        normalized_slug = self._normalize_agent_slug(slug)
        agent = await self.agent_repo.get_by_slug(normalized_slug)
        if not agent and normalized_slug != slug:
            agent = await self.agent_repo.get_by_slug(slug)
        if not agent:
            raise AgentNotFoundError(slug)
        return agent

    async def get_agent_with_versions(self, slug: str) -> Agent:
        normalized_slug = self._normalize_agent_slug(slug)
        agent = await self.agent_repo.get_by_slug_with_versions(normalized_slug)
        if not agent and normalized_slug != slug:
            agent = await self.agent_repo.get_by_slug_with_versions(slug)
        if not agent:
            raise AgentNotFoundError(slug)
        return agent

    async def get_agent_with_versions_by_id(self, agent_id: UUID) -> Agent:
        agent = await self.agent_repo.get_by_id_with_versions(agent_id)
        if not agent:
            raise AgentNotFoundError(agent_id)
        return agent

    async def get_agent_detail(self, agent_id: UUID) -> Dict[str, Any]:
        """Build AgentDetailResponse with versions."""
        agent = await self.agent_repo.get_by_id_with_versions(agent_id)
        if not agent:
            raise AgentNotFoundError(agent_id)

        enriched_versions = []
        for version in agent.versions:
            version_info = {
                "id": version.id,
                "agent_id": version.agent_id,
                "version": version.version,
                "status": version.status,
                # Prompt parts
                "identity": version.identity,
                "mission": version.mission,
                "scope": version.scope,
                "rules": version.rules,
                "tool_use_rules": version.tool_use_rules,
                "output_format": version.output_format,
                "examples": version.examples,
                # Execution config
                "model": version.model,
                "timeout_s": version.timeout_s,
                "max_steps": version.max_steps,
                "max_retries": version.max_retries,
                "max_tokens": version.max_tokens,
                "temperature": version.temperature,
                # Safety knobs
                "requires_confirmation_for_write": version.requires_confirmation_for_write,
                "risk_level": version.risk_level,
                "never_do": version.never_do,
                "allowed_ops": version.allowed_ops,
                # Routing
                "short_info": version.short_info,
                "tags": version.tags,
                "is_routable": version.is_routable,
                "routing_keywords": version.routing_keywords,
                "routing_negative_keywords": version.routing_negative_keywords,
                # Meta
                "notes": version.notes,
                "created_at": version.created_at,
                "updated_at": version.updated_at,
            }
            enriched_versions.append(version_info)

        return {
            "id": agent.id,
            "slug": agent.slug,
            "name": agent.name,
            "description": agent.description,
            "tags": agent.tags,
            "current_version_id": agent.current_version_id,
            "logging_level": agent.logging_level,
            "model": agent.model,
            "allowed_collection_ids": agent.allowed_collection_ids,
            "created_at": agent.created_at,
            "updated_at": agent.updated_at,
            "versions": enriched_versions,
        }

    async def update_agent(
        self,
        agent_id: UUID,
        name: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        logging_level: Optional[str] = None,
        model: Optional[str] = None,
        allowed_collection_ids: Optional[List[UUID]] = None,
    ) -> Agent:
        agent = await self.get_agent(agent_id)
        update_data = {}
        if name is not None:
            update_data['name'] = name
        if description is not None:
            update_data['description'] = description
        if tags is not None:
            update_data['tags'] = tags
        if logging_level is not None:
            update_data['logging_level'] = logging_level
        if model is not None:
            update_data['model'] = model
        if allowed_collection_ids is not None:
            update_data['allowed_collection_ids'] = allowed_collection_ids
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

    async def route_agent(self, request_text: str) -> Optional[Agent]:
        """Select best routable agent by keyword scoring over routing metadata."""
        stmt = (
            select(Agent, AgentVersion)
            .join(AgentVersion, Agent.current_version_id == AgentVersion.id)
            .where(
                AgentVersion.is_routable.is_(True),
                AgentVersion.status == AgentVersionStatus.PUBLISHED.value,
            )
        )
        result = await self.session.execute(stmt)
        candidates = result.all()

        if not candidates:
            return None

        normalized_text = request_text.lower().strip()

        def score(agent: Agent, version: AgentVersion) -> int:
            value = 0

            # Positive keywords
            if version.routing_keywords:
                for kw in version.routing_keywords:
                    if kw.lower() in normalized_text:
                        value += 3

            # Negative keywords (penalty)
            if version.routing_negative_keywords:
                for kw in version.routing_negative_keywords:
                    if kw.lower() in normalized_text:
                        value -= 5

            # Tags as secondary signal
            version_tags = version.tags or []
            for tag in version_tags:
                if tag.lower() in normalized_text:
                    value += 1

            if agent.tags:
                for tag in agent.tags:
                    if tag.lower() in normalized_text:
                        value += 1

            return value

        ranked = sorted(candidates, key=lambda row: score(row[0], row[1]), reverse=True)
        best_agent, best_version = ranked[0]
        return best_agent if score(best_agent, best_version) > 0 else None


    # ─────────────────────────────────────────────────────────────────────────
    # AGENT VERSION operations
    # ─────────────────────────────────────────────────────────────────────────

    async def create_version(
        self,
        agent_slug: str,
        data: Dict[str, Any],
        parent_version_id: Optional[UUID] = None,
    ) -> AgentVersion:
        """
        Create a new agent version (always draft).

        If parent_version_id is provided, inherits all fields
        from the parent version. Explicit values override inherited ones.
        """
        agent = await self.get_agent_by_slug(agent_slug)
        return await self._create_version_for_agent(agent.id, data, parent_version_id)

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

    async def get_version_by_number_and_agent_id(
        self, agent_id: UUID, version_number: int
    ) -> AgentVersion:
        version = await self.version_repo.get_by_agent_and_version(agent_id, version_number)
        if not version:
            raise AgentVersionNotFoundError(
                f"Version {version_number} not found for agent '{agent_id}'"
            )
        return version

    async def list_versions(
        self, agent_slug: str, status_filter: Optional[str] = None
    ) -> List[AgentVersion]:
        agent = await self.get_agent_by_slug(agent_slug)
        return await self.version_repo.get_all_by_agent(agent.id, status_filter)

    async def list_versions_by_agent_id(
        self, agent_id: UUID, status_filter: Optional[str] = None
    ) -> List[AgentVersion]:
        return await self.version_repo.get_all_by_agent(agent_id, status_filter)

    async def create_version_by_agent_id(
        self,
        agent_id: UUID,
        data: Dict[str, Any],
        parent_version_id: Optional[UUID] = None,
    ) -> AgentVersion:
        await self.get_agent(agent_id)
        return await self._create_version_for_agent(agent_id, data, parent_version_id)

    # ── Version fields that can be inherited from parent ─────────────────
    _VERSION_FIELDS = [
        "identity", "mission", "scope", "rules", "tool_use_rules",
        "output_format", "examples",
        "model", "timeout_s", "max_steps", "max_retries", "max_tokens", "temperature",
        "requires_confirmation_for_write", "risk_level", "never_do", "allowed_ops",
        "short_info", "tags", "is_routable", "routing_keywords", "routing_negative_keywords",
    ]

    async def _create_version_for_agent(
        self,
        agent_id: UUID,
        data: Dict[str, Any],
        parent_version_id: Optional[UUID] = None,
    ) -> AgentVersion:
        next_version = await self.version_repo.get_next_version(agent_id)

        inherited: Dict[str, Any] = {}
        if parent_version_id:
            parent = await self.version_repo.get_by_id(parent_version_id)
            if parent and parent.agent_id == agent_id:
                for f in self._VERSION_FIELDS:
                    val = getattr(parent, f, None)
                    if val is not None:
                        inherited[f] = val
                logger.info(f"Inheriting from v{parent.version} for agent {agent_id}")

        version_data = {**inherited}
        for f in self._VERSION_FIELDS + ["notes"]:
            if f in data and data[f] is not None:
                version_data[f] = data[f]

        version = AgentVersion(
            agent_id=agent_id,
            version=next_version,
            status=AgentVersionStatus.DRAFT.value,
            parent_version_id=parent_version_id,
            **version_data,
        )
        return await self.version_repo.create(version)

    async def update_version(
        self,
        version_id: UUID,
        data: Dict[str, Any],
    ) -> AgentVersion:
        version = await self.get_version(version_id)
        if not version.is_editable:
            raise AgentVersionNotEditableError(
                f"Version {version.version} is not editable (status: {version.status})"
            )

        update_data: Dict[str, Any] = {}
        for f in self._VERSION_FIELDS + ["notes"]:
            if f in data and data[f] is not None:
                update_data[f] = data[f]

        if update_data:
            return await self.version_repo.update(version, update_data)
        return version

    async def delete_version(self, version_id: UUID) -> None:
        version = await self.get_version(version_id)
        if version.status not in {
            AgentVersionStatus.PUBLISHED.value,
            AgentVersionStatus.ARCHIVED.value,
        }:
            raise AgentError(
                f"Only published or archived versions can be deleted (status: {version.status})."
            )
        agent = await self.agent_repo.get_by_id(version.agent_id)
        if agent and agent.current_version_id == version_id:
            raise AgentError("Cannot delete current version. Rebind another published version first.")
        await self.version_repo.delete(version)

    async def publish_version(self, version_id: UUID) -> AgentVersion:
        version = await self.get_version(version_id)
        if not version.can_publish:
            raise AgentError(
                f"Version {version.version} cannot be published (status: {version.status})"
            )

        await self.version_repo.update_status(version_id, AgentVersionStatus.PUBLISHED.value)

        return await self.get_version(version_id)

    async def archive_version(self, version_id: UUID) -> AgentVersion:
        version = await self.get_version(version_id)
        if not version.can_archive:
            raise AgentError(
                f"Version {version.version} cannot be archived (status: {version.status})"
            )

        await self.version_repo.update_status(version_id, AgentVersionStatus.ARCHIVED.value)

        agent = await self.agent_repo.get_by_id(version.agent_id)
        if agent.current_version_id == version_id:
            await self.agent_repo.update(agent, {'current_version_id': None})

        return await self.get_version(version_id)

    async def set_current_version(self, agent_id: UUID, version_id: UUID) -> Dict[str, Any]:
        """Set current version for an agent. Version must be published."""
        agent = await self.get_agent(agent_id)
        version = await self.get_version(version_id)
        
        if version.agent_id != agent_id:
            raise AgentError(f"Version {version_id} does not belong to agent {agent_id}")
        
        if version.status != AgentVersionStatus.PUBLISHED.value:
            raise AgentError(f"Version {version.version} must be published to set as current")
        
        await self.agent_repo.update(agent, {'current_version_id': version_id})
        
        # Return enriched agent detail
        return await self.get_agent_detail(agent_id)

    # ─────────────────────────────────────────────────────────────────────────
    # RUNTIME helpers
    # ─────────────────────────────────────────────────────────────────────────

    async def get_default_agent_slug(self, tenant_id: Optional[UUID] = None) -> str:
        """
        Resolve default agent slug for a tenant.
        Priority:
        1) tenant.default_agent_slug (if exists in DB)
        2) first routable published agent
        3) first agent with any published version
        """
        tenant_default: Optional[str] = None
        if tenant_id:
            result = await self.session.execute(
                select(Tenants.default_agent_slug).where(Tenants.id == tenant_id)
            )
            tenant_default = result.scalar_one_or_none()

        candidate_slugs: List[str] = []
        normalized_tenant_default = self._normalize_agent_slug(tenant_default)
        if normalized_tenant_default:
            candidate_slugs.append(normalized_tenant_default)
        if tenant_default and tenant_default not in candidate_slugs:
            candidate_slugs.append(tenant_default)
        for candidate in candidate_slugs:
            if not candidate:
                continue
            if await self.agent_repo.get_by_slug(candidate):
                return candidate

        # Choose the first routable published agent deterministically.
        routable_stmt = (
            select(Agent.slug)
            .join(AgentVersion, Agent.current_version_id == AgentVersion.id)
            .where(
                AgentVersion.is_routable.is_(True),
                AgentVersion.status == AgentVersionStatus.PUBLISHED.value,
            )
            .order_by(asc(Agent.created_at))
            .limit(1)
        )
        routable_slug = (await self.session.execute(routable_stmt)).scalar_one_or_none()
        if routable_slug:
            return routable_slug

        # Last resort: any agent with a published version.
        published_stmt = (
            select(Agent.slug)
            .join(AgentVersion, Agent.id == AgentVersion.agent_id)
            .where(AgentVersion.status == AgentVersionStatus.PUBLISHED.value)
            .order_by(asc(Agent.created_at))
            .limit(1)
        )
        published_slug = (await self.session.execute(published_stmt)).scalar_one_or_none()
        if published_slug:
            return published_slug

        raise AgentNotFoundError("no_published_agent_available")

    async def list_routable_agents(self) -> List[Agent]:
        """
        List only agents that have a published routable version.
        Used by triage to build available_agents list.
        """
        stmt = (
            select(Agent)
            .join(AgentVersion, Agent.current_version_id == AgentVersion.id)
            .where(
                AgentVersion.is_routable.is_(True),
                AgentVersion.status == AgentVersionStatus.PUBLISHED.value,
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def resolve_published_version(
        self,
        agent_slug: Optional[str] = None,
        tenant_id: Optional[UUID] = None,
    ) -> AgentVersion:
        """
        Resolve the published AgentVersion for runtime.
        Falls back to tenant default agent if slug not found.
        """
        selected_slug = self._normalize_agent_slug(agent_slug) if agent_slug is not None else None
        if selected_slug is None:
            selected_slug = await self.get_default_agent_slug(tenant_id)

        agent = await self.agent_repo.get_by_slug(selected_slug)
        if not agent:
            fallback = await self.get_default_agent_slug(tenant_id)
            agent = await self.agent_repo.get_by_slug(fallback)
            if not agent:
                raise AgentNotFoundError(fallback)

        version = None
        if agent.current_version_id:
            version = await self.version_repo.get_by_id(agent.current_version_id)
        if not version:
            version = await self.version_repo.get_published_by_agent(agent.id)
        if not version:
            raise AgentVersionNotFoundError(
                f"No published version for agent '{agent.slug}'"
            )

        return version

    async def resolve_agent_for_chat(
        self,
        agent_slug: Optional[str] = None,
        tenant_id: Optional[UUID] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Convenience method for ChatStreamService.

        Returns:
            Tuple of (prompt_text, metadata_dict)
        """
        version = await self.resolve_published_version(agent_slug, tenant_id)
        agent = await self.agent_repo.get_by_id(version.agent_id)

        return (
            version.compiled_prompt,
            {
                "agent_slug": agent.slug,
                "agent_version": version.version,
                "model": version.model,
                "max_steps": version.max_steps,
                "timeout_s": version.timeout_s,
                "max_tokens": version.max_tokens,
                "temperature": version.temperature,
            }
        )
