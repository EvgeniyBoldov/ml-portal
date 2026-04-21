"""
Tool Instances Admin API v3

Instance v3 classification axes:
- instance_kind: data | service
- placement: local | remote
- domain: classification label for filtering/UI. Runtime behavior uses explicit bindings/config.
"""
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query, status, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.operation_publication import build_runtime_operation_slug, resolve_publication
from app.agents.mcp_discovery import parse_discovered_operation
from app.api.deps import db_session, require_admin
from app.core.security import UserCtx
from app.models.discovered_tool import DiscoveredTool
from app.models.tool_instance import ToolInstance
from app.services.collection_binding import (
    resolve_collection_context_domain,
    resolve_collection_runtime_domain,
)
from app.services.instance_capabilities import is_mcp_service_instance
from app.services.collection_tool_resolver import CollectionToolResolver
from app.services.tool_discovery_service import ToolDiscoveryService
from app.services.tool_instance_service import ToolInstanceService, _UNSET
from app.schemas.tool_instances import (
    ToolInstanceCreate,
    ToolInstanceUpdate,
    ToolInstanceListItem,
    ToolInstanceResponse,
    ToolInstanceDetailResponse,
    RuntimeOperationListItem,
    HealthCheckResponse,
    InstanceRuntimeOnboardRequest,
    InstanceRuntimeOnboardResponse,
    LinkedDataInstanceRuntimeSummary,
    RescanResponse,
)

router = APIRouter(tags=["tool-instances"])


