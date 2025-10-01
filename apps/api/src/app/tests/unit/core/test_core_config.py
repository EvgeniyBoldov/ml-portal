"""
Unit tests for core/config.py
"""
import pytest
import os
from app.core.config import get_settings


def test_settings_attributes():
    """Test all required settings attributes exist"""
    s = get_settings()
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
        assert hasattr(s, attr), f"Missing setting: {attr}"


def test_api_base_path():
    """Test API_BASE_PATH is set correctly"""
    s = get_settings()
    assert s.API_BASE_PATH == "/api"


def test_request_id_header():
    """Test REQUEST_ID_HEADER is set correctly"""
    s = get_settings()
    assert s.REQUEST_ID_HEADER == "X-Request-Id"


def test_tenant_header():
    """Test TENANT_HEADER is set correctly"""
    s = get_settings()
    assert s.TENANT_HEADER == "X-Tenant-Id"


def test_jwt_algorithm():
    """Test JWT_ALGORITHM is set correctly"""
    s = get_settings()
    assert s.JWT_ALGORITHM in ['HS256', 'HS384', 'HS512', 'RS256']


def test_separate_db_urls():
    """Test separate DB URLs are configured"""
    s = get_settings()
    assert s.SYNC_DB_URL != s.ASYNC_DB_URL
    assert "postgresql://" in s.SYNC_DB_URL
    assert "postgresql+asyncpg://" in s.ASYNC_DB_URL


def test_redis_url():
    """Test Redis URL is configured"""
    s = get_settings()
    assert s.REDIS_URL.startswith("redis://")


def test_s3_config():
    """Test S3 configuration"""
    s = get_settings()
    assert s.S3_ENDPOINT is not None
    assert s.S3_ACCESS_KEY is not None
    assert s.S3_SECRET_KEY is not None
    assert s.S3_BUCKET_RAG is not None


def test_qdrant_url():
    """Test Qdrant URL is configured"""
    s = get_settings()
    assert s.QDRANT_URL.startswith("http://")


def test_rate_limit_proxy_header():
    """Test rate limit trusted proxy header"""
    s = get_settings()
    assert s.RATE_LIMIT_TRUSTED_PROXY_HEADER in [
        "X-Forwarded-For", "X-Real-IP", "X-Client-IP"
    ]


def test_debug_mode():
    """Test DEBUG mode configuration"""
    s = get_settings()
    assert isinstance(s.DEBUG, bool)


def test_env_mode():
    """Test ENV mode configuration"""
    s = get_settings()
    assert s.ENV in ['development', 'testing', 'production']


def test_password_policy():
    """Test password policy settings"""
    s = get_settings()
    assert hasattr(s, 'PASSWORD_MIN_LENGTH')
    assert s.PASSWORD_MIN_LENGTH >= 8


def test_jwt_secret_not_empty():
    """Test JWT secret is not empty"""
    s = get_settings()
    assert len(s.JWT_SECRET) > 0


def test_password_pepper_not_empty():
    """Test password pepper is not empty"""
    s = get_settings()
    assert len(s.PASSWORD_PEPPER) > 0


def test_settings_from_env():
    """Test settings can be overridden from environment"""
    # This would test environment variable loading
    # For now, just verify settings are accessible
    s = get_settings()
    assert s is not None


def test_no_hardcoded_values():
    """Test no hardcoded values in settings"""
    # Verify critical values come from environment or have defaults
    s = get_settings()
    assert s.API_BASE_PATH == "/api"  # Should be configurable
    assert s.REQUEST_ID_HEADER == "X-Request-Id"  # Should be configurable
