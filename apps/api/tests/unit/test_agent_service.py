"""
Unit tests for AgentService
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from fastapi import HTTPException

from app.services.agent_service import AgentService, AgentProfile


class TestAgentService:
    """Test AgentService methods"""
    
    @pytest.fixture
    def mock_session(self):
        """Mock SQLAlchemy async session"""
        return AsyncMock()
    
    @pytest.fixture
    def mock_agent_repo(self):
        """Mock agent repository"""
        repo = AsyncMock()
        repo.get_by_id = AsyncMock(return_value=None)
        repo.get_by_slug = AsyncMock(return_value=None)
        repo.create = AsyncMock()
        repo.update = AsyncMock()
        repo.delete = AsyncMock()
        repo.list_agents = AsyncMock(return_value=([], 0))
        return repo
    
    @pytest.fixture
    def mock_prompt_repo(self):
        """Mock prompt repository"""
        repo = AsyncMock()
        repo.get_by_slug = AsyncMock(return_value=None)
        return repo
    
    @pytest.fixture
    def agent_service(self, mock_session, mock_agent_repo, mock_prompt_repo):
        """Create AgentService with mock repos"""
        service = AgentService(mock_session)
        service.repo = mock_agent_repo
        service.prompt_repo = mock_prompt_repo
        return service
    
    @pytest.fixture
    def sample_agent(self):
        """Create sample agent mock"""
        agent = MagicMock()
        agent.id = uuid4()
        agent.slug = "chat-simple"
        agent.name = "Simple Chat Agent"
        agent.system_prompt_slug = "system-simple"
        agent.tools = ["rag.search"]
        agent.generation_config = {"temperature": 0.7}
        agent.is_active = True
        return agent
    
    @pytest.fixture
    def sample_prompt(self):
        """Create sample prompt mock"""
        prompt = MagicMock()
        prompt.id = uuid4()
        prompt.slug = "system-simple"
        prompt.template = "You are a helpful assistant."
        return prompt


class TestListAgents(TestAgentService):
    """Test list_agents method"""
    
    @pytest.mark.asyncio
    async def test_list_agents_default(self, agent_service, mock_agent_repo):
        """Should list agents with default pagination"""
        agents = [MagicMock(), MagicMock()]
        mock_agent_repo.list_agents.return_value = (agents, 2)
        
        result, total = await agent_service.list_agents()
        
        assert len(result) == 2
        assert total == 2
        mock_agent_repo.list_agents.assert_called_once_with(0, 100)
    
    @pytest.mark.asyncio
    async def test_list_agents_with_pagination(self, agent_service, mock_agent_repo):
        """Should pass pagination params"""
        mock_agent_repo.list_agents.return_value = ([], 0)
        
        await agent_service.list_agents(skip=10, limit=20)
        
        mock_agent_repo.list_agents.assert_called_once_with(10, 20)


class TestGetAgent(TestAgentService):
    """Test get_agent method"""
    
    @pytest.mark.asyncio
    async def test_get_agent_by_uuid(self, agent_service, mock_agent_repo, sample_agent):
        """Should get agent by UUID"""
        mock_agent_repo.get_by_id.return_value = sample_agent
        
        result = await agent_service.get_agent(str(sample_agent.id))
        
        assert result == sample_agent
        mock_agent_repo.get_by_id.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_agent_by_slug(self, agent_service, mock_agent_repo, sample_agent):
        """Should get agent by slug"""
        mock_agent_repo.get_by_slug.return_value = sample_agent
        
        result = await agent_service.get_agent("chat-simple")
        
        assert result == sample_agent
        mock_agent_repo.get_by_slug.assert_called_once_with("chat-simple")
    
    @pytest.mark.asyncio
    async def test_get_agent_not_found(self, agent_service, mock_agent_repo):
        """Should raise 404 when agent not found"""
        mock_agent_repo.get_by_id.return_value = None
        mock_agent_repo.get_by_slug.return_value = None
        
        with pytest.raises(HTTPException) as exc_info:
            await agent_service.get_agent("nonexistent")
        
        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail.lower()


class TestCreateAgent(TestAgentService):
    """Test create_agent method"""
    
    @pytest.mark.asyncio
    async def test_create_agent_success(self, agent_service, mock_agent_repo):
        """Should create agent successfully"""
        mock_agent_repo.get_by_slug.return_value = None
        created_agent = MagicMock()
        mock_agent_repo.create.return_value = created_agent
        
        data = MagicMock()
        data.slug = "new-agent"
        data.model_dump.return_value = {
            "slug": "new-agent",
            "name": "New Agent",
            "system_prompt_slug": "system-new"
        }
        
        result = await agent_service.create_agent(data)
        
        assert result == created_agent
        mock_agent_repo.create.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_create_agent_duplicate_slug(self, agent_service, mock_agent_repo, sample_agent):
        """Should raise 400 for duplicate slug"""
        mock_agent_repo.get_by_slug.return_value = sample_agent
        
        data = MagicMock()
        data.slug = "chat-simple"
        
        with pytest.raises(HTTPException) as exc_info:
            await agent_service.create_agent(data)
        
        assert exc_info.value.status_code == 400
        assert "already exists" in exc_info.value.detail.lower()


class TestUpdateAgent(TestAgentService):
    """Test update_agent method"""
    
    @pytest.mark.asyncio
    async def test_update_agent_success(self, agent_service, mock_agent_repo, sample_agent):
        """Should update agent successfully"""
        mock_agent_repo.get_by_slug.return_value = sample_agent
        mock_agent_repo.update.return_value = sample_agent
        
        data = MagicMock()
        data.model_dump.return_value = {"name": "Updated Name"}
        
        result = await agent_service.update_agent("chat-simple", data)
        
        assert result == sample_agent
        assert sample_agent.name == "Updated Name"
        mock_agent_repo.update.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_update_agent_not_found(self, agent_service, mock_agent_repo):
        """Should raise 404 when agent not found"""
        mock_agent_repo.get_by_slug.return_value = None
        
        data = MagicMock()
        data.model_dump.return_value = {}
        
        with pytest.raises(HTTPException) as exc_info:
            await agent_service.update_agent("nonexistent", data)
        
        assert exc_info.value.status_code == 404


class TestDeleteAgent(TestAgentService):
    """Test delete_agent method"""
    
    @pytest.mark.asyncio
    async def test_delete_agent_success(self, agent_service, mock_agent_repo, sample_agent):
        """Should delete agent successfully"""
        mock_agent_repo.get_by_slug.return_value = sample_agent
        
        await agent_service.delete_agent("chat-simple")
        
        mock_agent_repo.delete.assert_called_once_with(sample_agent)
    
    @pytest.mark.asyncio
    async def test_delete_agent_not_found(self, agent_service, mock_agent_repo):
        """Should raise 404 when agent not found"""
        mock_agent_repo.get_by_slug.return_value = None
        
        with pytest.raises(HTTPException) as exc_info:
            await agent_service.delete_agent("nonexistent")
        
        assert exc_info.value.status_code == 404


class TestGetAgentProfile(TestAgentService):
    """Test get_agent_profile method"""
    
    @pytest.mark.asyncio
    async def test_get_profile_default_agent(
        self, agent_service, mock_agent_repo, mock_prompt_repo, sample_agent, sample_prompt
    ):
        """Should get default agent profile"""
        mock_agent_repo.get_by_slug.return_value = sample_agent
        mock_prompt_repo.get_by_slug.return_value = sample_prompt
        
        result = await agent_service.get_agent_profile()
        
        assert isinstance(result, AgentProfile)
        assert result.agent == sample_agent
        assert result.system_prompt == sample_prompt
        assert result.tools == sample_agent.tools
        mock_agent_repo.get_by_slug.assert_called_with("chat-simple")
    
    @pytest.mark.asyncio
    async def test_get_profile_rag_agent(
        self, agent_service, mock_agent_repo, mock_prompt_repo, sample_agent, sample_prompt
    ):
        """Should get RAG agent profile when use_rag=True"""
        mock_agent_repo.get_by_slug.return_value = sample_agent
        mock_prompt_repo.get_by_slug.return_value = sample_prompt
        
        await agent_service.get_agent_profile(use_rag=True)
        
        mock_agent_repo.get_by_slug.assert_called_with("chat-rag")
    
    @pytest.mark.asyncio
    async def test_get_profile_custom_agent(
        self, agent_service, mock_agent_repo, mock_prompt_repo, sample_agent, sample_prompt
    ):
        """Should get custom agent profile by slug"""
        mock_agent_repo.get_by_slug.return_value = sample_agent
        mock_prompt_repo.get_by_slug.return_value = sample_prompt
        
        await agent_service.get_agent_profile(agent_slug="custom-agent")
        
        mock_agent_repo.get_by_slug.assert_called_with("custom-agent")
    
    @pytest.mark.asyncio
    async def test_get_profile_fallback_to_default(
        self, agent_service, mock_agent_repo, mock_prompt_repo, sample_agent, sample_prompt
    ):
        """Should fallback to default agent if requested not found"""
        # First call returns None (custom not found), second returns default
        mock_agent_repo.get_by_slug.side_effect = [None, sample_agent]
        mock_prompt_repo.get_by_slug.return_value = sample_prompt
        
        result = await agent_service.get_agent_profile(agent_slug="nonexistent")
        
        assert result.agent == sample_agent
        assert mock_agent_repo.get_by_slug.call_count == 2
    
    @pytest.mark.asyncio
    async def test_get_profile_no_default_raises(self, agent_service, mock_agent_repo):
        """Should raise 500 if default agent not found"""
        mock_agent_repo.get_by_slug.return_value = None
        
        with pytest.raises(HTTPException) as exc_info:
            await agent_service.get_agent_profile()
        
        assert exc_info.value.status_code == 500
        assert "not found" in exc_info.value.detail.lower()
    
    @pytest.mark.asyncio
    async def test_get_profile_missing_prompt_raises(
        self, agent_service, mock_agent_repo, mock_prompt_repo, sample_agent
    ):
        """Should raise 500 if system prompt not found"""
        mock_agent_repo.get_by_slug.return_value = sample_agent
        mock_prompt_repo.get_by_slug.return_value = None
        
        with pytest.raises(HTTPException) as exc_info:
            await agent_service.get_agent_profile()
        
        assert exc_info.value.status_code == 500
        assert "System prompt" in exc_info.value.detail


class TestResolveAgentForChat(TestAgentService):
    """Test resolve_agent_for_chat method"""
    
    @pytest.mark.asyncio
    async def test_resolve_returns_tuple(
        self, agent_service, mock_agent_repo, mock_prompt_repo, sample_agent, sample_prompt
    ):
        """Should return tuple of (template, slug, config)"""
        mock_agent_repo.get_by_slug.return_value = sample_agent
        mock_prompt_repo.get_by_slug.return_value = sample_prompt
        
        template, slug, config = await agent_service.resolve_agent_for_chat()
        
        assert template == sample_prompt.template
        assert slug == sample_prompt.slug
        assert config == sample_agent.generation_config
    
    @pytest.mark.asyncio
    async def test_resolve_with_rag(
        self, agent_service, mock_agent_repo, mock_prompt_repo, sample_agent, sample_prompt
    ):
        """Should resolve RAG agent when use_rag=True"""
        mock_agent_repo.get_by_slug.return_value = sample_agent
        mock_prompt_repo.get_by_slug.return_value = sample_prompt
        
        await agent_service.resolve_agent_for_chat(use_rag=True)
        
        mock_agent_repo.get_by_slug.assert_called_with("chat-rag")


class TestAgentProfile:
    """Test AgentProfile dataclass"""
    
    def test_agent_profile_creation(self):
        """Should create AgentProfile with all fields"""
        agent = MagicMock()
        prompt = MagicMock()
        tools = ["tool1", "tool2"]
        config = {"temperature": 0.5}
        
        profile = AgentProfile(
            agent=agent,
            system_prompt=prompt,
            tools=tools,
            generation_config=config
        )
        
        assert profile.agent == agent
        assert profile.system_prompt == prompt
        assert profile.tools == tools
        assert profile.generation_config == config
