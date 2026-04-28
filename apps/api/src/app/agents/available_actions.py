"""Builder for planner-safe AvailableActions snapshot."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.contracts import AgentAction, AvailableActions, OperationAction, ResolvedOperation
from app.models.agent import Agent
from app.models.agent_version import AgentVersion


def _normalize_risk(value: Optional[str]) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"safe", "write", "destructive"}:
        return normalized
    return "safe"


def _schema_hint(input_schema: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not input_schema:
        return None

    properties = input_schema.get("properties") or {}
    required = set(input_schema.get("required") or [])
    fields: Dict[str, Dict[str, Any]] = {}
    for name, field in properties.items():
        if not isinstance(field, dict):
            continue
        fields[name] = {
            "type": field.get("type", "any"),
            "required": name in required,
        }
    return {"fields": fields} if fields else None


class AvailableActionsBuilder:
    """Build compact planner whitelist from resolved operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def build(
        self,
        *,
        agent: Agent,
        agent_version: Optional[AgentVersion],
        resolved_operations: List[ResolvedOperation],
        routable_agents: Optional[List[Agent]] = None,
    ) -> AvailableActions:
        agent_actions = [
            AgentAction(
                agent_slug=agent.slug,
                description=agent.description,
                tags=agent.tags or [],
                risk_level=getattr(agent, "risk_level", None),
            )
        ]
        if routable_agents:
            for routable_agent in routable_agents:
                if routable_agent.slug == agent.slug:
                    continue
                agent_actions.append(
                    AgentAction(
                        agent_slug=routable_agent.slug,
                        description=routable_agent.description,
                        tags=routable_agent.tags or [],
                        risk_level=None,
                    )
                )

        operations: List[OperationAction] = []
        for resolved_operation in resolved_operations:
            operations.append(
                OperationAction(
                    operation_slug=resolved_operation.operation_slug,
                    op=resolved_operation.operation,
                    name=resolved_operation.name,
                    data_instance_slug=resolved_operation.data_instance_slug,
                    description=resolved_operation.description,
                    input_schema_hint=_schema_hint(resolved_operation.input_schema),
                    side_effects=resolved_operation.side_effects,
                    risk_level=_normalize_risk(resolved_operation.risk_level),
                    idempotent=resolved_operation.idempotent,
                    requires_confirmation=resolved_operation.requires_confirmation,
                    credential_scope=resolved_operation.credential_scope,
                    resource=resolved_operation.resource,
                    systems=list(
                        dict.fromkeys(
                            [resolved_operation.source, resolved_operation.data_instance_slug]
                            + list(resolved_operation.systems or [])
                        )
                    ),
                )
            )

        operations.sort(key=lambda item: (item.data_instance_slug or "", item.operation_slug, item.op))
        return AvailableActions(agents=agent_actions, operations=operations)
