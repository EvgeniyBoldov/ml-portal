"""
Limit Service - business logic for execution limits.

Architecture:
- Limit (container) - holds metadata: slug, name, description
- LimitVersion - holds versioned data: max_steps, timeouts, etc.
- current_version_id - points to the active version

Version workflow:
- Create → always draft
- Activate → draft → active (deprecates previous active)
- Deactivate → draft or active → deprecated
"""
import logging
from typing import List, Optional, Tuple, Dict, Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    LimitNotFoundError,
    LimitVersionNotFoundError,
    LimitAlreadyExistsError,
    LimitVersionNotEditableError,
    AppError as LimitError,
)
from app.models.limit import Limit, LimitVersion, LimitStatus
from app.repositories.limit_repository import LimitRepository, LimitVersionRepository

logger = logging.getLogger(__name__)


class LimitService:
    """Service for managing limits and their versions"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.limit_repo = LimitRepository(session)
        self.version_repo = LimitVersionRepository(session)

    # ─────────────────────────────────────────────────────────────────────────
    # LIMIT CONTAINER operations
    # ─────────────────────────────────────────────────────────────────────────

    async def create_limit(
        self,
        slug: str,
        name: str,
        description: Optional[str] = None,
    ) -> Limit:
        existing = await self.limit_repo.get_by_slug(slug)
        if existing:
            raise LimitAlreadyExistsError(f"Limit with slug '{slug}' already exists")

        limit = Limit(
            slug=slug,
            name=name,
            description=description,
        )

        return await self.limit_repo.create(limit)

    async def get_limit(self, limit_id: UUID) -> Limit:
        limit = await self.limit_repo.get_by_id(limit_id)
        if not limit:
            raise LimitNotFoundError(f"Limit '{limit_id}' not found")
        return limit

    async def get_limit_by_slug(self, slug: str) -> Limit:
        limit = await self.limit_repo.get_by_slug(slug)
        if not limit:
            raise LimitNotFoundError(f"Limit '{slug}' not found")
        return limit

    async def get_limit_with_versions(self, slug: str) -> Limit:
        limit = await self.limit_repo.get_by_slug_with_versions(slug)
        if not limit:
            raise LimitNotFoundError(f"Limit '{slug}' not found")
        return limit

    async def update_limit(
        self,
        limit_id: UUID,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Limit:
        limit = await self.get_limit(limit_id)

        update_data = {}
        if name is not None:
            update_data['name'] = name
        if description is not None:
            update_data['description'] = description

        if update_data:
            return await self.limit_repo.update(limit, update_data)
        return limit

    async def delete_limit(self, limit_id: UUID) -> None:
        limit = await self.get_limit(limit_id)

        if limit.slug == "default":
            raise LimitError("Cannot delete the default limit")

        await self.limit_repo.delete(limit)

    async def list_limits(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> Tuple[List[Limit], int]:
        return await self.limit_repo.list_limits(skip, limit)

    async def get_default_limit(self) -> Optional[Limit]:
        return await self.limit_repo.get_default()

    # ─────────────────────────────────────────────────────────────────────────
    # LIMIT VERSION operations
    # ─────────────────────────────────────────────────────────────────────────

    async def create_version(
        self,
        limit_slug: str,
        max_steps: Optional[int] = None,
        max_tool_calls: Optional[int] = None,
        max_wall_time_ms: Optional[int] = None,
        tool_timeout_ms: Optional[int] = None,
        max_retries: Optional[int] = None,
        extra_config: Optional[Dict[str, Any]] = None,
        notes: Optional[str] = None,
        parent_version_id: Optional[UUID] = None,
    ) -> LimitVersion:
        """
        Create a new limit version (always draft).

        If parent_version_id is provided, inherits all limit fields
        from the parent version. Explicit values override inherited ones.
        """
        limit = await self.get_limit_by_slug(limit_slug)
        next_version = await self.version_repo.get_next_version(limit.id)

        # Inherit from parent version if specified
        inherited = {
            'max_steps': None,
            'max_tool_calls': None,
            'max_wall_time_ms': None,
            'tool_timeout_ms': None,
            'max_retries': None,
            'extra_config': {},
        }

        if parent_version_id:
            parent = await self.version_repo.get_by_id(parent_version_id)
            if parent and parent.limit_id == limit.id:
                inherited['max_steps'] = parent.max_steps
                inherited['max_tool_calls'] = parent.max_tool_calls
                inherited['max_wall_time_ms'] = parent.max_wall_time_ms
                inherited['tool_timeout_ms'] = parent.tool_timeout_ms
                inherited['max_retries'] = parent.max_retries
                inherited['extra_config'] = parent.extra_config or {}
                logger.info(
                    f"Inheriting from v{parent.version} for limit '{limit_slug}'"
                )
            else:
                logger.warning(
                    f"Parent version {parent_version_id} not found or belongs to another limit"
                )

        version = LimitVersion(
            limit_id=limit.id,
            version=next_version,
            status=LimitStatus.DRAFT.value,
            max_steps=max_steps if max_steps is not None else inherited['max_steps'],
            max_tool_calls=max_tool_calls if max_tool_calls is not None else inherited['max_tool_calls'],
            max_wall_time_ms=max_wall_time_ms if max_wall_time_ms is not None else inherited['max_wall_time_ms'],
            tool_timeout_ms=tool_timeout_ms if tool_timeout_ms is not None else inherited['tool_timeout_ms'],
            max_retries=max_retries if max_retries is not None else inherited['max_retries'],
            extra_config=extra_config if extra_config is not None else inherited['extra_config'],
            notes=notes,
            parent_version_id=parent_version_id,
        )

        return await self.version_repo.create(version)

    async def get_version(self, version_id: UUID) -> LimitVersion:
        version = await self.version_repo.get_by_id(version_id)
        if not version:
            raise LimitVersionNotFoundError(f"Limit version '{version_id}' not found")
        return version

    async def get_version_by_number(
        self,
        limit_slug: str,
        version_number: int
    ) -> LimitVersion:
        limit = await self.get_limit_by_slug(limit_slug)
        version = await self.version_repo.get_by_limit_and_version(limit.id, version_number)
        if not version:
            raise LimitVersionNotFoundError(
                f"Version {version_number} not found for limit '{limit_slug}'"
            )
        return version

    async def list_versions(
        self,
        limit_slug: str,
        status_filter: Optional[str] = None
    ) -> List[LimitVersion]:
        limit = await self.get_limit_by_slug(limit_slug)
        return await self.version_repo.get_all_by_limit(limit.id, status_filter)

    async def update_version(
        self,
        version_id: UUID,
        max_steps: Optional[int] = None,
        max_tool_calls: Optional[int] = None,
        max_wall_time_ms: Optional[int] = None,
        tool_timeout_ms: Optional[int] = None,
        max_retries: Optional[int] = None,
        extra_config: Optional[Dict[str, Any]] = None,
        notes: Optional[str] = None,
    ) -> LimitVersion:
        version = await self.get_version(version_id)

        if not version.is_editable:
            raise LimitVersionNotEditableError(
                f"Version {version.version} is not editable (status: {version.status})"
            )

        update_data = {}
        if max_steps is not None:
            update_data['max_steps'] = max_steps
        if max_tool_calls is not None:
            update_data['max_tool_calls'] = max_tool_calls
        if max_wall_time_ms is not None:
            update_data['max_wall_time_ms'] = max_wall_time_ms
        if tool_timeout_ms is not None:
            update_data['tool_timeout_ms'] = tool_timeout_ms
        if max_retries is not None:
            update_data['max_retries'] = max_retries
        if extra_config is not None:
            update_data['extra_config'] = extra_config
        if notes is not None:
            update_data['notes'] = notes

        if update_data:
            return await self.version_repo.update(version, update_data)
        return version

    async def delete_version(self, version_id: UUID) -> None:
        version = await self.get_version(version_id)

        if version.status == LimitStatus.ACTIVE.value:
            raise LimitError("Cannot delete active version. Deactivate it first.")

        await self.version_repo.delete(version)

    async def activate_version(self, version_id: UUID) -> LimitVersion:
        """
        Activate a version (draft → active).
        Deprecates the currently active version.
        Updates current_version_id on the limit.
        """
        version = await self.get_version(version_id)

        if not version.can_activate:
            raise LimitError(
                f"Version {version.version} cannot be activated (status: {version.status})"
            )

        await self.version_repo.deactivate_active_version(version.limit_id)
        await self.version_repo.update_status(version_id, LimitStatus.ACTIVE.value)

        limit = await self.limit_repo.get_by_id(version.limit_id)
        await self.limit_repo.update(limit, {'current_version_id': version_id})

        return await self.get_version(version_id)

    async def deactivate_version(self, version_id: UUID) -> LimitVersion:
        version = await self.get_version(version_id)

        if not version.can_deactivate:
            raise LimitError(
                f"Version {version.version} cannot be deactivated (status: {version.status})"
            )

        await self.version_repo.update_status(version_id, LimitStatus.DEPRECATED.value)

        limit = await self.limit_repo.get_by_id(version.limit_id)
        if limit.current_version_id == version_id:
            await self.limit_repo.update(limit, {'current_version_id': None})

        return await self.get_version(version_id)

    # ─────────────────────────────────────────────────────────────────────────
    # EFFECTIVE LIMITS (for runtime)
    # ─────────────────────────────────────────────────────────────────────────

    async def get_effective_limits(self, limit_id: Optional[UUID]) -> Dict[str, Any]:
        """
        Get effective limits from a limit's current version.
        Falls back to default limit if limit_id is None.
        """
        limit = None
        if limit_id:
            limit = await self.limit_repo.get_by_id(limit_id)

        if not limit:
            limit = await self.limit_repo.get_default()

        if not limit:
            return self._get_fallback_limits()

        version = None
        if limit.current_version_id:
            version = await self.version_repo.get_by_id(limit.current_version_id)

        if not version:
            version = await self.version_repo.get_active_by_limit(limit.id)

        if not version:
            return self._get_fallback_limits()

        return {
            "max_steps": version.max_steps,
            "max_tool_calls": version.max_tool_calls,
            "max_wall_time_ms": version.max_wall_time_ms,
            "tool_timeout_ms": version.tool_timeout_ms,
            "max_retries": version.max_retries,
            **version.extra_config,
        }

    def _get_fallback_limits(self) -> Dict[str, Any]:
        return {
            "max_steps": 20,
            "max_tool_calls": 50,
            "max_wall_time_ms": 300000,
            "tool_timeout_ms": 30000,
            "max_retries": 3,
        }
