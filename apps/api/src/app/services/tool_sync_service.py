"""
ToolSyncService v2 — синхронизация tools из кода в БД.

Phase 1: Tool sync (ToolHandler → Tool container)
Phase 2: Backend release sync (VersionedTool → ToolBackendRelease)

В v2 Tool — это контейнер (slug, name, kind, tags).
Schemas (input/output) живут только в ToolBackendRelease.
"""
from typing import List, Set, Dict, Optional
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.logging import get_logger
from app.core.schema_hash import compute_schema_hash
from app.models.tool import Tool
from app.models.tool_group import ToolGroup
from app.models.tool_release import ToolBackendRelease
from app.agents.registry import ToolRegistry
from app.agents.handlers.base import ToolHandler

logger = get_logger(__name__)


class ToolSyncService:
    """
    Синхронизация tools и backend releases из кода в БД (v2).
    """

    def __init__(self, session: AsyncSession, worker_build_id: Optional[str] = None):
        self.session = session
        self.worker_build_id = worker_build_id

    # ─────────────────────────────────────────────────────────────────────────
    # PUBLIC API
    # ─────────────────────────────────────────────────────────────────────────

    async def sync_tools(self) -> dict:
        """Phase 1: Sync tools from ToolRegistry into DB."""
        stats = {"created": 0, "updated": 0, "groups_created": 0}

        handlers = ToolRegistry.list_all()
        logger.info(f"Syncing {len(handlers)} tools from registry to DB")

        group_slugs: Set[str] = {h.tool_group for h in handlers if hasattr(h, 'tool_group') and h.tool_group}
        existing_groups = await self._get_existing_group_slugs()
        group_id_map = await self._sync_tool_groups(group_slugs)
        stats["groups_created"] = len(group_slugs - existing_groups)

        for handler in handlers:
            tool = await self._get_tool_by_slug(handler.slug)
            tool_group_id = group_id_map.get(handler.tool_group) if hasattr(handler, 'tool_group') else None

            if tool is None:
                await self._create_tool(handler, tool_group_id)
                stats["created"] += 1
                logger.info(f"Created tool: {handler.slug}")
            else:
                updated = await self._update_tool(tool, handler, tool_group_id)
                if updated:
                    stats["updated"] += 1
                    logger.info(f"Updated tool: {handler.slug}")

        await self.session.commit()

        logger.info(
            f"Tool sync complete: {stats['created']} created, "
            f"{stats['updated']} updated"
        )
        return stats

    async def sync_backend_releases(self) -> dict:
        """Phase 2: Sync backend releases from VersionedTool registry."""
        from app.agents.handlers.versioned_tool import tool_registry

        stats = {
            "tools_synced": 0,
            "backend_releases_created": 0,
            "backend_releases_updated": 0,
            "schema_changes_detected": 0,
            "groups_created": 0,
        }

        tools = tool_registry.get_all()
        logger.info(f"Syncing {len(tools)} versioned tools from registry")

        if not tools:
            logger.info("No versioned tools found in registry")
            return stats

        group_slugs: Set[str] = {t.tool_group for t in tools}
        existing_groups = await self._get_existing_group_slugs()
        group_id_map = await self._sync_tool_groups(group_slugs)
        stats["groups_created"] = len(group_slugs - existing_groups)

        for versioned_tool in tools:
            tool = await self._ensure_versioned_tool_exists(versioned_tool, group_id_map)

            versions = versioned_tool.get_versions()
            for version_info in versions:
                result = await self._sync_backend_release(tool, version_info)
                if result == "created":
                    stats["backend_releases_created"] += 1
                elif result == "schema_changed":
                    stats["schema_changes_detected"] += 1
                    stats["backend_releases_updated"] += 1
                else:
                    stats["backend_releases_updated"] += 1

            stats["tools_synced"] += 1

        await self.session.commit()

        logger.info(
            f"Backend release sync complete: {stats['tools_synced']} tools, "
            f"{stats['backend_releases_created']} releases created, "
            f"{stats['backend_releases_updated']} releases updated, "
            f"{stats['schema_changes_detected']} schema changes detected"
        )
        return stats

    async def sync_all(self) -> dict:
        """Full sync: tools + backend releases."""
        tools_stats = await self.sync_tools()
        releases_stats = await self.sync_backend_releases()
        return {"tools": tools_stats, "backend_releases": releases_stats}

    # ─────────────────────────────────────────────────────────────────────────
    # SHARED HELPERS
    # ─────────────────────────────────────────────────────────────────────────

    async def _get_tool_by_slug(self, slug: str) -> Tool | None:
        stmt = select(Tool).where(Tool.slug == slug)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_all_tools(self) -> List[Tool]:
        stmt = select(Tool)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def _get_existing_group_slugs(self) -> Set[str]:
        stmt = select(ToolGroup.slug)
        result = await self.session.execute(stmt)
        return set(result.scalars().all())

    async def _sync_tool_groups(self, group_slugs: Set[str]) -> Dict[str, UUID]:
        group_id_map: Dict[str, UUID] = {}
        for slug in group_slugs:
            stmt = select(ToolGroup).where(ToolGroup.slug == slug)
            result = await self.session.execute(stmt)
            group = result.scalar_one_or_none()

            if group is None:
                group = ToolGroup(
                    slug=slug,
                    name=slug.capitalize(),
                    description=f"Tools for {slug} integration",
                )
                self.session.add(group)
                await self.session.flush()
                logger.info(f"Created tool group: {slug}")

            group_id_map[slug] = group.id
        return group_id_map

    # ─────────────────────────────────────────────────────────────────────────
    # PHASE 1: TOOL SYNC (ToolHandler → Tool container)
    # ─────────────────────────────────────────────────────────────────────────

    async def _create_tool(self, handler: ToolHandler, tool_group_id: UUID | None = None) -> Tool:
        """Create new tool container from handler."""
        tool = Tool(
            slug=handler.slug,
            name=handler.name,
            tool_group_id=tool_group_id,
            kind="read",
        )
        self.session.add(tool)
        await self.session.flush()
        return tool

    async def _update_tool(self, tool: Tool, handler: ToolHandler, tool_group_id: UUID | None = None) -> bool:
        """Update tool container from handler if changed."""
        updated = False

        if tool.name != handler.name:
            tool.name = handler.name
            updated = True

        if tool.tool_group_id != tool_group_id:
            tool.tool_group_id = tool_group_id
            updated = True

        if updated:
            self.session.add(tool)
            await self.session.flush()

        return updated

    # ─────────────────────────────────────────────────────────────────────────
    # PHASE 2: BACKEND RELEASE SYNC (VersionedTool → ToolBackendRelease)
    # ─────────────────────────────────────────────────────────────────────────

    async def _ensure_versioned_tool_exists(
        self,
        versioned_tool,
        group_id_map: Dict[str, UUID],
    ) -> Tool:
        """Ensure tool container exists in DB for a VersionedTool."""
        stmt = select(Tool).where(Tool.slug == versioned_tool.tool_slug)
        result = await self.session.execute(stmt)
        tool = result.scalar_one_or_none()

        group_id = group_id_map.get(versioned_tool.tool_group)

        if tool is None:
            tool = Tool(
                slug=versioned_tool.tool_slug,
                name=versioned_tool.name,
                tool_group_id=group_id,
                kind="read",
            )
            self.session.add(tool)
            await self.session.flush()
            logger.info(f"Created tool: {versioned_tool.tool_slug}")
        else:
            updated = False
            if tool.name != versioned_tool.name:
                tool.name = versioned_tool.name
                updated = True
            if tool.tool_group_id != group_id:
                tool.tool_group_id = group_id
                updated = True

            if updated:
                self.session.add(tool)
                await self.session.flush()
                logger.info(f"Updated tool: {versioned_tool.tool_slug}")

        return tool

    async def _sync_backend_release(self, tool: Tool, version_info) -> str:
        """Sync a single backend release. Returns: created/schema_changed/updated"""
        now = datetime.now(timezone.utc)
        new_hash = compute_schema_hash(
            version_info.input_schema,
            version_info.output_schema,
        )

        stmt = select(ToolBackendRelease).where(
            ToolBackendRelease.tool_id == tool.id,
            ToolBackendRelease.version == version_info.version
        )
        result = await self.session.execute(stmt)
        release = result.scalar_one_or_none()

        if release is None:
            release = ToolBackendRelease(
                tool_id=tool.id,
                version=version_info.version,
                input_schema=version_info.input_schema,
                output_schema=version_info.output_schema,
                description=version_info.description,
                method_name=version_info.method_name,
                deprecated=version_info.deprecated,
                deprecation_message=version_info.deprecation_message,
                schema_hash=new_hash,
                worker_build_id=self.worker_build_id,
                last_seen_at=now,
                synced_at=now,
            )
            self.session.add(release)
            await self.session.flush()
            logger.info(f"Created backend release: {tool.slug}@{version_info.version} (hash={new_hash[:8]})")
            return "created"

        schema_changed = release.schema_hash is not None and release.schema_hash != new_hash
        if schema_changed:
            logger.warning(
                f"Schema change detected for {tool.slug}@{version_info.version}: "
                f"{release.schema_hash[:8]} -> {new_hash[:8]}",
                extra={
                    "tool_slug": tool.slug,
                    "version": version_info.version,
                    "old_hash": release.schema_hash,
                    "new_hash": new_hash,
                    "worker_build_id": self.worker_build_id,
                },
            )

        updated = False
        if release.input_schema != version_info.input_schema:
            release.input_schema = version_info.input_schema
            updated = True
        if release.output_schema != version_info.output_schema:
            release.output_schema = version_info.output_schema
            updated = True
        if release.description != version_info.description:
            release.description = version_info.description
            updated = True
        if release.method_name != version_info.method_name:
            release.method_name = version_info.method_name
            updated = True
        if release.deprecated != version_info.deprecated:
            release.deprecated = version_info.deprecated
            updated = True
        if release.deprecation_message != version_info.deprecation_message:
            release.deprecation_message = version_info.deprecation_message
            updated = True

        release.schema_hash = new_hash
        release.worker_build_id = self.worker_build_id
        release.last_seen_at = now

        if updated or schema_changed:
            release.synced_at = now

        self.session.add(release)
        await self.session.flush()

        if updated:
            logger.info(f"Updated backend release: {tool.slug}@{version_info.version}")

        return "schema_changed" if schema_changed else "updated"


# ─────────────────────────────────────────────────────────────────────────────
# CONVENIENCE FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

async def sync_tools_from_registry(session: AsyncSession) -> dict:
    service = ToolSyncService(session)
    return await service.sync_tools()


async def sync_tool_versions(
    session: AsyncSession,
    worker_build_id: Optional[str] = None,
) -> dict:
    service = ToolSyncService(session, worker_build_id=worker_build_id)
    return await service.sync_backend_releases()


async def sync_all_tools(
    session: AsyncSession,
    worker_build_id: Optional[str] = None,
) -> dict:
    service = ToolSyncService(session, worker_build_id=worker_build_id)
    return await service.sync_all()
