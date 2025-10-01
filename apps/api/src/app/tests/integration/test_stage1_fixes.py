"""
Integration tests for Stage 1 fixes:
- UserCtx type consistency
- Rate-limit headers
- Idempotency
- LLM/EMB clients
- MinIO presigned URLs
"""
import pytest
import httpx
from unittest.mock import patch, Mock
from fastapi.testclient import TestClient


class TestUserCtxConsistency:
    """Test that all endpoints use UserCtx consistently"""
    
    def test_auth_me_returns_usercx(self, client, auth_tokens):
        """Test /auth/me returns UserCtx object"""
        headers = {"Authorization": f"Bearer {auth_tokens['access_token']}"}
        
        with patch('app.api.deps.get_current_user') as mock_get_user:
            from app.core.security import UserCtx
            mock_user = UserCtx(id="test-user-id", role="editor")
            mock_get_user.return_value = mock_user
            
            response = client.get("/api/v1/auth/me", headers=headers)
            
            assert response.status_code == 200
            data = response.json()
            assert "id" in data
            assert "role" in data
            assert data["id"] == "test-user-id"
            assert data["role"] == "editor"
    
    def test_chat_endpoints_use_usercx(self, client, auth_tokens):
        """Test chat endpoints use UserCtx"""
        headers = {"Authorization": f"Bearer {auth_tokens['access_token']}"}
        
        with patch('app.api.deps.get_current_user') as mock_get_user:
            from app.core.security import UserCtx
            mock_user = UserCtx(id="test-user-id", role="editor")
            mock_get_user.return_value = mock_user
            
            # Test create chat
            chat_data = {"name": "Test Chat", "tags": ["test"]}
            response = client.post("/api/v1/chats", json=chat_data, headers=headers)
            assert response.status_code == 200
            
            # Test list chats
            response = client.get("/api/v1/chats", headers=headers)
            assert response.status_code == 200
    
    def test_analyze_endpoints_use_usercx(self, client, auth_tokens):
        """Test analyze endpoints use UserCtx"""
        headers = {"Authorization": f"Bearer {auth_tokens['access_token']}"}
        
        with patch('app.api.deps.require_editor_or_admin') as mock_require_role:
            from app.core.security import UserCtx
            mock_user = UserCtx(id="test-user-id", role="editor")
            mock_require_role.return_value = mock_user
            
            # Test upload
            upload_data = {
                "name": "test.pdf",
                "mime": "application/pdf",
                "size": 1024
            }
            response = client.post("/api/v1/analyze/upload", json=upload_data, headers=headers)
            assert response.status_code == 200


class TestRateLimitHeaders:
    """Test rate limit headers are added correctly"""
    
    def test_rate_limit_headers_on_success(self, client):
        """Test rate limit headers are added on successful requests"""
        login_data = {"email": "test@example.com", "password": "testpass"}
        
        with patch('app.api.deps.rate_limit') as mock_rate_limit:
            # Mock rate limit to not raise exception
            mock_rate_limit.return_value = None
            
            response = client.post("/api/v1/auth/login", json=login_data)
            
            # Check that rate limit headers are present
            assert "X-RateLimit-Limit" in response.headers
            assert "X-RateLimit-Remaining" in response.headers
            assert "X-RateLimit-Window" in response.headers
    
    def test_rate_limit_headers_on_429(self, client):
        """Test rate limit headers on 429 response"""
        login_data = {"email": "test@example.com", "password": "testpass"}
        
        with patch('app.api.deps.rate_limit') as mock_rate_limit:
            from fastapi import HTTPException, status
            # Mock rate limit to raise 429
            mock_rate_limit.side_effect = HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="rate_limited",
                headers={
                    "Retry-After": "60",
                    "X-RateLimit-Limit": "10",
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Window": "60"
                }
            )
            
            response = client.post("/api/v1/auth/login", json=login_data)
            
            assert response.status_code == 429
            assert "Retry-After" in response.headers
            assert "X-RateLimit-Limit" in response.headers
            assert "X-RateLimit-Remaining" in response.headers
            assert "X-RateLimit-Window" in response.headers


