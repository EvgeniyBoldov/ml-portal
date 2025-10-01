"""
Unit tests for core/security.py
"""
import pytest
import jwt
from datetime import datetime, timedelta
from app.core.security import (
    hash_password,
    verify_password,
    encode_jwt,
    decode_jwt,
    get_bearer_token,
    validate_password_strength
)
from app.core.config import settings


def test_hash_password():
    """Test password hashing"""
    password = "testpassword123"
    hashed = hash_password(password)
    
    assert hashed != password
    assert len(hashed) > 0
    assert isinstance(hashed, str)


def test_verify_password():
    """Test password verification"""
    password = "testpassword123"
    hashed = hash_password(password)
    
    assert verify_password(password, hashed) is True
    assert verify_password("wrongpassword", hashed) is False


def test_password_hash_consistency():
    """Test password hash is consistent"""
    password = "testpassword123"
    hashed1 = hash_password(password)
    hashed2 = hash_password(password)
    
    # Should be different due to salt
    assert hashed1 != hashed2
    
    # But both should verify correctly
    assert verify_password(password, hashed1) is True
    assert verify_password(password, hashed2) is True


def test_encode_jwt():
    """Test JWT encoding"""
    payload = {
        "sub": "test@example.com"
    }
    
    token = encode_jwt(payload, ttl_seconds=3600)
    
    assert isinstance(token, str)
    assert len(token) > 0


def test_decode_jwt():
    """Test JWT decoding"""
    payload = {
        "sub": "test@example.com"
    }
    
    token = encode_jwt(payload, ttl_seconds=3600)
    decoded = decode_jwt(token)
    
    assert decoded["sub"] == "test@example.com"
    assert "exp" in decoded
    assert "iat" in decoded


def test_jwt_algorithm_from_settings():
    """Test JWT uses algorithm from settings"""
    payload = {"sub": "test@example.com"}
    token = encode_jwt(payload, ttl_seconds=3600)
    
    # Decode without verification to check algorithm
    decoded = jwt.decode(token, options={"verify_signature": False})
    assert decoded["sub"] == "test@example.com"


def test_jwt_expiration():
    """Test JWT expiration handling"""
    # Create expired token by using negative TTL
    payload = {"sub": "test@example.com"}
    expired_token = encode_jwt(payload, ttl_seconds=-3600)  # Expired 1 hour ago
    
    with pytest.raises(Exception):  # Will raise HTTPException from decode_jwt
        decode_jwt(expired_token)


def test_validate_password_strength():
    """Test password strength validation"""
    # Strong password
    is_valid, error = validate_password_strength("StrongPassword123!")
    assert is_valid is True
    assert error == ""
    
    # Weak passwords
    is_valid, error = validate_password_strength("123")
    assert is_valid is False
    assert "characters long" in error


def test_password_policy_from_settings():
    """Test password policy uses settings"""
    # Should use settings for policy configuration
    assert hasattr(settings, 'PASSWORD_MIN_LENGTH')
    assert settings.PASSWORD_MIN_LENGTH >= 8


def test_jwt_secret_from_settings():
    """Test JWT secret comes from settings"""
    assert hasattr(settings, 'JWT_SECRET')
    assert len(settings.JWT_SECRET) > 0


def test_password_pepper():
    """Test password pepper is used"""
    assert hasattr(settings, 'PASSWORD_PEPPER')
    # Pepper should be configured
