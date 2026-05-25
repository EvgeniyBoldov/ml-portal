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
from app.models.system_llm_role import SystemLLMRole, SystemLLMRoleType
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
from app.services.system_llm_role_contracts import build_response_contract
from app.services.execution_limits_service import ExecutionLimitsService, PLATFORM_SCOPE_REF
from app.models.execution_limit import ExecutionLimitScope

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

    seen_tool_ids: set[uuid.UUID] = set()
    seen_slugs: set[str] = set()

    for tool in discovered_tools:
        tool_record = tool_lookup.get(tool.tool_id) if tool.tool_id is not None else None
        tool_id = tool.tool_id
        if tool_id is not None:
            seen_tool_ids.add(tool_id)
        seen_slugs.add(tool.slug)
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

    # Fallback for published tools that are not present in discovered_tools.
    # This keeps sandbox "Available Tools" complete for local/publication-only tools.
    published_tools_result = await db.execute(
        select(Tool)
        .options(selectinload(Tool.releases))
        .where(Tool.current_version_id.isnot(None))
        .order_by(Tool.slug.asc())
    )
    published_tools = published_tools_result.scalars().all()
    for tool_record in published_tools:
        if tool_record.id in seen_tool_ids or tool_record.slug in seen_slugs:
            continue
        versions = [
            SandboxCatalogToolVersion(
                id=release.id,
                version=release.version,
                status=release.status,
            )
            for release in sorted(tool_record.releases, key=lambda item: item.version, reverse=True)
        ]
        domains = _derive_tool_domains(tool_record.slug, list(tool_record.domains or []))
        item = SandboxCatalogToolItem(
            id=tool_record.id,
            tool_id=tool_record.id,
            slug=tool_record.slug,
            name=tool_record.name,
            description=None,
            source="published",
            domains=domains,
            input_schema=None,
            output_schema=None,
            published=True,
            current_version_id=tool_record.current_version_id,
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

    role_rows = await db.execute(
        select(SystemLLMRole).where(
            SystemLLMRole.is_active.is_(True),
            SystemLLMRole.role_type.in_([
                SystemLLMRoleType.PLANNER.value,
                SystemLLMRoleType.SYNTHESIZER.value,
                SystemLLMRoleType.FACT_EXTRACTOR.value,
                SystemLLMRoleType.SUMMARY_COMPACTOR.value,
            ]),
        )
    )
    active_roles = {role.role_type: role for role in role_rows.scalars().all()}

    def _role_snapshot(role_type: str) -> dict:
        role = active_roles.get(role_type)
        if role is None:
            return {}
        return {
            "id": str(role.id),
            "role_type": role.role_type,
            "identity": role.identity,
            "mission": role.mission,
            "rules": role.rules,
            "safety": role.safety,
            "output_requirements": role.output_requirements,
            "model": role.model,
            "temperature": role.temperature,
            "max_tokens": role.max_tokens,
            "timeout_s": role.timeout_s,
            "max_retries": role.max_retries,
            "retry_backoff": role.retry_backoff,
        }

    limits_service = ExecutionLimitsService(db)
    _platform_limits = await limits_service.get_effective(
        scope_type=ExecutionLimitScope.PLATFORM,
        scope_ref=PLATFORM_SCOPE_REF,
    )
    role_limits: dict[str, dict] = {}
    for role_key in ("planner", "synthesizer", "fact_extractor", "summary_compactor"):
        limits = await limits_service.get_effective(
            scope_type=ExecutionLimitScope.ORCHESTRATOR_ROLE,
            scope_ref=role_key,
        )
        role_limits[role_key] = limits.__dict__

    system_routers = [
        SandboxCatalogRouterItem(
            id="planner",
            name="Planner",
            description="Оркестратор планирования и маршрутизации",
            config={**_role_snapshot(SystemLLMRoleType.PLANNER.value), "limits": role_limits.get("planner", {})},
            response_contract=build_response_contract(SystemLLMRoleType.PLANNER),
        ),
        SandboxCatalogRouterItem(
            id="synthesizer",
            name="Synthesizer",
            description="Оркестратор финального ответа",
            config={**_role_snapshot(SystemLLMRoleType.SYNTHESIZER.value), "limits": role_limits.get("synthesizer", {})},
            response_contract=build_response_contract(SystemLLMRoleType.SYNTHESIZER),
        ),
        SandboxCatalogRouterItem(
            id="fact_extractor",
            name="Fact Extractor",
            description="Оркестратор извлечения фактов",
            config={**_role_snapshot(SystemLLMRoleType.FACT_EXTRACTOR.value), "limits": role_limits.get("fact_extractor", {})},
            response_contract=build_response_contract(SystemLLMRoleType.FACT_EXTRACTOR),
        ),
        SandboxCatalogRouterItem(
            id="summary_compactor",
            name="Summary Compactor",
            description="Оркестратор уплотнения summary",
            config={**_role_snapshot(SystemLLMRoleType.SUMMARY_COMPACTOR.value), "limits": role_limits.get("summary_compactor", {})},
            response_contract=build_response_contract(SystemLLMRoleType.SUMMARY_COMPACTOR),
        ),
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
