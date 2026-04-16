"""
ToolRouter — selects the best ToolRelease for a given (tool_slug, op).

LLM/Planner NEVER chooses release. Only ToolRouter does.

Selection algorithm:
1. Filter candidates by tool_slug + op ∈ routing_ops
2. Remove deprecated/archived
3. Sort: lower risk → idempotent=true → pinned/active preference
4. Pick first
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.available_actions import _normalize_risk
from app.core.exceptions import ToolRouterError
from app.core.logging import get_logger
from app.models.tool import Tool
from app.models.tool_release import ToolRelease, ToolReleaseStatus

logger = get_logger(__name__)

RISK_ORDER = {"low": 0, "medium": 1, "high": 2}


@dataclass
class ToolReleaseSelection:
    """Result of ToolRouter.select()"""
    tool_release_id: UUID
    tool_slug: str
    op: str
    version: int
    reason: str
    exec_timeout_s: Optional[int] = None



class ToolRouter:
    """Selects the best ToolRelease for a (tool_slug, op) pair."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def select(
        self,
        tool_slug: str,
        op: str,
        *,
        pinned_release_id: Optional[UUID] = None,
        prefer_idempotent: bool = True,
        prefer_lower_risk: bool = True,
    ) -> ToolReleaseSelection:
        """
        Select best release for tool_slug + op.

        Args:
            tool_slug: Tool slug from planner NextAction
            op: Operation from planner NextAction
            pinned_release_id: If set, prefer this specific release
            prefer_idempotent: Sort idempotent=true first
            prefer_lower_risk: Sort lower risk first

        Returns:
            ToolReleaseSelection with chosen release

        Raises:
            ToolRouterError if no suitable release found
        """
        stmt = (
            select(ToolRelease, Tool.slug.label("tool_slug_col"))
            .join(Tool, Tool.id == ToolRelease.tool_id)
            .where(
                Tool.slug == tool_slug,
                ToolRelease.status != ToolReleaseStatus.ARCHIVED.value,
            )
        )
        result = await self.session.execute(stmt)
        rows = result.all()

        if not rows:
            raise ToolRouterError(
                f"No releases found for tool '{tool_slug}'"
            )

        # Filter by op ∈ routing_ops (or accept if routing_ops is empty/null)
        candidates: List[ToolRelease] = []
        for release, _ in rows:
            ops = release.routing_ops or []
            if not ops or op in ops:
                candidates.append(release)

        if not candidates:
            available_ops = set()
            for release, _ in rows:
                for o in (release.routing_ops or []):
                    available_ops.add(o)
            raise ToolRouterError(
                f"No release for tool '{tool_slug}' supports op '{op}'. "
                f"Available ops: {sorted(available_ops) or ['(none)']}"
            )

        # Strict pinned behavior: if pinned_release_id is passed, it must be used.
        if pinned_release_id:
            for c in candidates:
                if c.id == pinned_release_id:
                    return ToolReleaseSelection(
                        tool_release_id=c.id,
                        tool_slug=tool_slug,
                        op=op,
                        version=c.version,
                        reason=f"pinned release {c.id}",
                        exec_timeout_s=c.exec_timeout_s,
                    )
            raise ToolRouterError(
                f"Pinned release '{pinned_release_id}' for tool '{tool_slug}' "
                f"is unavailable or does not support op '{op}'"
            )

        # Sort candidates
        def sort_key(release: ToolRelease) -> tuple:
            risk = RISK_ORDER.get(
                _normalize_risk(release.routing_risk_level), 1
            )
            idempotent = 0 if release.routing_idempotent else 1
            is_active = 0 if release.status == ToolReleaseStatus.ACTIVE.value else 1
            return (
                risk if prefer_lower_risk else 0,
                idempotent if prefer_idempotent else 0,
                is_active,
                -release.version,  # newer version first
            )

        candidates.sort(key=sort_key)
        best = candidates[0]

        reason_parts = [f"v{best.version}"]
        if best.status == ToolReleaseStatus.ACTIVE.value:
            reason_parts.append("active")
        reason_parts.append(f"risk={_normalize_risk(best.routing_risk_level)}")

        return ToolReleaseSelection(
            tool_release_id=best.id,
            tool_slug=tool_slug,
            op=op,
            version=best.version,
            reason=", ".join(reason_parts),
            exec_timeout_s=best.exec_timeout_s,
        )
