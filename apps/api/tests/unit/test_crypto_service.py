"""
Unit tests for CryptoService
"""
import pytest
import json
from unittest.mock import patch

from app.core.crypto import CryptoService


class TestCryptoService:
    """Test CryptoService encryption/decryption"""
    
    @pytest.fixture
    def crypto_service(self):
        """Create CryptoService with test key"""
        with patch.dict('os.environ', {'CREDENTIALS_MASTER_KEY': 'test-master-key-12345'}):
            return CryptoService()
    
    @pytest.fixture
    def sample_payload(self):
        """Sample credentials payload"""
        return {
            "token": "secret-api-token-12345",
            "username": "admin",
            "password": "super-secret"
        }


class TestEncryptDecrypt(TestCryptoService):
    """Test encrypt and decrypt methods"""
    
    def test_encrypt_returns_string(self, crypto_service, sample_payload):
        """Encrypt should return a string"""
        encrypted = crypto_service.encrypt(sample_payload)
        
        assert isinstance(encrypted, str)
        assert len(encrypted) > 0
    
    def test_encrypted_is_not_plaintext(self, crypto_service, sample_payload):
        """Encrypted data should not contain plaintext"""
        encrypted = crypto_service.encrypt(sample_payload)
        
        assert "secret-api-token" not in encrypted
        assert "super-secret" not in encrypted
    
    def test_decrypt_returns_original(self, crypto_service, sample_payload):
        """Decrypt should return original payload"""
        encrypted = crypto_service.encrypt(sample_payload)
        decrypted = crypto_service.decrypt(encrypted)
        
        assert decrypted == sample_payload
    
    def test_encrypt_different_each_time(self, crypto_service, sample_payload):
        """Each encryption should produce different ciphertext (due to IV)"""
        encrypted1 = crypto_service.encrypt(sample_payload)
        encrypted2 = crypto_service.encrypt(sample_payload)
        
        # Same plaintext should produce different ciphertext
        assert encrypted1 != encrypted2
    
    def test_decrypt_both_versions(self, crypto_service, sample_payload):
        """Both encrypted versions should decrypt to same plaintext"""
        encrypted1 = crypto_service.encrypt(sample_payload)
        encrypted2 = crypto_service.encrypt(sample_payload)
        
        decrypted1 = crypto_service.decrypt(encrypted1)
        decrypted2 = crypto_service.decrypt(encrypted2)
        
        assert decrypted1 == decrypted2 == sample_payload


class TestEdgeCases(TestCryptoService):
    """Test edge cases"""
    
    def test_empty_payload(self, crypto_service):
        """Should handle empty dict"""
        encrypted = crypto_service.encrypt({})
        decrypted = crypto_service.decrypt(encrypted)
        
        assert decrypted == {}
    
    def test_nested_payload(self, crypto_service):
        """Should handle nested structures"""
        payload = {
            "oauth": {
                "client_id": "abc",
                "client_secret": "xyz",
                "tokens": {
                    "access": "token1",
                    "refresh": "token2"
                }
            }
        }
        
        encrypted = crypto_service.encrypt(payload)
        decrypted = crypto_service.decrypt(encrypted)
        
        assert decrypted == payload
    
    def test_unicode_payload(self, crypto_service):
        """Should handle unicode characters"""
        payload = {"password": "пароль123🔐"}
        
        encrypted = crypto_service.encrypt(payload)
        decrypted = crypto_service.decrypt(encrypted)
        
        assert decrypted == payload
    
    def test_large_payload(self, crypto_service):
        """Should handle large payloads"""
        payload = {"data": "x" * 10000}
        
        encrypted = crypto_service.encrypt(payload)
        decrypted = crypto_service.decrypt(encrypted)
        
        assert decrypted == payload


class TestInvalidInput(TestCryptoService):
    """Test invalid input handling"""
    
    def test_decrypt_invalid_data(self, crypto_service):
        """Should raise error for invalid encrypted data"""
        with pytest.raises(Exception):
            crypto_service.decrypt("not-valid-encrypted-data")
    
    def test_decrypt_empty_string(self, crypto_service):
        """Should raise error for empty string"""
        with pytest.raises(Exception):
            crypto_service.decrypt("")


class TestKeyDerivation:
    """Test key derivation from master key"""
    
    def test_same_key_same_result(self):
        """Same master key should produce consistent encryption"""
        CryptoService.reset()
        with patch.dict('os.environ', {'CREDENTIALS_MASTER_KEY': 'consistent-key'}):
            service1 = CryptoService()
            CryptoService.reset()
            service2 = CryptoService()
        
        payload = {"secret": "value"}
        
        # Both services should be able to decrypt each other's data
        encrypted = service1.encrypt(payload)
        decrypted = service2.decrypt(encrypted)
        
        assert decrypted == payload
    
    def test_different_key_fails(self):
        """Different master key should fail to decrypt"""
        payload = {"secret": "value"}
        
        CryptoService.reset()
        with patch.dict('os.environ', {'CREDENTIALS_MASTER_KEY': 'key-one'}):
            service1 = CryptoService()
            encrypted = service1.encrypt(payload)
        
        CryptoService.reset()
        with patch.dict('os.environ', {'CREDENTIALS_MASTER_KEY': 'key-two'}):
            service2 = CryptoService()
            
            with pytest.raises(Exception):
                service2.decrypt(encrypted)
