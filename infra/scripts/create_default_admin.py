#!/usr/bin/env python3
"""
Скрипт для создания пользователя admin/admin123 по умолчанию
Используется при запуске контейнеров для обеспечения наличия администратора
"""
import sys
import os
import asyncio
from pathlib import Path

# Добавляем путь к приложению
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "apps" / "api" / "src" / "app"))

from app.core.db import get_session_factory
from app.repositories.users_repo import AsyncUsersRepository
from app.repositories.tenants_repo import AsyncTenantsRepository
from app.repositories.model_registry_repo import AsyncModelRegistryRepository
import bcrypt
import uuid
import os
from pathlib import Path
from datetime import datetime
from sqlalchemy import text
from typing import Dict


async def ensure_models_exist(session_factory) -> list[str]:
    """Проверяет наличие моделей в файловой системе и создает записи в БД"""
    models_dir = Path("/app/models_llm")
    available_models = []
    
    # Список ожидаемых моделей
    expected_models = [
        {
            "model": "all-MiniLM-L6-v2",
            "version": "latest",
            "modality": "text",
            "vector_dim": 384,
            "path": str(models_dir / "sentence-transformers--all-MiniLM-L6-v2"),
            "default_for_new": True
        },
        {
            "model": "multilingual-e5-small", 
            "version": "latest",
            "modality": "text",
            "vector_dim": 384,
            "path": str(models_dir / "multilingual-e5-small"),
            "default_for_new": True
        },
        {
            "model": "bge-large-en",
            "version": "latest", 
            "modality": "text",
            "vector_dim": 1024,
            "path": str(models_dir / "bge-large-en"),
            "default_for_new": False
        }
    ]
    
    async with session_factory() as session:
        try:
            model_repo = AsyncModelRegistryRepository(session)
            
            for model_info in expected_models:
                model_path = Path(model_info["path"])
                
                # Проверяем, существует ли модель в файловой системе
                if model_path.exists() and model_path.is_dir():
                    print(f"✅ Найдена модель: {model_info['model']}")
                    
                    # Проверяем, есть ли уже запись в БД
                    existing_model = await model_repo.get_by_model(model_info["model"])
                    
                    if not existing_model:
                        # Создаем запись в БД
                        await model_repo.create({
                            "id": uuid.uuid4(),
                            "model": model_info["model"],
                            "version": model_info["version"],
                            "modality": model_info["modality"],
                            "state": "active",
                            "vector_dim": model_info["vector_dim"],
                            "path": model_info["path"],
                            "default_for_new": model_info["default_for_new"],
                            "notes": f"Auto-created from {model_path}"
                        })
                        print(f"   📝 Создана запись в БД: {model_info['model']}")
                    else:
                        print(f"   📝 Запись уже существует: {model_info['model']}")
                    
                    available_models.append(model_info["model"])
                else:
                    print(f"⚠️  Модель не найдена: {model_info['model']} (путь: {model_path})")
            
            await session.commit()
            return available_models
            
        except Exception as e:
            print(f"❌ Ошибка при проверке моделей: {e}")
            await session.rollback()
            return []


async def create_default_tenant(session_factory, available_models: list[str]) -> uuid.UUID:
    """Создает тенант по умолчанию с доступными моделями"""
    tenant_name = "admins"
    
    async with session_factory() as session:
        try:
            tenants_repo = AsyncTenantsRepository(session)
            
            # Проверяем, существует ли тенант
            existing_tenant = await tenants_repo.get_by_name(tenant_name)
            
            if existing_tenant:
                print(f"✅ Тенант {tenant_name} уже существует (ID: {existing_tenant.id})")
                return existing_tenant.id
            
            # Создаем тенант
            print(f"🏢 Создаем тенант {tenant_name}...")
            
            # Берем первые 2 модели для embed_models (максимум 2)
            embed_models = available_models[:2] if available_models else []
            
            # Создаем тенант через сырой SQL
            tenant_id = uuid.uuid4()
            await session.execute(
                text("""
                    INSERT INTO tenants (id, name, is_active, embed_models, rerank_model, ocr, layout, created_at, updated_at)
                    VALUES (:id, :name, :is_active, :embed_models, :rerank_model, :ocr, :layout, :created_at, :updated_at)
                """),
                {
                    "id": tenant_id,
                    "name": tenant_name,
                    "is_active": True,
                    "embed_models": embed_models,
                    "rerank_model": None,
                    "ocr": False,
                    "layout": False,
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }
            )
            
            # Получаем созданный тенант
            result = await session.execute(
                text("SELECT id, name FROM tenants WHERE id = :id"),
                {"id": tenant_id}
            )
            tenant_row = result.fetchone()
            tenant = type('Tenant', (), {'id': tenant_row[0], 'name': tenant_row[1]})()
            
            await session.commit()
            
            print(f"✅ Тенант {tenant_name} создан!")
            print(f"   🆔 ID: {tenant.id}")
            print(f"   🤖 Embed модели: {embed_models}")
            
            return tenant.id
            
        except Exception as e:
            print(f"❌ Ошибка при создании тенанта: {e}")
            await session.rollback()
            raise


async def link_admin_to_tenant(session_factory, admin_user_id: uuid.UUID, tenant_id: uuid.UUID):
    """Связывает admin пользователя с тенантом"""
    from sqlalchemy import text
    
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
    
    # Инициализируем базу данных
    from app.core.db import lifespan
    async with lifespan(None):
        session_factory = get_session_factory()
        
        try:
            # 1. Проверяем и создаем модели в БД
            print("🤖 Проверяем наличие моделей...")
            available_models = await ensure_models_exist(session_factory)
            
            # 2. Создаем тенант по умолчанию
            print("🏢 Создаем тенант по умолчанию...")
            tenant_id = await create_default_tenant(session_factory, available_models)
            
            # 3. Создаем или находим admin пользователя
            from sqlalchemy import text
            
            async with session_factory() as session:
                users_repo = AsyncUsersRepository(session)
                
                # Проверяем, существует ли пользователь
                existing_user = await users_repo.get_by_login(admin_login)
                
                if existing_user:
                    print(f"✅ Пользователь {admin_login} уже существует (ID: {existing_user.id})")
                    admin_user_id = existing_user.id
                    
                    # Проверяем, есть ли у пользователя тенант
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
                
                # 4. Связываем admin пользователя с тенантом
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
                
                # 6. Инициализация коллекций Qdrant для доступных моделей
                try:
                    from app.repositories.model_registry_repo import AsyncModelRegistryRepository
                    from app.adapters.impl.qdrant import QdrantVectorStore
                    async with session_factory() as _s2:
                        mr = AsyncModelRegistryRepository(_s2)
                        vector_store = QdrantVectorStore()
                        for model_alias in available_models:
                            m = await mr.get_by_model(model_alias)
                            if m and getattr(m, "vector_dim", None):
                                collection_name = f"{tenant_id}__{model_alias}"
                                await vector_store.ensure_collection(collection_name, int(m.vector_dim))
                                print(f"✅ Qdrant коллекция готова: {collection_name}")
                except Exception as e:
                    print(f"❌ Ошибка инициализации Qdrant: {e}")
                
                return True
                
        except Exception as e:
            print(f"❌ Ошибка при создании admin пользователя: {e}")
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
