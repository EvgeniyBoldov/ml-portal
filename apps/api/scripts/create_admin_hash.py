#!/usr/bin/env python3
"""
Скрипт для создания хеша пароля admin123
"""
import sys
from pathlib import Path

# Добавляем путь к приложению
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.security import hash_password

if __name__ == "__main__":
    password = "admin123"
    hashed = hash_password(password)
    print(f"Password: {password}")
    print(f"Hash: {hashed}")

