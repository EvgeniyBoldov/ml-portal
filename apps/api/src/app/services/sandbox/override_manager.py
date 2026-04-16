from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID

from app.models.sandbox import SandboxOverride


class SandboxOverrideManager:
    """Runtime override entities lifecycle."""

    def __init__(self, host) -> None:
        self.host = host

    async def create_override(
        self,
        *,
        session_id: UUID,
        entity_type: str,
        label: str,
        config_snapshot: Dict[str, Any],
        entity_id: Optional[UUID] = None,
        is_active: bool = False,
    ) -> SandboxOverride:
        if is_active:
            await self.host.overrides.deactivate_siblings(
                session_id, entity_type, entity_id
            )
        obj = SandboxOverride(
            session_id=session_id,
            entity_type=entity_type,
            entity_id=entity_id,
            label=label,
            is_active=is_active,
            config_snapshot=config_snapshot,
        )
        result = await self.host.overrides.create(obj)
        await self.host.sessions.touch(session_id)
        return result

    async def update_override(self, override_id: UUID, data: dict) -> Optional[SandboxOverride]:
        obj = await self.host.overrides.get_by_id(override_id)
        if not obj:
            return None
        if data.get("is_active"):
            await self.host.overrides.deactivate_siblings(
                obj.session_id, obj.entity_type, obj.entity_id
            )
        result = await self.host.overrides.update(obj, data)
        await self.host.sessions.touch(obj.session_id)
        return result

    async def activate_override(self, override_id: UUID) -> Optional[SandboxOverride]:
        obj = await self.host.overrides.get_by_id(override_id)
        if not obj:
            return None
        await self.host.overrides.deactivate_siblings(
            obj.session_id, obj.entity_type, obj.entity_id
        )
        result = await self.host.overrides.update(obj, {"is_active": True})
        await self.host.sessions.touch(obj.session_id)
        return result

    async def delete_override(self, override_id: UUID) -> bool:
        obj = await self.host.overrides.get_by_id(override_id)
        if not obj:
            return False
        session_id = obj.session_id
        await self.host.overrides.delete(obj)
        await self.host.sessions.touch(session_id)
        return True

    async def reset_overrides(self, session_id: UUID) -> int:
        count = await self.host.overrides.delete_all_by_session(session_id)
        await self.host.sessions.touch(session_id)
        return count

    async def list_overrides(self, session_id: UUID) -> List[SandboxOverride]:
        return await self.host.overrides.list_by_session(session_id)

    async def get_active_overrides(self, session_id: UUID) -> List[SandboxOverride]:
        return await self.host.overrides.get_active_overrides(session_id)