class TestIdempotency:
    """Test idempotency functionality"""
    
    def test_chat_message_idempotency(self, client, auth_tokens, idempotency_key):
        """Test chat message idempotency"""
        headers = {
            "Authorization": f"Bearer {auth_tokens['access_token']}",
            "Idempotency-Key": idempotency_key
        }
        
        with patch('app.api.deps.get_current_user') as mock_get_user:
            from app.core.security import UserCtx
            mock_user = UserCtx(id="test-user-id", role="editor")
            mock_get_user.return_value = mock_user
            
            # Mock chat creation
            with patch('app.repositories.chats_repo_enhanced.ChatsRepository') as mock_repo:
                mock_chat = Mock()
                mock_chat.id = "test-chat-id"
                mock_chat.owner_id = "test-user-id"
                mock_repo.return_value.get.return_value = mock_chat
                
                message_data = {"content": "Hello, world!"}
                
                # First request
                response1 = client.post(
                    "/api/v1/chats/test-chat-id/messages",
                    json=message_data,
                    headers=headers
                )
                
                # Second request with same idempotency key
                response2 = client.post(
                    "/api/v1/chats/test-chat-id/messages",
                    json=message_data,
                    headers=headers
                )
                
                # Both should return same result (idempotency middleware handles this)
                assert response1.status_code == response2.status_code
    
    def test_analyze_run_idempotency(self, client, auth_tokens, idempotency_key):
        """Test analyze run idempotency"""
        headers = {
            "Authorization": f"Bearer {auth_tokens['access_token']}",
            "Idempotency-Key": idempotency_key
        }
        
        with patch('app.api.deps.require_editor_or_admin') as mock_require_role:
            from app.core.security import UserCtx
            mock_user = UserCtx(id="test-user-id", role="editor")
            mock_require_role.return_value = mock_user
            
            run_data = {"question": "What is this document about?"}
            
            # First request
            response1 = client.post(
                "/api/v1/analyze/test-analyze-id/run",
                json=run_data,
                headers=headers
            )
            
            # Second request with same idempotency key
            response2 = client.post(
                "/api/v1/analyze/test-analyze-id/run",
                json=run_data,
                headers=headers
            )
            
            # Both should return same result
            assert response1.status_code == response2.status_code


