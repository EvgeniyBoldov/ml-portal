"""Runtime access snapshot service.

Builds a single RBAC/access snapshot shared across runtime stages.
"""
from __future__ import annotations

from typing import Any, Dict
from uuid import UUID

from app.agents.contracts import RuntimeExecutionSnapshot
from app.agents.runtime_rbac_resolver import RuntimeRbacResolver
from app.services.agent_service import AgentService


class RuntimeAccessSnapshotService:
    """Resolve effective permissions and routable agents once per runtime request."""

    def __init__(self, runtime_rbac_resolver: RuntimeRbacResolver) -> None:
        self.runtime_rbac_resolver = runtime_rbac_resolver

    async def build_snapshot(
        self,
        *,
        user_id: UUID,
        tenant_id: UUID,
        runtime_config: Dict[str, Any],
        agent_service: AgentService,
    ) -> RuntimeExecutionSnapshot:
        default_tool_allow = bool((runtime_config or {}).get("default_tool_allow", True))
        default_collection_allow = bool((runtime_config or {}).get("default_collection_allow", True))

        effective_permissions = await self.runtime_rbac_resolver.resolve_effective_permissions(
            user_id=user_id,
            tenant_id=tenant_id,
            default_tool_allow=default_tool_allow,
            default_collection_allow=default_collection_allow,
        )
        raw_routable_agents = await agent_service.list_routable_agents()
        routable_agents, denied = self.runtime_rbac_resolver.filter_agents_by_slug(
            raw_routable_agents,
            effective_permissions=effective_permissions,
            slug_getter=lambda item: getattr(item, "slug", None),
            default_allow=True,
        )
        return RuntimeExecutionSnapshot(
            effective_permissions=effective_permissions,
            routable_agents=routable_agents,
            denied_routable_agents=denied,
        )