async def _resolve_provider_instance(db: AsyncSession, instance: ToolInstance) -> Optional[ToolInstance]:
    if not instance.access_via_instance_id:
        return instance
    stmt = select(ToolInstance).where(ToolInstance.id == instance.access_via_instance_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


def _materialize_runtime_operations(
    *,
    instance: ToolInstance,
    provider: ToolInstance,
    discovered_tools: List[DiscoveredTool],
) -> List[RuntimeOperationListItem]:
    items: List[RuntimeOperationListItem] = []
    seen: set[str] = set()
    runtime_domain = resolve_collection_runtime_domain(
        instance.config,
        fallback_domain=instance.domain,
    )
    collection_context_domain = resolve_collection_context_domain(instance.config)
    context_domains = [collection_context_domain] if collection_context_domain else None
    for discovered_tool in discovered_tools:
        publication = resolve_publication(
            raw_slug=discovered_tool.slug,
            discovered_domains=discovered_tool.domains or [],
            context_domains=context_domains,
        )
        if publication is None:
            continue
        canonical_name = publication.canonical_op_slug
        operation_slug = build_runtime_operation_slug(instance.slug, canonical_name)
        if operation_slug in seen:
            continue
        seen.add(operation_slug)

        discovered_operation = parse_discovered_operation(
            tool_name=discovered_tool.slug,
            description=discovered_tool.description,
            input_schema=discovered_tool.input_schema,
            output_schema=discovered_tool.output_schema,
        )
        risk_level = discovered_operation.risk_level
        side_effects = discovered_operation.side_effects
        idempotent = True
        requires_confirmation = discovered_operation.requires_confirmation
        items.append(
            RuntimeOperationListItem(
                operation_slug=operation_slug,
                operation=canonical_name,
                source=discovered_tool.source,
                discovered_tool_slug=discovered_tool.slug,
                provider_instance_slug=provider.slug if provider else None,
                risk_level=risk_level,
                side_effects=side_effects,
                idempotent=idempotent,
                requires_confirmation=requires_confirmation,
            )
        )
    return items


def _provider_kind_from_instance(instance: ToolInstance) -> Optional[str]:
    config = instance.config or {}
    raw = config.get("provider_kind")
    normalized = str(raw or "").strip().lower()
    return normalized or None


async def _load_discovered_tools_for_instance(
    db: AsyncSession,
    instance: ToolInstance,
    provider: ToolInstance,
) -> List[DiscoveredTool]:
    resolver = CollectionToolResolver(db)
    return await resolver.load_discovered_tools(
        instance=instance,
        provider=provider,
    )


async def _runtime_tool_summary(
    db: AsyncSession,
    instance: ToolInstance,
) -> tuple[int, int, List[RuntimeOperationListItem]]:
    if str(getattr(instance, "instance_kind", "")).strip().lower() != "data":
        return 0, 0, []
    if not getattr(instance, "is_active", False):
        return 0, 0, []

    provider = await _resolve_provider_instance(db, instance)
    if not provider:
        return 0, 0, []

    discovered_tools = await _load_discovered_tools_for_instance(db, instance, provider)
    runtime_operations = _materialize_runtime_operations(
        instance=instance,
        provider=provider,
        discovered_tools=discovered_tools,
    )
    return len(discovered_tools), len(runtime_operations), runtime_operations


def _aggregate_linked_runtime(
    linked_items: List[LinkedDataInstanceRuntimeSummary],
) -> tuple[int, int, int]:
    ready = sum(1 for item in linked_items if item.is_runtime_ready)
    not_ready = len(linked_items) - ready
    runtime_ops_total = sum(item.runtime_operations_count for item in linked_items)
    return ready, not_ready, runtime_ops_total


# ── Instance CRUD ────────────────────────────────────────────────────

@router.get("", response_model=List[ToolInstanceListItem])
async def list_tool_instances(
    skip: int = 0,
    limit: int = 100,
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    instance_kind: Optional[str] = Query(None, description="Filter: data|service"),
    connector_type: Optional[str] = Query(None, description="Filter: data|mcp|model"),
    placement: Optional[str] = Query(None, description="Filter: local|remote"),
    connector_subtype: Optional[str] = Query(None, description="Filter: sql|api"),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """List all tool instances. Admin only."""
    service = ToolInstanceService(db)
    instances, _ = await service.list_instances(
        skip=skip,
        limit=limit,
        is_active=is_active,
        instance_kind=instance_kind,
        connector_type=connector_type,
        placement=placement,
        connector_subtype=connector_subtype,
    )
    result = []
    for inst in instances:
        item = ToolInstanceListItem(
            id=inst.id,
            slug=inst.slug,
            name=inst.name,
            description=inst.description,
            instance_kind=inst.instance_kind,
            connector_type=inst.connector_type,
            connector_subtype=inst.connector_subtype,
            placement=inst.placement,
            provider_kind=_provider_kind_from_instance(inst),
            url=inst.url,
            health_status=inst.health_status,
            is_active=inst.is_active,
            access_via_instance_id=inst.access_via_instance_id,
            created_at=inst.created_at,
        )
        result.append(item)
    return result


@router.post("", response_model=ToolInstanceResponse, status_code=status.HTTP_201_CREATED)
async def create_tool_instance(
    data: ToolInstanceCreate,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Create a new tool instance."""
    import re
    slug = data.slug
    if not slug:
        slug = re.sub(r'[^a-z0-9]+', '-', data.name.lower()).strip('-')

    service = ToolInstanceService(db)
    instance = await service.create_instance(
        slug=slug,
        name=data.name,
        instance_kind=data.instance_kind,
        connector_type=data.connector_type,
        connector_subtype=data.connector_subtype,
        url=data.url,
        description=data.description,
        config=data.config,
        provider_kind=data.provider_kind,
        access_via_instance_id=data.access_via_instance_id,
    )
    await db.commit()
    await db.refresh(instance)
    return instance


@router.post("/rescan", response_model=RescanResponse)
async def rescan_instances(
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Rescan and sync local instances with actual data."""
    service = ToolInstanceService(db)
    result = await service.rescan_local_instances()
    await db.commit()
    return RescanResponse(
        created=result.created,
        updated=result.updated,
        deleted=result.deleted,
        errors=result.errors,
    )


@router.post("/{instance_id}/onboard-runtime", response_model=InstanceRuntimeOnboardResponse)
async def onboard_instance_runtime(
    instance_id: UUID,
    data: InstanceRuntimeOnboardRequest,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """
    One-shot onboarding for MCP service instance:
    - probe + scoped discovered-tools rescan (+ optional mass enable)
    - evaluate linked data instances runtime readiness/operations
    """
    service = ToolInstanceService(db)
    discovery = ToolDiscoveryService(db)
    provider = await service.get_instance(instance_id)
    if not is_mcp_service_instance(provider):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Instance '{provider.slug}' is not MCP service "
                f"(got {provider.instance_kind}.{provider.domain})"
            ),
        )

    onboarding = await discovery.onboard_mcp_provider(
        provider_instance_id=provider.id,
        enable_all_in_runtime=data.enable_all_in_runtime,
        include_local=data.include_local_tools,
    )

    linked_stmt = select(ToolInstance).where(
        ToolInstance.access_via_instance_id == provider.id,
        ToolInstance.connector_type == "data",
    )
    if not data.include_inactive_linked:
        linked_stmt = linked_stmt.where(ToolInstance.is_active.is_(True))
    linked_result = await db.execute(linked_stmt.order_by(ToolInstance.slug))
    linked_instances = list(linked_result.scalars().all())

    linked_items: List[LinkedDataInstanceRuntimeSummary] = []
    for linked in linked_instances:
        is_ready, reason, semantic_source = await service.evaluate_instance_readiness(linked)
        discovered_count, runtime_count, _ = await _runtime_tool_summary(db, linked)
        linked_items.append(
            LinkedDataInstanceRuntimeSummary(
                instance_id=linked.id,
                slug=linked.slug,
                connector_subtype=linked.connector_subtype,
                is_runtime_ready=is_ready,
                runtime_readiness_reason=reason,
                semantic_source=semantic_source,
                discovered_tools_count=discovered_count,
                runtime_operations_count=runtime_count,
            )
        )

    linked_ready_count, linked_not_ready_count, linked_runtime_operations_total = (
        _aggregate_linked_runtime(linked_items)
    )

    await db.commit()
    return InstanceRuntimeOnboardResponse(
        provider_instance_id=provider.id,
        provider_slug=provider.slug,
        onboarding=onboarding,
        linked_instances_total=len(linked_items),
        linked_ready_count=linked_ready_count,
        linked_not_ready_count=linked_not_ready_count,
        linked_runtime_operations_total=linked_runtime_operations_total,
        linked_instances=linked_items,
    )


@router.get("/{instance_id}", response_model=ToolInstanceDetailResponse)
async def get_tool_instance(
    instance_id: UUID,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Get tool instance detail. Admin only."""
    service = ToolInstanceService(db)
    instance = await service.get_instance(instance_id)
    _, _, runtime_operations = await _runtime_tool_summary(db, instance)

    return ToolInstanceDetailResponse(
        id=instance.id,
        slug=instance.slug,
        name=instance.name,
        description=instance.description,
        instance_kind=instance.instance_kind,
        connector_type=instance.connector_type,
        connector_subtype=instance.connector_subtype,
        placement=instance.placement,
        provider_kind=_provider_kind_from_instance(instance),
        url=instance.url,
        config=instance.config,
        health_status=instance.health_status,
        is_active=instance.is_active,
        access_via_instance_id=instance.access_via_instance_id,
        created_at=instance.created_at,
        updated_at=instance.updated_at,
        access_via_name=instance.access_via.name if instance.access_via else None,
        runtime_operations=runtime_operations,
    )


@router.put("/{instance_id}", response_model=ToolInstanceResponse)
async def update_tool_instance(
    instance_id: UUID,
    data: ToolInstanceUpdate,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Update tool instance."""
    service = ToolInstanceService(db)
    instance = await service.update_instance(
        instance_id=instance_id,
        name=data.name,
        description=data.description,
        instance_kind=data.instance_kind,
        connector_type=data.connector_type,
        connector_subtype=data.connector_subtype,
        url=data.url,
        config=data.config,
        provider_kind=data.provider_kind,
        is_active=data.is_active,
        access_via_instance_id=(
            data.access_via_instance_id
            if "access_via_instance_id" in data.model_fields_set
            else _UNSET
        ),
    )
    await db.commit()
    await db.refresh(instance)
    return instance


@router.delete("/{instance_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tool_instance(
    instance_id: UUID,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Delete tool instance with validation."""
    service = ToolInstanceService(db)
    await service.delete_instance(instance_id)
    await db.commit()


@router.post("/{instance_id}/health-check", response_model=HealthCheckResponse)
async def check_tool_instance_health(
    instance_id: UUID,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Perform health check on tool instance. Admin only."""
    service = ToolInstanceService(db)
    try:
        result = await service.check_health(instance_id)
        await db.commit()
        return HealthCheckResponse(
            status=result.status,
            message=result.message,
            details=result.details,
        )
    except ToolInstanceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
