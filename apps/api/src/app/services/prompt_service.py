from typing import Any, Dict, List, Optional, Tuple
import jinja2
from jinja2 import meta

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.prompt import Prompt
from app.repositories.prompt_repository import PromptRepository
from app.core.exceptions import NotFoundException, ValidationException


class PromptService:
    def __init__(self, session: AsyncSession):
        self.repo = PromptRepository(session)
        self.env = jinja2.Environment(
            loader=jinja2.BaseLoader(),
            autoescape=False,  # Prompts usually need raw text
            trim_blocks=True,
            lstrip_blocks=True,
            undefined=jinja2.StrictUndefined  # Raise error on missing vars
        )

    async def get_template(self, slug: str) -> Prompt:
        prompt = await self.repo.get_by_slug(slug)
        if not prompt:
            raise NotFoundException(f"Prompt template '{slug}' not found")
        return prompt

    async def render(self, slug: str, variables: Dict[str, Any]) -> str:
        """
        Render a prompt template by slug with provided variables.
        Validates that all required variables are present.
        """
        prompt = await self.get_template(slug)
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
        """
        Validate Jinja2 syntax and return list of undeclared variables.
        """
        try:
            ast = self.env.parse(template_str)
            return list(meta.find_undeclared_variables(ast))
        except jinja2.TemplateSyntaxError as e:
            raise ValidationException(f"Invalid Jinja2 syntax: {e}")

    async def create_or_update(
        self,
        slug: str,
        name: str,
        template: str,
        description: Optional[str] = None,
        input_variables: Optional[List[str]] = None,
        model_config: Optional[Dict[str, Any]] = None,
        type: str = "chat"
    ) -> Prompt:
        """
        Create a new prompt or update existing one (creating new version).
        """
        # Auto-detect variables if not provided
        if input_variables is None:
            input_variables = self.validate_template(template)
        else:
            # Validate provided template against syntax
            detected_vars = set(self.validate_template(template))
            # It's okay if input_variables has MORE vars (maybe optional?), 
            # but usually we want to sync them.
            # For now, let's just trust the auto-detection for validation logic.
            pass

        existing = await self.repo.get_by_slug(slug)
        new_version = (existing.version + 1) if existing else 1

        prompt = Prompt(
            slug=slug,
            name=name,
            description=description,
            template=template,
            input_variables=input_variables,
            model_config=model_config or {},
            version=new_version,
            type=type,
            is_active=True
        )
        
        return await self.repo.create(prompt)

    async def list_prompts(
        self, 
        skip: int = 0, 
        limit: int = 100,
        type_filter: Optional[str] = None
    ) -> Tuple[List[Prompt], int]:
        return await self.repo.list_prompts(skip, limit, type_filter)
