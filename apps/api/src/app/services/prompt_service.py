from typing import Dict, Any, List, Optional
from uuid import UUID
import re

from jinja2 import Environment, TemplateSyntaxError, meta
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.prompt import Prompt, PromptVersion, PromptStatus
from app.repositories.prompt_repository import PromptRepository, PromptVersionRepository
from app.core.exceptions import NotFoundException, ValidationException


class PromptService:
    """Service for managing prompts and their versions"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.prompt_repo = PromptRepository(session)
        self.version_repo = PromptVersionRepository(session)
        self.jinja_env = Environment()

    # ─────────────────────────────────────────────────────────────────────────
    # VALIDATION
    # ─────────────────────────────────────────────────────────────────────────

    def validate_template(self, template: str) -> List[str]:
        """Validate Jinja2 template and extract variables"""
        try:
            ast = self.jinja_env.parse(template)
            variables = list(meta.find_undeclared_variables(ast))
            return variables
        except TemplateSyntaxError as e:
            raise ValidationException(f"Invalid Jinja2 template: {e}")

    def _render_text(self, template: str, variables: Dict[str, Any]) -> str:
        """Render Jinja2 template with variables"""
        try:
            tmpl = self.jinja_env.from_string(template)
            return tmpl.render(**variables)
        except Exception as e:
            raise ValidationException(f"Template rendering failed: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # PROMPT CONTAINER operations
    # ─────────────────────────────────────────────────────────────────────────

    async def create_prompt(
        self,
        slug: str,
        name: str,
        description: Optional[str],
        type: str
    ) -> Prompt:
        """Create new prompt container"""
        # Check if slug already exists
        existing = await self.prompt_repo.get_by_slug(slug)
        if existing:
            raise ValidationException(f"Prompt with slug '{slug}' already exists")
        
        prompt = Prompt(
            slug=slug,
            name=name,
            description=description,
            type=type
        )
        
        return await self.prompt_repo.create(prompt)

    async def get_prompt_by_slug(self, slug: str) -> Prompt:
        """Get prompt container by slug"""
        prompt = await self.prompt_repo.get_by_slug(slug)
        if not prompt:
            raise NotFoundException(f"Prompt '{slug}' not found")
        return prompt

    async def get_prompt_by_id(self, prompt_id: UUID) -> Prompt:
        """Get prompt container by ID"""
        prompt = await self.prompt_repo.get_by_id(prompt_id)
        if not prompt:
            raise NotFoundException(f"Prompt not found")
        return prompt

    async def update_prompt(
        self,
        prompt_id: UUID,
        name: Optional[str] = None,
        description: Optional[str] = None
    ) -> Prompt:
        """Update prompt container metadata"""
        prompt = await self.get_prompt_by_id(prompt_id)
        
        update_data = {}
        if name is not None:
            update_data['name'] = name
        if description is not None:
            update_data['description'] = description
        
        if update_data:
            return await self.prompt_repo.update(prompt, update_data)
        return prompt

    async def list_prompts(
        self,
        skip: int = 0,
        limit: int = 100,
        type_filter: Optional[str] = None
    ):
        """List prompt containers"""
        return await self.prompt_repo.list_prompts(skip, limit, type_filter)

    # ─────────────────────────────────────────────────────────────────────────
    # VERSION operations
    # ─────────────────────────────────────────────────────────────────────────

    async def create_version(
        self,
        slug: str,
        template: str,
        parent_version_id: Optional[UUID] = None,
        input_variables: Optional[List[str]] = None,
        generation_config: Optional[Dict[str, Any]] = None
    ) -> PromptVersion:
        """Create new version of a prompt"""
        # Get prompt container
        prompt = await self.get_prompt_by_slug(slug)
        
        # Auto-detect variables if not provided
        if input_variables is None:
            input_variables = self.validate_template(template)
        
        # Determine version number
        next_version = await self.version_repo.get_next_version(prompt.id)
        
        # Get parent version data if specified
        if parent_version_id:
            parent = await self.version_repo.get_by_id(parent_version_id)
            if not parent:
                raise NotFoundException("Parent version not found")
            if parent.prompt_id != prompt.id:
                raise ValidationException("Parent version belongs to different prompt")
        
        version = PromptVersion(
            prompt_id=prompt.id,
            template=template,
            input_variables=input_variables,
            generation_config=generation_config or {},
            version=next_version,
            status=PromptStatus.DRAFT.value,
            parent_version_id=parent_version_id
        )
        
        return await self.version_repo.create(version)

    async def get_version_by_id(self, version_id: UUID) -> PromptVersion:
        """Get version by ID"""
        version = await self.version_repo.get_by_id(version_id)
        if not version:
            raise NotFoundException("Version not found")
        return version

    async def get_version_by_number(self, slug: str, version: int) -> PromptVersion:
        """Get specific version by slug and version number"""
        prompt = await self.get_prompt_by_slug(slug)
        version_obj = await self.version_repo.get_by_prompt_and_version(prompt.id, version)
        if not version_obj:
            raise NotFoundException(f"Version {version} not found for prompt '{slug}'")
        return version_obj

    async def get_active_version(self, slug: str) -> PromptVersion:
        """Get active version of a prompt"""
        prompt = await self.get_prompt_by_slug(slug)
        version = await self.version_repo.get_active_by_prompt(prompt.id)
        if not version:
            raise NotFoundException(f"No active version for prompt '{slug}'")
        return version

    async def get_all_versions(self, slug: str) -> List[PromptVersion]:
        """Get all versions of a prompt"""
        prompt = await self.get_prompt_by_slug(slug)
        return await self.version_repo.get_all_by_prompt(prompt.id)

    async def update_version(
        self,
        version_id: UUID,
        template: Optional[str] = None,
        input_variables: Optional[List[str]] = None,
        generation_config: Optional[Dict[str, Any]] = None
    ) -> PromptVersion:
        """Update draft version"""
        version = await self.get_version_by_id(version_id)
        
        if version.status != PromptStatus.DRAFT.value:
            raise ValidationException(
                f"Cannot edit version in '{version.status}' status. Only drafts can be edited."
            )
        
        update_data = {}
        
        if template is not None:
            update_data['template'] = template
            # Re-validate and update variables
            update_data['input_variables'] = self.validate_template(template)
        
        if input_variables is not None:
            update_data['input_variables'] = input_variables
        
        if generation_config is not None:
            update_data['generation_config'] = generation_config
        
        if update_data:
            return await self.version_repo.update(version, update_data)
        return version

    async def activate_version(
        self,
        version_id: UUID,
        archive_current: bool = True
    ) -> PromptVersion:
        """Activate a draft version"""
        version = await self.get_version_by_id(version_id)
        
        if version.status != PromptStatus.DRAFT.value:
            raise ValidationException(
                f"Cannot activate version in '{version.status}' status. Only drafts can be activated."
            )
        
        # Archive current active version if requested
        if archive_current:
            await self.version_repo.archive_active_version(version.prompt_id)
        
        # Activate this version
        await self.version_repo.update_status(version_id, PromptStatus.ACTIVE.value)
        version.status = PromptStatus.ACTIVE.value
        
        return version

    async def archive_version(self, version_id: UUID) -> PromptVersion:
        """Archive a version"""
        version = await self.get_version_by_id(version_id)
        
        if version.status == PromptStatus.ARCHIVED.value:
            raise ValidationException("Version is already archived")
        
        await self.version_repo.update_status(version_id, PromptStatus.ARCHIVED.value)
        version.status = PromptStatus.ARCHIVED.value
        
        return version

    # ─────────────────────────────────────────────────────────────────────────
    # RENDER operations
    # ─────────────────────────────────────────────────────────────────────────

    async def render_active(self, slug: str, variables: Dict[str, Any]) -> str:
        """Render active version template with provided variables"""
        version = await self.get_active_version(slug)
        return self._render_text(version.template, variables)

    async def render_version(
        self,
        slug: str,
        version_number: int,
        variables: Dict[str, Any]
    ) -> str:
        """Render specific version template with provided variables"""
        version = await self.get_version_by_number(slug, version_number)
        return self._render_text(version.template, variables)
