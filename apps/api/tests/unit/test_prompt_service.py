from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.exceptions import NotFoundException, ValidationException
from app.models.prompt import PromptStatus
from app.services.prompt_service import PromptService


@pytest.fixture
def service() -> PromptService:
    svc = PromptService(AsyncMock())
    svc.prompt_repo = AsyncMock()
    svc.version_repo = AsyncMock()
    return svc


def test_validate_template_extracts_vars(service: PromptService):
    variables = service.validate_template("Hello {{ name }} {{ item }}")
    assert set(variables) == {"name", "item"}


def test_validate_template_raises_on_syntax_error(service: PromptService):
    with pytest.raises(ValidationException):
        service.validate_template("{% invalid %}")


def test_render_text_renders_values(service: PromptService):
    assert service._render_text("Hi {{ user|upper }}", {"user": "dev"}) == "Hi DEV"


def test_render_text_raises_on_invalid_template(service: PromptService):
    with pytest.raises(ValidationException):
        service._render_text("{{ unclosed", {})


@pytest.mark.asyncio
async def test_get_prompt_by_slug_returns_prompt(service: PromptService):
    prompt = MagicMock()
    service.prompt_repo.get_by_slug.return_value = prompt
    result = await service.get_prompt_by_slug("chat.system")
    assert result is prompt


@pytest.mark.asyncio
async def test_get_prompt_by_slug_raises_not_found(service: PromptService):
    service.prompt_repo.get_by_slug.return_value = None
    with pytest.raises(NotFoundException):
        await service.get_prompt_by_slug("missing")


@pytest.mark.asyncio
async def test_create_version_auto_detects_input_variables(service: PromptService):
    prompt = MagicMock()
    prompt.id = uuid4()
    service.prompt_repo.get_by_slug.return_value = prompt
    service.version_repo.get_next_version = AsyncMock(return_value=3)
    service.version_repo.create = AsyncMock(side_effect=lambda v: v)

    created = await service.create_version(
        slug="chat.system",
        template="Hello {{ name }}",
    )

    assert created.version == 3
    assert created.input_variables == ["name"]
    assert created.status == PromptStatus.DRAFT.value


@pytest.mark.asyncio
async def test_render_active_uses_active_version_template(service: PromptService):
    active = MagicMock()
    active.template = "Hello {{ name }}"
    service.get_active_version = AsyncMock(return_value=active)
    rendered = await service.render_active("chat.system", {"name": "world"})
    assert rendered == "Hello world"

