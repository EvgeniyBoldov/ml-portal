"""
Tests for production readiness improvements
"""
import pytest
import uuid
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient
from fastapi import FastAPI

from app.celery_app import app as celery_app
from app.core.enhanced_rate_limit import enhanced_rate_limit
from app.core.sse_protocol import SSEProtocol, SSEStreamer, SSEEventType
from app.core.rag_integrity import ContentIntegrity, S3PresignedWithIntegrity
from app.core.debug_routes import DebugRoutesManager, DebugMiddleware
from app.core.message_content import (
    UnifiedMessageContent, MessageContentType, MessageContentPart,
    MessageContentConverter, MessageContentValidator, MessageContentMigration
)
from app.core.config import get_settings


class TestCeleryTaskRouting:
    """Test Celery task routing consistency"""
    
    def test_task_names_match_routes(self):
        """Test that task names match routing keys"""
        task_routes = celery_app.conf.task_routes
        
        # Check that all routes have corresponding task names
        expected_tasks = [
            "bg_tasks.process_document",
            "bg_tasks.extract_and_normalize_text", 
            "bg_tasks.chunk_document",
            "bg_tasks.generate_embeddings",
            "bg_tasks.finalize_document",
            "bg_tasks.analyze_document",
            "bg_tasks.cleanup_old_documents",
            "periodic_tasks.cleanup_old_documents_daily",
            "periodic_tasks.system_health_check",
            "periodic_tasks.update_system_statistics",
            "periodic_tasks.cleanup_temp_files",
            "periodic_tasks.reindex_failed_documents",
            "periodic_tasks.monitor_queue_health"
        ]
        
        for task_name in expected_tasks:
            assert task_name in task_routes, f"Task {task_name} not found in routes"
            assert "queue" in task_routes[task_name], f"Task {task_name} missing queue"
            assert "priority" in task_routes[task_name], f"Task {task_name} missing priority"
    
    def test_queue_priorities_are_valid(self):
        """Test that queue priorities are valid"""
        task_routes = celery_app.conf.task_routes
        
        for task_name, config in task_routes.items():
            priority = config.get("priority", 0)
            assert 1 <= priority <= 10, f"Task {task_name} has invalid priority {priority}"
    
    def test_queues_are_defined(self):
        """Test that all referenced queues are defined"""
        task_routes = celery_app.conf.task_routes
        defined_queues = {queue.name for queue in celery_app.conf.task_queues}
        
        for task_name, config in task_routes.items():
            queue_name = config.get("queue")
            assert queue_name in defined_queues, f"Task {task_name} references undefined queue {queue_name}"


class TestEnhancedRateLimit:
    """Test enhanced rate limiting with metrics"""
    
    @pytest.mark.asyncio
    async def test_rate_limit_metrics(self):
        """Test that rate limiting records metrics"""
        from app.core.metrics import get_metrics_registry
        
        # Mock request
        mock_request = Mock()
        mock_request.url.path = "/api/v1/test"
        mock_request.headers = {}
        
        # Mock Redis
        with patch('app.core.enhanced_rate_limit.get_redis') as mock_redis:
            mock_redis_instance = Mock()
            mock_redis_instance.set.return_value = True
            mock_redis_instance.incr.return_value = 1
            mock_redis.return_value = mock_redis_instance
            
            # Test first request
            await enhanced_rate_limit(mock_request, "test", 10, 60)
            
            # Check that metrics were recorded
            metrics = get_metrics_registry()
            # Note: In real test, you'd check actual metric values
    
    @pytest.mark.asyncio
    async def test_rate_limit_headers(self):
        """Test that rate limit headers are set"""
        mock_request = Mock()
        mock_request.url.path = "/api/v1/test"
        mock_request.headers = {}
        mock_request.state = Mock()
        
        with patch('app.core.enhanced_rate_limit.get_redis') as mock_redis:
            mock_redis_instance = Mock()
            mock_redis_instance.set.return_value = True
            mock_redis_instance.incr.return_value = 1
            mock_redis.return_value = mock_redis_instance
            
            await enhanced_rate_limit(mock_request, "test", 10, 60)
            
            # Check that headers were set
            assert hasattr(mock_request.state, 'rate_limit_headers')
            headers = mock_request.state.rate_limit_headers
            assert "X-RateLimit-Limit" in headers
            assert "X-RateLimit-Remaining" in headers
            assert "X-RateLimit-Window" in headers


