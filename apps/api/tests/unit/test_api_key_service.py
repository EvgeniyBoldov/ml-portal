"""
Unit tests for APIKeyService
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime, timezone, timedelta

from app.services.api_key_service import APIKeyService
from app.models.api_key import APIKey, hash_api_key


class TestAPIKeyService:
    """Test APIKeyService methods"""
    
    @pytest.fixture
    def mock_session(self):
        """Mock SQLAlchemy async session"""
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        session.delete = AsyncMock()
        session.execute = AsyncMock()
        return session
    
    @pytest.fixture
    def api_key_service(self, mock_session):
        """Create APIKeyService with mock session"""
        return APIKeyService(mock_session)
    
    @pytest.fixture
    def sample_user_id(self):
        return uuid4()
    
    @pytest.fixture
    def sample_tenant_id(self):
        return uuid4()


class TestCreateKey(TestAPIKeyService):
    """Test API key creation"""
    
    @pytest.mark.asyncio
    async def test_create_key_returns_key_and_raw(self, api_key_service, mock_session, sample_user_id):
        """Should return APIKey and raw key string"""
        api_key, raw_key = await api_key_service.create_key(
            name="Test Key",
            user_id=sample_user_id,
            description="Test description"
        )
        
        assert api_key is not None
        assert raw_key is not None
        assert raw_key.startswith("mlp_")
        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_create_key_with_scopes(self, api_key_service, mock_session, sample_user_id):
        """Should create key with custom scopes"""
        scopes = ["tools:read", "prompts:read"]
        
        api_key, raw_key = await api_key_service.create_key(
            name="Scoped Key",
            user_id=sample_user_id,
            scopes=scopes
        )
        
        assert api_key.scopes == scopes
    
    @pytest.mark.asyncio
    async def test_create_key_with_tenant(self, api_key_service, mock_session, sample_user_id, sample_tenant_id):
        """Should create key with tenant association"""
        api_key, raw_key = await api_key_service.create_key(
            name="Tenant Key",
            user_id=sample_user_id,
            tenant_id=sample_tenant_id
        )
        
        assert api_key.tenant_id == sample_tenant_id
    
    @pytest.mark.asyncio
    async def test_create_key_with_expiration(self, api_key_service, mock_session, sample_user_id):
        """Should create key with expiration date"""
        expires_at = datetime.now(timezone.utc) + timedelta(days=30)
        
        api_key, raw_key = await api_key_service.create_key(
            name="Expiring Key",
            user_id=sample_user_id,
            expires_at=expires_at
        )
        
        assert api_key.expires_at == expires_at
    
    @pytest.mark.asyncio
    async def test_create_key_with_allowed_tools(self, api_key_service, mock_session, sample_user_id):
        """Should create key with tool restrictions"""
        allowed_tools = ["rag.search", "netbox.query"]
        
        api_key, raw_key = await api_key_service.create_key(
            name="Tool Restricted Key",
            user_id=sample_user_id,
            allowed_tools=allowed_tools
        )
        
        assert api_key.allowed_tools == allowed_tools


class TestVerifyKey(TestAPIKeyService):
    """Test API key verification"""
    
    @pytest.fixture
    def mock_api_key(self, sample_user_id):
        """Create mock API key"""
        api_key = MagicMock(spec=APIKey)
        api_key.id = uuid4()
        api_key.name = "Test Key"
        api_key.user_id = sample_user_id
        api_key.is_active = True
        api_key.expires_at = None
        api_key.is_valid = MagicMock(return_value=True)
        return api_key
    
    @pytest.mark.asyncio
    async def test_verify_key_success(self, api_key_service, mock_session, mock_api_key):
        """Should return API key for valid key"""
        raw_key = "mlp_test_key_12345678901234567890"
        mock_api_key.key_hash = hash_api_key(raw_key)
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_api_key
        mock_session.execute.return_value = mock_result
        
        result = await api_key_service.verify_key(raw_key)
        
        assert result == mock_api_key
        # Should update last_used_at
        assert mock_session.execute.call_count == 2
    
    @pytest.mark.asyncio
    async def test_verify_key_not_found(self, api_key_service, mock_session):
        """Should return None for non-existent key"""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        
        result = await api_key_service.verify_key("mlp_nonexistent_key")
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_verify_key_invalid_prefix(self, api_key_service, mock_session):
        """Should return None for key without mlp_ prefix"""
        result = await api_key_service.verify_key("invalid_key_format")
        
        assert result is None
        mock_session.execute.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_verify_key_empty(self, api_key_service, mock_session):
        """Should return None for empty key"""
        result = await api_key_service.verify_key("")
        
        assert result is None
        mock_session.execute.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_verify_key_expired(self, api_key_service, mock_session, mock_api_key):
        """Should return None for expired key"""
        raw_key = "mlp_expired_key_1234567890123456"
        mock_api_key.key_hash = hash_api_key(raw_key)
        mock_api_key.is_valid.return_value = False
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_api_key
        mock_session.execute.return_value = mock_result
        
        result = await api_key_service.verify_key(raw_key)
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_verify_key_inactive(self, api_key_service, mock_session, mock_api_key):
        """Should return None for inactive key"""
        raw_key = "mlp_inactive_key_123456789012345"
        mock_api_key.key_hash = hash_api_key(raw_key)
        mock_api_key.is_active = False
        mock_api_key.is_valid.return_value = False
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_api_key
        mock_session.execute.return_value = mock_result
        
        result = await api_key_service.verify_key(raw_key)
        
        assert result is None


class TestListKeys(TestAPIKeyService):
    """Test listing API keys"""
    
    @pytest.mark.asyncio
    async def test_list_keys_by_user(self, api_key_service, mock_session, sample_user_id):
        """Should list keys filtered by user"""
        mock_keys = [MagicMock(), MagicMock()]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_keys
        mock_session.execute.return_value = mock_result
        
        result = await api_key_service.list_keys(user_id=sample_user_id)
        
        assert len(result) == 2
        mock_session.execute.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_list_keys_by_tenant(self, api_key_service, mock_session, sample_tenant_id):
        """Should list keys filtered by tenant"""
        mock_keys = [MagicMock()]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_keys
        mock_session.execute.return_value = mock_result
        
        result = await api_key_service.list_keys(tenant_id=sample_tenant_id)
        
        assert len(result) == 1
    
    @pytest.mark.asyncio
    async def test_list_keys_include_inactive(self, api_key_service, mock_session):
        """Should include inactive keys when requested"""
        mock_keys = [MagicMock(), MagicMock(), MagicMock()]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_keys
        mock_session.execute.return_value = mock_result
        
        result = await api_key_service.list_keys(include_inactive=True)
        
        assert len(result) == 3


class TestRevokeKey(TestAPIKeyService):
    """Test revoking API keys"""
    
    @pytest.mark.asyncio
    async def test_revoke_key_success(self, api_key_service, mock_session):
        """Should revoke existing key"""
        key_id = uuid4()
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_session.execute.return_value = mock_result
        
        result = await api_key_service.revoke_key(key_id)
        
        assert result is True
        mock_session.flush.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_revoke_key_not_found(self, api_key_service, mock_session):
        """Should return False for non-existent key"""
        key_id = uuid4()
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_session.execute.return_value = mock_result
        
        result = await api_key_service.revoke_key(key_id)
        
        assert result is False


class TestDeleteKey(TestAPIKeyService):
    """Test deleting API keys"""
    
    @pytest.mark.asyncio
    async def test_delete_key_success(self, api_key_service, mock_session):
        """Should delete existing key"""
        key_id = uuid4()
        mock_api_key = MagicMock()
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_api_key
        mock_session.execute.return_value = mock_result
        
        result = await api_key_service.delete_key(key_id)
        
        assert result is True
        mock_session.delete.assert_called_once_with(mock_api_key)
        mock_session.flush.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_delete_key_not_found(self, api_key_service, mock_session):
        """Should return False for non-existent key"""
        key_id = uuid4()
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        
        result = await api_key_service.delete_key(key_id)
        
        assert result is False
        mock_session.delete.assert_not_called()


class TestGetKeyById(TestAPIKeyService):
    """Test getting API key by ID"""
    
    @pytest.mark.asyncio
    async def test_get_key_by_id_found(self, api_key_service, mock_session):
        """Should return key when found"""
        key_id = uuid4()
        mock_api_key = MagicMock()
        mock_api_key.id = key_id
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_api_key
        mock_session.execute.return_value = mock_result
        
        result = await api_key_service.get_key_by_id(key_id)
        
        assert result == mock_api_key
    
    @pytest.mark.asyncio
    async def test_get_key_by_id_not_found(self, api_key_service, mock_session):
        """Should return None when not found"""
        key_id = uuid4()
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        
        result = await api_key_service.get_key_by_id(key_id)
        
        assert result is None


class TestAPIKeyModel:
    """Test APIKey model methods"""
    
    def test_create_generates_key(self):
        """APIKey.create should generate unique key"""
        user_id = uuid4()
        
        api_key, raw_key = APIKey.create(
            name="Test",
            user_id=user_id
        )
        
        assert raw_key.startswith("mlp_")
        assert len(raw_key) > 20
        assert api_key.key_prefix == raw_key[:12]
    
    def test_verify_correct_key(self):
        """verify should return True for correct key"""
        user_id = uuid4()
        api_key, raw_key = APIKey.create(name="Test", user_id=user_id)
        
        assert api_key.verify(raw_key) is True
    
    def test_verify_wrong_key(self):
        """verify should return False for wrong key"""
        user_id = uuid4()
        api_key, raw_key = APIKey.create(name="Test", user_id=user_id)
        
        assert api_key.verify("mlp_wrong_key") is False
    
    def test_is_valid_active_no_expiry(self):
        """is_valid should return True for active key without expiry"""
        user_id = uuid4()
        api_key, _ = APIKey.create(name="Test", user_id=user_id)
        api_key.is_active = True
        api_key.expires_at = None
        
        assert api_key.is_valid() is True
    
    def test_is_valid_inactive(self):
        """is_valid should return False for inactive key"""
        user_id = uuid4()
        api_key, _ = APIKey.create(name="Test", user_id=user_id)
        api_key.is_active = False
        
        assert api_key.is_valid() is False
    
    def test_is_valid_expired(self):
        """is_valid should return False for expired key"""
        user_id = uuid4()
        api_key, _ = APIKey.create(
            name="Test",
            user_id=user_id,
            expires_at=datetime.now(timezone.utc) - timedelta(days=1)
        )
        
        assert api_key.is_valid() is False
    
    def test_has_scope(self):
        """has_scope should check scope presence"""
        user_id = uuid4()
        api_key, _ = APIKey.create(
            name="Test",
            user_id=user_id,
            scopes=["tools:read", "prompts:read"]
        )
        
        assert api_key.has_scope("tools:read") is True
        assert api_key.has_scope("admin:write") is False
    
    def test_can_use_tool_all_allowed(self):
        """can_use_tool should return True when allowed_tools is None"""
        user_id = uuid4()
        api_key, _ = APIKey.create(name="Test", user_id=user_id)
        api_key.allowed_tools = None
        
        assert api_key.can_use_tool("any.tool") is True
    
    def test_can_use_tool_restricted(self):
        """can_use_tool should check tool presence when restricted"""
        user_id = uuid4()
        api_key, _ = APIKey.create(
            name="Test",
            user_id=user_id,
            allowed_tools=["rag.search"]
        )
        
        assert api_key.can_use_tool("rag.search") is True
        assert api_key.can_use_tool("netbox.query") is False
    
    def test_can_use_prompt_all_allowed(self):
        """can_use_prompt should return True when allowed_prompts is None"""
        user_id = uuid4()
        api_key, _ = APIKey.create(name="Test", user_id=user_id)
        api_key.allowed_prompts = None
        
        assert api_key.can_use_prompt("any.prompt") is True
    
    def test_can_use_prompt_restricted(self):
        """can_use_prompt should check prompt presence when restricted"""
        user_id = uuid4()
        api_key, _ = APIKey.create(
            name="Test",
            user_id=user_id,
            allowed_prompts=["chat-simple"]
        )
        
        assert api_key.can_use_prompt("chat-simple") is True
        assert api_key.can_use_prompt("admin-prompt") is False
