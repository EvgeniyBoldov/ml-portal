from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Optional, Set
from uuid import UUID

from dataclasses import dataclass, field

from app.agents.contracts import RuntimeExecutionSnapshot
from app.services.agent_service import AgentService
from app.services.runtime_access_snapshot_service import RuntimeAccessSnapshotService


@dataclass
class OrchestrationContext:
    request_text: str
    user_id: str
    tenant_id: str
    snapshot: RuntimeExecutionSnapshot
    requested_agent_slug: Optional[str] = None
    default_agent_slug: Optional[str] = None
    effective_agent_slug: Optional[str] = None
    platform_config: Dict[str, Any] = field(default_factory=dict)


class OrchestrationContextBuilder:
    """Build a single orchestration context snapshot for runtime pipeline."""

    def __init__(self, runtime_access_snapshot_service: RuntimeAccessSnapshotService) -> None:
        self.runtime_access_snapshot_service = runtime_access_snapshot_service

    async def build(
        self,
        *,
        request_text: str,
        user_id: UUID,
        tenant_id: UUID,
        requested_agent_slug: Optional[str],
        default_slugs: Set[Optional[str]],
        sandbox_overrides: Dict[str, Any],
        agent_service: AgentService,
        load_platform_config: Callable[[], Awaitable[Dict[str, Any]]],
    ) -> OrchestrationContext:
        platform_config = await load_platform_config()
        platform_ov = sandbox_overrides.get("platform", {})
        if platform_ov:
            platform_config.update(platform_ov)

        default_agent_slug = await agent_service.get_default_agent_slug(tenant_id)
        effective_agent_slug = requested_agent_slug
        if effective_agent_slug in default_slugs:
            effective_agent_slug = default_agent_slug

        snapshot = await self.runtime_access_snapshot_service.build_snapshot(
            user_id=user_id,
            tenant_id=tenant_id,
            runtime_config=platform_config,
            agent_service=agent_service,
        )

        return OrchestrationContext(
            request_text=request_text,
            user_id=str(user_id),
            tenant_id=str(tenant_id),
            requested_agent_slug=requested_agent_slug,
            default_agent_slug=default_agent_slug,
            effective_agent_slug=effective_agent_slug,
            platform_config=platform_config,
            snapshot=snapshot,
        )
