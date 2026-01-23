"""
Unit tests for PermissionService
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.services.permission_service import PermissionService, EffectivePermissions


class TestPermissionService:
    """Test PermissionService methods"""
    
    @pytest.fixture
    def mock_session(self):
        """Mock SQLAlchemy async session"""
        return AsyncMock()
    
    @pytest.fixture
    def mock_permission_repo(self):
        """Mock permission repository"""
        repo = AsyncMock()
        repo.get_by_id = AsyncMock(return_value=None)
        repo.get_by_scope = AsyncMock(return_value=None)
        repo.create = AsyncMock()
        repo.update = AsyncMock()
        repo.delete = AsyncMock()
        repo.list_all = AsyncMock(return_value=[])
        return repo
    
    @pytest.fixture
    def permission_service(self, mock_session, mock_permission_repo):
        """Create PermissionService with mock repo"""
        service = PermissionService(mock_session)
        service.repo = mock_permission_repo
        return service
    
    @pytest.fixture
    def default_permission_set(self):
        """Create default permission set mock"""
        ps = MagicMock()
        ps.id = uuid4()
        ps.scope = "default"
        ps.tenant_id = None
        ps.user_id = None
        ps.allowed_tools = ["rag.search", "jira.create"]
        ps.denied_tools = ["admin.delete"]
        ps.allowed_collections = ["docs", "tickets"]
        ps.denied_collections = []
        return ps
    
    @pytest.fixture
    def tenant_permission_set(self):
        """Create tenant permission set mock"""
        ps = MagicMock()
        ps.id = uuid4()
        ps.scope = "tenant"
        ps.tenant_id = uuid4()
        ps.user_id = None
        ps.allowed_tools = ["slack.send"]
        ps.denied_tools = ["jira.create"]
        ps.allowed_collections = ["internal"]
        ps.denied_collections = ["docs"]
        return ps
    
    @pytest.fixture
    def user_permission_set(self):
        """Create user permission set mock"""
        ps = MagicMock()
        ps.id = uuid4()
        ps.scope = "user"
        ps.tenant_id = uuid4()
        ps.user_id = uuid4()
        ps.allowed_tools = ["jira.create"]
        ps.denied_tools = []
        ps.allowed_collections = ["docs"]
        ps.denied_collections = []
        return ps


class TestGetEffectivePermissions(TestPermissionService):
    """Test get_effective_permissions method"""
    
    @pytest.mark.asyncio
    async def test_default_only(self, permission_service, mock_permission_repo, default_permission_set):
        """Should return default permissions when no tenant/user overrides"""
        mock_permission_repo.get_by_scope.side_effect = [
            default_permission_set,  # default
            None,  # tenant
            None,  # user
        ]
        
        result = await permission_service.get_effective_permissions()
        
        assert isinstance(result, EffectivePermissions)
        assert "rag.search" in result.allowed_tools
        assert "admin.delete" in result.denied_tools
    
    @pytest.mark.asyncio
    async def test_tenant_overrides_default(
        self, permission_service, mock_permission_repo, 
        default_permission_set, tenant_permission_set
    ):
        """Tenant permissions should override default"""
        tenant_id = tenant_permission_set.tenant_id
        mock_permission_repo.get_by_scope.side_effect = [
            default_permission_set,
            tenant_permission_set,
            None,
        ]
        
        result = await permission_service.get_effective_permissions(tenant_id=tenant_id)
        
        # Tenant denied jira.create, should be in denied
        assert "jira.create" in result.denied_tools
        # Tenant allowed slack.send
        assert "slack.send" in result.allowed_tools
    
    @pytest.mark.asyncio
    async def test_user_overrides_tenant(
        self, permission_service, mock_permission_repo,
        default_permission_set, tenant_permission_set, user_permission_set
    ):
        """User permissions should override tenant"""
        tenant_id = tenant_permission_set.tenant_id
        user_id = user_permission_set.user_id
        
        mock_permission_repo.get_by_scope.side_effect = [
            default_permission_set,
            tenant_permission_set,
            user_permission_set,
        ]
        
        result = await permission_service.get_effective_permissions(
            tenant_id=tenant_id, 
            user_id=user_id
        )
        
        # User allowed jira.create (overrides tenant deny)
        assert "jira.create" in result.allowed_tools
        # User allowed docs (overrides tenant deny)
        assert "docs" in result.allowed_collections
    
    @pytest.mark.asyncio
    async def test_empty_when_no_permissions(self, permission_service, mock_permission_repo):
        """Should return empty permissions when nothing configured"""
        mock_permission_repo.get_by_scope.return_value = None
        
        result = await permission_service.get_effective_permissions()
        
        assert result.allowed_tools == []
        assert result.denied_tools == []
        assert result.allowed_collections == []
        assert result.denied_collections == []


class TestIsToolAllowed(TestPermissionService):
    """Test is_tool_allowed method"""
    
    @pytest.mark.asyncio
    async def test_allowed_tool(self, permission_service, mock_permission_repo, default_permission_set):
        """Should return True for allowed tool"""
        mock_permission_repo.get_by_scope.side_effect = [
            default_permission_set, None, None
        ]
        
        result = await permission_service.is_tool_allowed("rag.search")
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_denied_tool(self, permission_service, mock_permission_repo, default_permission_set):
        """Should return False for denied tool"""
        mock_permission_repo.get_by_scope.side_effect = [
            default_permission_set, None, None
        ]
        
        result = await permission_service.is_tool_allowed("admin.delete")
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_unknown_tool_denied_by_default(self, permission_service, mock_permission_repo, default_permission_set):
        """Should return False for unknown tool (not in allowed list)"""
        mock_permission_repo.get_by_scope.side_effect = [
            default_permission_set, None, None
        ]
        
        result = await permission_service.is_tool_allowed("unknown.tool")
        
        assert result is False


class TestIsCollectionAllowed(TestPermissionService):
    """Test is_collection_allowed method"""
    
    @pytest.mark.asyncio
    async def test_allowed_collection(self, permission_service, mock_permission_repo, default_permission_set):
        """Should return True for allowed collection"""
        mock_permission_repo.get_by_scope.side_effect = [
            default_permission_set, None, None
        ]
        
        result = await permission_service.is_collection_allowed("docs")
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_denied_collection(
        self, permission_service, mock_permission_repo, 
        default_permission_set, tenant_permission_set
    ):
        """Should return False for denied collection"""
        mock_permission_repo.get_by_scope.side_effect = [
            default_permission_set, tenant_permission_set, None
        ]
        
        result = await permission_service.is_collection_allowed(
            "docs", 
            tenant_id=tenant_permission_set.tenant_id
        )
        
        # Tenant denied docs
        assert result is False


class TestEffectivePermissions:
    """Test EffectivePermissions dataclass"""
    
    def test_creation(self):
        """Should create EffectivePermissions with all fields"""
        ep = EffectivePermissions(
            allowed_tools=["tool1"],
            denied_tools=["tool2"],
            allowed_collections=["col1"],
            denied_collections=["col2"]
        )
        
        assert ep.allowed_tools == ["tool1"]
        assert ep.denied_tools == ["tool2"]
        assert ep.allowed_collections == ["col1"]
        assert ep.denied_collections == ["col2"]
    
    def test_default_empty_lists(self):
        """Should default to empty lists"""
        ep = EffectivePermissions()
        
        assert ep.allowed_tools == []
        assert ep.denied_tools == []
        assert ep.allowed_collections == []
        assert ep.denied_collections == []
