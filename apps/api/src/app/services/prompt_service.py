from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID
import jinja2
from jinja2 import meta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.prompt import Prompt, PromptStatus, PromptType
from app.models.agent import Agent
from app.repositories.prompt_repository import PromptRepository
from app.core.exceptions import NotFoundException, ValidationException
from app.schemas.prompts import (
    PromptCreate, 
    PromptVersionCreate, 
    PromptUpdate,
    PromptListItem,
    PromptResponse,
    AgentUsingPrompt,
    PromptVersionInfo
)


class PromptService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = PromptRepository(session)
        self.env = jinja2.Environment(
            loader=jinja2.BaseLoader(),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
            undefined=jinja2.StrictUndefined
        )

    # ─────────────────────────────────────────────────────────────────────────
    # READ operations
    # ─────────────────────────────────────────────────────────────────────────
    
    async def get_by_id(self, prompt_id: UUID) -> Prompt:
        """Get prompt by ID."""
        prompt = await self.repo.get_by_id(prompt_id)
        if not prompt:
            raise NotFoundException(f"Prompt with id '{prompt_id}' not found")
        return prompt

    async def get_active_template(self, slug: str) -> Prompt:
        """Get active version of prompt by slug (for runtime use)."""
        prompt = await self.repo.get_active_by_slug(slug)
        if not prompt:
            raise NotFoundException(f"No active prompt template '{slug}' found")
        return prompt

    async def get_version(self, slug: str, version: int) -> Prompt:
        """Get specific version of a prompt."""
        prompt = await self.repo.get_by_slug_and_version(slug, version)
        if not prompt:
            raise NotFoundException(f"Prompt '{slug}' version {version} not found")
        return prompt

    async def get_all_versions(self, slug: str) -> List[PromptVersionInfo]:
        """Get all versions of a prompt."""
        versions = await self.repo.get_all_versions(slug)
        if not versions:
            raise NotFoundException(f"Prompt '{slug}' not found")
        return [PromptVersionInfo.model_validate(v) for v in versions]

    async def list_prompts(
        self, 
        skip: int = 0, 
        limit: int = 100,
        type_filter: Optional[str] = None
    ) -> Tuple[List[PromptListItem], int]:
        """List prompts with aggregated version info."""
        items, total = await self.repo.list_prompts(skip, limit, type_filter)
        return [PromptListItem.model_validate(item) for item in items], total

    async def get_agents_using_prompt(
        self, 
        slug: str, 
        version: Optional[int] = None
    ) -> List[AgentUsingPrompt]:
        """Get agents using this prompt (optionally filtered by version)."""
        # For now, agents reference prompt by slug only
        # In future, we might add version reference to Agent model
        stmt = select(Agent.slug, Agent.name).where(
            Agent.system_prompt_slug == slug
        )
        result = await self.session.execute(stmt)
        
        # Get active version for this prompt
        active = await self.repo.get_active_by_slug(slug)
        active_version = active.version if active else 1
        
        return [
            AgentUsingPrompt(
                slug=row.slug, 
                name=row.name, 
                version=active_version
            ) 
            for row in result.all()
        ]

    # ─────────────────────────────────────────────────────────────────────────
    # CREATE operations
    # ─────────────────────────────────────────────────────────────────────────

    async def create_prompt(self, data: PromptCreate) -> Prompt:
        """Create a new prompt (first version as draft)."""
        # Check if slug already exists
        existing = await self.repo.get_latest_by_slug(data.slug)
        if existing:
            raise ValidationException(f"Prompt with slug '{data.slug}' already exists")
        
        # Auto-detect variables
        input_variables = data.input_variables or self.validate_template(data.template)
        
        prompt = Prompt(
            slug=data.slug,
            name=data.name,
            description=data.description,
            template=data.template,
            input_variables=input_variables,
            generation_config=data.generation_config or {},
            version=1,
            status=PromptStatus.DRAFT.value,
            type=data.type,
            parent_version_id=None
        )
        
        return await self.repo.create(prompt)

    async def create_version(self, slug: str, data: PromptVersionCreate) -> Prompt:
        """Create new version from existing prompt."""
        # Get parent version
        parent = await self.repo.get_by_id(data.parent_version_id)
        if not parent:
            raise NotFoundException(f"Parent version not found")
        if parent.slug != slug:
            raise ValidationException(f"Parent version belongs to different prompt")
        
        # Get next version number
        next_version = await self.repo.get_next_version(slug)
        
        # Auto-detect variables
        input_variables = data.input_variables or self.validate_template(data.template)
        
        prompt = Prompt(
            slug=slug,
            name=data.name,
            description=data.description,
            template=data.template,
            input_variables=input_variables,
            generation_config=data.generation_config or {},
            version=next_version,
            status=PromptStatus.DRAFT.value,
            type=parent.type,  # Inherit type from parent
            parent_version_id=parent.id
        )
        
        return await self.repo.create(prompt)

    # ─────────────────────────────────────────────────────────────────────────
    # UPDATE operations
    # ─────────────────────────────────────────────────────────────────────────

    async def update_draft(self, prompt_id: UUID, data: PromptUpdate) -> Prompt:
        """Update a draft prompt. Only drafts can be edited."""
        prompt = await self.get_by_id(prompt_id)
        
        if prompt.status != PromptStatus.DRAFT.value:
            raise ValidationException(
                f"Cannot edit prompt in '{prompt.status}' status. Only drafts can be edited."
            )
        
        update_data = data.model_dump(exclude_unset=True)
        
        # Re-validate template if changed
        if 'template' in update_data:
            update_data['input_variables'] = self.validate_template(update_data['template'])
        
        return await self.repo.update(prompt, update_data)

    async def activate(self, prompt_id: UUID, archive_current: bool = True) -> Prompt:
        """Activate a draft prompt. Optionally archive current active version."""
        prompt = await self.get_by_id(prompt_id)
        
        if prompt.status != PromptStatus.DRAFT.value:
            raise ValidationException(
                f"Cannot activate prompt in '{prompt.status}' status. Only drafts can be activated."
            )
        
        # Archive current active version if requested
        if archive_current:
            await self.repo.archive_active_version(prompt.slug)
        
        # Activate this version
        await self.repo.update_status(prompt_id, PromptStatus.ACTIVE.value)
        prompt.status = PromptStatus.ACTIVE.value
        
        return prompt

    async def archive(self, prompt_id: UUID) -> Prompt:
        """Archive a prompt version."""
        prompt = await self.get_by_id(prompt_id)
        
        if prompt.status == PromptStatus.ARCHIVED.value:
            raise ValidationException("Prompt is already archived")
        
        await self.repo.update_status(prompt_id, PromptStatus.ARCHIVED.value)
        prompt.status = PromptStatus.ARCHIVED.value
        
        return prompt

    # ─────────────────────────────────────────────────────────────────────────
    # RENDER operations
    # ─────────────────────────────────────────────────────────────────────────

    async def render(self, slug: str, variables: Dict[str, Any]) -> str:
        """Render active prompt template with provided variables."""
        prompt = await self.get_active_template(slug)
        return self._render_text(prompt.template, variables)

    async def render_version(
        self, 
        slug: str, 
        version: int, 
        variables: Dict[str, Any]
    ) -> str:
        """Render specific version of prompt template."""
        prompt = await self.get_version(slug, version)
        return self._render_text(prompt.template, variables)

    def _render_text(self, template_str: str, variables: Dict[str, Any]) -> str:
        try:
            template = self.env.from_string(template_str)
            return template.render(**variables)
        except jinja2.UndefinedError as e:
            raise ValidationException(f"Missing variable in prompt template: {e}")
        except jinja2.TemplateSyntaxError as e:
            raise ValidationException(f"Invalid Jinja2 syntax in prompt: {e}")

    def validate_template(self, template_str: str) -> List[str]:
        """Validate Jinja2 syntax and return list of undeclared variables."""
        try:
            ast = self.env.parse(template_str)
            return list(meta.find_undeclared_variables(ast))
        except jinja2.TemplateSyntaxError as e:
            raise ValidationException(f"Invalid Jinja2 syntax: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # BASELINE operations
    # ─────────────────────────────────────────────────────────────────────────

    async def merge_baselines(
        self,
        default_baseline_slug: Optional[str],
        agent_baseline_slug: Optional[str]
    ) -> str:
        """
        Merge default and agent baseline prompts.
        Priority: agent baseline > default baseline
        
        Returns merged template string.
        """
        default_template = ""
        agent_template = ""
        
        # Get default baseline if specified
        if default_baseline_slug:
            try:
                default_prompt = await self.get_active_template(default_baseline_slug)
                if default_prompt.type != PromptType.BASELINE.value:
                    raise ValidationException(
                        f"Prompt '{default_baseline_slug}' is not a baseline (type={default_prompt.type})"
                    )
                default_template = default_prompt.template
            except NotFoundException:
                # Default baseline not found - continue without it
                pass
        
        # Get agent baseline if specified
        if agent_baseline_slug:
            try:
                agent_prompt = await self.get_active_template(agent_baseline_slug)
                if agent_prompt.type != PromptType.BASELINE.value:
                    raise ValidationException(
                        f"Prompt '{agent_baseline_slug}' is not a baseline (type={agent_prompt.type})"
                    )
                agent_template = agent_prompt.template
            except NotFoundException:
                # Agent baseline not found - continue without it
                pass
        
        # Merge with agent priority
        if not default_template and not agent_template:
            return ""
        
        if not default_template:
            return agent_template
        
        if not agent_template:
            return default_template
        
        # Both exist - merge with agent priority (agent comes after default)
        return f"{default_template}\n\n{agent_template}"