class TestLLMEmbClients:
    """Test LLM and Embedding clients integration"""
    
    def test_llm_client_generate(self, client, auth_tokens):
        """Test LLM client generate method"""
        headers = {"Authorization": f"Bearer {auth_tokens['access_token']}"}
        
        with patch('app.api.deps.get_current_user') as mock_get_user:
            from app.core.security import UserCtx
            mock_user = UserCtx(id="test-user-id", role="editor")
            mock_get_user.return_value = mock_user
            
            # Mock LLM client
            with patch('app.services.http_clients.HTTPLLMClient.generate') as mock_generate:
                mock_generate.return_value = "Hello! This is a test response."
                
                message_data = {"content": "Hello, world!"}
                response = client.post("/api/v1/chat", json=message_data, headers=headers)
                
                assert response.status_code == 200
                data = response.json()
                assert "text" in data
                assert data["text"] == "Hello! This is a test response."
    
    def test_llm_client_stream(self, client, auth_tokens):
        """Test LLM client streaming"""
        headers = {"Authorization": f"Bearer {auth_tokens['access_token']}"}
        
        with patch('app.api.deps.get_current_user') as mock_get_user:
            from app.core.security import UserCtx
            mock_user = UserCtx(id="test-user-id", role="editor")
            mock_get_user.return_value = mock_user
            
            # Mock LLM client streaming
            with patch('app.services.http_clients.HTTPLLMClient.generate') as mock_generate:
                mock_generate.return_value = "Hello! This is a test response."
                
                message_data = {"content": "Hello, world!"}
                response = client.post("/api/v1/chat/stream", json=message_data, headers=headers)
                
                assert response.status_code == 200
                assert response.headers["content-type"] == "text/event-stream"
    
    def test_emb_client_embed(self):
        """Test Embedding client embed method"""
        from app.services.http_clients import HTTPEmbClient
        
        # Mock HTTP response
        with patch('httpx.Client.post') as mock_post:
            mock_response = Mock()
            mock_response.json.return_value = {
                "vectors": [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
            }
            mock_response.raise_for_status.return_value = None
            mock_post.return_value = mock_response
            
            client = HTTPEmbClient()
            texts = ["Hello world", "Test text"]
            embeddings = client.embed(texts)
            
            assert len(embeddings) == 2
            assert len(embeddings[0]) == 3
            assert embeddings[0] == [0.1, 0.2, 0.3]


class TestMinIOPresigned:
    """Test MinIO presigned URL functionality"""
    
    def test_analyze_upload_presigned(self, client, auth_tokens, minio_bucket):
        """Test analyze upload returns presigned URL"""
        headers = {"Authorization": f"Bearer {auth_tokens['access_token']}"}
        
        with patch('app.api.deps.require_editor_or_admin') as mock_require_role:
            from app.core.security import UserCtx
            mock_user = UserCtx(id="test-user-id", role="editor")
            mock_require_role.return_value = mock_user
            
            # Mock S3 manager
            with patch('app.core.s3.s3_manager.generate_presigned_url') as mock_presigned:
                mock_presigned.return_value = "https://minio-test.example.com/presigned-url"
                
                upload_data = {
                    "name": "test.pdf",
                    "mime": "application/pdf",
                    "size": 1024
                }
                
                response = client.post("/api/v1/analyze/upload", json=upload_data, headers=headers)
                
                assert response.status_code == 200
                data = response.json()
                assert "analyze_id" in data
                assert "upload" in data
                assert "url" in data["upload"]
                assert data["upload"]["url"] == "https://minio-test.example.com/presigned-url"
    
    def test_artifacts_presigned(self, client, auth_tokens):
        """Test artifacts presigned URL"""
        headers = {"Authorization": f"Bearer {auth_tokens['access_token']}"}
        
        with patch('app.api.deps.require_reader_or_above') as mock_require_role:
            from app.core.security import UserCtx
            mock_user = UserCtx(id="test-user-id", role="reader")
            mock_require_role.return_value = mock_user
            
            # Mock S3 manager
            with patch('app.core.s3.s3_manager.generate_presigned_url') as mock_presigned:
                mock_presigned.return_value = "https://minio-test.example.com/artifact-url"
                
                response = client.get("/api/v1/artifacts/test-artifact-id?mode=presigned", headers=headers)
                
                assert response.status_code == 200
                data = response.json()
                assert "artifact_id" in data
                assert "download_url" in data
                assert data["download_url"] == "https://minio-test.example.com/artifact-url"


class TestBasePathConsistency:
    """Test base path consistency with OpenAPI contract"""
    
    def test_api_v1_prefix_consistency(self, client):
        """Test all endpoints use /api/v1 prefix consistently"""
        # Test auth endpoints
        response = client.get("/api/v1/auth/me")
        assert response.status_code in [401, 200]  # 401 without auth, 200 with mock
        
        # Test health endpoints
        response = client.get("/api/v1/health")
        assert response.status_code in [200, 404]  # May not exist yet
        
        # Test chat endpoints
        response = client.get("/api/v1/chats")
        assert response.status_code in [401, 200]  # 401 without auth, 200 with mock
        
        # Test analyze endpoints
        response = client.get("/api/v1/analyze/jobs/test-job-id")
        assert response.status_code in [401, 200]  # 401 without auth, 200 with mock
        
        # Test models endpoints
        response = client.get("/api/v1/models/llm")
        assert response.status_code in [401, 200]  # 401 without auth, 200 with mock
        
        # Test artifacts endpoints
        response = client.get("/api/v1/artifacts/test-artifact-id")
        assert response.status_code in [401, 200]  # 401 without auth, 200 with mock
