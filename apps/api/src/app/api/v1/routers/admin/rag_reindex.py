from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_uow, require_admin
from app.core.security import UserCtx
from app.services.rag_batch_reindex_orchestrator import RAGBatchReindexOrchestrator

router = APIRouter(tags=["rag-reindex"])


class ReindexRunResponse(BaseModel):
    scanned: int
    queued: int
    skipped: int
    failed: int
    items: list[dict[str, str]]
    dry_run: bool


@router.post("/reindex/run", response_model=ReindexRunResponse)
async def run_rag_reindex(
    tenant_id: Optional[uuid.UUID] = Query(None),
    model_alias: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    dry_run: bool = Query(False),
    session: AsyncSession = Depends(db_uow),
    _: UserCtx = Depends(require_admin),
):
    orchestrator = RAGBatchReindexOrchestrator(session)
    result = await orchestrator.enqueue_stale_documents(
        tenant_id=tenant_id,
        model_alias=model_alias,
        limit=limit,
        dry_run=dry_run,
    )
    return ReindexRunResponse(
        scanned=result.scanned,
        queued=result.queued,
        skipped=result.skipped,
        failed=result.failed,
        items=result.items,
        dry_run=dry_run,
    )
