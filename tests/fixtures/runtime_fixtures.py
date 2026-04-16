"""
Фикстуры для E2E тестов runtime рефакторинга
"""
import pytest
import asyncio
from uuid import uuid4
from typing import Dict, Any, List, Optional
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent
from app.models.agent_version import AgentVersion
from app.models.tool import Tool
from app.models.tool_release import ToolRelease
from app.models.permission_set import PermissionSet, PermissionScope, PermissionValue
from app.models.credential_set import Credential, AuthType
from app.models.tool_instance import ToolInstance, InstanceType
from app.agents.router import ExecutionRequest, ExecutionMode, AvailableActions, AvailableTool, EffectivePermissions
from app.agents.context import ToolContext


@pytest.fixture
async def sample_tenant():
    """Sample tenant для тестов"""
    tenant = MagicMock()
    tenant.id = uuid4()
    tenant.name = "Test Tenant"
    tenant.slug = "test-tenant"
    return tenant


@pytest.fixture
async def sample_user():
    """Sample user для тестов"""
    user = MagicMock()
    user.id = uuid4()
    user.email = "test@example.com"
    user.login = "testuser"
    return user


@pytest.fixture
async def sample_agent():
    """Sample agent для тестов"""
    agent = MagicMock(spec=Agent)
    agent.id = uuid4()
    agent.slug = "test-agent"
    agent.name = "Test Agent"
    agent.description = "Agent for testing"
    agent.current_version_id = uuid4()
    agent.logging_level = "brief"
    agent.supports_partial_mode = True
    agent.capabilities = {"chat": True, "tools": True}
    return agent


@pytest.fixture
async def sample_agent_version(sample_agent):
    """Sample agent version для тестов"""
    version = MagicMock(spec=AgentVersion)
    version.id = uuid4()
    version.agent_id = sample_agent.id
    version.version = 1
    version.prompt_text = "You are a helpful assistant for testing."
    version.compiled_prompt = "You are a helpful assistant for testing. Available tools: rag.search"
    version.status = "active"
    return version


@pytest.fixture
async def sample_tool():
    """Sample tool для тестов"""
    tool = MagicMock(spec=Tool)
    tool.id = uuid4()
    tool.slug = "rag.search"
    tool.name = "RAG Search"
    tool.description = "Search in knowledge base"
    tool.category = "search"
    return tool


@pytest.fixture
async def sample_tool_release(sample_tool):
    """Sample tool release для тестов"""
    release = MagicMock(spec=ToolRelease)
    release.id = uuid4()
    release.tool_id = sample_tool.id
    release.version = "1.0.0"
    release.status = "active"
    release.schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"}
        },
        "required": ["query"]
    }
    return release


@pytest.fixture
async def sample_tool_instance(sample_tool_release):
    """Sample tool instance для тестов"""
    instance = MagicMock(spec=ToolInstance)
    instance.id = uuid4()
    instance.tool_id = sample_tool_release.tool_id
    instance.tool_release_id = sample_tool_release.id
    instance.instance_type = InstanceType.BUILTIN
    instance.scope = PermissionScope.DEFAULT
    instance.config = {}
    return instance


@pytest.fixture
async def sample_permission_set():
    """Sample permission set для тестов"""
    permission_set = MagicMock(spec=PermissionSet)
    permission_set.id = uuid4()
    permission_set.scope = PermissionScope.DEFAULT
    permission_set.allowed_tools = {"rag.search"}
    permission_set.denied_tools = set()
    permission_set.allowed_collections = set()
    permission_set.denied_collections = set()
    return permission_set


@pytest.fixture
async def sample_credential_set():
    """Sample credential set для тестов"""
    credential_set = MagicMock(spec=Credential)
    credential_set.id = uuid4()
    credential_set.auth_type = AuthType.NONE
    credential_set.encrypted_data = {}
    return credential_set


@pytest.fixture
async def execution_request_factory():
    """Factory для создания ExecutionRequest"""
    
    def create_execution_request(
        agent,
        agent_version,
        tools: List[str] = None,
        mode: ExecutionMode = ExecutionMode.FULL,
        policy_data: Dict[str, Any] = None,
        limit_data: Dict[str, Any] = None
    ) -> ExecutionRequest:
        """Создать ExecutionRequest с нужными параметрами"""
        
        # Default tools
        if tools is None:
            tools = ["rag.search"]
        
        # Create available tools
        available_tools = []
        for tool_slug in tools:
            tool = MagicMock(spec=AvailableTool)
            tool.tool_slug = tool_slug
            tool.op = "run"
            tool.side_effects = False
            tool.risk_level = "low"
            tool.idempotent = True
            available_tools.append(tool)
        
        # Create available actions
        actions = MagicMock(spec=AvailableActions)
        actions.tools = available_tools
        actions.agents = []
        
        # Create permissions
        permissions = MagicMock(spec=EffectivePermissions)
        permissions.allowed_tools = set(tools)
        permissions.denied_reasons = {}
        
        # Create request
        request = MagicMock(spec=ExecutionRequest)
        request.agent = agent
        request.agent_version = agent_version
        request.mode = mode
        request.request_text = "Test request"
        request.prompt = agent_version.compiled_prompt
        request.available_actions = actions
        request.effective_permissions = permissions
        request.policy_data = policy_data or {"execution": {"max_steps": 10}}
        request.limit_data = limit_data or {"limits": {"max_tool_calls": 50}}
        request.routing_duration_ms = 100
        request.routing_reasons = ["test"]
        request.partial_mode_warning = None
        
        return request
    
    return create_execution_request


