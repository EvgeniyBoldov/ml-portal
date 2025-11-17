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
from typing import Any, Dict, List, Optional


async def ensure_models_exist(session_factory) -> Dict[str, Any]:
    """Проверяет наличие моделей в файловой системе и создает записи в БД"""
    models_dir = Path("/app/models_llm")
    expected_models: List[Dict[str, Any]] = [
        {
            "model": "all-MiniLM-L6-v2",
            "version": "latest",
            "modality": "text",
            "vector_dim": 384,
            "path": str(models_dir / "sentence-transformers--all-MiniLM-L6-v2"),
            "is_global": True,
        },
        {
            "model": "multilingual-e5-small",
            "version": "latest",
            "modality": "text",
            "vector_dim": 384,
            "path": str(models_dir / "multilingual-e5-small"),
            "is_global": False,
        },
        {
            "model": "bge-large-en",
            "version": "latest",
            "modality": "text",
            "vector_dim": 1024,
            "path": str(models_dir / "bge-large-en"),
            "is_global": False,
        },
    ]

    available_text_models: List[str] = []
    available_rerank_models: List[str] = []
    global_text_model: Optional[str] = None
    global_rerank_model: Optional[str] = None

    async with session_factory() as session:
        try:
            model_repo = AsyncModelRegistryRepository(session)

            for model_info in expected_models:
                model_path = Path(model_info["path"])

                if not model_path.exists() or not model_path.is_dir():
                    print(f"⚠️  Модель не найдена: {model_info['model']} (путь: {model_path})")
                    continue

                print(f"✅ Найдена модель: {model_info['model']}")
                existing_model = await model_repo.get_by_model(model_info["model"])

                payload = {
                    "version": model_info["version"],
                    "modality": model_info["modality"],
                    "state": "active",
                    "vector_dim": model_info.get("vector_dim"),
                    "path": model_info["path"],
                    "is_global": model_info.get("is_global", False),
                    "notes": f"Auto-created from {model_path}",
                }

                if existing_model:
                    update_data = {
                        key: value
                        for key, value in payload.items()
                        if getattr(existing_model, key) != value
                    }

                    if update_data:
                        await model_repo.update(existing_model.id, update_data)
                        print(f"   🔄 Обновлена запись в БД: {model_info['model']}")
                    else:
                        print(f"   📝 Запись уже актуальна: {model_info['model']}")
                else:
                    create_payload = {
                        "id": uuid.uuid4(),
                        "model": model_info["model"],
                        **payload,
                    }
                    await model_repo.create(create_payload)
                    print(f"   📝 Создана запись в БД: {model_info['model']}")

                if model_info["modality"] == "text":
                    available_text_models.append(model_info["model"])
                    if model_info.get("is_global"):
                        global_text_model = model_info["model"]
                elif model_info["modality"] == "rerank":
                    available_rerank_models.append(model_info["model"])
                    if model_info.get("is_global"):
                        global_rerank_model = model_info["model"]

            await session.commit()
            return {
                "available_text_models": available_text_models or None,
                "global_text_model": global_text_model,
                "available_rerank_models": available_rerank_models or None,
                "global_rerank_model": global_rerank_model,
            }

        except Exception as e:
            print(f"❌ Ошибка при проверке моделей: {e}")
            await session.rollback()
            return {
                "available_text_models": None,
                "global_text_model": None,
                "available_rerank_models": None,
                "global_rerank_model": None,
            }


async def create_default_tenant(session_factory, models_info: Dict[str, Any]) -> uuid.UUID:
    """Создает тенант по умолчанию с привязкой к доступным моделям"""
    tenant_name = "admins"
    global_text_model = models_info.get("global_text_model")
    text_models = models_info.get("available_text_models") or []
    extra_embed_model = next((m for m in text_models if m != global_text_model), None)

    async with session_factory() as session:
        try:
            tenants_repo = AsyncTenantsRepository(session)
            
            # Проверяем, существует ли тенант
            existing_tenant = await tenants_repo.get_by_name(tenant_name)
            
            if existing_tenant:
                print(f"✅ Тенант {tenant_name} уже существует (ID: {existing_tenant.id})")
                should_commit = False
                if extra_embed_model and existing_tenant.extra_embed_model != extra_embed_model:
                    print("   🔄 Обновляем extra_embed_model для существующего тенанта")
                    existing_tenant.extra_embed_model = extra_embed_model
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
                extra_embed_model=extra_embed_model,
                ocr=False,
                layout=False,
            )

            await session.commit()

            print(f"✅ Тенант {tenant_name} создан!")
            print(f"   🆔 ID: {tenant.id}")
            print(f"   🤖 Global embed: {global_text_model}")
            print(f"   ➕ Extra embed: {extra_embed_model}")
            
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
            models_info = await ensure_models_exist(session_factory)
            available_text_models = models_info.get("available_text_models") or []
            global_text_model = models_info.get("global_text_model")
            if not global_text_model:
                print("⚠️  Не удалось определить глобальную текстовую модель. Проверьте файлы моделей.")
            
            # 2. Создаем тенант по умолчанию
            print("🏢 Создаем тенант по умолчанию...")
            tenant_id = await create_default_tenant(session_factory, models_info)
            
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
                        target_models = sorted(
                            set(available_text_models + ([global_text_model] if global_text_model else []))
                        )
                        for model_alias in target_models:
                            if not model_alias:
                                continue
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
