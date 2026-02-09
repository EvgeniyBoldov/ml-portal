"""
Service for Tool Releases
"""
from typing import List, Optional, Dict, Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.schema_hash import compute_schema_diff
from app.models.tool import Tool
from app.models.tool_group import ToolGroup
from app.models.tool_release import ToolBackendRelease, ToolRelease, ToolReleaseStatus
from app.repositories.tool_release_repository import (
    ToolBackendReleaseRepository,
    ToolReleaseRepository,
    ToolWithReleasesRepository,
    ToolGroupWithToolsRepository,
)
from app.schemas.tool_releases import (
    ToolReleaseCreate,
    ToolReleaseUpdate,
    ToolGroupCreate,
    ToolGroupUpdate,
)

logger = get_logger(__name__)


class ToolReleaseServiceError(Exception):
    """Base exception for tool release service"""
    pass


class ToolNotFoundError(ToolReleaseServiceError):
    """Tool not found"""
    pass


class ToolGroupNotFoundError(ToolReleaseServiceError):
    """Tool group not found"""
    pass


class ReleaseNotFoundError(ToolReleaseServiceError):
    """Release not found"""
    pass


class BackendReleaseNotFoundError(ToolReleaseServiceError):
    """Backend release not found"""
    pass


class ReleaseNotEditableError(ToolReleaseServiceError):
    """Release is not editable (not in draft status)"""
    pass


class ToolGroupHasToolsError(ToolReleaseServiceError):
    """Cannot delete tool group with tools"""
    pass


