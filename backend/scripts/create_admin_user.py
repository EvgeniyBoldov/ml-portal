#!/usr/bin/env python3
"""
Скрипт для создания администратора при запуске контейнера
"""
import os
import sys
import asyncio
from pathlib import Path

# Добавляем путь к приложению
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.db import SessionLocal
from app.models.user import Users
from app.core.security import hash_password
from app.core.config import settings

def create_admin_user():
    """Создает пользователя admin с паролем admin123"""
    session = SessionLocal()
    try:
        # Проверяем, существует ли уже пользователь admin
        existing_user = session.query(Users).filter(Users.login == "admin").first()
        if existing_user:
            print("Пользователь admin уже существует")
            return
        
        # Создаем нового пользователя
        admin_user = Users(
            login="admin",
            password_hash=hash_password("admin123"),
            role="admin",
            is_active=True
        )
        
        session.add(admin_user)
        session.commit()
        print("Пользователь admin создан успешно")
        
    except Exception as e:
        print(f"Ошибка при создании пользователя admin: {e}")
        session.rollback()
    finally:
        session.close()

if __name__ == "__main__":
    create_admin_user()