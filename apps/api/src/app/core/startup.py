"""
Application startup tasks.

All one-time initialization that runs during lifespan (after DB is ready):
  1. ensure_default_admin   — create default admin user + tenant if absent
  2. register_embedding_models — load enabled models into EmbeddingServiceFactory
  3. sync_tool_catalog       — sync ToolRegistry → tools table
  4. sync_tool_backend_releases — sync versioned registry → backend_releases table
  5. rescan_local_instances  — reconcile local ToolInstances (RAG, collections)
  6. validate_connectors     — validate connector subtype/config contracts (fail-fast)

Each task is isolated: failure is logged but does NOT abort startup.
"""
from __future__ import annotations

import os
from typing import Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.logging import get_logger

logger = get_logger(__name__)


async def ensure_default_admin(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """Create default admin user and default tenant if they do not exist."""
    try:
        from app.models.user import Users
        from app.models.tenant import Tenants, UserTenants
        from app.core.security import hash_password
        from sqlalchemy import select
        import uuid as _uuid

        admin_login = os.getenv("DEFAULT_ADMIN_LOGIN", "admin")
        admin_password = os.getenv("DEFAULT_ADMIN_PASSWORD", "admin123")
        admin_email = os.getenv("DEFAULT_ADMIN_EMAIL", "admin@example.com")

        async with session_factory() as session:
            tenant_result = await session.execute(
                select(Tenants).where(Tenants.name == "default")
            )
            default_tenant = tenant_result.scalar_one_or_none()

            if not default_tenant:
                default_tenant = Tenants(
                    id=_uuid.uuid4(),
                    name="default",
                    description="Default tenant",
                    is_active=True,
                )
                session.add(default_tenant)
                await session.flush()
                logger.info("Created default tenant")

            result = await session.execute(
                select(Users).where(Users.login == admin_login)
            )
            admin = result.scalar_one_or_none()

            if not admin:
                admin = Users(
                    id=_uuid.uuid4(),
                    login=admin_login,
                    email=admin_email,
                    password_hash=hash_password(admin_password),
                    role="admin",
                    is_active=True,
                )
                session.add(admin)
                await session.flush()
                logger.info(f"Created default admin user: {admin_login}")
            else:
                updated = False
                if admin.role != "admin":
                    admin.role = "admin"
                    updated = True
                if not admin.is_active:
                    admin.is_active = True
                    updated = True
                if updated:
                    await session.flush()
                    logger.info(f"Normalized role for default admin user: {admin_login}")

            link_result = await session.execute(
                select(UserTenants).where(
                    UserTenants.user_id == admin.id,
                    UserTenants.tenant_id == default_tenant.id,
                )
            )
            if not link_result.scalar_one_or_none():
                session.add(
                    UserTenants(
                        id=_uuid.uuid4(),
                        user_id=admin.id,
                        tenant_id=default_tenant.id,
                        is_default=True,
                    )
                )
                logger.info("Linked admin user to default tenant")

            await session.commit()
            logger.info(f"Admin user '{admin_login}' ready with tenant '{default_tenant.name}'")
    except Exception as exc:
        logger.error(f"Failed to create default admin: {exc}")


async def register_embedding_models(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """Load enabled embedding models from DB into EmbeddingServiceFactory."""
    try:
        from app.models.model_registry import Model, ModelType
        from app.adapters.embeddings import EmbeddingServiceFactory, ModelConfig
        from sqlalchemy import select

        async with session_factory() as session:
            result = await session.execute(
                select(Model).where(
                    (Model.type == ModelType.EMBEDDING) & (Model.enabled == True)
                )
            )
            models = result.scalars().all()

            for model in models:
                base_url = model.base_url or ""
                if not base_url and model.instance:
                    base_url = model.instance.url or ""
                if not base_url and model.extra_config and model.extra_config.get("base_url"):
                    base_url = model.extra_config["base_url"]

                api_key = None
                if model.instance_id:
                    try:
                        from app.services.credential_service import CredentialService

                        decrypted = await CredentialService(session).resolve_credentials(
                            instance_id=model.instance_id,
                            strategy="PLATFORM_FIRST",
                        )
                        if decrypted:
                            if decrypted.auth_type == "api_key":
                                api_key = decrypted.payload.get("api_key")
                            elif decrypted.auth_type == "token":
                                api_key = decrypted.payload.get("token")
                    except Exception as exc:
                        logger.warning(f"Failed to resolve credentials for {model.alias}: {exc}")

                if not api_key and model.instance and model.instance.config:
                    api_key = model.instance.config.get("api_key")
                    if not api_key:
                        ref = model.instance.config.get("api_key_ref")
                        if ref:
                            api_key = os.getenv(ref)

                dimensions = None
                if model.extra_config and "vector_dim" in model.extra_config:
                    dimensions = model.extra_config["vector_dim"]

                EmbeddingServiceFactory.register_model(
                    ModelConfig(
                        alias=model.alias,
                        provider=model.provider or "",
                        provider_model_name=model.provider_model_name,
                        base_url=base_url,
                        api_key=api_key,
                        dimensions=dimensions,
                        extra_config=model.extra_config,
                        connector=getattr(model, "connector", None) or "",
                    )
                )
                logger.info(f"Registered embedding model: {model.alias}")

            logger.info(f"Registered {len(models)} embedding models")
    except Exception as exc:
        logger.error(f"Failed to register embedding models: {exc}")


async def sync_tool_catalog(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """Sync runtime ToolRegistry entries into the tools table."""
    try:
        from app.agents.registry import ToolRegistry
        from app.services.tool_catalog_sync_service import ToolCatalogSyncService

        ToolRegistry._ensure_initialized()

        async with session_factory() as session:
            stats = await ToolCatalogSyncService(session).sync_tools()
            await session.commit()
            logger.info(f"Tool catalog sync: {stats}")
    except Exception as exc:
        logger.error(f"Failed to sync tool catalog: {exc}")


async def sync_tool_backend_releases(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """Sync versioned registry tools into backend_releases table."""
    try:
        from app.services.tool_backend_release_sync_service import ToolBackendReleaseSyncService

        async with session_factory() as session:
            service = ToolBackendReleaseSyncService(
                session,
                worker_build_id=os.getenv("WORKER_BUILD_ID"),
            )
            stats = await service.sync_backend_releases()
            await session.commit()
            logger.info(f"Tool backend release sync: {stats}")
    except Exception as exc:
        logger.error(f"Failed to sync tool backend releases: {exc}")


async def rescan_local_instances(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """Reconcile local ToolInstances (RAG global, collection instances)."""
    try:
        from app.services.tool_instance_service import ToolInstanceService

        async with session_factory() as session:
            result = await ToolInstanceService(session).rescan_local_instances()
            await session.commit()
            logger.info(
                f"Local instance rescan: created={result.created}, "
                f"deleted={result.deleted}, errors={result.errors}"
            )
    except Exception as exc:
        logger.error(f"Failed to rescan local instances: {exc}")


async def seed_default_agents(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """Upsert seed agents (rag-search, data-analyst, …)."""
    try:
        from app.services.agent_seed_service import AgentSeedService

        async with session_factory() as session:
            stats = await AgentSeedService(session).seed_all()
            await session.commit()
            if stats["created"] > 0:
                logger.info(f"Agent seed: {stats}")
    except Exception as exc:
        logger.error(f"Failed to seed agents: {exc}")


async def validate_connectors(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """
    Validate all connectors against subtype templates.
    This task is fail-fast by design and must break startup on mismatch.
    """
    from sqlalchemy import select

    from app.models.tool_instance import ToolInstance
    from app.services.connector_templates import (
        normalize_data_connector_subtype,
        validate_connector_config,
    )

    async with session_factory() as session:
        result = await session.execute(select(ToolInstance).order_by(ToolInstance.slug))
        instances = list(result.scalars().all())

        errors: list[str] = []
        for inst in instances:
            connector_type = str(inst.connector_type or "").strip().lower()
            subtype = str(inst.connector_subtype or "").strip().lower() or None
            if connector_type != "data" and subtype is not None:
                errors.append(
                    f"{inst.slug}: connector_subtype is allowed only for data connectors "
                    f"(got type={connector_type}, subtype={subtype})"
                )
                continue
            try:
                normalized_subtype = normalize_data_connector_subtype(
                    connector_type=connector_type,
                    connector_subtype=subtype,
                    legacy_domain=inst.domain,
                )
                validate_connector_config(
                    connector_type=connector_type,
                    connector_subtype=normalized_subtype,
                    config=inst.config,
                )
            except Exception as exc:
                errors.append(f"{inst.slug}: {exc}")

        if errors:
            raise RuntimeError(
                "Connector template validation failed:\n" + "\n".join(errors)
            )


async def run_all(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """Run all startup tasks in order. Each failure is isolated."""
    tasks: list[tuple[str, Callable]] = [
        ("ensure_default_admin", ensure_default_admin),
        ("register_embedding_models", register_embedding_models),
        ("sync_tool_catalog", sync_tool_catalog),
        ("sync_tool_backend_releases", sync_tool_backend_releases),
        ("rescan_local_instances", rescan_local_instances),
        ("validate_connectors", validate_connectors),
    ]
    for name, task in tasks:
        logger.info(f"[startup] Running {name}...")
        await task(session_factory)
