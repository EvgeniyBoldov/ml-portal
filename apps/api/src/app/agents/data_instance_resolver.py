from __future__ import annotations

from dataclasses import dataclass
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


class RuntimeDataInstanceResolver:
    """Resolve runtime-ready data instances with providers and bound collections."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        instance_service: ToolInstanceService,
    ) -> None:
        self.session = session
        self.instance_service = instance_service

    async def resolve(self) -> List[AllowedDataInstance]:
        stmt = select(ToolInstance).where(
            ToolInstance.connector_type == "data",
            ToolInstance.is_active.is_(True),
        )
        result = await self.session.execute(stmt)
        instances = result.scalars().all()

        resolved: List[AllowedDataInstance] = []
        for instance in instances:
            is_ready, readiness_reason, _ = await self.instance_service.evaluate_instance_readiness(
                instance
            )
            collection = await self._load_bound_collection(instance)
            runtime_domain = self._resolve_runtime_domain(collection, instance)
            if not is_ready:
                resolved.append(
                    AllowedDataInstance(
                        instance=instance,
                        provider=None,
                        collection=None,
                        readiness_reason=readiness_reason,
                        runtime_domain=runtime_domain,
                    )
                )
                continue

            provider = await self._load_provider_instance(instance)

            if provider is not None:
                provider_ready, provider_reason = await self._is_provider_runtime_ready(provider)
                if not provider_ready:
                    resolved.append(
                        AllowedDataInstance(
                            instance=instance,
                            provider=None,
                            collection=None,
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

    async def _load_bound_collection(
        self,
        instance: ToolInstance,
    ) -> Optional[Collection]:
        if not instance.is_data:
            return None
        result = await self.session.execute(
            select(Collection)
            .options(
                selectinload(Collection.schema),
                selectinload(Collection.current_version),
            )
            .where(Collection.data_instance_id == instance.id)
            .order_by(Collection.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _resolve_runtime_domain(collection: Optional[Collection], instance: ToolInstance) -> str:
        if collection is None:
            return str(instance.domain or "").strip()
        collection_type = str(collection.collection_type or "").strip().lower()
        if collection_type == CollectionType.TABLE.value:
            return "collection.table"
        if collection_type == CollectionType.DOCUMENT.value:
            return "collection.document"
        if collection_type == CollectionType.SQL.value:
            return "collection.sql"
        if collection_type == CollectionType.API.value:
            return "collection.api"
        return str(instance.domain or "").strip()

    async def _load_provider_instance(
        self,
        instance: ToolInstance,
    ) -> Optional[ToolInstance]:
        if not instance.access_via_instance_id:
            return None
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
