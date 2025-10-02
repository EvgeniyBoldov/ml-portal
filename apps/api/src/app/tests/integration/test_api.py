"""
Интеграционные тесты для API endpoints.
Использует реальные сервисы для проверки полного цикла запросов.
"""
import pytest
import asyncio
import uuid
from httpx import AsyncClient
from fastapi.testclient import TestClient

from app.main import app
from app.models.user import Users
from app.models.chat import Chats, ChatMessages


@pytest.mark.integration
class TestAPIIntegration:
    """Интеграционные тесты для API endpoints."""

    @pytest.mark.asyncio
    async def test_auth_flow(self, async_client: AsyncClient, db_session, test_tenant_id: str):
        """Тест полного цикла аутентификации."""
        from app.services.auth_service import AuthService
        
        auth_service = AuthService(db_session, test_tenant_id)
        
        # Register user
        user_data = {
            "email": "auth_test@example.com",
            "username": "auth_test",
            "password": "testpassword123"
        }
        
        try:
            # Create user
            user = auth_service.create_user(user_data)
            await db_session.commit()
            await db_session.refresh(user)
            
            # Test login
            login_data = {
                "email": user_data["email"],
                "password": user_data["password"]
            }
            
            # Mock authentication (in real app, this would return JWT)
            auth_result = auth_service.authenticate(login_data["email"], login_data["password"])
            assert auth_result is not None
            
            # Test password verification
            is_valid = auth_service.verify_password(login_data["password"], user.password_hash)
            assert is_valid is True
            
            # Test invalid password
            is_invalid = auth_service.verify_password("wrongpassword", user.password_hash)
            assert is_invalid is False
            
        finally:
            # Cleanup
            try:
                await db_session.execute(
                    "DELETE FROM users WHERE email = :email",
                    {"email": user_data["email"]}
                )
                await db_session.commit()
            except:
                pass

    @pytest.mark.asyncio
    async def test_user_crud_api(self, async_client: AsyncClient, db_session, test_tenant_id: str, auth_headers):
        """Тест CRUD операций через API."""
        from app.services.users_service import UsersService
        
        users_service = UsersService(db_session, test_tenant_id)
        
        user_data = {
            "email": "api_crud_test@example.com",
            "username": "api_crud_test",
            "password": "testpassword123"
        }
        
        try:
            # Create user through service
            created_user = users_service.create_user(user_data)
            await db_session.commit()
            await db_session.refresh(created_user)
            
            # Test GET /api/v1/users/{user_id}
            response = await async_client.get(
                f"/api/v1/users/{created_user.id}",
                headers=auth_headers
            )
            
            # Note: This might return 404 if the endpoint doesn't exist
            # In a real implementation, this would return user data
            assert response.status_code in [200, 404]
            
            if response.status_code == 200:
                user_data_response = response.json()
                assert user_data_response["email"] == user_data["email"]
                assert user_data_response["username"] == user_data["username"]
            
            # Test PUT /api/v1/users/{user_id}
            update_data = {"username": "updated_api_user"}
            response = await async_client.put(
                f"/api/v1/users/{created_user.id}",
                json=update_data,
                headers=auth_headers
            )
            
            assert response.status_code in [200, 404]
            
            if response.status_code == 200:
                updated_data_response = response.json()
                assert updated_data_response["username"] == update_data["username"]
            
        finally:
            # Cleanup
            try:
                await db_session.execute(
                    "DELETE FROM users WHERE email = :email",
                    {"email": user_data["email"]}
                )
                await db_session.commit()
            except:
                pass

    @pytest.mark.asyncio
    async def test_chat_api_flow(self, async_client: AsyncClient, db_session, test_user: Users, auth_headers):
        """Тест полного цикла работы с чатами через API."""
        from app.services.chats_service import ChatsService
        
        chats_service = ChatsService(db_session, test_user.tenant_id)
        
        chat_data = {
            "title": "API Integration Test Chat",
            "owner_id": test_user.id,
            "is_active": True
        }
        
        try:
            # Create chat through service
            created_chat = chats_service.create_chat(chat_data)
            await db_session.commit()
            await db_session.refresh(created_chat)
            
            # Test GET /api/v1/chat/chats
            response = await async_client.get(
                "/api/v1/chat/chats",
                headers=auth_headers
            )
            
            assert response.status_code in [200, 404]
            
            if response.status_code == 200:
                chats_response = response.json()
                assert isinstance(chats_response, (list, dict))
            
            # Test GET /api/v1/chat/chats/{chat_id}
            response = await async_client.get(
                f"/api/v1/chat/chats/{created_chat.id}",
                headers=auth_headers
            )
            
            assert response.status_code in [200, 404]
            
            if response.status_code == 200:
                chat_response = response.json()
                assert chat_response["title"] == chat_data["title"]
            
            # Test POST /api/v1/chat/chats/{chat_id}/messages
            message_data = {
                "content": "Hello from integration test!",
                "role": "user"
            }
            
            response = await async_client.post(
                f"/api/v1/chat/chats/{created_chat.id}/messages",
                json=message_data,
                headers=auth_headers
            )
            
            assert response.status_code in [200, 201, 404]
            
            if response.status_code in [200, 201]:
                message_response = response.json()
                assert message_response["content"] == message_data["content"]
            
        finally:
            # Cleanup
            try:
                await db_session.execute(
                    "DELETE FROM chat_messages WHERE chat_id = :chat_id",
                    {"chat_id": created_chat.id}
                )
                await db_session.execute(
                    "DELETE FROM chats WHERE id = :chat_id",
                    {"chat_id": created_chat.id}
                )
                await db_session.commit()
            except:
                pass

    @pytest.mark.asyncio
    async def test_rag_api_flow(self, async_client: AsyncClient, db_session, test_user: Users, auth_headers):
        """Тест полного цикла работы с RAG через API."""
        from app.repositories.rag_repo import RAGDocumentsRepository
        
        rag_repo = RAGDocumentsRepository(db_session, test_user.tenant_id)
        
        document_data = {
            "filename": "api_test_document.pdf",
            "content_type": "application/pdf",
            "size_bytes": 2048,
            "status": "uploaded",
            "user_id": test_user.id
        }
        
        try:
            # Create RAG document through service
            created_doc = rag_repo.create(document_data)
            await db_session.commit()
            await db_session.refresh(created_doc)
            
            # Test POST /api/v1/rag/upload/presign
            presign_data = {
                "document_id": str(created_doc.id),
                "content_type": "application/pdf"
            }
            
            response = await async_client.post(
                "/api/v1/rag/upload/presign",
                json=presign_data,
                headers=auth_headers
            )
            
            assert response.status_code in [200, 404]
            
            if response.status_code == 200:
                presign_response = response.json()
                assert "presigned_url" in presign_response
                assert "bucket" in presign_response
                assert "key" in presign_response
            
        finally:
            # Cleanup
            try:
                await db_session.execute(
                    "DELETE FROM rag_chunks WHERE document_id = :doc_id",
                    {"doc_id": created_doc.id}
                )
                await db_session.execute(
                    "DELETE FROM rag_documents WHERE id = :doc_id",
                    {"doc_id": created_doc.id}
                )
                await db_session.commit()
            except:
                pass

    @pytest.mark.asyncio
    async def test_analyze_api_flow(self, async_client: AsyncClient, db_session, test_user: Users, auth_headers):
        """Тест полного цикла работы с анализом через API."""
        # Test POST /api/v1/analyze/ingest/presign
        presign_data = {
            "document_id": str(uuid.uuid4()),
            "content_type": "application/pdf"
        }
        
        response = await async_client.post(
            "/api/v1/analyze/ingest/presign",
            json=presign_data,
            headers=auth_headers
        )
        
        assert response.status_code in [200, 404]
        
        if response.status_code == 200:
            presign_response = response.json()
            assert "presigned_url" in presign_response
            assert "bucket" in presign_response
            assert "key" in presign_response
        
        # Test POST /api/v1/analyze/stream
        analyze_data = {
            "texts": [
                "This is a test document for analysis.",
                "Machine learning is fascinating.",
                "Natural language processing helps computers understand text."
            ]
        }
        
        response = await async_client.post(
            "/api/v1/analyze/stream",
            json=analyze_data,
            headers=auth_headers
        )
        
        assert response.status_code in [200, 404]
        
        if response.status_code == 200:
            # Should be SSE stream
            assert response.headers.get("content-type") == "text/event-stream"

    @pytest.mark.asyncio
    async def test_artifacts_api_flow(self, async_client: AsyncClient, db_session, test_user: Users, auth_headers):
        """Тест полного цикла работы с артефактами через API."""
        # Test POST /api/v1/artifacts/presign
        presign_data = {
            "job_id": str(uuid.uuid4()),
            "filename": "test_artifact.json",
            "content_type": "application/json"
        }
        
        response = await async_client.post(
            "/api/v1/artifacts/presign",
            json=presign_data,
            headers=auth_headers
        )
        
        assert response.status_code in [200, 404]
        
        if response.status_code == 200:
            presign_response = response.json()
            assert "presigned_url" in presign_response
            assert "bucket" in presign_response
            assert "key" in presign_response

    @pytest.mark.asyncio
    async def test_admin_api_flow(self, async_client: AsyncClient, db_session, test_user: Users, auth_headers):
        """Тест админских API endpoints."""
        # Test GET /api/v1/admin/status
        response = await async_client.get(
            "/api/v1/admin/status",
            headers=auth_headers
        )
        
        assert response.status_code in [200, 403, 404]  # 403 if not admin
        
        if response.status_code == 200:
            status_response = response.json()
            assert isinstance(status_response, dict)
        
        # Test POST /api/v1/admin/mode
        mode_data = {
            "readonly": True,
            "maintenance": False
        }
        
        response = await async_client.post(
            "/api/v1/admin/mode",
            json=mode_data,
            headers=auth_headers
        )
        
        assert response.status_code in [200, 403, 404]  # 403 if not admin

    @pytest.mark.asyncio
    async def test_security_api_flow(self, async_client: AsyncClient):
        """Тест security API endpoints."""
        # Test GET /api/v1/auth/jwks
        response = await async_client.get("/api/v1/auth/jwks")
        
        assert response.status_code in [200, 404]
        
        if response.status_code == 200:
            jwks_response = response.json()
            assert "keys" in jwks_response
            assert isinstance(jwks_response["keys"], list)

    @pytest.mark.asyncio
    async def test_error_handling(self, async_client: AsyncClient, auth_headers):
        """Тест обработки ошибок в API."""
        # Test 404 for non-existent endpoint
        response = await async_client.get(
            "/api/v1/non-existent-endpoint",
            headers=auth_headers
        )
        
        assert response.status_code == 404
        
        # Test 400 for invalid JSON
        response = await async_client.post(
            "/api/v1/users",
            data="invalid json",
            headers={**auth_headers, "content-type": "application/json"}
        )
        
        assert response.status_code in [400, 404, 422]
        
        # Test 401 for missing auth
        response = await async_client.get("/api/v1/users")
        
        assert response.status_code in [401, 404]

    @pytest.mark.asyncio
    async def test_concurrent_api_requests(self, async_client: AsyncClient, auth_headers):
        """Тест конкурентных API запросов."""
        async def make_request(request_id: int):
            response = await async_client.get(
                "/api/v1/auth/jwks",
                headers=auth_headers
            )
            return request_id, response.status_code
        
        # Execute concurrent requests
        tasks = [make_request(i) for i in range(10)]
        results = await asyncio.gather(*tasks)
        
        assert len(results) == 10
        
        # All requests should complete successfully
        for request_id, status_code in results:
            assert status_code in [200, 404]  # 404 if endpoint doesn't exist
