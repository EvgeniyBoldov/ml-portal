from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.collection_resolver import CollectionResolver
from app.agents.derived_semantics import DerivedSemanticProfile
from app.models.tool_instance import ToolInstance
from app.services.collection_binding import resolve_collection_runtime_domain
from app.services.tool_instance_service import ToolInstanceService


@dataclass(slots=True)
class AllowedDataInstance:
    instance: ToolInstance
    provider: Optional[ToolInstance]
    profile: Optional[DerivedSemanticProfile]
    readiness_reason: str
    runtime_domain: str


class RuntimeDataInstanceResolver:
    """Resolve runtime-ready data instances with providers and semantic profiles."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        instance_service: ToolInstanceService,
        collection_resolver: CollectionResolver,
    ) -> None:
        self.session = session
        self.instance_service = instance_service
        self.collection_resolver = collection_resolver

    async def resolve(self) -> List[AllowedDataInstance]:
        stmt = select(ToolInstance).where(
            ToolInstance.connector_type == "data",
            ToolInstance.is_active.is_(True),
        )
        result = await self.session.execute(stmt)
        instances = result.scalars().all()

        resolved: List[AllowedDataInstance] = []
        for instance in instances:
            runtime_domain = resolve_collection_runtime_domain(
                instance.config,
                fallback_domain=instance.domain,
            )
            is_ready, readiness_reason, _ = await self.instance_service.evaluate_instance_readiness(
                instance
            )
            if not is_ready:
                resolved.append(
                    AllowedDataInstance(
                        instance=instance,
                        provider=None,
                        profile=None,
                        readiness_reason=readiness_reason,
                        runtime_domain=runtime_domain,
                    )
                )
                continue

            profile = await self._load_active_semantic_profile(instance)
            provider = await self._load_provider_instance(instance)

            if provider is not None:
                provider_ready, provider_reason = await self._is_provider_runtime_ready(provider)
                if not provider_ready:
                    resolved.append(
                        AllowedDataInstance(
                            instance=instance,
                            provider=None,
                            profile=None,
                            readiness_reason=f"provider_{provider_reason}",
                            runtime_domain=runtime_domain,
                        )
                    )
                    continue

            resolved.append(
                AllowedDataInstance(
                    instance=instance,
                    provider=provider,
                    profile=profile,
                    readiness_reason=readiness_reason,
                    runtime_domain=runtime_domain,
                )
            )
        return resolved

    async def _load_active_semantic_profile(
        self,
        instance: ToolInstance,
    ) -> Optional[DerivedSemanticProfile]:
        if instance.is_data:
            return await self.collection_resolver.resolve_for_instance(instance)
        return None

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
