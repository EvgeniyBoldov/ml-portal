"""Sandbox catalog — components tree for sidebar."""
import uuid
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, require_admin
from app.core.security import UserCtx
from app.models.agent import Agent
from app.models.discovered_tool import DiscoveredTool
from app.models.tool import Tool
from app.schemas.sandbox import (
    SandboxCatalogAgentItem,
    SandboxCatalogAgentVersion,
    SandboxCatalogDomainGroup,
    SandboxCatalogResponse,
    SandboxCatalogRouterItem,
    SandboxCatalogToolItem,
    SandboxCatalogToolVersion,
)
from app.services.sandbox_override_resolver import SandboxOverrideResolver
from app.services.sandbox_service import SandboxService

from .helpers import tenant_uuid

router = APIRouter()


def _derive_tool_domains(slug: str, registry_domains: list[str]) -> list[str]:
    domains = [domain for domain in registry_domains if domain]
    if domains:
        return domains

    parts = [part for part in slug.split(".") if part]
    if not parts:
        return ["other"]
    if len(parts) >= 2 and parts[0] == "collection" and parts[1] in {"document", "table"}:
        return [f"{parts[0]}.{parts[1]}"]
    return [parts[0]]


@router.get("/sessions/{session_id}/catalog", response_model=SandboxCatalogResponse)
async def get_sandbox_catalog(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(db_session),
    user: UserCtx = Depends(require_admin),
):
    """Get sidebar catalog: tools + agents + system routers + resolver blueprints."""
    svc = SandboxService(db)
    session = await svc.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.tenant_id != await tenant_uuid(db, user):
        raise HTTPException(status_code=404, detail="Session not found")

    tool_items: list[SandboxCatalogToolItem] = []
    grouped_tools: dict[str, list[SandboxCatalogToolItem]] = defaultdict(list)

    tool_rows = await db.execute(
        select(DiscoveredTool)
        .where(DiscoveredTool.is_active.is_(True))
        .order_by(DiscoveredTool.slug.asc(), DiscoveredTool.provider_instance_id.asc().nullsfirst())
    )
    discovered_tools = tool_rows.scalars().all()

    tool_lookup_result = await db.execute(
        select(Tool)
        .options(selectinload(Tool.releases))
        .where(Tool.id.in_([item.tool_id for item in discovered_tools if item.tool_id is not None]))
    )
    tool_lookup = {tool.id: tool for tool in tool_lookup_result.scalars().all()}

    for tool in discovered_tools:
        tool_record = tool_lookup.get(tool.tool_id) if tool.tool_id is not None else None
        tool_id = tool.tool_id
        current_version_id = tool_record.current_version_id if tool_record is not None else None
        versions = []
        if tool_record is not None:
            versions = [
                SandboxCatalogToolVersion(
                    id=release.id,
                    version=release.version,
                    status=release.status,
                )
                for release in sorted(tool_record.releases, key=lambda item: item.version, reverse=True)
            ]
        domains = _derive_tool_domains(tool.slug, list(tool.domains or []))
        item = SandboxCatalogToolItem(
            id=tool.id,
            tool_id=tool_id,
            slug=tool.slug,
            name=tool.name,
            description=tool.description,
            source=tool.source,
            domains=domains,
            input_schema=tool.input_schema,
            output_schema=tool.output_schema,
            published=bool(current_version_id),
            current_version_id=current_version_id,
            versions=versions,
        )
        tool_items.append(item)
        grouped_tools[domains[0]].append(item)

    agents_result = await db.execute(
        select(Agent)
        .options(selectinload(Agent.versions))
        .order_by(Agent.slug.asc())
    )
    agents = agents_result.scalars().unique().all()
    agent_items = [
        SandboxCatalogAgentItem(
            id=a.id,
            slug=a.slug,
            name=a.name,
            current_version_id=a.current_version_id,
            versions=[
                SandboxCatalogAgentVersion(
                    id=v.id,
                    version=v.version,
                    status=v.status,
                )
                for v in sorted(a.versions, key=lambda av: av.version, reverse=True)
            ],
        )
        for a in agents
    ]

    system_routers = [
        SandboxCatalogRouterItem(id="default", name="Default Router", description="Стандартный роутер"),
        SandboxCatalogRouterItem(id="planner", name="Planner Router", description="Маршрутизация через planner"),
    ]

    domain_groups = [
        SandboxCatalogDomainGroup(domain=domain, tools=sorted(items, key=lambda item: item.name.lower()))
        for domain, items in sorted(grouped_tools.items(), key=lambda pair: pair[0])
    ]

    return SandboxCatalogResponse(
        tools=tool_items,
        domain_groups=domain_groups,
        agents=agent_items,
        system_routers=system_routers,
        resolver_blueprints=SandboxOverrideResolver.describe_blueprints(),
    )