class ToolReleaseService:
    """Service for managing tool releases"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.backend_repo = ToolBackendReleaseRepository(session)
        self.release_repo = ToolReleaseRepository(session)
        self.tool_repo = ToolWithReleasesRepository(session)
        self.group_repo = ToolGroupWithToolsRepository(session)
    
    # ─────────────────────────────────────────────────────────────────────────
    # TOOL GROUPS
    # ─────────────────────────────────────────────────────────────────────────
    
    async def list_groups(self) -> List[ToolGroup]:
        """List all tool groups"""
        return await self.group_repo.list_all()
    
    async def get_group(self, slug: str) -> ToolGroup:
        """Get tool group by slug"""
        group = await self.group_repo.get_by_slug(slug)
        if not group:
            raise ToolGroupNotFoundError(f"Tool group '{slug}' not found")
        return group
    
    async def create_group(self, data: ToolGroupCreate) -> ToolGroup:
        """Create a new tool group"""
        group = ToolGroup(
            slug=data.slug,
            name=data.name,
            description=data.description,
            type=data.type,
            description_for_router=data.description_for_router,
        )
        await self.group_repo.create(group)
        await self.session.commit()
        logger.info(f"Created tool group: {data.slug}")
        return group
    
    async def update_group(self, slug: str, data: ToolGroupUpdate) -> ToolGroup:
        """Update a tool group"""
        group = await self.get_group(slug)
        
        if data.name is not None:
            group.name = data.name
        if data.description is not None:
            group.description = data.description
        if data.type is not None:
            group.type = data.type
        if data.description_for_router is not None:
            group.description_for_router = data.description_for_router
        
        await self.group_repo.update(group)
        await self.session.commit()
        logger.info(f"Updated tool group: {slug}")
        return group
    
    async def delete_group(self, slug: str) -> None:
        """Delete a tool group"""
        group = await self.get_group(slug)
        
        if group.tools:
            raise ToolGroupHasToolsError(
                f"Cannot delete tool group '{slug}' with {len(group.tools)} tools"
            )
        
        await self.group_repo.delete(group)
        await self.session.commit()
        logger.info(f"Deleted tool group: {slug}")
    
    # ─────────────────────────────────────────────────────────────────────────
    # TOOLS
    # ─────────────────────────────────────────────────────────────────────────
    
    async def list_tools_by_group(self, group_slug: str) -> List[Tool]:
        """List all tools in a group"""
        group = await self.get_group(group_slug)
        return await self.tool_repo.list_by_group(group.id)
    
    async def get_tool(self, slug: str) -> Tool:
        """Get tool by slug"""
        tool = await self.tool_repo.get_by_slug(slug)
        if not tool:
            raise ToolNotFoundError(f"Tool '{slug}' not found")
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
    
    # ─────────────────────────────────────────────────────────────────────────
    # TOOL RELEASES (CRUD)
    # ─────────────────────────────────────────────────────────────────────────
    
    async def list_releases(self, tool_slug: str) -> List[ToolRelease]:
        """List all releases for a tool"""
        tool = await self.get_tool(tool_slug)
        return await self.release_repo.list_by_tool(tool.id)
    
    async def get_release(self, tool_slug: str, version: int) -> ToolRelease:
        """Get release by tool slug and version"""
        tool = await self.get_tool(tool_slug)
        release = await self.release_repo.get_by_tool_and_version(tool.id, version)
        if not release:
            raise ReleaseNotFoundError(
                f"Release v{version} not found for tool '{tool_slug}'"
            )
        return release
    
    async def create_release(
        self, 
        tool_slug: str, 
        data: ToolReleaseCreate,
        from_release_id: Optional[UUID] = None,
    ) -> ToolRelease:
        """
        Create a new release (draft).
        
        If from_release_id is provided, copies meta-fields from parent release
        and generates field_hints diff for new/removed schema fields.
        """
        tool = await self.get_tool(tool_slug)
        
        # Verify backend release exists
        backend_release = await self.backend_repo.get_by_id(data.backend_release_id)
        if not backend_release or backend_release.tool_id != tool.id:
            raise BackendReleaseNotFoundError(
                f"Backend release not found for tool '{tool_slug}'"
            )
        
        # Get next version number
        next_version = await self.release_repo.get_next_version(tool.id)
        
        # Inherit from parent release if specified
        parent_release = None
        if from_release_id:
            parent_release = await self.release_repo.get_by_id(from_release_id)
            if not parent_release or parent_release.tool_id != tool.id:
                raise ReleaseNotFoundError(
                    f"Parent release not found for tool '{tool_slug}'"
                )
        
        # Build release fields — explicit data takes priority over inherited
        config = data.config
        description_for_llm = data.description_for_llm
        category = data.category
        tags = data.tags
        field_hints = data.field_hints
        examples = data.examples
        return_summary = data.return_summary
        notes = data.notes
        
        if parent_release:
            # Inherit fields that were not explicitly provided (empty defaults)
            if not config:
                config = parent_release.config or {}
            if description_for_llm is None:
                description_for_llm = parent_release.description_for_llm
            if category is None:
                category = parent_release.category
            if not tags:
                tags = parent_release.tags or []
            if not field_hints:
                field_hints = dict(parent_release.field_hints or {})
            if not examples:
                examples = list(parent_release.examples or [])
            if return_summary is None:
                return_summary = parent_release.return_summary
            
            # Generate field_hints diff if backend release changed
            if parent_release.backend_release_id != data.backend_release_id:
                old_br = await self.backend_repo.get_by_id(parent_release.backend_release_id)
                if old_br:
                    diff = compute_schema_diff(
                        old_br.input_schema or {},
                        backend_release.input_schema or {},
                    )
                    # Add new fields with empty hints
                    for added in diff["added_fields"]:
                        if added["name"] not in field_hints:
                            field_hints[added["name"]] = ""
                    # Mark removed fields
                    for removed in diff["removed_fields"]:
                        if removed["name"] in field_hints:
                            field_hints[removed["name"]] = f"[REMOVED] {field_hints[removed['name']]}"
        
        release = ToolRelease(
            tool_id=tool.id,
            version=next_version,
            backend_release_id=data.backend_release_id,
            status=ToolReleaseStatus.DRAFT.value,
            config=config,
            description_for_llm=description_for_llm,
            category=category,
            tags=tags,
            field_hints=field_hints,
            examples=examples,
            return_summary=return_summary,
            notes=notes,
            parent_release_id=from_release_id,
        )
        
        await self.release_repo.create(release)
        await self.session.commit()
        
        logger.info(
            f"Created release v{next_version} for {tool_slug}"
            + (f" (inherited from v{parent_release.version})" if parent_release else "")
        )
        return await self.get_release(tool_slug, next_version)
    
    async def update_release(
        self, 
        tool_slug: str, 
        version: int, 
        data: ToolReleaseUpdate
    ) -> ToolRelease:
        """Update a release (only draft)"""
        release = await self.get_release(tool_slug, version)
        
        if release.status != ToolReleaseStatus.DRAFT.value:
            raise ReleaseNotEditableError(
                f"Release v{version} is not editable (status: {release.status})"
            )
        
        if data.backend_release_id is not None:
            # Verify backend release exists
            backend_release = await self.backend_repo.get_by_id(data.backend_release_id)
            if not backend_release or backend_release.tool_id != release.tool_id:
                raise BackendReleaseNotFoundError("Backend release not found")
            release.backend_release_id = data.backend_release_id
        
        if data.config is not None:
            release.config = data.config
        
        if data.description_for_llm is not None:
            release.description_for_llm = data.description_for_llm
        
        if data.category is not None:
            release.category = data.category
        
        if data.tags is not None:
            release.tags = data.tags
        
        if data.field_hints is not None:
            release.field_hints = data.field_hints
        
        if data.examples is not None:
            release.examples = data.examples
        
        if data.return_summary is not None:
            release.return_summary = data.return_summary
        
        if data.notes is not None:
            release.notes = data.notes
        
        await self.release_repo.update(release)
        await self.session.commit()
        
        logger.info(f"Updated release v{version} for {tool_slug}")
        return await self.get_release(tool_slug, version)
    
    async def activate_release(self, tool_slug: str, version: int) -> ToolRelease:
        """Activate a release (archive current active, fix expected_schema_hash)"""
        release = await self.get_release(tool_slug, version)
        
        if release.status != ToolReleaseStatus.DRAFT.value:
            raise ReleaseNotEditableError(
                f"Only draft releases can be activated (current: {release.status})"
            )
        
        # Archive current active release if exists
        current_active = await self.release_repo.get_active(release.tool_id)
        if current_active:
            current_active.status = ToolReleaseStatus.ARCHIVED.value
            await self.release_repo.update(current_active)
            logger.info(f"Archived release v{current_active.version} for {tool_slug}")
        
        # Fix expected_schema_hash from current backend release
        backend_release = await self.backend_repo.get_by_id(release.backend_release_id)
        if backend_release and backend_release.schema_hash:
            release.expected_schema_hash = backend_release.schema_hash
        
        # Activate new release
        release.status = ToolReleaseStatus.ACTIVE.value
        await self.release_repo.update(release)
        await self.session.commit()
        
        logger.info(
            f"Activated release v{version} for {tool_slug}"
            + (f" (expected_schema_hash={release.expected_schema_hash[:8]})" if release.expected_schema_hash else "")
        )
        return await self.get_release(tool_slug, version)
    
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
    
    async def archive_release(self, tool_slug: str, version: int) -> ToolRelease:
        """Archive a release"""
        release = await self.get_release(tool_slug, version)
        
        if release.status == ToolReleaseStatus.ARCHIVED.value:
            raise ReleaseNotEditableError("Release is already archived")
        
        # If this is the recommended release, clear it
        tool = await self.get_tool(tool_slug)
        if tool.current_version_id == release.id:
            tool.current_version_id = None
            await self.tool_repo.update(tool)
        
        release.status = ToolReleaseStatus.ARCHIVED.value
        await self.release_repo.update(release)
        await self.session.commit()
        
        logger.info(f"Archived release v{version} for {tool_slug}")
        return await self.get_release(tool_slug, version)
