from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.collection import Collection
from app.models.template_analysis_status import TemplateAnalysisStatus
from app.repositories.base import AsyncRepository

logger = get_logger(__name__)


class AsyncTemplateAnalysisStatusRepository(AsyncRepository):
    def __init__(self, session: AsyncSession, tenant_id: Optional[UUID] = None):
        super().__init__(session, TemplateAnalysisStatus)
        self.tenant_id = tenant_id

    def _build_tenant_filter(self, stmt):
        if self.tenant_id:
            stmt = stmt.join(Collection, TemplateAnalysisStatus.collection_id == Collection.id)
            stmt = stmt.where(Collection.tenant_id == self.tenant_id)
        return stmt

    async def get_nodes_by_row_id(self, row_id: UUID) -> List[TemplateAnalysisStatus]:
        stmt = select(TemplateAnalysisStatus).where(TemplateAnalysisStatus.row_id == row_id)
        stmt = self._build_tenant_filter(stmt)
        stmt = stmt.order_by(TemplateAnalysisStatus.node_key)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_node(self, row_id: UUID, node_key: str) -> Optional[TemplateAnalysisStatus]:
        stmt = select(TemplateAnalysisStatus).where(
            TemplateAnalysisStatus.row_id == row_id,
            TemplateAnalysisStatus.node_key == node_key,
        )
        stmt = self._build_tenant_filter(stmt)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert_node(
        self,
        *,
        collection_id: UUID,
        row_id: UUID,
        node_key: str,
        status: str,
        celery_task_id: Optional[str] = None,
        error_short: Optional[str] = None,
        metrics_json: Optional[Dict[str, Any]] = None,
        started_at: Optional[datetime] = None,
        finished_at: Optional[datetime] = None,
    ) -> TemplateAnalysisStatus:
        existing = await self.get_node(row_id, node_key)
        if existing:
            existing.collection_id = collection_id
            existing.status = status
            if celery_task_id is not None:
                existing.celery_task_id = celery_task_id
            existing.error_short = error_short
            existing.metrics_json = metrics_json
            if started_at:
                existing.started_at = started_at
            if finished_at:
                existing.finished_at = finished_at
            existing.updated_at = datetime.now(timezone.utc)
            await self.session.flush()
            return existing

        node = TemplateAnalysisStatus(
            collection_id=collection_id,
            row_id=row_id,
            node_key=node_key,
            status=status,
            celery_task_id=celery_task_id,
            error_short=error_short,
            metrics_json=metrics_json,
            started_at=started_at,
            finished_at=finished_at,
        )
        self.session.add(node)
        await self.session.flush()
        return node

    async def delete_nodes_by_row_id(self, collection_id: UUID, row_id: UUID) -> int:
        stmt = delete(TemplateAnalysisStatus).where(
            TemplateAnalysisStatus.collection_id == collection_id,
            TemplateAnalysisStatus.row_id == row_id,
        )
        if self.tenant_id:
            stmt = stmt.where(
                TemplateAnalysisStatus.collection_id.in_(
                    select(Collection.id).where(Collection.tenant_id == self.tenant_id)
                )
            )
        result = await self.session.execute(stmt)
        return int(result.rowcount or 0)

    async def get_failed_row_ids(self, collection_id: UUID) -> set[UUID]:
        stmt = select(TemplateAnalysisStatus.row_id).where(
            TemplateAnalysisStatus.collection_id == collection_id,
            TemplateAnalysisStatus.status == "failed",
        ).distinct()
        result = await self.session.execute(stmt)
        return {UUID(str(row_id)) for (row_id,) in result.all()}
