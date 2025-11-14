#!/usr/bin/env python3
"""
Скрипт для добавления тенанта админу
"""
import sys
import os
import asyncio
from pathlib import Path

# Добавляем путь к приложению
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "apps" / "api" / "src" / "app"))

from app.core.db import get_async_session
from app.repositories.users_repo import AsyncUsersRepository
from app.repositories.tenants_repo import AsyncTenantsRepository
import uuid


async def add_tenant_to_admin():
    """Добавляет тенанта админу"""
    admin_login = "admin"
    default_tenant_id = uuid.UUID("fb983a10-c5f8-4840-a9d3-856eea0dc729")
    
    print(f"🔍 Ищем пользователя {admin_login}...")
    
    async for session in get_async_session():
        try:
            users_repo = AsyncUsersRepository(session)
            tenants_repo = AsyncTenantsRepository(session)
            
            # Находим пользователя
            user = await users_repo.get_by_login(admin_login)
            
            if not user:
                print(f"❌ Пользователь {admin_login} не найден")
                return False
            
            print(f"✅ Пользователь {admin_login} найден (ID: {user.id})")
            
            # Проверяем, есть ли уже тенант
            if user.tenant_ids and len(user.tenant_ids) > 0:
                print(f"✅ У пользователя уже есть тенанты: {user.tenant_ids}")
                return True
            
            # Создаем или находим дефолтный тенант
            tenant = await tenants_repo.get_by_id(default_tenant_id)
            
            if not tenant:
                print("🏢 Создаем дефолтный тенант...")
                tenant = await tenants_repo.create(
                    id=default_tenant_id,
                    name="Default Admin Tenant",
                    description="Default tenant for admin user",
                    is_active=True
                )
                print(f"✅ Тенант создан: {tenant.id}")
            else:
                print(f"✅ Тенант уже существует: {tenant.id}")
            
            # Обновляем пользователя с тенантом
            print("🔧 Добавляем тенанта пользователю...")
            user.tenant_ids = [str(default_tenant_id)]
            await session.commit()
            
            print(f"✅ Тенант {default_tenant_id} добавлен админу")
            return True
            
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            await session.rollback()
            return False
        finally:
            await session.close()


async def main():
    """Основная функция"""
    print("🚀 Запуск скрипта добавления тенанта админу...")
    
    success = await add_tenant_to_admin()
    
    if success:
        print("✅ Скрипт выполнен успешно!")
        sys.exit(0)
    else:
        print("❌ Скрипт завершился с ошибкой!")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
