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
    """Создает пользователя admin с паролем из ENV"""
    session = SessionLocal()
    try:
        # Проверяем, существует ли уже пользователь admin
        existing_user = session.query(Users).filter(Users.login == "admin").first()
        if existing_user:
            print("Пользователь admin уже существует")
            return
        
        # Получаем пароль из ENV
        admin_password = os.getenv("ADMIN_PASSWORD")
        if not admin_password:
            print("❌ ERROR: ADMIN_PASSWORD environment variable is required!")
            print("   Set ADMIN_PASSWORD to a secure password for the admin user.")
            print("   Example: ADMIN_PASSWORD=mySecurePassword123")
            sys.exit(1)
        
        # Проверяем, что пароль не дефолтный в продакшене
        if admin_password in ["admin123", "admin", "password", "123456"]:
            env = os.getenv("ENVIRONMENT", "development")
            if env == "production":
                print("❌ ERROR: Weak password detected in production!")
                print("   Use a strong password for ADMIN_PASSWORD in production.")
                sys.exit(1)
            else:
                print("⚠️  WARNING: Using weak password in development mode")
        
        # Создаем нового пользователя
        admin_user = Users(
            login="admin",
            password_hash=hash_password(admin_password),
            role="admin",
            is_active=True
        )
        
        session.add(admin_user)
        session.commit()
        print("✅ Пользователь admin создан успешно")
        
    except Exception as e:
        print(f"❌ Ошибка при создании пользователя admin: {e}")
        session.rollback()
        sys.exit(1)
    finally:
        session.close()

if __name__ == "__main__":
    create_admin_user()