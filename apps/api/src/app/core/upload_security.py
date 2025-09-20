"""
Модуль для проверки безопасности загружаемых файлов
"""
import re
from typing import Dict, Any, Optional, AsyncIterable
from fastapi import UploadFile
from pydantic import BaseModel

ALLOWED_EXT = {".pdf", ".txt", ".md", ".png", ".jpg", ".jpeg", ".docx", ".csv", ".xlsx"}
MAX_SIZE = 10 * 1024 * 1024  # 10MB
CHUNK = 64 * 1024

_FN_FORBID_PAT = re.compile(r"(^$)|(^\.)|(\.\.)|[\\/]|[\x00-\x1f]")

class UploadSecurityConfig(BaseModel):
    """Конфигурация для проверки безопасности файлов"""
    max_file_size: int = MAX_SIZE
    allowed_extensions: set = ALLOWED_EXT

def _iter_chunks(file, chunk_size: int = CHUNK) -> bytes:
    """Синхронное чтение файла по частям"""
    while True:
        chunk = file.read(chunk_size)
        if not chunk:
            break
        yield chunk

def _ext_of(name: str) -> str:
    from pathlib import Path
    return Path(name).suffix.lower()

def _suspicious_name(name: str) -> bool:
    return bool(_FN_FORBID_PAT.search(name))

def validate_file(filename: str, fileobj) -> bool:
    """Синхронная валидация файла"""
    from pathlib import Path
    
    # Базовая проверка имени и расширения
    if _suspicious_name(filename):
        raise ValueError("forbidden: suspicious filename")
    ext = Path(filename).suffix.lower()
    if not ext:
        raise ValueError("unsupported: no extension")
    if ext not in ALLOWED_EXT:
        raise ValueError("forbidden: extension not allowed")
    
    size = 0
    while True:
        chunk = fileobj.read(CHUNK)
        if not chunk:
            break
        size += len(chunk)
        if size > MAX_SIZE:
            raise ValueError("size_exceeded")
    
    return True

async def async_validate_file(file: UploadFile) -> bool:
    """
    Validate uploaded file for security (async version) - wrapper for backward compatibility
    """
    # Синхронная валидация для совместимости
    validate_file(file.filename, file.file)
    return True

class UploadSecurityValidator:
    """Валидатор безопасности загружаемых файлов"""
    
    def __init__(self, config: Optional[UploadSecurityConfig] = None):
        self.config = config or UploadSecurityConfig()
    
    def validate_file(self, filename: str, fileobj) -> bool:
        """
        Валидирует загружаемый файл на безопасность (синхронная версия)
        
        Args:
            filename: Имя файла
            fileobj: Объект файла
            
        Returns:
            True если файл валиден
            
        Raises:
            ValueError: Если файл не прошел валидацию
        """
        return validate_file(filename, fileobj)