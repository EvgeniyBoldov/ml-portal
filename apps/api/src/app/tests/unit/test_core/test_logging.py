"""
Unit тесты для системы логирования.
"""
import pytest
from unittest.mock import patch, MagicMock
from app.core.logging import get_logger


class TestLogging:
    """Unit тесты для системы логирования."""

    def test_get_logger(self):
        """Тест получения логгера."""
        # Act
        logger = get_logger("test_module")

        # Assert
        assert logger is not None
        assert logger.name == "test_module"

    def test_get_logger_with_different_modules(self):
        """Тест получения логгеров для разных модулей."""
        # Act
        logger1 = get_logger("module1")
        logger2 = get_logger("module2")

        # Assert
        assert logger1 is not None
        assert logger2 is not None
        assert logger1.name == "module1"
        assert logger2.name == "module2"

    def test_logger_has_standard_methods(self):
        """Тест наличия стандартных методов логгера."""
        # Arrange
        logger = get_logger("test_module")

        # Assert
        assert hasattr(logger, 'debug')
        assert hasattr(logger, 'info')
        assert hasattr(logger, 'warning')
        assert hasattr(logger, 'error')
        assert hasattr(logger, 'critical')

    def test_logger_methods_callable(self):
        """Тест вызова методов логгера."""
        # Arrange
        logger = get_logger("test_module")

        # Act & Assert - проверяем, что методы можно вызвать
        try:
            logger.debug("Debug message")
            logger.info("Info message")
            logger.warning("Warning message")
            logger.error("Error message")
            logger.critical("Critical message")
        except Exception as e:
            pytest.fail(f"Logger methods should be callable, but got error: {e}")

    def test_logger_with_nested_module(self):
        """Тест получения логгера для вложенного модуля."""
        # Act
        logger = get_logger("app.services.users_service")

        # Assert
        assert logger is not None
        assert logger.name == "app.services.users_service"
