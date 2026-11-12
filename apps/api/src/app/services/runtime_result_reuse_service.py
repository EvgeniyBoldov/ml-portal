"""Authorized cross-turn discovery and import of immutable Result Store snapshots."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.runtime_run_context_repository import RuntimeRunContextRepository
from app.services.tool_result_store import ResultSnapshotUnavailable, ToolResultStore


class RuntimeResultReuseService:
    """Join primary run ownership with Result Store user/tenant/TTL checks."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.run_contexts = RuntimeRunContextRepository(session)
        self.results = ToolResultStore()

    async def authorize_source_runs(
        self, *, run_ids: list[str], chat_id: str, owner_id: str,
        branch_id: str | None,
    ) -> list[str]:
        rows = await self.run_contexts.owned_many(
            run_ids=run_ids, chat_id=chat_id, owner_id=owner_id, branch_id=branch_id,
        )
        return [str(row.id) for row in rows]

    async def list_prior_snapshots(
        self, *, source_run_id: str, current_chat_id: str, owner_id: str,
        branch_id: str | None, tenant_id: UUID, user_id: UUID,
        offset: int = 0, limit: int = 30, selected_result_ids: list[str] | None = None,
        current_run_id: str | None = None,
    ) -> dict[str, Any]:
        if current_run_id is not None and source_run_id == current_run_id:
            raise ResultSnapshotUnavailable()
        await self._require_owned_source_run(
            source_run_id=source_run_id, chat_id=current_chat_id,
            owner_id=owner_id, branch_id=branch_id,
        )
        return await self.results.list_prior_snapshots(
            source_run_id=source_run_id, tenant_id=tenant_id, user_id=user_id,
            offset=offset, limit=limit, selected_result_ids=selected_result_ids,
        )

    async def import_snapshot(
        self, *, source_run_id: str, result_id: str, revision: int,
        current_run_id: str, current_chat_id: str, owner_id: str,
        branch_id: str | None, tenant_id: UUID, user_id: UUID,
        task_id: str | None = None, agent_execution_id: str | None = None,
    ) -> dict[str, Any]:
        if source_run_id == current_run_id:
            raise ResultSnapshotUnavailable()
        await self._require_owned_source_run(
            source_run_id=source_run_id, chat_id=current_chat_id,
            owner_id=owner_id, branch_id=branch_id,
        )
        return await self.results.import_snapshot(
            source_run_id=source_run_id, source_result_id=result_id,
            source_revision=revision, target_run_id=current_run_id,
            target_tenant_id=tenant_id, target_user_id=user_id,
            target_task_id=task_id, target_agent_execution_id=agent_execution_id,
        )

    async def _require_owned_source_run(
        self, *, source_run_id: str, chat_id: str, owner_id: str,
        branch_id: str | None,
    ) -> None:
        try:
            UUID(source_run_id)
            UUID(chat_id)
            UUID(owner_id)
        except (TypeError, ValueError) as exc:
            raise ResultSnapshotUnavailable() from exc
        owned = await self.run_contexts.owned(
            run_id=source_run_id, chat_id=chat_id, owner_id=owner_id,
            branch_id=branch_id,
        )
        if owned is None:
            raise ResultSnapshotUnavailable()