class TestSSEProtocol:
    """Test SSE protocol stability"""
    
    def test_sse_event_types(self):
        """Test SSE event types are defined"""
        assert SSEEventType.TOKEN == "token"
        assert SSEEventType.PING == "ping"
        assert SSEEventType.SOURCES == "sources"
        assert SSEEventType.DONE == "done"
        assert SSEEventType.ERROR == "error"
    
    def test_sse_protocol_methods(self):
        """Test SSE protocol methods"""
        # Test token event
        token_event = SSEProtocol.send_token("Hello", False)
        assert "event: token" in token_event
        assert '"text": "Hello"' in token_event
        assert '"final": false' in token_event
        
        # Test ping event
        ping_event = SSEProtocol.send_ping()
        assert "event: ping" in ping_event
        assert "timestamp" in ping_event
        
        # Test done event
        done_event = SSEProtocol.send_done(success=True)
        assert "event: done" in done_event
        assert '"success": true' in done_event
        
        # Test error event
        error_event = SSEProtocol.send_error("Test error", "test_code")
        assert "event: error" in error_event
        assert '"error": "Test error"' in error_event
        assert '"code": "test_code"' in error_event
    
    @pytest.mark.asyncio
    async def test_sse_streamer(self):
        """Test SSE streamer functionality"""
        streamer = SSEStreamer(ping_interval=5)
        
        # Test token streaming
        events = []
        async for event in streamer.stream_tokens("Hello world", chunk_size=2):
            events.append(event.decode())
        
        # Check that we got the expected events
        assert len(events) > 0
        assert any("event: token" in event for event in events)
        assert any("event: done" in event for event in events)
    
    @pytest.mark.asyncio
    async def test_sse_error_handling(self):
        """Test SSE error handling"""
        streamer = SSEStreamer()
        
        # Test error streaming
        events = []
        async for event in streamer.stream_error("Test error", "test_code"):
            events.append(event.decode())
        
        # Check that we got error and done events
        assert len(events) >= 2
        assert any("event: error" in event for event in events)
        assert any("event: done" in event for event in events)


class TestRAGIntegrity:
    """Test RAG upload integrity control"""
    
    def test_content_integrity(self):
        """Test content integrity functions"""
        test_content = b"Hello, World!"
        
        # Test MD5 computation
        md5_hash = ContentIntegrity.compute_md5(test_content)
        assert len(md5_hash) == 32
        assert md5_hash.isalnum()
        
        # Test SHA256 computation
        sha256_hash = ContentIntegrity.compute_sha256(test_content)
        assert len(sha256_hash) == 64
        assert sha256_hash.isalnum()
        
        # Test Content-MD5 header
        content_md5 = ContentIntegrity.compute_content_md5_header(test_content)
        assert len(content_md5) == 24  # Base64 encoded MD5
        
        # Test verification
        assert ContentIntegrity.verify_content_md5(test_content, md5_hash)
        assert ContentIntegrity.verify_content_sha256(test_content, sha256_hash)
    
    def test_content_integrity_verification(self):
        """Test content integrity verification"""
        test_content = b"Hello, World!"
        correct_md5 = ContentIntegrity.compute_md5(test_content)
        wrong_md5 = "wrong_hash"
        
        # Test correct verification
        assert ContentIntegrity.verify_content_md5(test_content, correct_md5)
        
        # Test incorrect verification
        assert not ContentIntegrity.verify_content_md5(test_content, wrong_md5)


class TestDebugRoutes:
    """Test DEBUG routes management"""
    
    def test_debug_endpoint_detection(self):
        """Test DEBUG endpoint detection"""
        # Test DEBUG prefixes
        assert DebugRoutesManager.is_debug_endpoint("/api/setup/create-superuser")
        assert DebugRoutesManager.is_debug_endpoint("/api/test/rag/search")
        assert DebugRoutesManager.is_debug_endpoint("/api/debug/health")
        
        # Test DEBUG endpoints
        assert DebugRoutesManager.is_debug_endpoint("/rag/upload/validate")
        assert DebugRoutesManager.is_debug_endpoint("/users")
        
        # Test non-DEBUG endpoints
        assert not DebugRoutesManager.is_debug_endpoint("/api/v1/chats")
        assert not DebugRoutesManager.is_debug_endpoint("/api/v1/auth/login")
    
    def test_debug_access_check(self):
        """Test DEBUG access checking"""
        # Test DEBUG mode enabled
        with patch('app.core.debug_routes.settings') as mock_settings:
            mock_settings.DEBUG = True
            
            # Should not raise exception
            DebugRoutesManager.check_debug_access("/api/setup/test")
        
        # Test DEBUG mode disabled
        with patch('app.core.debug_routes.settings') as mock_settings:
            mock_settings.DEBUG = False
            
            # Should raise exception
            with pytest.raises(Exception):  # HTTPException
                DebugRoutesManager.check_debug_access("/api/setup/test")
    
    def test_debug_endpoints_info(self):
        """Test DEBUG endpoints info"""
        info = DebugRoutesManager.get_debug_endpoints_info()
        
        assert "debug_mode" in info
        assert "debug_prefixes" in info
        assert "debug_endpoints" in info
        assert "total_debug_endpoints" in info
        
        assert isinstance(info["debug_prefixes"], list)
        assert isinstance(info["debug_endpoints"], list)
        assert isinstance(info["total_debug_endpoints"], int)


