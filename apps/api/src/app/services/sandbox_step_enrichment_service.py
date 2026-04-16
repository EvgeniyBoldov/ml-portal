"""
SandboxStepEnrichmentService — enrichment of sandbox run step payloads.

Resolves UUID references in step_data to human-readable labels,
and injects branch/snapshot context. Extracted from sandbox/runs.py router.
"""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger

logger = get_logger(__name__)

_KNOWN_ENTITY_KEYS: frozenset[str] = frozenset({
    "agent_id",
    "agent_version_id",
    "tool_id",
    "tool_release_id",
    "current_version_id",
    "collection_id",
    "instance_id",
    "tool_instance_id",
    "data_instance_id",
    "access_via_instance_id",
})


def _as_uuid(value: object) -> Optional[uuid.UUID]:
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


class SandboxStepEnrichmentService:
    """Resolve UUID refs in step payloads and inject sandbox context labels."""

    def __init__(self, session: AsyncSession) -> None:
        self._db = session
        self._cache: dict[str, dict[str, str]] = {}

    async def enrich(
        self,
        step_data: dict,
        *,
        branch_name: Optional[str] = None,
        snapshot_hash: Optional[str] = None,
    ) -> dict:
        """Return a copy of step_data enriched with refs and context labels."""
        enriched = dict(step_data or {})

        if branch_name:
            enriched.setdefault("branch_name", branch_name)
        if snapshot_hash:
            enriched.setdefault("snapshot_hash", snapshot_hash)
        if branch_name and snapshot_hash:
            enriched.setdefault("snapshot_label", f"{branch_name}@{snapshot_hash[:8]}")

        refs: dict[str, dict[str, str]] = {}

        run_uuid = _as_uuid(enriched.get("run_id"))
        if run_uuid:
            refs["run_id"] = {
                "kind": "run",
                "id": str(run_uuid),
                "label": f"Run {str(run_uuid)[:8]}",
            }

        for key, value in list(enriched.items()):
            if key not in _KNOWN_ENTITY_KEYS:
                continue
            ref_uuid = _as_uuid(value)
            if not ref_uuid:
                continue
            ref = await self._resolve_ref(key, ref_uuid)
            if ref:
                refs[key] = ref

        if refs:
            enriched["refs"] = refs

        return enriched

    async def _resolve_ref(
        self,
        key: str,
        ref_id: uuid.UUID,
    ) -> Optional[dict[str, str]]:
        cache_key = f"{key}:{ref_id}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        ref = await self._fetch_ref(key, ref_id)
        if ref:
            self._cache[cache_key] = ref
        return ref

    async def _fetch_ref(
        self,
        key: str,
        ref_id: uuid.UUID,
    ) -> Optional[dict[str, str]]:
        from app.models.agent import Agent
        from app.models.agent_version import AgentVersion
        from app.models.tool import Tool
        from app.models.tool_release import ToolRelease
        from app.models.collection import Collection
        from app.models.tool_instance import ToolInstance

        if key == "agent_id":
            row = await self._db.scalar(select(Agent).where(Agent.id == ref_id))
            if not row:
                return None
            return {"kind": "agent", "id": str(ref_id), "label": f"{row.slug} ({row.name})"}

        if key == "agent_version_id":
            row = await self._db.scalar(select(AgentVersion).where(AgentVersion.id == ref_id))
            if not row:
                return None
            return {"kind": "agent_version", "id": str(ref_id), "label": f"v{row.version} [{row.status}]"}

        if key == "tool_id":
            row = await self._db.scalar(select(Tool).where(Tool.id == ref_id))
            if not row:
                return None
            return {"kind": "tool", "id": str(ref_id), "label": f"{row.slug} ({row.name})"}

        if key in {"tool_release_id", "current_version_id"}:
            row = await self._db.scalar(select(ToolRelease).where(ToolRelease.id == ref_id))
            if not row:
                return None
            return {"kind": "tool_release", "id": str(ref_id), "label": f"v{row.version} [{row.status}]"}

        if key == "collection_id":
            row = await self._db.scalar(select(Collection).where(Collection.id == ref_id))
            if not row:
                return None
            return {"kind": "collection", "id": str(ref_id), "label": f"{row.slug} ({row.name})"}

        if key in {"instance_id", "tool_instance_id", "data_instance_id", "access_via_instance_id"}:
            row = await self._db.scalar(select(ToolInstance).where(ToolInstance.id == ref_id))
            if not row:
                return None
            return {"kind": "instance", "id": str(ref_id), "label": f"{row.slug} ({row.name})"}

        return None
