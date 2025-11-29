#!/usr/bin/env python3
"""
Скрипт для создания пользователя admin/admin123 по умолчанию
Используется при запуске контейнеров для обеспечения наличия администратора
"""
import sys
import os
import asyncio
import uuid
import bcrypt
from pathlib import Path
from sqlalchemy import text
from typing import Any, Dict, List, Optional

# Добавляем путь к приложению
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "apps" / "api" / "src" / "app"))

from app.core.db import get_session_factory, lifespan
from app.repositories.users_repo import AsyncUsersRepository
from app.repositories.tenants_repo import AsyncTenantsRepository
from app.services.model_service import ModelService
from app.models.model_registry import ModelType


async def check_default_models(session_factory) -> Dict[str, str]:
    """Проверяет наличие дефолтных моделей (создаются миграцией)"""
    print("🤖 Проверяем наличие моделей...")
    
    async with session_factory() as session:
        service = ModelService(session)
        
        # Check LLM
        llm = await service.get_default_model(ModelType.LLM_CHAT)
        if llm:
            print(f"✅ LLM модель: {llm.alias} ({llm.provider})")
        else:
            print("⚠️  Нет дефолтной LLM модели!")
            
        # Check Embedding
        embed = await service.get_default_model(ModelType.EMBEDDING)
        if embed:
            print(f"✅ Embedding модель: {embed.alias} ({embed.provider})")
        else:
            print("⚠️  Нет дефолтной Embedding модели!")
            
        return {
            "llm_alias": llm.alias if llm else None,
            "embed_alias": embed.alias if embed else None
        }


async def create_default_tenant(session_factory, models_info: Dict[str, str]) -> uuid.UUID:
    """Создает тенант по умолчанию"""
    tenant_name = "admins"
    embed_alias = models_info.get("embed_alias")

    async with session_factory() as session:
        try:
            tenants_repo = AsyncTenantsRepository(session)
            
            # Проверяем, существует ли тенант
            existing_tenant = await tenants_repo.get_by_name(tenant_name)
            
            if existing_tenant:
                print(f"✅ Тенант {tenant_name} уже существует (ID: {existing_tenant.id})")
                should_commit = False
                if embed_alias and existing_tenant.embedding_model_alias != embed_alias:
                    print(f"   🔄 Обновляем embedding_model_alias: {embed_alias}")
                    existing_tenant.embedding_model_alias = embed_alias
                    should_commit = True
                if should_commit:
                    await session.commit()
                return existing_tenant.id
            
            # Создаем тенант
            print(f"🏢 Создаем тенант {tenant_name}...")
            
            tenant = await tenants_repo.create(
                name=tenant_name,
                is_active=True,
                description="Default administrators tenant",
                embedding_model_alias=embed_alias,
                ocr=False,
                layout=False,
            )

            await session.commit()

            print(f"✅ Тенант {tenant_name} создан!")
            print(f"   🆔 ID: {tenant.id}")
            print(f"   🧠 Embedding: {embed_alias}")
            
            return tenant.id
            
        except Exception as e:
            print(f"❌ Ошибка при создании тенанта: {e}")
            await session.rollback()
            raise


async def link_admin_to_tenant(session_factory, admin_user_id: uuid.UUID, tenant_id: uuid.UUID):
    """Связывает admin пользователя с тенантом"""
    async with session_factory() as session:
        try:
            # Проверяем, есть ли уже связь
            result = await session.execute(
                text("SELECT id FROM user_tenants WHERE user_id = :user_id AND tenant_id = :tenant_id"),
                {"user_id": admin_user_id, "tenant_id": tenant_id}
            )
            existing_link = result.fetchone()
            
            if existing_link:
                print(f"✅ Связь admin -> тенант уже существует")
                return
            
            # Создаем связь
            await session.execute(
                text("INSERT INTO user_tenants (id, user_id, tenant_id, is_default) VALUES (:id, :user_id, :tenant_id, :is_default)"),
                {
                    "id": uuid.uuid4(),
                    "user_id": admin_user_id,
                    "tenant_id": tenant_id,
                    "is_default": True
                }
            )
            
            await session.commit()
            print(f"✅ Admin пользователь связан с тенантом")
            
        except Exception as e:
            print(f"❌ Ошибка при связывании пользователя с тенантом: {e}")
            await session.rollback()
            raise


