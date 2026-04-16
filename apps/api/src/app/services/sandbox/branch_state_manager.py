from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from app.models.sandbox import (
    SandboxBranch,
    SandboxBranchOverride,
    SandboxOverrideSnapshot,
)
from app.services.sandbox_override_resolver import SandboxOverrideResolver


class SandboxBranchStateManager:
    """Branch lifecycle + branch overrides + immutable snapshots."""

    def __init__(self, host) -> None:
        self.host = host

    async def list_branches(self, session_id: UUID) -> List[SandboxBranch]:
        return await self.host.branches.list_by_session(session_id)

    async def get_branch(self, branch_id: UUID) -> Optional[SandboxBranch]:
        return await self.host.branches.get_by_id(branch_id)

    async def create_branch(
        self,
        *,
        session_id: UUID,
        user_id: UUID,
        name: str,
        parent_branch_id: Optional[UUID] = None,
        parent_run_id: Optional[UUID] = None,
    ) -> SandboxBranch:
        branch = SandboxBranch(
            session_id=session_id,
            name=name,
            created_by=user_id,
            parent_branch_id=parent_branch_id,
            parent_run_id=parent_run_id,
        )
        return await self.host.branches.create(branch)

    async def fork_branch(
        self,
        *,
        session_id: UUID,
        source_branch_id: UUID,
        user_id: UUID,
        name: str,
        parent_run_id: Optional[UUID] = None,
        copy_overrides: bool = True,
    ) -> SandboxBranch:
        new_branch = await self.create_branch(
            session_id=session_id,
            user_id=user_id,
            name=name,
            parent_branch_id=source_branch_id,
            parent_run_id=parent_run_id,
        )
        if copy_overrides:
            source_overrides = await self.host.branch_overrides.list_by_branch(source_branch_id)
            for override in source_overrides:
                copied = SandboxBranchOverride(
                    branch_id=new_branch.id,
                    entity_type=override.entity_type,
                    entity_id=override.entity_id,
                    field_path=override.field_path,
                    value_json=override.value_json,
                    value_type=override.value_type,
                    updated_by=user_id,
                )
                await self.host.branch_overrides.create(copied)
        return new_branch

    async def list_branch_overrides(self, branch_id: UUID) -> List[SandboxBranchOverride]:
        return await self.host.branch_overrides.list_by_branch(branch_id)

    async def upsert_branch_override(
        self,
        *,
        branch_id: UUID,
        user_id: UUID,
        entity_type: str,
        field_path: str,
        value_json: Dict[str, Any] | List[Any] | str | int | float | bool | None,
        value_type: str = "json",
        entity_id: Optional[UUID] = None,
    ) -> SandboxBranchOverride:
        existing = await self.host.branch_overrides.get_by_unique_key(
            branch_id=branch_id,
            entity_type=entity_type,
            entity_id=entity_id,
            field_path=field_path,
        )
        if existing:
            return await self.host.branch_overrides.update(
                existing,
                {
                    "value_json": value_json,
                    "value_type": value_type,
                    "updated_by": user_id,
                },
            )

        item = SandboxBranchOverride(
            branch_id=branch_id,
            entity_type=entity_type,
            entity_id=entity_id,
            field_path=field_path,
            value_json=value_json,
            value_type=value_type,
            updated_by=user_id,
        )
        return await self.host.branch_overrides.create(item)

    async def delete_branch_override(
        self,
        *,
        branch_id: UUID,
        entity_type: str,
        field_path: str,
        entity_id: Optional[UUID] = None,
    ) -> bool:
        existing = await self.host.branch_overrides.get_by_unique_key(
            branch_id=branch_id,
            entity_type=entity_type,
            entity_id=entity_id,
            field_path=field_path,
        )
        if not existing:
            return False
        await self.host.branch_overrides.delete(existing)
        return True

    async def delete_branch_overrides_for_entity(
        self,
        *,
        branch_id: UUID,
        entity_type: str,
        entity_id: Optional[UUID] = None,
    ) -> int:
        return await self.host.branch_overrides.delete_by_entity(
            branch_id=branch_id,
            entity_type=entity_type,
            entity_id=entity_id,
        )

    async def reset_branch_overrides(self, branch_id: UUID) -> int:
        return await self.host.branch_overrides.delete_all_by_branch(branch_id)

    async def create_snapshot(
        self,
        *,
        session_id: UUID,
        branch_id: UUID,
        user_id: UUID,
    ) -> SandboxOverrideSnapshot:
        overrides = await self.host.branch_overrides.list_by_branch(branch_id)
        payload = {
            "resolver_fingerprint": SandboxOverrideResolver.schema_fingerprint(),
            "resolver_blueprints": SandboxOverrideResolver.describe_blueprints(),
            "overrides": [
                {
                    "id": str(ov.id),
                    "entity_type": ov.entity_type,
                    "entity_id": str(ov.entity_id) if ov.entity_id else None,
                    "field_path": ov.field_path,
                    "value_json": ov.value_json,
                    "value_type": ov.value_type,
                    "updated_by": str(ov.updated_by),
                    "updated_at": ov.updated_at.isoformat(),
                }
                for ov in overrides
            ],
            "resolved_at": datetime.now(timezone.utc).isoformat(),
        }
        payload_str = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        snapshot_hash = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()
        snapshot = SandboxOverrideSnapshot(
            session_id=session_id,
            branch_id=branch_id,
            snapshot_hash=snapshot_hash,
            payload_json=payload,
            created_by=user_id,
        )
        return await self.host.snapshots.create(snapshot)

    async def get_snapshot(self, snapshot_id: UUID) -> Optional[SandboxOverrideSnapshot]:
        return await self.host.snapshots.get_by_id(snapshot_id)

    async def resolve_effective_config_from_snapshot(
        self,
        *,
        session_id: UUID,
        branch_id: UUID,
        snapshot_id: UUID,
    ) -> Dict[str, Any]:
        snapshot = await self.host.snapshots.get_by_id(snapshot_id)
        if not snapshot or snapshot.session_id != session_id or snapshot.branch_id != branch_id:
            raise ValueError(
                f"Sandbox snapshot {snapshot_id} is missing or does not belong to session {session_id} / branch {branch_id}"
            )

        config: Dict[str, Any] = {
            "overrides": {},
            "resolved_at": datetime.now(timezone.utc).isoformat(),
            "snapshot_id": str(snapshot_id),
            "branch_id": str(branch_id),
            "resolver_fingerprint": snapshot.payload_json.get("resolver_fingerprint"),
            "resolver_blueprints": snapshot.payload_json.get("resolver_blueprints", []),
        }
        overrides = snapshot.payload_json.get("overrides", []) if snapshot.payload_json else []
        for ov in overrides:
            key_parts = [ov.get("entity_type") or "", ov.get("entity_id") or "", ov.get("field_path") or ""]
            key = ":".join(key_parts)
            config["overrides"][key] = {
                "override_id": ov.get("id"),
                "entity_type": ov.get("entity_type"),
                "entity_id": ov.get("entity_id"),
                "field_path": ov.get("field_path"),
                "value_json": ov.get("value_json"),
                "value_type": ov.get("value_type"),
            }
        return config