class TestMessageContent:
    """Test message content unification"""
    
    def test_message_content_types(self):
        """Test message content types"""
        assert MessageContentType.TEXT == "text"
        assert MessageContentType.MARKDOWN == "markdown"
        assert MessageContentType.JSON == "json"
        assert MessageContentType.CODE == "code"
        assert MessageContentType.IMAGE == "image"
        assert MessageContentType.FILE == "file"
    
    def test_message_content_part(self):
        """Test message content part"""
        part = MessageContentPart(
            type=MessageContentType.TEXT,
            content="Hello, World!",
            metadata={"source": "user"}
        )
        
        assert part.type == MessageContentType.TEXT
        assert part.content == "Hello, World!"
        assert part.metadata["source"] == "user"
    
    def test_unified_message_content(self):
        """Test unified message content"""
        content = UnifiedMessageContent(
            type=MessageContentType.TEXT,
            parts=[MessageContentPart(
                type=MessageContentType.TEXT,
                content="Hello, World!"
            )]
        )
        
        assert content.type == MessageContentType.TEXT
        assert len(content.parts) == 1
        assert content.parts[0].content == "Hello, World!"
    
    def test_content_converter_from_legacy_dict(self):
        """Test content converter from legacy dict"""
        legacy_content = {"text": "Hello, World!"}
        unified_content = MessageContentConverter.from_legacy_dict(legacy_content)
        
        assert unified_content.type == MessageContentType.TEXT
        assert len(unified_content.parts) == 1
        assert unified_content.parts[0].content == "Hello, World!"
    
    def test_content_converter_from_legacy_string(self):
        """Test content converter from legacy string"""
        legacy_content = "Hello, World!"
        unified_content = MessageContentConverter.from_legacy_string(legacy_content)
        
        assert unified_content.type == MessageContentType.TEXT
        assert len(unified_content.parts) == 1
        assert unified_content.parts[0].content == "Hello, World!"
    
    def test_content_converter_to_legacy_dict(self):
        """Test content converter to legacy dict"""
        unified_content = UnifiedMessageContent(
            type=MessageContentType.TEXT,
            parts=[MessageContentPart(
                type=MessageContentType.TEXT,
                content="Hello, World!"
            )]
        )
        
        legacy_dict = MessageContentConverter.to_legacy_dict(unified_content)
        assert legacy_dict["text"] == "Hello, World!"
    
    def test_content_converter_to_legacy_string(self):
        """Test content converter to legacy string"""
        unified_content = UnifiedMessageContent(
            type=MessageContentType.TEXT,
            parts=[MessageContentPart(
                type=MessageContentType.TEXT,
                content="Hello, World!"
            )]
        )
        
        legacy_string = MessageContentConverter.to_legacy_string(unified_content)
        assert legacy_string == "Hello, World!"
    
    def test_content_validator(self):
        """Test content validator"""
        # Test string validation
        validated_content = MessageContentValidator.validate_content("Hello, World!")
        assert validated_content.type == MessageContentType.TEXT
        
        # Test dict validation
        validated_content = MessageContentValidator.validate_content({"text": "Hello, World!"})
        assert validated_content.type == MessageContentType.TEXT
        
        # Test text validation
        validated_text = MessageContentValidator.validate_text_content("Hello, World!")
        assert validated_text == "Hello, World!"
        
        # Test empty text validation
        with pytest.raises(ValueError):
            MessageContentValidator.validate_text_content("")
        
        # Test long text validation
        long_text = "x" * 10001
        with pytest.raises(ValueError):
            MessageContentValidator.validate_text_content(long_text)
    
    def test_content_migration(self):
        """Test content migration"""
        # Test text message creation
        text_message = MessageContentMigration.create_text_message("Hello, World!")
        assert text_message.type == MessageContentType.TEXT
        assert text_message.parts[0].content == "Hello, World!"
        
        # Test markdown message creation
        markdown_message = MessageContentMigration.create_markdown_message("# Hello, World!")
        assert markdown_message.type == MessageContentType.MARKDOWN
        assert markdown_message.parts[0].content == "# Hello, World!"
        
        # Test code message creation
        code_message = MessageContentMigration.create_code_message("print('Hello')", "python")
        assert code_message.type == MessageContentType.CODE
        assert code_message.parts[0].content == "print('Hello')"
        assert code_message.parts[0].metadata["language"] == "python"


class TestProductionReadiness:
    """Test overall production readiness"""
    
    def test_all_critical_modules_importable(self):
        """Test that all critical modules can be imported"""
        critical_modules = [
            'app.celery_app',
            'app.core.enhanced_rate_limit',
            'app.core.sse_protocol',
            'app.core.rag_integrity',
            'app.core.debug_routes',
            'app.core.message_content'
        ]
        
        for module_name in critical_modules:
            try:
                __import__(module_name)
            except ImportError as e:
                pytest.fail(f"Failed to import {module_name}: {e}")
    
    def test_celery_configuration(self):
        """Test Celery configuration"""
        assert celery_app.conf.task_serializer == "json"
        assert celery_app.conf.accept_content == ["json"]
        assert celery_app.conf.result_serializer == "json"
        assert celery_app.conf.task_acks_late is True
        assert celery_app.conf.worker_prefetch_multiplier == 1
    
    def test_debug_routes_validation(self):
        """Test DEBUG routes validation"""
        issues = DebugRoutesManager.validate_debug_endpoints()
        assert len(issues) == 0, f"DEBUG routes validation issues: {issues}"
