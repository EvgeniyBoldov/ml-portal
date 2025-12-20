"""
Unit tests for PromptService
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.prompt_service import PromptService
from app.core.exceptions import NotFoundException, ValidationException


class TestPromptService:
    """Test PromptService methods"""
    
    @pytest.fixture
    def mock_session(self):
        """Mock SQLAlchemy async session"""
        return AsyncMock()
    
    @pytest.fixture
    def mock_repo(self):
        """Mock prompt repository"""
        repo = AsyncMock()
        repo.get_by_slug = AsyncMock(return_value=None)
        repo.create = AsyncMock()
        repo.list_prompts = AsyncMock(return_value=([], 0))
        return repo
    
    @pytest.fixture
    def prompt_service(self, mock_session, mock_repo):
        """Create PromptService with mock repo"""
        service = PromptService(mock_session)
        service.repo = mock_repo
        return service
    
    @pytest.fixture
    def sample_prompt(self):
        """Create sample prompt mock"""
        prompt = MagicMock()
        prompt.id = uuid4()
        prompt.slug = "chat-simple"
        prompt.name = "Simple Chat"
        prompt.template = "You are a helpful assistant. {{ context }}"
        prompt.input_variables = ["context"]
        prompt.version = 1
        prompt.type = "chat"
        prompt.is_active = True
        return prompt


class TestGetTemplate(TestPromptService):
    """Test get_template method"""
    
    @pytest.mark.asyncio
    async def test_get_template_found(self, prompt_service, mock_repo, sample_prompt):
        """Should return prompt when found"""
        mock_repo.get_by_slug.return_value = sample_prompt
        
        result = await prompt_service.get_template("chat-simple")
        
        assert result == sample_prompt
        mock_repo.get_by_slug.assert_called_once_with("chat-simple")
    
    @pytest.mark.asyncio
    async def test_get_template_not_found(self, prompt_service, mock_repo):
        """Should raise NotFoundException when not found"""
        mock_repo.get_by_slug.return_value = None
        
        with pytest.raises(NotFoundException) as exc_info:
            await prompt_service.get_template("nonexistent")
        
        assert "not found" in str(exc_info.value).lower()


class TestRender(TestPromptService):
    """Test render method"""
    
    @pytest.mark.asyncio
    async def test_render_success(self, prompt_service, mock_repo, sample_prompt):
        """Should render template with variables"""
        mock_repo.get_by_slug.return_value = sample_prompt
        
        result = await prompt_service.render("chat-simple", {"context": "Hello world"})
        
        assert "Hello world" in result
    
    @pytest.mark.asyncio
    async def test_render_missing_variable(self, prompt_service, mock_repo, sample_prompt):
        """Should raise ValidationException for missing variable"""
        mock_repo.get_by_slug.return_value = sample_prompt
        
        with pytest.raises(ValidationException) as exc_info:
            await prompt_service.render("chat-simple", {})
        
        assert "Missing variable" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_render_complex_template(self, prompt_service, mock_repo):
        """Should render complex Jinja2 template"""
        prompt = MagicMock()
        prompt.template = """
{% for item in items %}
- {{ item }}
{% endfor %}
Total: {{ items | length }}
"""
        mock_repo.get_by_slug.return_value = prompt
        
        result = await prompt_service.render("test", {"items": ["a", "b", "c"]})
        
        assert "- a" in result
        assert "- b" in result
        assert "- c" in result
        assert "Total: 3" in result


class TestRenderText(TestPromptService):
    """Test _render_text method"""
    
    def test_render_simple_variable(self, prompt_service):
        """Should render simple variable substitution"""
        result = prompt_service._render_text(
            "Hello, {{ name }}!",
            {"name": "World"}
        )
        
        assert result == "Hello, World!"
    
    def test_render_multiple_variables(self, prompt_service):
        """Should render multiple variables"""
        result = prompt_service._render_text(
            "{{ greeting }}, {{ name }}!",
            {"greeting": "Hi", "name": "User"}
        )
        
        assert result == "Hi, User!"
    
    def test_render_with_filters(self, prompt_service):
        """Should support Jinja2 filters"""
        result = prompt_service._render_text(
            "{{ name | upper }}",
            {"name": "test"}
        )
        
        assert result == "TEST"
    
    def test_render_with_conditionals(self, prompt_service):
        """Should support Jinja2 conditionals"""
        result = prompt_service._render_text(
            "{% if show %}Visible{% endif %}",
            {"show": True}
        )
        
        assert result == "Visible"
    
    def test_render_missing_variable_raises(self, prompt_service):
        """Should raise ValidationException for undefined variable"""
        with pytest.raises(ValidationException) as exc_info:
            prompt_service._render_text(
                "Hello, {{ undefined_var }}!",
                {}
            )
        
        assert "Missing variable" in str(exc_info.value)
    
    def test_render_invalid_syntax_raises(self, prompt_service):
        """Should raise ValidationException for invalid syntax"""
        with pytest.raises(ValidationException) as exc_info:
            prompt_service._render_text(
                "{{ unclosed",
                {}
            )
        
        assert "Invalid Jinja2 syntax" in str(exc_info.value)


class TestValidateTemplate(TestPromptService):
    """Test validate_template method"""
    
    def test_validate_returns_variables(self, prompt_service):
        """Should return list of undeclared variables"""
        result = prompt_service.validate_template(
            "Hello {{ name }}, your {{ item }} is ready"
        )
        
        assert "name" in result
        assert "item" in result
    
    def test_validate_empty_template(self, prompt_service):
        """Should return empty list for template without variables"""
        result = prompt_service.validate_template("Hello, World!")
        
        assert result == []
    
    def test_validate_complex_template(self, prompt_service):
        """Should detect variables in complex template"""
        result = prompt_service.validate_template("""
{% for item in items %}
  {{ item.name }}: {{ item.value }}
{% endfor %}
Total: {{ total }}
""")
        
        assert "items" in result
        assert "total" in result
    
    def test_validate_invalid_syntax_raises(self, prompt_service):
        """Should raise ValidationException for invalid syntax"""
        with pytest.raises(ValidationException) as exc_info:
            prompt_service.validate_template("{% invalid %}")
        
        assert "Invalid Jinja2 syntax" in str(exc_info.value)


class TestCreateOrUpdate(TestPromptService):
    """Test create_or_update method"""
    
    @pytest.mark.asyncio
    async def test_create_new_prompt(self, prompt_service, mock_repo):
        """Should create new prompt with version 1"""
        mock_repo.get_by_slug.return_value = None
        created_prompt = MagicMock()
        mock_repo.create.return_value = created_prompt
        
        result = await prompt_service.create_or_update(
            slug="new-prompt",
            name="New Prompt",
            template="Hello {{ name }}"
        )
        
        assert result == created_prompt
        mock_repo.create.assert_called_once()
        
        # Check version is 1
        created_arg = mock_repo.create.call_args[0][0]
        assert created_arg.version == 1
    
    @pytest.mark.asyncio
    async def test_update_existing_prompt_increments_version(self, prompt_service, mock_repo, sample_prompt):
        """Should increment version when updating"""
        sample_prompt.version = 3
        mock_repo.get_by_slug.return_value = sample_prompt
        updated_prompt = MagicMock()
        mock_repo.create.return_value = updated_prompt
        
        result = await prompt_service.create_or_update(
            slug="chat-simple",
            name="Updated Prompt",
            template="Updated {{ content }}"
        )
        
        # Check version is incremented
        created_arg = mock_repo.create.call_args[0][0]
        assert created_arg.version == 4
    
    @pytest.mark.asyncio
    async def test_create_auto_detects_variables(self, prompt_service, mock_repo):
        """Should auto-detect input variables"""
        mock_repo.get_by_slug.return_value = None
        mock_repo.create.return_value = MagicMock()
        
        await prompt_service.create_or_update(
            slug="test",
            name="Test",
            template="Hello {{ name }}, {{ greeting }}"
        )
        
        created_arg = mock_repo.create.call_args[0][0]
        assert "name" in created_arg.input_variables
        assert "greeting" in created_arg.input_variables
    
    @pytest.mark.asyncio
    async def test_create_with_explicit_variables(self, prompt_service, mock_repo):
        """Should use explicit input_variables if provided"""
        mock_repo.get_by_slug.return_value = None
        mock_repo.create.return_value = MagicMock()
        
        await prompt_service.create_or_update(
            slug="test",
            name="Test",
            template="Hello {{ name }}",
            input_variables=["name", "optional_var"]
        )
        
        created_arg = mock_repo.create.call_args[0][0]
        assert created_arg.input_variables == ["name", "optional_var"]
    
    @pytest.mark.asyncio
    async def test_create_with_generation_config(self, prompt_service, mock_repo):
        """Should store generation config"""
        mock_repo.get_by_slug.return_value = None
        mock_repo.create.return_value = MagicMock()
        
        gen_config = {"temperature": 0.7, "max_tokens": 1000}
        
        await prompt_service.create_or_update(
            slug="test",
            name="Test",
            template="Hello",
            generation_config=gen_config
        )
        
        created_arg = mock_repo.create.call_args[0][0]
        assert created_arg.generation_config == gen_config
    
    @pytest.mark.asyncio
    async def test_create_with_type(self, prompt_service, mock_repo):
        """Should set prompt type"""
        mock_repo.get_by_slug.return_value = None
        mock_repo.create.return_value = MagicMock()
        
        await prompt_service.create_or_update(
            slug="test",
            name="Test",
            template="System prompt",
            type="system"
        )
        
        created_arg = mock_repo.create.call_args[0][0]
        assert created_arg.type == "system"


class TestListPrompts(TestPromptService):
    """Test list_prompts method"""
    
    @pytest.mark.asyncio
    async def test_list_prompts_default(self, prompt_service, mock_repo):
        """Should list prompts with default pagination"""
        prompts = [MagicMock(), MagicMock()]
        mock_repo.list_prompts.return_value = (prompts, 2)
        
        result, total = await prompt_service.list_prompts()
        
        assert len(result) == 2
        assert total == 2
        mock_repo.list_prompts.assert_called_once_with(0, 100, None)
    
    @pytest.mark.asyncio
    async def test_list_prompts_with_pagination(self, prompt_service, mock_repo):
        """Should pass pagination params"""
        mock_repo.list_prompts.return_value = ([], 0)
        
        await prompt_service.list_prompts(skip=10, limit=20)
        
        mock_repo.list_prompts.assert_called_once_with(10, 20, None)
    
    @pytest.mark.asyncio
    async def test_list_prompts_with_type_filter(self, prompt_service, mock_repo):
        """Should filter by type"""
        mock_repo.list_prompts.return_value = ([], 0)
        
        await prompt_service.list_prompts(type_filter="system")
        
        mock_repo.list_prompts.assert_called_once_with(0, 100, "system")
