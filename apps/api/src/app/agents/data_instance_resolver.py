from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from types import SimpleNamespace
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.collection import Collection, CollectionType
from app.models.tool_instance import ToolInstance
from app.core.logging import get_logger
from app.services.tool_instance_service import ToolInstanceService


logger = get_logger(__name__)


@dataclass(slots=True)
class AllowedDataInstance:
    instance: ToolInstance
    provider: Optional[ToolInstance]
    collection: Optional[Collection]
    readiness_reason: str
    runtime_domain: str


class CollectionRuntimeResolver:
    """Resolve an execution source for every active collection.

    Collection is the selection root.  Local collections select their shared
    provider solely from ``collection_type``; ``data_instance_id`` remains a
    persistence compatibility field and is not consulted for that decision.
    Remote collections retain the explicit source -> MCP provider chain.
    """

    def __init__(
        self,
        *,
        session: AsyncSession,
        instance_service: ToolInstanceService,
    ) -> None:
        self.session = session
        self.instance_service = instance_service

    async def resolve(self) -> List[AllowedDataInstance]:
        started = monotonic()
        resolved: List[AllowedDataInstance] = []
        collections = await self._load_active_collections()
        # A local collection type shares one runtime provider.  Resolving it
        # invokes ensure_local_service_instances(), so doing that once per
        # collection turns preflight into repeated writes/lookups and can wait
        # behind a concurrent collection-admin transaction.
        local_service_cache: Dict[str, ToolInstance] = {}
        logger.info(
            "preflight_collection_sources_started",
            extra={"collections_count": len(collections)},
        )
        for collection in collections:
            collection_started = monotonic()
            collection_context = {
                "collection_slug": str(getattr(collection, "slug", "") or ""),
                "collection_type": str(getattr(collection, "collection_type", "") or ""),
            }
            logger.info("preflight_collection_source_started", extra=collection_context)
            instance = await self._resolve_collection_source(
                collection,
                local_service_cache=local_service_cache,
            )
            if instance is None:
                missing_source = SimpleNamespace(
                    slug=f"missing-source-{collection_context['collection_slug']}",
                    domain="",
                )
                resolved.append(
                    AllowedDataInstance(
                        instance=missing_source,
                        provider=None,
                        collection=collection,
                        readiness_reason="missing_source",
                        runtime_domain=self._resolve_runtime_domain(collection, missing_source),
                    )
                )
                logger.warning(
                    "preflight_collection_source_completed",
                    extra={
                        **collection_context,
                        "readiness_reason": "missing_source",
                        "duration_ms": int((monotonic() - collection_started) * 1000),
                    },
                )
                continue
            is_ready, readiness_reason, _ = await self.instance_service.evaluate_instance_readiness(
                instance
            )
            runtime_domain = self._resolve_runtime_domain(collection, instance)

            if not is_ready:
                resolved.append(
                    AllowedDataInstance(
                        instance=instance,
                        provider=None,
                        collection=collection,
                        readiness_reason=readiness_reason,
                        runtime_domain=runtime_domain,
                    )
                )
                logger.info(
                    "preflight_collection_source_completed",
                    extra={
                        **collection_context,
                        "instance_slug": str(getattr(instance, "slug", "") or ""),
                        "readiness_reason": readiness_reason,
                        "duration_ms": int((monotonic() - collection_started) * 1000),
                    },
                )
                continue

            provider = await self._resolve_provider_instance(instance)

            if provider is not None:
                provider_ready, provider_reason = await self._is_provider_runtime_ready(provider)
                if not provider_ready:
                    resolved.append(
                        AllowedDataInstance(
                            instance=instance,
                            provider=None,
                            collection=collection,
                            readiness_reason=f"provider_{provider_reason}",
                            runtime_domain=runtime_domain,
                        )
                    )
                    logger.info(
                        "preflight_collection_source_completed",
                        extra={
                            **collection_context,
                            "instance_slug": str(getattr(instance, "slug", "") or ""),
                            "readiness_reason": f"provider_{provider_reason}",
                            "duration_ms": int((monotonic() - collection_started) * 1000),
                        },
                    )
                    continue

            resolved.append(
                AllowedDataInstance(
                    instance=instance,
                    provider=provider,
                    collection=collection,
                    readiness_reason=readiness_reason,
                    runtime_domain=runtime_domain,
                )
            )
            logger.info(
                "preflight_collection_source_completed",
                extra={
                    **collection_context,
                    "instance_slug": str(getattr(instance, "slug", "") or ""),
                    "provider_slug": str(getattr(provider, "slug", "") or ""),
                    "readiness_reason": readiness_reason,
                    "duration_ms": int((monotonic() - collection_started) * 1000),
                },
            )
        logger.info(
            "preflight_collection_sources_completed",
            extra={
                "collections_count": len(collections),
                "duration_ms": int((monotonic() - started) * 1000),
            },
        )
        return resolved

    async def _load_active_collections(self) -> List[Collection]:
        result = await self.session.execute(
            select(Collection)
            .options(
                selectinload(Collection.schema),
                selectinload(Collection.current_version),
                selectinload(Collection.data_instance),
            )
            .where(
                Collection.is_active.is_(True),
                Collection.lifecycle_status != "deprecated",
            )
            .order_by(Collection.created_at.asc())
        )
        return list(result.scalars().all())

    async def _resolve_collection_source(
        self,
        collection: Collection,
        *,
        local_service_cache: Optional[Dict[str, ToolInstance]] = None,
    ) -> Optional[ToolInstance]:
        collection_type = str(collection.collection_type or "").strip().lower()
        if collection_type in {
            CollectionType.TABLE.value,
            CollectionType.DOCUMENT.value,
            CollectionType.TEMPLATE.value,
        }:
            if local_service_cache is not None and collection_type in local_service_cache:
                return local_service_cache[collection_type]
            instance = await self.instance_service.resolve_local_service_for_collection_type(
                collection_type
            )
            if local_service_cache is not None:
                local_service_cache[collection_type] = instance
            return instance
        return collection.data_instance

    @staticmethod
    def _resolve_runtime_domain(collection: Optional[Collection], instance: ToolInstance) -> str:
        if collection is None:
            return str(instance.domain or "").strip()
        collection_type = str(collection.collection_type or "").strip().lower()
        if collection_type == CollectionType.TABLE.value:
            return "collection.table"
        if collection_type == CollectionType.DOCUMENT.value:
            return "collection.document"
        if collection_type == CollectionType.TEMPLATE.value:
            return "collection.template"
        if collection_type == CollectionType.SQL.value:
            return "collection.sql"
        if collection_type == CollectionType.API.value:
            return "collection.api"
        return str(instance.domain or "").strip()

    async def _resolve_provider_instance(
        self,
        instance: ToolInstance,
    ) -> Optional[ToolInstance]:
        # Standard remote chain: data instance references provider via access_via.
        if not instance.access_via_instance_id:
            # Local/service-backed collections may bind directly to provider-like
            # service instances; keep the same instance as execution provider.
            return instance if not instance.is_data else None
        result = await self.session.execute(
            select(ToolInstance).where(ToolInstance.id == instance.access_via_instance_id)
        )
        return result.scalar_one_or_none()

    async def _is_provider_runtime_ready(self, provider: ToolInstance) -> tuple[bool, str]:
        if not provider.is_active:
            return False, "inactive"

        provider_ready, provider_reason, _ = await self.instance_service.evaluate_instance_readiness(
            provider
        )
        if not provider_ready:
            return False, provider_reason

        health_status = str(getattr(provider, "health_status", "") or "").strip().lower()
        if health_status == "unhealthy":
            return False, "unhealthy"
        return True, "ready"
