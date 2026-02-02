"""
Service for managing baselines and their versions.
Baseline is a separate entity from Prompt for managing restrictions and rules.
"""
from typing import Dict, Any, List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.baseline import Baseline, BaselineVersion, BaselineStatus, BaselineScope
from app.repositories.baseline_repository import BaselineRepository, BaselineVersionRepository
from app.core.exceptions import NotFoundException, ValidationException


class BaselineService:
    """Service for managing baselines and their versions"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.baseline_repo = BaselineRepository(session)
        self.version_repo = BaselineVersionRepository(session)

    # ─────────────────────────────────────────────────────────────────────────
    # BASELINE CONTAINER operations
    # ─────────────────────────────────────────────────────────────────────────

    async def create_baseline(
        self,
        slug: str,
        name: str,
        description: Optional[str] = None,
        scope: str = BaselineScope.DEFAULT.value,
        tenant_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
        is_active: bool = True,
    ) -> Baseline:
        """Create new baseline container"""
        # Check if slug already exists
        existing = await self.baseline_repo.get_by_slug(slug)
        if existing:
            raise ValidationException(f"Baseline with slug '{slug}' already exists")
        
        # Validate scope constraints
        if scope == BaselineScope.TENANT.value and not tenant_id:
            raise ValidationException("tenant_id is required for tenant scope")
        if scope == BaselineScope.USER.value and not user_id:
            raise ValidationException("user_id is required for user scope")
        if scope == BaselineScope.DEFAULT.value:
            tenant_id = None
            user_id = None
        
        baseline = Baseline(
            slug=slug,
            name=name,
            description=description,
            scope=scope,
            tenant_id=tenant_id,
            user_id=user_id,
            is_active=is_active,
        )
        
        return await self.baseline_repo.create(baseline)

    async def get_baseline_by_slug(self, slug: str) -> Baseline:
        """Get baseline container by slug"""
        baseline = await self.baseline_repo.get_by_slug(slug)
        if not baseline:
            raise NotFoundException(f"Baseline '{slug}' not found")
        return baseline

    async def get_baseline_by_id(self, baseline_id: UUID) -> Baseline:
        """Get baseline container by ID"""
        baseline = await self.baseline_repo.get_by_id(baseline_id)
        if not baseline:
            raise NotFoundException(f"Baseline not found")
        return baseline

    async def update_baseline(
        self,
        baseline_id: UUID,
        name: Optional[str] = None,
        description: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> Baseline:
        """Update baseline container metadata"""
        baseline = await self.get_baseline_by_id(baseline_id)
        
        update_data = {}
        if name is not None:
            update_data['name'] = name
        if description is not None:
            update_data['description'] = description
        if is_active is not None:
            update_data['is_active'] = is_active
        
        if update_data:
            return await self.baseline_repo.update(baseline, update_data)
        return baseline

    async def list_baselines(
        self,
        skip: int = 0,
        limit: int = 100,
        scope_filter: Optional[str] = None,
        tenant_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
        is_active: Optional[bool] = None,
    ):
        """List baseline containers"""
        return await self.baseline_repo.list_baselines(
            skip, limit, scope_filter, tenant_id, user_id, is_active
        )

    async def delete_baseline(self, baseline_id: UUID) -> bool:
        """Delete baseline container"""
        return await self.baseline_repo.delete(baseline_id)

    async def get_effective_baselines(
        self,
        tenant_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
    ) -> List[Baseline]:
        """
        Get effective baselines for a user/tenant.
        Resolution priority: User > Tenant > Default
        Returns all applicable baselines.
        """
        return await self.baseline_repo.get_effective_baselines(tenant_id, user_id)

    async def get_merged_baseline_content(
        self,
        tenant_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
    ) -> str:
        """
        Get merged baseline content for a user/tenant.
        Combines all applicable baselines into a single string.
        """
        baselines = await self.get_effective_baselines(tenant_id, user_id)
        
        contents = []
        for baseline in baselines:
            active_version = await self.version_repo.get_active_by_baseline(baseline.id)
            if active_version:
                contents.append(f"# {baseline.name}\n{active_version.template}")
        
        return "\n\n".join(contents)

    # ─────────────────────────────────────────────────────────────────────────
    # VERSION operations
    # ─────────────────────────────────────────────────────────────────────────

    async def create_version(
        self,
        slug: str,
        template: str,
        parent_version_id: Optional[UUID] = None,
        notes: Optional[str] = None,
    ) -> BaselineVersion:
        """Create new version for a baseline"""
        baseline = await self.get_baseline_by_slug(slug)
        
        # Check if there's already a draft
        if await self.version_repo.has_draft(baseline.id):
            raise ValidationException(
                f"Baseline '{slug}' already has a draft version. "
                "Edit the existing draft or activate it first."
            )
        
        next_version = await self.version_repo.get_next_version(baseline.id)
        
        version = BaselineVersion(
            baseline_id=baseline.id,
            template=template,
            version=next_version,
            status=BaselineStatus.DRAFT.value,
            parent_version_id=parent_version_id,
            notes=notes,
        )
        
        return await self.version_repo.create(version)

    async def get_version(self, version_id: UUID) -> BaselineVersion:
        """Get version by ID"""
        version = await self.version_repo.get_by_id(version_id)
        if not version:
            raise NotFoundException("Version not found")
        return version

    async def get_active_version(self, slug: str) -> Optional[BaselineVersion]:
        """Get active version of a baseline"""
        baseline = await self.get_baseline_by_slug(slug)
        return await self.version_repo.get_active_by_baseline(baseline.id)

    async def get_versions(self, slug: str) -> List[BaselineVersion]:
        """Get all versions of a baseline"""
        baseline = await self.get_baseline_by_slug(slug)
        return await self.version_repo.get_all_by_baseline(baseline.id)

    async def update_version(
        self,
        version_id: UUID,
        template: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> BaselineVersion:
        """Update a draft version"""
        version = await self.get_version(version_id)
        
        if not version.is_editable:
            raise ValidationException("Only draft versions can be edited")
        
        update_data = {}
        if template is not None:
            update_data['template'] = template
        if notes is not None:
            update_data['notes'] = notes
        
        if update_data:
            return await self.version_repo.update(version, update_data)
        return version

    async def activate_version(self, version_id: UUID) -> BaselineVersion:
        """Activate a draft version (archives current active)"""
        version = await self.get_version(version_id)
        
        if not version.can_activate:
            raise ValidationException("Only draft versions can be activated")
        
        # Archive current active version
        await self.version_repo.archive_active_version(version.baseline_id)
        
        # Activate this version
        await self.version_repo.update_status(version_id, BaselineStatus.ACTIVE.value)
        
        # Update recommended_version_id in baseline
        baseline = await self.get_baseline_by_id(version.baseline_id)
        await self.baseline_repo.update(baseline, {'recommended_version_id': version_id})
        
        # Refresh and return
        return await self.get_version(version_id)

    async def archive_version(self, version_id: UUID) -> BaselineVersion:
        """Archive a version"""
        version = await self.get_version(version_id)
        
        if version.status == BaselineStatus.ARCHIVED.value:
            raise ValidationException("Version is already archived")
        
        await self.version_repo.update_status(version_id, BaselineStatus.ARCHIVED.value)
        
        return await self.get_version(version_id)

    async def update_recommended_version(self, slug: str, version_id: UUID) -> Baseline:
        """Set the recommended version for a baseline. Version must be active."""
        baseline = await self.get_baseline_by_slug(slug)
        version = await self.get_version(version_id)
        
        if version.baseline_id != baseline.id:
            raise ValidationException("Version does not belong to this baseline")
        
        if version.status != BaselineStatus.ACTIVE.value:
            raise ValidationException("Only active versions can be set as recommended")
        
        await self.baseline_repo.update(baseline, {'recommended_version_id': version_id})
        
        return await self.get_baseline_by_slug(slug)

    # ─────────────────────────────────────────────────────────────────────────
    # RENDERING
    # ─────────────────────────────────────────────────────────────────────────

    async def render_baseline(
        self,
        slug: str,
        version: Optional[int] = None,
    ) -> str:
        """
        Render baseline template.
        If version is not specified, uses active version.
        """
        baseline = await self.get_baseline_by_slug(slug)
        
        if version is not None:
            baseline_version = await self.version_repo.get_by_baseline_and_version(
                baseline.id, version
            )
        else:
            baseline_version = await self.version_repo.get_active_by_baseline(baseline.id)
        
        if not baseline_version:
            raise NotFoundException(
                f"No {'active ' if version is None else ''}version found for baseline '{slug}'"
            )
        
        return baseline_version.template
