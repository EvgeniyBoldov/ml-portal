"""
ToolBackendReleaseSyncService — синхронизация backend releases из code registry в БД.

Отвечает только за VersionedTool -> ToolBackendRelease.
Если tool container ещё не существует, он создаётся как часть publication flow.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.handlers.versioned_tool import VersionedTool, tool_registry
from app.core.logging import get_logger
from app.core.schema_hash import compute_schema_hash
from app.models.tool import Tool
from app.models.tool_release import ToolBackendRelease

logger = get_logger(__name__)


class ToolBackendReleaseSyncService:
    """Sync backend releases from VersionedTool registry into DB."""

    def __init__(self, session: AsyncSession, worker_build_id: Optional[str] = None):
        self.session = session
        self.worker_build_id = worker_build_id

    async def sync_backend_releases(self, tool_slug: Optional[str] = None) -> dict:
        """Sync backend releases for all tools or a single tool slug."""
        stats = {
            "tools_synced": 0,
            "backend_releases_created": 0,
            "backend_releases_updated": 0,
            "schema_changes_detected": 0,
        }

        tools = list(self._iter_versioned_tools(tool_slug))
        logger.info("Syncing %s versioned tools from registry", len(tools))

        if not tools:
            if tool_slug:
                raise ValueError(f"Versioned tool '{tool_slug}' not found in registry")
            logger.info("No versioned tools found in registry")
            return stats

        for versioned_tool in tools:
            tool = await self._ensure_tool_exists(versioned_tool)

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
            "Backend release sync complete: %s tools, %s releases created, %s releases updated, %s schema changes detected",
            stats["tools_synced"],
            stats["backend_releases_created"],
            stats["backend_releases_updated"],
            stats["schema_changes_detected"],
        )
        return stats

    def _iter_versioned_tools(self, tool_slug: Optional[str]) -> Iterable[VersionedTool]:
        tools = tool_registry.get_all()
        if tool_slug is None:
            return tools
        return [tool for tool in tools if tool.tool_slug == tool_slug]

    async def _ensure_tool_exists(self, versioned_tool: VersionedTool) -> Tool:
        stmt = select(Tool).where(Tool.slug == versioned_tool.tool_slug)
        result = await self.session.execute(stmt)
        tool = result.scalar_one_or_none()

        domains = self._resolve_domains(versioned_tool)

        if tool is None:
            tool = Tool(
                slug=versioned_tool.tool_slug,
                name=versioned_tool.name,
                domains=domains,
                kind="read",
            )
            self.session.add(tool)
            await self.session.flush()
            logger.info("Created tool container for backend publication: %s", versioned_tool.tool_slug)
            return tool

        updated = False
        if tool.name != versioned_tool.name:
            tool.name = versioned_tool.name
            updated = True
        if tool.domains != domains:
            tool.domains = domains
            updated = True

        if updated:
            self.session.add(tool)
            await self.session.flush()
            logger.info("Updated tool container for backend publication: %s", versioned_tool.tool_slug)

        return tool

    def _resolve_domains(self, versioned_tool: VersionedTool) -> List[str]:
        raw_domains = getattr(versioned_tool, "domains", None) or []
        domains: List[str] = []
        for domain in raw_domains:
            value = str(domain).strip()
            if value and value not in domains:
                domains.append(value)

        if domains:
            return domains

        slug = str(getattr(versioned_tool, "tool_slug", "") or "").strip()
        if slug:
            prefix = slug.split(".", 1)[0].strip()
            if prefix:
                return [prefix]
        return []

    async def _sync_backend_release(self, tool: Tool, version_info) -> str:
        now = datetime.now(timezone.utc)
        new_hash = compute_schema_hash(
            version_info.input_schema,
            version_info.output_schema,
        )

        stmt = select(ToolBackendRelease).where(
            ToolBackendRelease.tool_id == tool.id,
            ToolBackendRelease.version == version_info.version,
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
            logger.info(
                "Created backend release: %s@%s (hash=%s)",
                tool.slug,
                version_info.version,
                new_hash[:8],
            )
            return "created"

        schema_changed = release.schema_hash is not None and release.schema_hash != new_hash
        if schema_changed:
            logger.warning(
                "Schema change detected for %s@%s: %s -> %s",
                tool.slug,
                version_info.version,
                release.schema_hash[:8],
                new_hash[:8],
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
            logger.info("Updated backend release: %s@%s", tool.slug, version_info.version)

        return "schema_changed" if schema_changed else "updated"


async def sync_backend_releases_from_registry(
    session: AsyncSession,
    worker_build_id: Optional[str] = None,
    tool_slug: Optional[str] = None,
) -> dict:
    service = ToolBackendReleaseSyncService(session, worker_build_id=worker_build_id)
    return await service.sync_backend_releases(tool_slug=tool_slug)