@pytest.fixture
async def tool_context_factory():
    """Factory для создания ToolContext"""
    
    def create_tool_context(
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
        chat_id: Optional[str] = None,
        extra: Dict[str, Any] = None
    ) -> ToolContext:
        """Создать ToolContext с нужными параметрами"""
        
        return ToolContext(
            tenant_id=tenant_id or uuid4(),
            user_id=user_id or uuid4(),
            chat_id=chat_id or uuid4(),
            request_id=str(uuid4()),
            extra=extra or {}
        )
    
    return create_tool_context


@pytest.fixture
async def mock_llm_responses():
    """Mock LLM ответы для детерминированных тестов"""
    
    responses = {
        "tool_call": {
            "content": None,
            "tool_calls": [
                {
                    "id": "test_tool_1",
                    "tool": "rag.search",
                    "arguments": {"query": "test query"}
                }
            ]
        },
        "final_response": {
            "content": "This is a test response from the assistant.",
            "tool_calls": None
        },
        "error_response": {
            "error": "LLM error occurred",
            "tool_calls": None
        }
    }
    
    return responses


@pytest.fixture
async def mock_system_llm_executor():
    """Mock SystemLLMExecutor для тестов"""
    
    class MockSystemLLMExecutor:
        def __init__(self, session, llm_client):
            self.session = session
            self.llm_client = llm_client
            self.call_count = 0
        
        async def execute_planner_with_fallback(self, planner_input):
            """Mock planner execution"""
            self.call_count += 1
            
            from app.agents.contracts import NextAction, ActionType, ToolActionPayload, ActionMeta
            
            # Возвращаем tool action для первых вызовов, затем final
            if self.call_count <= 2:
                next_action = NextAction(
                    action_type=ActionType.TOOL,
                    tool=ToolActionPayload(
                        intent=MagicMock()
                    ),
                    meta=ActionMeta(why=f"Test action {self.call_count}")
                )
                next_action.tool.intent.tool_slug = "rag.search"
                next_action.tool.intent.op = "run"
                next_action.tool.input = {"query": f"test query {self.call_count}"}
            else:
                next_action = NextAction(
                    action_type=ActionType.FINAL,
                    final=MagicMock(),
                    meta=ActionMeta(why="Final response")
                )
            
            return next_action
        
        async def execute_triage(self, triage_input):
            """Mock triage execution"""
            from app.schemas.system_llm_roles import TriageDecision
            
            return TriageDecision(
                type="agent",
                confidence=0.8,
                reasoning="Test triage reasoning"
            ), str(uuid4())
    
    return MockSystemLLMExecutor


@pytest.fixture
async def mock_tool_router():
    """Mock ToolRouter для тестов"""
    
    class MockToolRouter:
        def __init__(self):
            self.handlers = {}
        
        def register_handler(self, tool_slug, handler):
            self.handlers[tool_slug] = handler
        
        async def select(self, tool_slug, op, tool_instances):
            """Mock tool selection"""
            handler = MagicMock()
            handler.slug = tool_slug
            
            # Mock execution
            from app.agents.context import ToolResult
            handler.execute = AsyncMock(return_value=ToolResult(
                success=True,
                data={"results": [f"Mock result for {tool_slug}"]},
                metadata={}
            ))
            
            return handler
    
    return MockToolRouter()


@pytest.fixture
async def mock_policy_engine():
    """Mock PolicyEngine для тестов"""
    
    class MockPolicyEngine:
        def __init__(self, policy_data, limit_data):
            self.policy_data = policy_data
            self.limit_data = limit_data
        
        def evaluate(self, next_action, compact_ctx, available_actions):
            """Mock policy evaluation"""
            from app.agents.contracts import PolicyDecision, PolicyDecisionType
            
            return PolicyDecision(
                decision_type=PolicyDecisionType.ALLOW,
                reason="Mock policy allow"
            )
    
    return MockPolicyEngine


@pytest.fixture
async def test_chat_messages():
    """Test сообщения для чата"""
    return [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello, how are you?"},
        {"role": "assistant", "content": "I'm doing well, thank you!"},
        {"role": "user", "content": "Can you help me with something?"},
        {"role": "assistant", "content": "Of course! What do you need help with?"},
        {"role": "user", "content": "Search for information about AI"}
    ]


@pytest.fixture
async def mock_session_with_transaction():
    """Mock session с поддержкой транзакций"""
    session = AsyncMock(spec=AsyncSession)
    
    # Mock transaction methods
    session.begin = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.flush = AsyncMock()
    session.close = AsyncMock()
    
    # Mock query execution
    mock_result = AsyncMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_result.scalars.return_value.all.return_value = []
    mock_result.first.return_value = None
    session.execute.return_value = mock_result
    
    # Mock add/delete
    session.add = MagicMock()
    session.delete = MagicMock()
    
    return session


@pytest.fixture
async def runtime_test_data():
    """Комплексные тестовые данные для runtime тестов"""
    return {
        "simple_chat": {
            "messages": [
                {"role": "user", "content": "Hello"}
            ],
            "expected_tools": [],
            "expected_steps": 1
        },
        "tool_execution": {
            "messages": [
                {"role": "user", "content": "Search for test data"}
            ],
            "expected_tools": ["rag.search"],
            "expected_steps": 2
        },
        "multi_tool": {
            "messages": [
                {"role": "user", "content": "Search for AI and then ML"}
            ],
            "expected_tools": ["rag.search"],
            "expected_steps": 3
        },
        "error_scenario": {
            "messages": [
                {"role": "user", "content": "This should cause an error"}
            ],
            "expected_tools": [],
            "expected_steps": 1,
            "should_error": True
        }
    }
