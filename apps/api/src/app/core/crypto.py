"""
CryptoService - шифрование/дешифрование секретов для CredentialSet

Использует Fernet (AES-128-CBC) с мастер-ключом из переменных окружения.
"""
import os
import json
import base64
import hashlib
from typing import Dict, Any, Optional
from cryptography.fernet import Fernet, InvalidToken

from app.core.exceptions import CryptoError
from app.core.logging import get_logger

logger = get_logger(__name__)


class CryptoService:
    """
    Сервис для шифрования/дешифрования credentials.
    
    Мастер-ключ берется из переменной окружения CREDENTIALS_MASTER_KEY.
    Если ключ не задан, генерируется предупреждение и используется fallback.
    
    Формат encrypted_payload:
    - Base64-encoded Fernet token
    - Внутри: JSON с credentials
    
    Пример использования:
        crypto = CryptoService()
        
        # Шифрование
        payload = {"token": "secret-api-key"}
        encrypted = crypto.encrypt(payload)
        
        # Дешифрование
        decrypted = crypto.decrypt(encrypted)
    """
    
    _instance: Optional["CryptoService"] = None
    _fernet: Optional[Fernet] = None
    
    def __new__(cls) -> "CryptoService":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_fernet()
        return cls._instance
    
    def _init_fernet(self) -> None:
        """Инициализация Fernet с мастер-ключом"""
        master_key = os.getenv("CREDENTIALS_MASTER_KEY")
        
        if not master_key:
            logger.warning(
                "CREDENTIALS_MASTER_KEY not set! Using fallback key. "
                "This is INSECURE for production!"
            )
            master_key = "INSECURE_FALLBACK_KEY_DO_NOT_USE_IN_PRODUCTION"
        
        fernet_key = self._derive_fernet_key(master_key)
        self._fernet = Fernet(fernet_key)
    
    def _derive_fernet_key(self, master_key: str) -> bytes:
        """
        Derive a valid Fernet key from arbitrary master key.
        Fernet requires a 32-byte base64-encoded key.
        """
        key_bytes = hashlib.sha256(master_key.encode()).digest()
        return base64.urlsafe_b64encode(key_bytes)
    
    def encrypt(self, payload: Dict[str, Any]) -> str:
        """
        Зашифровать payload (dict) в строку.
        
        Args:
            payload: Словарь с credentials (например, {"token": "..."})
            
        Returns:
            Base64-encoded encrypted string
            
        Raises:
            CryptoError: При ошибке шифрования
        """
        if not self._fernet:
            raise CryptoError("Fernet not initialized")
        
        try:
            json_bytes = json.dumps(payload).encode("utf-8")
            encrypted = self._fernet.encrypt(json_bytes)
            return encrypted.decode("utf-8")
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            raise CryptoError(f"Encryption failed: {e}") from e
    
    def decrypt(self, encrypted_payload: str) -> Dict[str, Any]:
        """
        Расшифровать строку обратно в payload (dict).
        
        Args:
            encrypted_payload: Base64-encoded encrypted string
            
        Returns:
            Словарь с credentials
            
        Raises:
            CryptoError: При ошибке дешифрования или невалидном токене
        """
        if not self._fernet:
            raise CryptoError("Fernet not initialized")
        
        try:
            decrypted = self._fernet.decrypt(encrypted_payload.encode("utf-8"))
            return json.loads(decrypted.decode("utf-8"))
        except InvalidToken:
            logger.error("Invalid token - decryption failed")
            raise CryptoError("Invalid token - wrong key or corrupted data")
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode failed after decryption: {e}")
            raise CryptoError(f"Invalid payload format: {e}") from e
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            raise CryptoError(f"Decryption failed: {e}") from e
    
    def rotate_key(self, old_encrypted: str, new_master_key: str) -> str:
        """
        Перешифровать payload с новым мастер-ключом.
        
        Используется при ротации ключей.
        
        Args:
            old_encrypted: Payload, зашифрованный старым ключом
            new_master_key: Новый мастер-ключ
            
        Returns:
            Payload, зашифрованный новым ключом
        """
        payload = self.decrypt(old_encrypted)
        
        new_fernet_key = self._derive_fernet_key(new_master_key)
        new_fernet = Fernet(new_fernet_key)
        
        json_bytes = json.dumps(payload).encode("utf-8")
        return new_fernet.encrypt(json_bytes).decode("utf-8")
    
    @classmethod
    def reset(cls) -> None:
        """Reset singleton (для тестов)"""
        cls._instance = None
        cls._fernet = None


def get_crypto_service() -> CryptoService:
    """Get CryptoService singleton"""
    return CryptoService()
