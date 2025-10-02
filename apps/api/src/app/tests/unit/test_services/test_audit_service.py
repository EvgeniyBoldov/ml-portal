"""
Unit тесты для AuditService.
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime
from app.schemas.users import AuditAction


class TestAuditService:
    """Unit тесты для AuditService."""

    @pytest.fixture
    def mock_session(self):
        """Создает мок сессии."""
        session = MagicMock()
        session.add = MagicMock()
        session.commit = MagicMock()
        return session

    @pytest.fixture
    def audit_service(self, mock_session):
        """Создает экземпляр AuditService с моками."""
        from app.services.audit_service import AuditService
        return AuditService(mock_session)

    def test_audit_service_initialization(self, audit_service, mock_session):
        """Тест инициализации AuditService."""
        # Assert
        assert audit_service.session == mock_session

    def test_log_action_method_exists(self, audit_service):
        """Тест наличия метода log_action."""
        # Assert
        assert hasattr(audit_service, 'log_action')
        assert callable(getattr(audit_service, 'log_action'))

    def test_log_user_action_method_exists(self, audit_service):
        """Тест наличия метода log_user_action."""
        # Assert
        assert hasattr(audit_service, 'log_user_action')
        assert callable(getattr(audit_service, 'log_user_action'))

    def test_log_action_basic(self, audit_service, mock_session):
        """Тест базового логирования действия."""
        # Arrange
        action = "test_action"
        actor_user_id = "user123"
        object_type = "document"
        object_id = "doc456"

        # Act
        audit_service.log_action(
            action=action,
            actor_user_id=actor_user_id,
            object_type=object_type,
            object_id=object_id
        )

        # Assert
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    def test_log_action_with_meta(self, audit_service, mock_session):
        """Тест логирования действия с метаданными."""
        # Arrange
        action = "test_action"
        meta = {"key": "value", "count": 42}

        # Act
        audit_service.log_action(action=action, meta=meta)

        # Assert
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    def test_log_action_with_request(self, audit_service, mock_session):
        """Тест логирования действия с запросом."""
        # Arrange
        action = "test_action"
        mock_request = MagicMock()
        mock_request.headers = {
            "X-Forwarded-For": "192.168.1.1, 10.0.0.1",
            "User-Agent": "Mozilla/5.0"
        }
        mock_request.client = MagicMock()
        mock_request.client.host = "127.0.0.1"

        # Act
        audit_service.log_action(action=action, request=mock_request)

        # Assert
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    def test_log_user_action(self, audit_service, mock_session):
        """Тест логирования действия пользователя."""
        # Arrange
        action = AuditAction.LOGIN
        target_user_id = "user123"
        actor_user_id = "admin123"
        meta = {"ip": "192.168.1.1"}

        # Act
        audit_service.log_user_action(
            action=action,
            target_user_id=target_user_id,
            actor_user_id=actor_user_id,
            **meta
        )

        # Assert
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    def test_log_user_action_with_object(self, audit_service, mock_session):
        """Тест логирования действия пользователя с объектом."""
        # Arrange
        action = AuditAction.UPDATE
        target_user_id = "user123"
        actor_user_id = "admin123"

        # Act
        audit_service.log_user_action(
            action=action,
            target_user_id=target_user_id,
            actor_user_id=actor_user_id
        )

        # Assert
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    def test_audit_service_attributes(self, audit_service):
        """Тест атрибутов AuditService."""
        # Assert
        assert hasattr(audit_service, 'session')

    def test_audit_service_methods(self, audit_service):
        """Тест методов AuditService."""
        # Assert
        assert hasattr(audit_service, 'log_action')
        assert hasattr(audit_service, 'log_user_action')
        assert callable(getattr(audit_service, 'log_action'))
        assert callable(getattr(audit_service, 'log_user_action'))
