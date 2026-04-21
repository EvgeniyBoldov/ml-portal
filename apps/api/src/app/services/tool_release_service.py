"""Service for tools, backend releases and runtime releases."""
from typing import List, Optional, Dict, Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.tool import Tool
from app.models.tool_release import ToolBackendRelease, ToolRelease, ToolReleaseStatus
from app.repositories.tool_release_repository import (
    ToolBackendReleaseRepository,
    ToolReleaseRepository,
    ToolWithReleasesRepository,
)
from app.schemas.tool_releases import (
    ToolReleaseCreate,
    ToolReleaseUpdate,
)

from app.core.exceptions import (
    ToolNotFoundError,
    ReleaseNotFoundError,
    BackendReleaseNotFoundError,
    ReleaseNotEditableError,
    ReleasePinnedError,
    AppError as ToolReleaseServiceError,
)

logger = get_logger(__name__)


class ToolReleaseService:
    """Service for managing tool releases"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.backend_repo = ToolBackendReleaseRepository(session)
        self.release_repo = ToolReleaseRepository(session)
        self.tool_repo = ToolWithReleasesRepository(session)

    async def get_tool(self, slug: str) -> Tool:
        """Get tool by slug"""
        tool = await self.tool_repo.get_by_slug(slug)
        if not tool:
            raise ToolNotFoundError(f"Tool '{slug}' not found")
        return tool

    async def get_tool_by_id(self, tool_id: UUID) -> Tool:
        """Get tool by UUID"""
        tool = await self.tool_repo.get_by_id(tool_id)
        if not tool:
            raise ToolNotFoundError(f"Tool '{tool_id}' not found")
        return tool
    
    async def set_current_version(self, tool_slug: str, release_id: UUID) -> Tool:
        """Set current version for a tool"""
        tool = await self.get_tool(tool_slug)
        
        release = await self.release_repo.get_by_id(release_id)
        if not release or release.tool_id != tool.id:
            raise ReleaseNotFoundError(f"Release not found for tool '{tool_slug}'")
        
        if release.status != ToolReleaseStatus.ACTIVE.value:
            raise ReleaseNotEditableError("Only active releases can be set as current version")
        
        tool.current_version_id = release_id
        await self.tool_repo.update(tool)
        await self.session.commit()
        
        logger.info(f"Set current version for {tool_slug}: v{release.version}")
        return await self.get_tool(tool_slug)
    
    # ─────────────────────────────────────────────────────────────────────────
    # BACKEND RELEASES (read-only)
    # ─────────────────────────────────────────────────────────────────────────
    
    async def list_backend_releases(self, tool_slug: str) -> List[ToolBackendRelease]:
        """List all backend releases for a tool"""
        tool = await self.get_tool(tool_slug)
        return await self.backend_repo.list_by_tool(tool.id)

    async def list_backend_releases_by_tool_id(self, tool_id: UUID) -> List[ToolBackendRelease]:
        """List all backend releases for a tool by UUID"""
        return await self.backend_repo.list_by_tool(tool_id)

    async def get_backend_release(
        self,
        tool_slug: str,
        version: str
    ) -> ToolBackendRelease:
        """Get backend release by tool slug and version"""
        tool = await self.get_tool(tool_slug)
        release = await self.backend_repo.get_by_tool_and_version(tool.id, version)
        if not release:
            raise BackendReleaseNotFoundError(
                f"Backend release '{version}' not found for tool '{tool_slug}'"
            )
        return release

    async def get_backend_release_by_tool_id(
        self,
        tool_id: UUID,
        version: str
    ) -> ToolBackendRelease:
        """Get backend release by tool UUID and version"""
        release = await self.backend_repo.get_by_tool_and_version(tool_id, version)
        if not release:
            raise BackendReleaseNotFoundError(
                f"Backend release '{version}' not found for tool '{tool_id}'"
            )
        return release
    
    # ─────────────────────────────────────────────────────────────────────────
    # TOOL RELEASES (CRUD)
    # ─────────────────────────────────────────────────────────────────────────
    
    async def list_releases(self, tool_slug: str) -> List[ToolRelease]:
        """List all releases for a tool"""
        tool = await self.get_tool(tool_slug)
        return await self.release_repo.list_by_tool(tool.id)

    async def list_releases_by_tool_id(self, tool_id: UUID) -> List[ToolRelease]:
        """List all releases for a tool by UUID"""
        return await self.release_repo.list_by_tool(tool_id)

    async def get_release(self, tool_slug: str, version: int) -> ToolRelease:
        """Get release by tool slug and version"""
        tool = await self.get_tool(tool_slug)
        release = await self.release_repo.get_by_tool_and_version(tool.id, version)
        if not release:
            raise ReleaseNotFoundError(
                f"Release v{version} not found for tool '{tool_slug}'"
            )
        return release

    async def get_release_by_tool_id(self, tool_id: UUID, version: int) -> ToolRelease:
        """Get release by tool UUID and version"""
        release = await self.release_repo.get_by_tool_and_version(tool_id, version)
        if not release:
            raise ReleaseNotFoundError(
                f"Release v{version} not found for tool '{tool_id}'"
            )
        return release
    
    async def create_release_by_tool_id(
        self,
        tool_id: UUID,
        data: ToolReleaseCreate,
        from_release_id: Optional[UUID] = None,
    ) -> ToolRelease:
        """Create a new release by tool UUID"""
        tool = await self.get_tool_by_id(tool_id)
        return await self._create_release_for_tool(tool, data, from_release_id)

    async def create_release(
        self,
        tool_slug: str,
        data: ToolReleaseCreate,
        from_release_id: Optional[UUID] = None,
    ) -> ToolRelease:
        """
        Create a new release (draft).

        If from_release_id is provided, copies meta-fields from parent release.
        """
        tool = await self.get_tool(tool_slug)
        return await self._create_release_for_tool(tool, data, from_release_id)

    async def _create_release_for_tool(
        self,
        tool: Tool,
        data: ToolReleaseCreate,
        from_release_id: Optional[UUID] = None,
    ) -> ToolRelease:
        """Internal: create release for a given tool object"""

        # Validate backend release if provided
        backend_release = None
        if data.backend_release_id:
            backend_release = await self.backend_repo.get_by_id(data.backend_release_id)
            if not backend_release or backend_release.tool_id != tool.id:
                raise BackendReleaseNotFoundError(
                    f"Backend release not found for tool '{tool.id}'"
                )

        next_version = await self.release_repo.get_next_version(tool.id)

        parent_release = None
        if from_release_id:
            parent_release = await self.release_repo.get_by_id(from_release_id)
            if not parent_release or parent_release.tool_id != tool.id:
                raise ReleaseNotFoundError(
                    f"Parent release not found for tool '{tool.id}'"
                )

        release = ToolRelease(
            tool_id=tool.id,
            version=next_version,
            backend_release_id=data.backend_release_id,
            status=ToolReleaseStatus.DRAFT.value,
            parent_release_id=from_release_id,
        )

        await self.release_repo.create(release)
        await self.session.commit()

        logger.info(
            f"Created release v{next_version} for tool {tool.id}"
            + (f" (inherited from v{parent_release.version})" if parent_release else "")
        )
        return await self.get_release_by_tool_id(tool.id, next_version)
    
    async def update_release_by_tool_id(
        self,
        tool_id: UUID,
        version: int,
        data: ToolReleaseUpdate
    ) -> ToolRelease:
        """Update a release by tool UUID (only draft)"""
        release = await self.get_release_by_tool_id(tool_id, version)
        return await self._update_release(release, data)

    async def update_release(
        self,
        tool_slug: str,
        version: int,
        data: ToolReleaseUpdate
    ) -> ToolRelease:
        """Update a release (only draft)"""
        release = await self.get_release(tool_slug, version)
        return await self._update_release(release, data)

    async def _update_release(self, release: ToolRelease, data: ToolReleaseUpdate) -> ToolRelease:

        if release.status != ToolReleaseStatus.DRAFT.value:
            raise ReleaseNotEditableError(
                f"Release v{release.version} is not editable (status: {release.status})"
            )

        if data.backend_release_id is not None:
            backend_release = await self.backend_repo.get_by_id(data.backend_release_id)
            if not backend_release or backend_release.tool_id != release.tool_id:
                raise BackendReleaseNotFoundError("Backend release not found")
            release.backend_release_id = data.backend_release_id

        update_dict = data.model_dump(exclude_unset=True, exclude={"backend_release_id"})
        for field, value in update_dict.items():
            if value is not None:
                setattr(release, field, value)

        await self.release_repo.update(release)
        await self.session.commit()

        logger.info(f"Updated release v{release.version} for tool {release.tool_id}")
        return await self.get_release_by_tool_id(release.tool_id, release.version)
    
    async def activate_release_by_tool_id(self, tool_id: UUID, version: int) -> ToolRelease:
        """Publish a draft release by tool UUID."""
        release = await self.get_release_by_tool_id(tool_id, version)
        return await self._activate_release(release)

    async def activate_release(self, tool_slug: str, version: int) -> ToolRelease:
        """Publish a draft release."""
        release = await self.get_release(tool_slug, version)
        return await self._activate_release(release)

    async def _activate_release(self, release: ToolRelease) -> ToolRelease:
        
        if release.status != ToolReleaseStatus.DRAFT.value:
            raise ReleaseNotEditableError(
                f"Only draft releases can be published (current: {release.status})"
            )

        # Fix expected_schema_hash from current backend release
        if release.backend_release_id is not None:
            backend_release = await self.backend_repo.get_by_id(release.backend_release_id)
            if backend_release and backend_release.schema_hash:
                release.expected_schema_hash = backend_release.schema_hash

        # Publish new release
        release.status = ToolReleaseStatus.ACTIVE.value
        await self.release_repo.update(release)

        await self.session.commit()

        logger.info(
            f"Published release v{release.version} for tool {release.tool_id}"
            + (f" (expected_schema_hash={release.expected_schema_hash[:8]})" if release.expected_schema_hash else "")
        )
        return await self.get_release_by_tool_id(release.tool_id, release.version)
    
    async def get_schema_diff_by_tool_id(
        self,
        tool_id: UUID,
        from_backend_release_id: UUID,
        to_backend_release_id: UUID,
    ) -> Dict[str, Any]:
        """Compute schema diff by tool UUID"""
        from_release = await self.backend_repo.get_by_id(from_backend_release_id)
        if not from_release or from_release.tool_id != tool_id:
            raise BackendReleaseNotFoundError("Source backend release not found")

        to_release = await self.backend_repo.get_by_id(to_backend_release_id)
        if not to_release or to_release.tool_id != tool_id:
            raise BackendReleaseNotFoundError("Target backend release not found")

        return compute_schema_diff(
            from_release.input_schema or {},
            to_release.input_schema or {},
        )

    async def get_schema_diff(
        self,
        tool_slug: str,
        from_backend_release_id: UUID,
        to_backend_release_id: UUID,
    ) -> Dict[str, Any]:
        """
        Compute schema diff between two backend releases of the same tool.

        Returns:
            {"added_fields": [...], "removed_fields": [...], "changed_fields": [...]}
        """
        tool = await self.get_tool(tool_slug)
        
        from_release = await self.backend_repo.get_by_id(from_backend_release_id)
        if not from_release or from_release.tool_id != tool.id:
            raise BackendReleaseNotFoundError("Source backend release not found")
        
        to_release = await self.backend_repo.get_by_id(to_backend_release_id)
        if not to_release or to_release.tool_id != tool.id:
            raise BackendReleaseNotFoundError("Target backend release not found")
        
        return compute_schema_diff(
            from_release.input_schema or {},
            to_release.input_schema or {},
        )

    async def archive_release_by_tool_id(self, tool_id: UUID, version: int) -> ToolRelease:
        """Archive a release by tool UUID"""
        release = await self.get_release_by_tool_id(tool_id, version)
        return await self._archive_release(release)

    async def archive_release(self, tool_slug: str, version: int) -> ToolRelease:
        """Archive a release"""
        release = await self.get_release(tool_slug, version)
        return await self._archive_release(release)

    async def _archive_release(self, release: ToolRelease) -> ToolRelease:
        if release.status == ToolReleaseStatus.ARCHIVED.value:
            raise ReleaseNotEditableError("Release is already archived")

        tool = await self.tool_repo.get_by_id(release.tool_id)
        if tool and tool.current_version_id == release.id:
            tool.current_version_id = None
            await self.tool_repo.update(tool)

        release.status = ToolReleaseStatus.ARCHIVED.value
        await self.release_repo.update(release)
        await self.session.commit()

        logger.info(f"Archived release v{release.version} for tool '{release.tool_id}'")
        return release

    async def delete_release_by_tool_id(self, tool_id: UUID, version: int) -> None:
        """Delete release by tool UUID. Only active/archived are allowed and current cannot be deleted."""
        release = await self.get_release_by_tool_id(tool_id, version)
        if release.status not in {
            ToolReleaseStatus.ACTIVE.value,
            ToolReleaseStatus.ARCHIVED.value,
        }:
            raise ReleaseNotEditableError(
                f"Only active or archived releases can be deleted (current: {release.status})"
            )

        tool = await self.tool_repo.get_by_id(release.tool_id)
        if tool and tool.current_version_id == release.id:
            raise ReleasePinnedError("Cannot delete current release. Rebind another active release first.")

        await self.release_repo.delete(release)
        await self.session.commit()

    async def set_current_version_by_id(self, tool_id: UUID, release_id: UUID) -> Tool:
        """Set current version for a tool by UUID"""
        tool = await self.get_tool_by_id(tool_id)
        release = await self.release_repo.get_by_id(release_id)

        if not release or release.tool_id != tool.id:
            raise ReleaseNotFoundError("Release not found for this tool")

        if release.status != ToolReleaseStatus.ACTIVE.value:
            raise ReleaseNotEditableError("Only active releases can be set as current")

        tool.current_version_id = release_id
        await self.tool_repo.update(tool)
        await self.session.commit()

        logger.info(f"Set current version for tool '{tool_id}' to release '{release_id}'")
        return tool
