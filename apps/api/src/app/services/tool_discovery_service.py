"""
ToolDiscoveryService — сканирование и кеширование инструментов.

Два источника:
- LOCAL: из ToolRegistry (builtins), привязанные к конкретному local service instance.
- MCP: из service.remote.mcp ToolInstance. domains берутся из instance.domain.

Результаты сохраняются в discovered_tools.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple
from uuid import UUID

import httpx
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import selectinload

from app.agents.mcp_discovery import parse_discovered_operation
from app.agents.registry import ToolRegistry
from app.core.logging import get_logger
from app.models.discovered_tool import DiscoveredTool
from app.models.tool_instance import ToolInstance
from app.services.collection_binding import resolve_collection_context_domain
from app.services.instance_capabilities import is_mcp_service_instance

logger = get_logger(__name__)

MCP_ACCEPT_HEADER = "application/json, text/event-stream"
MCP_PROTOCOL_VERSION = "2024-11-05"


class ToolDiscoveryService:
    """Scan local registry + MCP providers → upsert into discovered_tools."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def rescan_all(self) -> Dict[str, Any]:
        """
        Full rescan: local tools + all active MCP providers.
        Returns stats dict.
        """
        return await self.rescan(include_local=True, provider_instance_id=None)

    async def rescan(
        self,
        *,
        include_local: bool,
        provider_instance_id: Optional[UUID],
    ) -> Dict[str, Any]:
        """
        Scoped rescan:
        - include_local=True -> local registry scan
        - provider_instance_id=<uuid> -> scan only one MCP provider
        - provider_instance_id=None -> scan all active MCP providers
        """
        now = datetime.now(timezone.utc)
        local_count = 0
        if include_local:
            local_count = await self._scan_local_tools(now)

        mcp_count, scanned_provider_ids = await self._scan_mcp_providers(
            now,
            provider_instance_id=provider_instance_id,
        )

        stale = await self._mark_stale(
            now,
            include_local=include_local,
            full_mcp_scan=provider_instance_id is None,
            scanned_provider_ids=scanned_provider_ids,
        )

        await self.session.flush()
        return {
            "scope": "provider" if provider_instance_id else "all",
            "provider_instance_id": str(provider_instance_id) if provider_instance_id else None,
            "local_upserted": local_count,
            "mcp_upserted": mcp_count,
            "marked_inactive": stale,
        }

    async def list_all(
        self,
        *,
        source: Optional[str] = None,
        provider_instance_id: Optional[UUID] = None,
        domain: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> List[DiscoveredTool]:
        """List discovered tools with optional filters."""
        stmt = (
            select(DiscoveredTool)
            .options(
                selectinload(DiscoveredTool.tool),
                selectinload(DiscoveredTool.provider_instance),
            )
            .order_by(DiscoveredTool.slug)
        )
        if source:
            stmt = stmt.where(DiscoveredTool.source == source)
        if provider_instance_id is not None:
            stmt = stmt.where(DiscoveredTool.provider_instance_id == provider_instance_id)
        if domain:
            stmt = stmt.where(DiscoveredTool.domains.any(domain))
        if is_active is not None:
            stmt = stmt.where(DiscoveredTool.is_active == is_active)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def probe_mcp_provider(self, provider_instance_id: UUID) -> Dict[str, Any]:
        """
        Fetch tools from one MCP provider without writing into discovered_tools.
        Used as a sandbox/verification step before publication.
        """
        provider = await self._get_mcp_provider(provider_instance_id)
        tools = await self._fetch_mcp_tools(provider.url)
        preview: List[Dict[str, Any]] = []
        for tool in tools:
            name = str(tool.get("name") or "").strip()
            if not name:
                continue
            discovered = parse_discovered_operation(
                tool_name=name,
                description=tool.get("description"),
                input_schema=tool.get("inputSchema"),
                output_schema=tool.get("outputSchema"),
            )
            preview.append(
                {
                    "slug": discovered.name,
                    "name": discovered.name,
                    "description": discovered.description,
                    "has_input_schema": bool(discovered.input_schema),
                    "has_output_schema": bool(discovered.output_schema),
                }
            )
        return {
            "provider_instance_id": str(provider.id),
            "provider_slug": provider.slug,
            "provider_url": provider.url,
            "tools_count": len(preview),
            "tools": preview,
        }

    async def onboard_mcp_provider(
        self,
        *,
        provider_instance_id: UUID,
        enable_all_in_runtime: bool = False,
        include_local: bool = False,
    ) -> Dict[str, Any]:
        """
        One-step onboarding flow:
        1) Probe provider (sandbox check)
        2) Scoped rescan for this provider (optionally with local tools)
        3) Optionally enable discovered tools in runtime for this provider
        """
        probe = await self.probe_mcp_provider(provider_instance_id)
        rescan_stats = await self.rescan(
            include_local=include_local,
            provider_instance_id=provider_instance_id,
        )

        linked_tools_updated = 0
        if enable_all_in_runtime:
            linked_tools_updated = await self._set_provider_runtime_publication(
                provider_instance_id=provider_instance_id,
                use_in_runtime=True,
            )

        total_active, runtime_enabled_tools = await self._count_provider_tools(provider_instance_id)
        return {
            "provider_instance_id": str(provider_instance_id),
            "enable_all_in_runtime": bool(enable_all_in_runtime),
            "probe_tools_count": probe["tools_count"],
            "rescan_stats": rescan_stats,
            "enabled_updated": linked_tools_updated,
            "runtime_enabled_tools": runtime_enabled_tools,
            "linked_tools_updated": linked_tools_updated,
            "active_discovered_tools": total_active,
            "published_tools": runtime_enabled_tools,
        }

    # ── Local scan ─────────────────────────────────────────────────────────

    # Internal runtime tools that should NOT appear in discovered_tools
    # (currently empty — all collection tools are public)
    INTERNAL_TOOL_SLUGS: frozenset[str] = frozenset()

    async def _scan_local_tools(self, now: datetime) -> int:
        """Upsert local handlers into discovered_tools per local service provider."""
        handlers = ToolRegistry.list_all()
        local_providers = await self._load_local_service_providers()
        count = 0
        for provider_kind, provider in local_providers.items():
            provider_domain = self._provider_kind_to_domain(provider_kind)
            if not provider_domain:
                continue
            for handler in handlers:
                if handler.slug in self.INTERNAL_TOOL_SLUGS:
                    continue

                descriptor = handler.to_mcp_descriptor()
                domains = descriptor.get("domains", []) or getattr(handler, "domains", []) or []
                if provider_domain not in domains:
                    continue

                discovered = parse_discovered_operation(
                    tool_name=handler.slug,
                    description=(descriptor.get("description") or handler.description),
                    input_schema=descriptor.get("inputSchema"),
                    output_schema=descriptor.get("outputSchema"),
                )
                await self._upsert(
                    slug=discovered.name,
                    name=handler.name,
                    description=discovered.description,
                    source="local",
                    provider_instance_id=provider.id,
                    domains=domains,
                    input_schema=discovered.input_schema,
                    output_schema=discovered.output_schema,
                    now=now,
                )
                count += 1
        return count

    async def _load_local_service_providers(self) -> Dict[str, ToolInstance]:
        stmt = select(ToolInstance).where(
            ToolInstance.is_active.is_(True),
            ToolInstance.connector_type == "mcp",
            ToolInstance.placement == "local",
        )
        result = await self.session.execute(stmt)
        providers = list(result.scalars().all())
        mapping: Dict[str, ToolInstance] = {}
        for provider in providers:
            provider_kind = str((provider.config or {}).get("provider_kind") or "").strip().lower()
            if provider_kind in {"local_documents", "local_tables"}:
                mapping[provider_kind] = provider
        return mapping

    @staticmethod
    def _provider_kind_to_domain(provider_kind: str) -> Optional[str]:
        if provider_kind == "local_documents":
            return "collection.document"
        if provider_kind == "local_tables":
            return "collection.table"
        return None

    # ── MCP scan ───────────────────────────────────────────────────────────

    async def _scan_mcp_providers(
        self,
        now: datetime,
        *,
        provider_instance_id: Optional[UUID],
    ) -> Tuple[int, List[UUID]]:
        """Scan MCP providers and upsert their tools."""
        providers = await self._load_mcp_providers(provider_instance_id)

        total = 0
        scanned_provider_ids: List[UUID] = []
        for provider in providers:
            if not provider.url:
                continue
            try:
                tools = await self._fetch_mcp_tools(provider.url)
                scanned_provider_ids.append(provider.id)
                mcp_domains = await self._resolve_mcp_domains(provider)
                for tool in tools:
                    tool_name = tool.get("name", "")
                    if not tool_name:
                        continue

                    discovered = parse_discovered_operation(
                        tool_name=tool_name,
                        description=tool.get("description", ""),
                        input_schema=tool.get("inputSchema"),
                        output_schema=tool.get("outputSchema"),
                    )
                    await self._upsert(
                        slug=discovered.name,
                        name=discovered.name,
                        description=discovered.description,
                        source="mcp",
                        provider_instance_id=provider.id,
                        domains=mcp_domains,
                        input_schema=discovered.input_schema,
                        output_schema=discovered.output_schema,
                        now=now,
                    )
                    total += 1
            except Exception:
                logger.exception("MCP scan failed for provider %s (%s)", provider.slug, provider.url)
        return total, scanned_provider_ids

    async def _load_mcp_providers(self, provider_instance_id: Optional[UUID]) -> Sequence[ToolInstance]:
        if provider_instance_id is None:
            stmt = (
                select(ToolInstance)
                .where(
                    ToolInstance.is_active == True,
                    or_(
                        ToolInstance.connector_type == "mcp",
                        ToolInstance.instance_kind == "service",
                    ),
                )
            )
            result = await self.session.execute(stmt)
            providers = list(result.scalars().all())
            return [provider for provider in providers if is_mcp_service_instance(provider)]
        provider = await self._get_mcp_provider(provider_instance_id)
        return [provider]

    async def _get_mcp_provider(self, provider_instance_id: UUID) -> ToolInstance:
        stmt = select(ToolInstance).where(ToolInstance.id == provider_instance_id)
        result = await self.session.execute(stmt)
        provider = result.scalar_one_or_none()
        if provider is None:
            raise ValueError(f"MCP provider instance '{provider_instance_id}' not found")
        if not is_mcp_service_instance(provider):
            raise ValueError(
                f"Instance '{provider.slug}' is not MCP service (got {provider.instance_kind}.{provider.domain})"
            )
        if not provider.is_active:
            raise ValueError(f"MCP provider instance '{provider.slug}' is inactive")
        if not provider.url:
            raise ValueError(f"MCP provider instance '{provider.slug}' has empty url")
        return provider

    async def _resolve_mcp_domains(self, provider: ToolInstance) -> List[str]:
        """
        Determine domains for MCP tools based on linked data instances.

        Priority:
        1. Explicit config.domains on provider
        2. Domains from data instances that reference this provider via access_via_instance_id
        3. Provider's own domain (if not generic "mcp")
        """
        config_domains = (provider.config or {}).get("domains")
        if config_domains and isinstance(config_domains, list):
            return config_domains

        stmt = (
            select(ToolInstance)
            .where(
                ToolInstance.access_via_instance_id == provider.id,
                ToolInstance.connector_type == "data",
                ToolInstance.is_active.is_(True),
            )
            .order_by(ToolInstance.slug)
        )
        result = await self.session.execute(stmt)
        linked_instances = list(result.scalars().all())
        linked_domains: List[str] = []
        for instance in linked_instances:
            collection_domain = resolve_collection_context_domain(instance.config)
            if collection_domain and collection_domain not in linked_domains:
                linked_domains.append(collection_domain)

            for capability_domain in self._extract_capability_domains(instance.config):
                if capability_domain not in linked_domains:
                    linked_domains.append(capability_domain)
        if linked_domains:
            return linked_domains

        # No linked data yet: keep discovered tools domain-agnostic until explicit mapping appears.
        return []

    @staticmethod
    def _extract_capability_domains(config: Optional[Dict[str, Any]]) -> List[str]:
        cfg = config or {}
        domains: List[str] = []

        raw_domains = cfg.get("capability_domains")
        if isinstance(raw_domains, list):
            for raw in raw_domains:
                normalized = str(raw or "").strip()
                if normalized and normalized not in domains:
                    domains.append(normalized)

        raw_single = cfg.get("capability_domain")
        normalized_single = str(raw_single or "").strip()
        if normalized_single and normalized_single not in domains:
            domains.append(normalized_single)

        return domains

    # ── MCP protocol ───────────────────────────────────────────────────────

    async def _fetch_mcp_tools(self, provider_url: str) -> List[Dict[str, Any]]:
        timeout = 30
        async with httpx.AsyncClient(timeout=timeout) as client:
            init_response = await client.post(
                provider_url,
                headers={
                    "Content-Type": "application/json",
                    "Accept": MCP_ACCEPT_HEADER,
                },
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": MCP_PROTOCOL_VERSION,
                        "capabilities": {},
                        "clientInfo": {"name": "ml-portal", "version": "1.0"},
                    },
                },
            )
            init_response.raise_for_status()
            session_id = init_response.headers.get("mcp-session-id")
            if not session_id:
                raise ValueError(f"MCP initialize missing session id for {provider_url}")

            tools_response = await client.post(
                provider_url,
                headers={
                    "Content-Type": "application/json",
                    "Accept": MCP_ACCEPT_HEADER,
                    "mcp-session-id": session_id,
                },
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/list",
                    "params": {},
                },
            )
            tools_response.raise_for_status()
            payload = self._parse_mcp_response(tools_response.text)
            tools = payload.get("result", {}).get("tools", [])
            if not isinstance(tools, list):
                raise ValueError("MCP tools/list response does not contain a tools array")
            return tools

    @staticmethod
    def _parse_mcp_response(body: str) -> Dict[str, Any]:
        body = (body or "").strip()
        if not body:
            raise ValueError("Unable to parse MCP response body")
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            pass
        data_lines: List[str] = []
        for line in body.splitlines():
            if line.startswith("data:"):
                data_lines.append(line[len("data:"):].strip())
        if data_lines:
            joined = "\n".join(data_lines).strip()
            if joined:
                return json.loads(joined)
        start = body.find("{")
        if start >= 0:
            return json.loads(body[start:])
        raise ValueError("Unable to parse MCP response body")

    # ── Upsert / lifecycle ─────────────────────────────────────────────────

    async def _upsert(
        self,
        *,
        slug: str,
        name: str,
        description: Optional[str],
        source: str,
        provider_instance_id: Optional[UUID],
        domains: List[str],
        input_schema: Optional[Dict[str, Any]],
        output_schema: Optional[Dict[str, Any]],
        now: datetime,
    ) -> None:
        """Upsert a discovered tool row.

        Uses partial unique index:
        - uq_discovered_slug_provider (slug, provider_instance_id) WHERE provider_instance_id IS NOT NULL
        """
        stmt = pg_insert(DiscoveredTool).values(
            slug=slug,
            name=name,
            description=description,
            source=source,
            provider_instance_id=provider_instance_id,
            domains=domains,
            input_schema=input_schema,
            output_schema=output_schema,
            is_active=True,
            last_seen_at=now,
            updated_at=now,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["slug", "provider_instance_id"],
            index_where=DiscoveredTool.provider_instance_id.isnot(None),
            set_={
                "name": name,
                "description": description,
                "domains": domains,
                "input_schema": input_schema,
                "output_schema": output_schema,
                "is_active": True,
                "last_seen_at": now,
                "updated_at": now,
            },
        )
        await self.session.execute(stmt)

    async def _mark_stale(
        self,
        scan_time: datetime,
        *,
        include_local: bool,
        full_mcp_scan: bool,
        scanned_provider_ids: List[UUID],
    ) -> int:
        """Mark tools not seen in current scan scope as inactive."""
        predicates = []
        if include_local:
            predicates.append(DiscoveredTool.source == "local")
        if full_mcp_scan:
            predicates.append(DiscoveredTool.source == "mcp")
        elif scanned_provider_ids:
            predicates.append(
                (DiscoveredTool.source == "mcp")
                & (DiscoveredTool.provider_instance_id.in_(scanned_provider_ids))
            )
        if not predicates:
            return 0

        stmt = (
            update(DiscoveredTool)
            .where(
                DiscoveredTool.is_active == True,  # noqa: E712
                DiscoveredTool.last_seen_at < scan_time,
                or_(*predicates),
            )
            .values(is_active=False, updated_at=scan_time)
        )
        result = await self.session.execute(stmt)
        return result.rowcount

    async def _count_provider_tools(self, provider_instance_id: UUID) -> Tuple[int, int]:
        base_filter = (
            DiscoveredTool.source == "mcp",
            DiscoveredTool.provider_instance_id == provider_instance_id,
            DiscoveredTool.is_active == True,  # noqa: E712
        )

        total_stmt = select(func.count()).select_from(DiscoveredTool).where(*base_filter)
        total = int((await self.session.execute(total_stmt)).scalar_one() or 0)
        published = total
        return total, published

    async def _set_provider_runtime_publication(
        self,
        *,
        provider_instance_id: UUID,
        use_in_runtime: bool,
    ) -> int:
        """
        Compatibility hook for onboarding flow.

        Runtime publication now depends on tool-linking lifecycle; direct mass-publish
        is intentionally a no-op until explicit publication pipeline is reintroduced.
        """
        _ = provider_instance_id, use_in_runtime
        return 0
