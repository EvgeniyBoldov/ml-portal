from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.collection import Collection, CollectionType
from app.models.tool_instance import ToolInstance
from app.services.tool_instance_service import ToolInstanceService


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
        resolved: List[AllowedDataInstance] = []
        for collection in await self._load_active_collections():
            instance = await self._resolve_collection_source(collection)
            if instance is None:
                missing_source = SimpleNamespace(slug=f"missing-source-{collection.slug}", domain="")
                resolved.append(
                    AllowedDataInstance(
                        instance=missing_source,
                        provider=None,
                        collection=collection,
                        readiness_reason="missing_source",
                        runtime_domain=self._resolve_runtime_domain(collection, missing_source),
                    )
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

    async def _resolve_collection_source(self, collection: Collection) -> Optional[ToolInstance]:
        collection_type = str(collection.collection_type or "").strip().lower()
        if collection_type in {
            CollectionType.TABLE.value,
            CollectionType.DOCUMENT.value,
            CollectionType.TEMPLATE.value,
        }:
            return await self.instance_service.resolve_local_service_for_collection_type(collection_type)
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
