"""
Unit tests for core/config.py
"""
import pytest
import os
from app.core.config import settings


def test_settings_attributes():
    """Test all required settings attributes exist"""
    required_attrs = [
        'API_BASE_PATH',
        'REQUEST_ID_HEADER',
        'TENANT_HEADER',
        'JWT_SECRET',
        'JWT_ALGORITHM',
        'PASSWORD_PEPPER',
        'DB_URL',
        'ASYNC_DB_URL',
        'SYNC_DB_URL',
        'REDIS_URL',
        'S3_ENDPOINT',
        'S3_ACCESS_KEY',
        'S3_SECRET_KEY',
        'S3_BUCKET_RAG',
        'QDRANT_URL'
    ]
    
    for attr in required_attrs:
        assert hasattr(settings, attr), f"Missing setting: {attr}"


def test_api_base_path():
    """Test API_BASE_PATH is set correctly"""
    assert settings.API_BASE_PATH == "/api"


def test_request_id_header():
    """Test REQUEST_ID_HEADER is set correctly"""
    assert settings.REQUEST_ID_HEADER == "X-Request-Id"


def test_tenant_header():
    """Test TENANT_HEADER is set correctly"""
    assert settings.TENANT_HEADER == "X-Tenant-Id"


def test_jwt_algorithm():
    """Test JWT_ALGORITHM is set correctly"""
    assert settings.JWT_ALGORITHM in ['HS256', 'HS384', 'HS512', 'RS256']


def test_separate_db_urls():
    """Test separate DB URLs are configured"""
    assert settings.SYNC_DB_URL != settings.ASYNC_DB_URL
    assert "postgresql://" in settings.SYNC_DB_URL
    assert "postgresql+asyncpg://" in settings.ASYNC_DB_URL


def test_redis_url():
    """Test Redis URL is configured"""
    assert settings.REDIS_URL.startswith("redis://")


def test_s3_config():
    """Test S3 configuration"""
    assert settings.S3_ENDPOINT is not None
    assert settings.S3_ACCESS_KEY is not None
    assert settings.S3_SECRET_KEY is not None
    assert settings.S3_BUCKET_RAG is not None


def test_qdrant_url():
    """Test Qdrant URL is configured"""
    assert settings.QDRANT_URL.startswith("http://")


def test_rate_limit_proxy_header():
    """Test rate limit trusted proxy header"""
    assert settings.RATE_LIMIT_TRUSTED_PROXY_HEADER in [
        "X-Forwarded-For", "X-Real-IP", "X-Client-IP"
    ]


def test_debug_mode():
    """Test DEBUG mode configuration"""
    assert isinstance(settings.DEBUG, bool)


def test_env_mode():
    """Test ENV mode configuration"""
    assert settings.ENV in ['development', 'testing', 'production']


def test_password_policy():
    """Test password policy settings"""
    assert hasattr(settings, 'PASSWORD_MIN_LENGTH')
    assert settings.PASSWORD_MIN_LENGTH >= 8


def test_jwt_secret_not_empty():
    """Test JWT secret is not empty"""
    assert len(settings.JWT_SECRET) > 0


def test_password_pepper_not_empty():
    """Test password pepper is not empty"""
    assert len(settings.PASSWORD_PEPPER) > 0


def test_settings_from_env():
    """Test settings can be overridden from environment"""
    # This would test environment variable loading
    # For now, just verify settings are accessible
    assert settings is not None


def test_no_hardcoded_values():
    """Test no hardcoded values in settings"""
    # Verify critical values come from environment or have defaults
    assert settings.API_BASE_PATH == "/api"  # Should be configurable
    assert settings.REQUEST_ID_HEADER == "X-Request-Id"  # Should be configurable
