"""
Unit тесты для конфигурации.
"""
import pytest
import os
from app.core.config import Settings, get_settings


class TestConfig:
    """Unit тесты для конфигурации."""

    def test_settings_creation(self):
        """Тест создания настроек."""
        # Act
        settings = Settings()

        # Assert
        assert settings is not None
        assert hasattr(settings, 'DB_URL')
        assert hasattr(settings, 'REDIS_URL')
        assert hasattr(settings, 'JWT_SECRET')

    def test_get_settings_singleton(self):
        """Тест получения настроек (singleton)."""
        # Act
        settings1 = get_settings()
        settings2 = get_settings()

        # Assert
        assert settings1 is settings2  # Должен быть тот же объект

    def test_settings_with_env_vars(self):
        """Тест настроек с переменными окружения."""
        # Arrange
        test_db_url = "sqlite:///test.db"
        test_redis_url = "redis://localhost:6379/1"
        
        os.environ["DB_URL"] = test_db_url
        os.environ["REDIS_URL"] = test_redis_url

        try:
            # Act
            settings = Settings()

            # Assert
            assert settings.DB_URL == test_db_url
            assert settings.REDIS_URL == test_redis_url
        finally:
            # Cleanup
            if "DB_URL" in os.environ:
                del os.environ["DB_URL"]
            if "REDIS_URL" in os.environ:
                del os.environ["REDIS_URL"]

    def test_settings_default_values(self):
        """Тест значений по умолчанию."""
        # Act
        settings = Settings()

        # Assert
        assert settings.JWT_ALGORITHM == "HS256"
        assert settings.JWT_ISSUER is not None
        assert settings.JWT_AUDIENCE is not None