async def create_default_admin():
    """Создает пользователя admin/admin123 если его еще нет"""
    admin_login = os.getenv("DEFAULT_ADMIN_LOGIN", "admin")
    admin_password = os.getenv("DEFAULT_ADMIN_PASSWORD", "admin123")
    admin_email = os.getenv("DEFAULT_ADMIN_EMAIL", "admin@example.com")
    
    print(f"🔍 Проверяем наличие пользователя {admin_login}...")
    
    # Инициализируем приложение (БД и прочее)
    async with lifespan(None):
        session_factory = get_session_factory()
        
        try:
            # 1. Проверяем модели
            models_info = await check_default_models(session_factory)
            
            # 2. Создаем тенант по умолчанию
            tenant_id = await create_default_tenant(session_factory, models_info)
            
            # 3. Создаем или находим admin пользователя
            async with session_factory() as session:
                users_repo = AsyncUsersRepository(session)
                
                # Проверяем существование пользователя
                existing_user = await users_repo.get_by_login(admin_login)
                
                if existing_user:
                    print(f"✅ Пользователь {admin_login} уже существует (ID: {existing_user.id})")
                    admin_user_id = existing_user.id
                    
                    # Проверяем связь с тенантом
                    result = await session.execute(
                        text("SELECT tenant_id FROM user_tenants WHERE user_id = :user_id"),
                        {"user_id": admin_user_id}
                    )
                    existing_tenant_link = result.fetchone()
                    
                    if not existing_tenant_link:
                        print("⚠️  У пользователя нет тенанта, создаем связь...")
                        await link_admin_to_tenant(session_factory, admin_user_id, tenant_id)
                    else:
                        print(f"✅ Пользователь уже связан с тенантом")
                else:
                    # Создаем пользователя admin
                    print(f"👤 Создаем пользователя {admin_login}...")
                    
                    password_hash = bcrypt.hashpw(admin_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
                    
                    user = await users_repo.create(
                        id=uuid.uuid4(),
                        login=admin_login,
                        email=admin_email,
                        password_hash=password_hash,
                        role="admin",
                        is_active=True,
                    )
                    
                    await session.commit()
                    admin_user_id = user.id
                    
                    print(f"✅ Пользователь {admin_login} успешно создан!")
                    print(f"   📧 Email: {admin_email}")
                    print(f"   🔑 Пароль: {admin_password}")
                    print(f"   🆔 ID: {user.id}")
                    print(f"   👑 Роль: admin")
                
                # 4. Связываем admin пользователя с тенантом (если новый)
                if not existing_user:
                    print("🔗 Связываем admin пользователя с тенантом...")
                    await link_admin_to_tenant(session_factory, admin_user_id, tenant_id)
                
                # 5. Инициализация MinIO бакета
                try:
                    from app.adapters.impl.minio import get_minio_client
                    bucket_name = os.getenv("S3_BUCKET_RAG", "rag")
                    import asyncio as _asyncio
                    client = get_minio_client()
                    exists = await _asyncio.to_thread(client.bucket_exists, bucket_name)
                    if not exists:
                        await _asyncio.to_thread(client.make_bucket, bucket_name)
                        print(f"✅ Создан бакет MinIO: {bucket_name}")
                    else:
                        print(f"✅ Бакет MinIO уже существует: {bucket_name}")
                except Exception as e:
                    print(f"❌ Ошибка инициализации MinIO: {e}")
                
                # 6. Инициализация коллекций Qdrant - больше не нужна при старте
                # Коллекции создаются лениво в RAG ingest pipeline
                
                return True
                
        except Exception as e:
            print(f"❌ Ошибка при создании admin пользователя: {e}")
            import traceback
            traceback.print_exc()
            return False


async def main():
    """Основная функция"""
    print("🚀 Запуск скрипта создания пользователя admin...")
    
    success = await create_default_admin()
    
    if success:
        print("✅ Скрипт выполнен успешно!")
        sys.exit(0)
    else:
        print("❌ Скрипт завершился с ошибкой!")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
