"""Application-owned LongMemory lifecycle and status projection."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.long_memory_document import LongMemoryDocumentOperation
from app.models.rag_ingest import Source
from app.repositories.long_memory_document_repository import LongMemoryDocumentRepository
from app.repositories.rag_status_repo import AsyncRAGStatusRepository


class LongMemoryDocumentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = LongMemoryDocumentRepository(session)

    async def enqueue(self, document_id: UUID, action: Literal["add", "delete"], *,
                      automatic: bool = False, ingest_run_id: str | None = None) -> LongMemoryDocumentOperation | None:
        document = await self.repository.lock_document(document_id)
        if document is None:
            raise ValueError("Document not found")
        if action == "add" and (document.status == "archived" or not document.s3_key_processed):
            raise ValueError("Canonical document is unavailable")
        if automatic and not await self.repository.enabled(document_id):
            return None
        previous = await self.repository.latest(document_id)
        if previous and previous.action == action and (
            (previous.status in {"pending", "running"} and previous.payload.get("canonical_key") == document.s3_key_processed) or ingest_run_id and previous.payload.get("ingest_run_id") == ingest_run_id
        ):
            return previous
        document.long_memory_generation = int(document.long_memory_generation or 0) + 1
        operation = LongMemoryDocumentOperation(document_id=document_id, tenant_id=document.tenant_id,
            generation=document.long_memory_generation, action=action,
            payload={"canonical_key": document.s3_key_processed, "ingest_run_id": ingest_run_id})
        self.session.add(operation)
        if not automatic:
            source = await self.session.get(Source, document_id)
            if source:
                source.meta = {**dict(source.meta or {}), "memory": {
                    **dict((source.meta or {}).get("memory") or {}), "policy": "explicit", "enabled": action == "add"}}
        await self.session.flush()
        await self.project(operation, {"status": "queued", "action": action, "steps": {
            "extract": {"status": "queued", "metrics": {"action": action}},
            "index": {"status": "queued", "metrics": {"action": action}}}})
        return operation

    async def project(self, operation: LongMemoryDocumentOperation, progress: dict[str, Any]) -> bool:
        operation.progress = progress
        operation.updated_at = datetime.now(timezone.utc)
        document = await self.repository.lock_document(operation.document_id)
        if document is None or document.long_memory_generation != operation.generation:
            return False
        repo = AsyncRAGStatusRepository(self.session)
        for step, value in progress.get("steps", {}).items():
            if step not in {"extract", "index"}:
                continue
            status = value["status"]
            node = await repo.upsert_node(doc_id=document.id, node_type="memory", node_key="knowledge" if step == "extract" else "graph",
                status="processing" if status == "running" else status, error_short=progress.get("error"),
                metrics_json={**dict(value.get("metrics") or {}), "action": operation.action},
                started_at=datetime.fromisoformat(value["started_at"]) if value.get("started_at") else None,
                finished_at=datetime.fromisoformat(value["finished_at"]) if value.get("finished_at") else None)
            node.started_at = datetime.fromisoformat(value["started_at"]) if value.get("started_at") else None
            node.finished_at = datetime.fromisoformat(value["finished_at"]) if value.get("finished_at") else None

        return True

    async def inspection(self, document_id: UUID) -> dict[str, Any]:
        operation = await self.repository.latest(document_id)
        return {"document_id": str(document_id), "operation_id": str(operation.id) if operation else None,
            "status": operation.status if operation else "not_queued", "action": operation.action if operation else None,
            "progress": operation.progress if operation else {}, "error": operation.error if operation else None}


async def document_memory_nodes(session: AsyncSession, document_id: UUID) -> list[dict[str, Any]]:
    nodes = await LongMemoryDocumentRepository(session).nodes(document_id)
    by_key = {node.node_key: node for node in nodes}
    result = []
    for key in ("knowledge", "graph"):
        node = by_key.get(key)
        if node:
            result.append({"key": key, "status": node.status, "error": node.error_short,
                "metrics": node.metrics_json, "started_at": node.started_at.isoformat() if node.started_at else None,
                "finished_at": node.finished_at.isoformat() if node.finished_at else None,
                "updated_at": node.updated_at.isoformat()})
    return result
