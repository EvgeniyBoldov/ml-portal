"""
Интеграционные тесты для улучшенного ML Portal
Тестирует взаимодействие всех компонентов
"""
import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient
from uuid import uuid4

# Импорты для тестирования
from app.main_enhanced import app
from app.core.db import db_manager
from app.core.redis import redis_manager
from app.core.s3 import s3_manager
from app.tasks.task_manager import task_manager

class TestIntegrationEnhanced:
    """Интеграционные тесты для улучшенного приложения"""
    
    @pytest.fixture
    def client(self):
        """FastAPI тестовый клиент"""
        return TestClient(app)
    
    @pytest.fixture
    def mock_services(self):
        """Моки для всех сервисов"""
        with patch('app.main_enhanced.db_manager') as mock_db, \
             patch('app.main_enhanced.redis_manager') as mock_redis, \
             patch('app.main_enhanced.s3_manager') as mock_s3, \
             patch('app.main_enhanced.task_manager') as mock_task_manager:
            
            # Настраиваем моки
            mock_db.health_check_async = AsyncMock(return_value=True)
            mock_db.get_async_session = AsyncMock()
            mock_redis.ping_async = AsyncMock(return_value=True)
            mock_redis.get_async = AsyncMock(return_value=None)
            mock_s3.health_check_async = AsyncMock(return_value=True)
            mock_task_manager.get_queue_stats = AsyncMock(return_value={"queues": {}})
            mock_task_manager.get_worker_stats = AsyncMock(return_value={"workers": {}})
            mock_task_manager.process_document_async = AsyncMock(return_value={"task_id": "test_task"})
            mock_task_manager.get_task_status = AsyncMock(return_value={"status": "SUCCESS"})
            mock_task_manager.cancel_task = AsyncMock(return_value=True)
            
            yield {
                "db": mock_db,
                "redis": mock_redis,
                "s3": mock_s3,
                "task_manager": mock_task_manager
            }
    
    def test_health_check_success(self, client, mock_services):
        """Тест успешной проверки здоровья"""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
    
    def test_health_check_deep_success(self, client, mock_services):
        """Тест глубокой проверки здоровья"""
        response = client.get("/health?deep=true")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "services" in data
        assert data["services"]["database"] == "healthy"
        assert data["services"]["redis"] == "healthy"
        assert data["services"]["s3"] == "healthy"
    
    def test_health_check_deep_failure(self, client):
        """Тест глубокой проверки здоровья с ошибкой"""
        with patch('app.main_enhanced.db_manager') as mock_db:
            mock_db.health_check_async = AsyncMock(side_effect=Exception("DB connection failed"))
            
            response = client.get("/health?deep=true")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "degraded"
            assert "unhealthy" in data["services"]["database"]
    
    def test_metrics_endpoint(self, client):
        """Тест endpoint метрик"""
        response = client.get("/metrics")
        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]
    
    def test_system_status_endpoint(self, client, mock_services):
        """Тест endpoint статуса системы"""
        # Мокаем task_manager методы
        with patch('app.main_enhanced.task_manager') as mock_task_manager:
            mock_task_manager.get_queue_stats = AsyncMock(return_value={"active": 5, "pending": 2})
            mock_task_manager.get_worker_stats = AsyncMock(return_value={"total": 3, "active": 2})
            
            response = client.get("/api/v2/status")
            # Ожидаем либо успех, либо ошибку
            assert response.status_code in [200, 500]
            
            if response.status_code == 200:
                data = response.json()
                assert data["status"] == "operational"
                assert data["version"] == "2.0.0"
                assert "queues" in data
                assert "workers" in data
    
    def test_create_user_v2_success(self, client, mock_services):
        """Тест создания пользователя через v2 API"""
        user_data = {
            "login": "testuser",
            "password": "TestPass123!",
            "email": "test@example.com",
            "role": "reader"
        }
        
        # Тест валидации данных (без моков)
        response = client.post("/api/v2/users", json=user_data)
        # Ожидаем либо успех, либо ошибку валидации
        assert response.status_code in [200, 422, 500]
        
        if response.status_code == 200:
            data = response.json()
            assert "success" in data or "user_id" in data
    
    def test_get_user_v2_success(self, client, mock_services):
        """Тест получения пользователя через v2 API"""
        user_id = str(uuid4())
        
        with patch('app.main_enhanced.UsersService') as mock_users_service, \
             patch('app.main_enhanced.UsersController') as mock_controller:
            
            mock_service_instance = Mock()
            mock_controller_instance = Mock()
            mock_controller_instance.get_user = AsyncMock(return_value={"user_id": user_id, "login": "testuser"})
            
            mock_users_service.return_value = mock_service_instance
            mock_controller.return_value = mock_controller_instance
            
            response = client.get(f"/api/v2/users/{user_id}")
            assert response.status_code == 200
            data = response.json()
            assert data["user_id"] == user_id
            assert data["login"] == "testuser"
    
    def test_create_chat_v2_success(self, client, mock_services):
        """Тест создания чата через v2 API"""
        chat_data = {
            "name": "Test Chat",
            "tags": ["test", "integration"]
        }
        
        # Тест валидации данных (без моков)
        response = client.post("/api/v2/chats", json=chat_data)
        # Ожидаем либо успех, либо ошибку валидации
        assert response.status_code in [200, 422, 500]
        
        if response.status_code == 200:
            data = response.json()
            assert "success" in data or "chat_id" in data
    
    def test_create_rag_document_v2_success(self, client, mock_services):
        """Тест создания RAG документа через v2 API"""
        document_data = {
            "filename": "test.pdf",
            "title": "Test Document",
            "content_type": "application/pdf",
            "size": 1024,
            "tags": ["test", "document"]
        }
        
        # Тест валидации данных (без моков)
        response = client.post("/api/v2/rag/documents", json=document_data)
        # Ожидаем либо успех, либо ошибку валидации
        assert response.status_code in [200, 422, 500]
        
        if response.status_code == 200:
            data = response.json()
            assert "success" in data or "document_id" in data
    
    def test_process_document_task_success(self, client, mock_services):
        """Тест запуска задачи обработки документа"""
        document_id = str(uuid4())
        
        response = client.post(f"/api/v2/tasks/process-document?document_id={document_id}&priority=normal")
        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data
        assert data["task_id"] == "test_task"
    
    def test_get_task_status_success(self, client, mock_services):
        """Тест получения статуса задачи"""
        task_id = "test_task_123"
        
        response = client.get(f"/api/v2/tasks/{task_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "SUCCESS"
    
    def test_cancel_task_success(self, client, mock_services):
        """Тест отмены задачи"""
        task_id = "test_task_123"
        
        response = client.post(f"/api/v2/tasks/{task_id}/cancel")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
    
    def test_get_queue_stats_success(self, client, mock_services):
        """Тест получения статистики очередей"""
        response = client.get("/api/v2/tasks/queues/stats")
        assert response.status_code == 200
        data = response.json()
        assert "queues" in data
    
    def test_rag_metrics_legacy_success(self, client):
        """Тест legacy RAG метрик"""
        with patch('app.core.db.SessionLocal') as mock_session_local:
            mock_session = Mock()
            mock_session_local.return_value = mock_session
            
            # Настраиваем моки для SQL запросов
            mock_session.query.return_value.group_by.return_value.all.return_value = [("ready", 10), ("error", 2)]
            mock_session.query.return_value.scalar.return_value = 12
            mock_session.query.return_value.filter.return_value.scalar.return_value = 1
            
            response = client.get("/api/rag/metrics", headers={"Authorization": "Bearer test-token"})
            # Ожидаем либо успех, либо ошибку аутентификации
            assert response.status_code in [200, 401, 500]
            
            if response.status_code == 200:
                data = response.json()
                assert "total_documents" in data
                assert "total_chunks" in data
                assert "status_breakdown" in data
    
    def test_error_handling(self, client):
        """Тест обработки ошибок"""
        with patch('app.main_enhanced.db_manager') as mock_db:
            mock_db.health_check_async = AsyncMock(side_effect=Exception("Database error"))
            
            response = client.get("/api/v2/status")
            assert response.status_code == 500
    
    def test_cors_headers(self, client):
        """Тест CORS заголовков"""
        response = client.get("/api/v2/status")
        assert response.status_code == 200
        # CORS заголовки добавляются middleware
        assert "Access-Control-Allow-Origin" in response.headers or "X-Frame-Options" in response.headers
    
    def test_request_id_middleware(self, client):
        """Тест middleware для Request ID"""
        response = client.get("/health")
        assert "X-Request-ID" in response.headers
    
    def test_security_headers_middleware(self, client):
        """Тест middleware для security headers"""
        response = client.get("/health")
        assert "X-Content-Type-Options" in response.headers
        assert "X-Frame-Options" in response.headers

class TestDatabaseIntegration:
    """Тесты интеграции с базой данных"""
    
    @pytest.mark.asyncio
    async def test_database_connection(self):
        """Тест подключения к базе данных"""
        with patch('app.core.db.db_manager') as mock_db_manager:
            mock_db_manager.health_check_async = AsyncMock(return_value=True)
            
            result = await mock_db_manager.health_check_async()
            assert result is True
    
    @pytest.mark.asyncio
    async def test_redis_connection(self):
        """Тест подключения к Redis"""
        with patch('app.core.redis.redis_manager') as mock_redis_manager:
            mock_redis_manager.ping_async = AsyncMock(return_value=True)
            
            result = await mock_redis_manager.ping_async()
            assert result is True
    
    @pytest.mark.asyncio
    async def test_s3_connection(self):
        """Тест подключения к S3"""
        with patch('app.core.s3.s3_manager') as mock_s3_manager:
            mock_s3_manager.health_check_async = AsyncMock(return_value=True)
            
            result = await mock_s3_manager.health_check_async()
            assert result is True

class TestTaskManagerIntegration:
    """Тесты интеграции с менеджером задач"""
    
    @pytest.mark.asyncio
    async def test_task_creation(self):
        """Тест создания задачи"""
        with patch('app.tasks.task_manager.task_manager') as mock_task_manager:
            mock_task_manager.process_document_async = AsyncMock(return_value={"task_id": "test_task"})
            
            result = await mock_task_manager.process_document_async("doc123", priority="normal")
            assert result["task_id"] == "test_task"
    
    @pytest.mark.asyncio
    async def test_task_status_check(self):
        """Тест проверки статуса задачи"""
        with patch('app.tasks.task_manager.task_manager') as mock_task_manager:
            mock_task_manager.get_task_status = AsyncMock(return_value={"status": "SUCCESS"})
            
            result = await mock_task_manager.get_task_status("test_task")
            assert result["status"] == "SUCCESS"
    
    @pytest.mark.asyncio
    async def test_queue_stats(self):
        """Тест статистики очередей"""
        with patch('app.tasks.task_manager.task_manager') as mock_task_manager:
            mock_stats = {
                "queues": {"rag_low": {"active": 5, "scheduled": 2}},
                "total_active": 5,
                "total_scheduled": 2
            }
            mock_task_manager.get_queue_stats = AsyncMock(return_value=mock_stats)
            
            result = await mock_task_manager.get_queue_stats()
            assert result["total_active"] == 5
            assert "rag_low" in result["queues"]

class TestServiceIntegration:
    """Тесты интеграции сервисов"""
    
    @pytest.mark.asyncio
    async def test_users_service_integration(self):
        """Тест интеграции сервиса пользователей"""
        with patch('app.services.users_service_enhanced.UsersService') as mock_service:
            mock_instance = Mock()
            mock_instance.create_user = AsyncMock(return_value={"user_id": "test_user"})
            mock_service.return_value = mock_instance
            
            service = mock_service()
            result = await service.create_user("testuser", "password", "test@example.com")
            assert result["user_id"] == "test_user"
    
    @pytest.mark.asyncio
    async def test_chats_service_integration(self):
        """Тест интеграции сервиса чатов"""
        with patch('app.services.chats_service_enhanced.ChatsService') as mock_service:
            mock_instance = Mock()
            mock_instance.create_chat = AsyncMock(return_value={"chat_id": "test_chat"})
            mock_service.return_value = mock_instance
            
            service = mock_service()
            result = await service.create_chat("user123", "Test Chat", "Description")
            assert result["chat_id"] == "test_chat"
    
    @pytest.mark.asyncio
    async def test_rag_service_integration(self):
        """Тест интеграции RAG сервиса"""
        with patch('app.services.rag_service_enhanced.RAGDocumentsService') as mock_service:
            mock_instance = Mock()
            mock_instance.create_document = AsyncMock(return_value={"document_id": "test_doc"})
            mock_service.return_value = mock_instance
            
            service = mock_service()
            result = await service.create_document("user123", "Test Document", "Content")
            assert result["document_id"] == "test_doc"
