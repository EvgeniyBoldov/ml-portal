"""Read-only, bounded projections for the admin LongMemory experiment."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.long_memory_document import LongMemoryDocumentOperation
from app.models.memory_scope import DocumentMemoryScope, MemoryScope
from app.models.rag import RAGDocument
from app.services.hipporag_service import HippoRAGService


_EXTRACT_METRICS = ("passages", "unique_passages", "processed_passages", "entities", "facts", "extracted_triples")
_INDEX_METRICS = ("encoded_texts", "reused_vectors", "scopes_total", "scopes_completed", "scope_nodes", "scope_edges")


def _progress(operation: LongMemoryDocumentOperation | None) -> dict[str, Any]:
    return dict(operation.progress or {}) if operation else {}


def _metrics(operation: LongMemoryDocumentOperation | None) -> dict[str, int]:
    progress = _progress(operation)
    steps = progress.get("steps") or {}
    extract = (steps.get("extract") or {}).get("metrics") or {}
    index = (steps.get("index") or {}).get("metrics") or {}
    result = {key: int(extract.get(key) or 0) for key in _EXTRACT_METRICS}
    result.update({key: int(index.get(key) or 0) for key in _INDEX_METRICS})
    return result


def _status(operation: LongMemoryDocumentOperation | None) -> str:
    if operation is None:
        return "not_registered"
    if operation.action == "delete" and operation.status == "completed":
        return "deleted"
    return operation.status


class LongMemoryAdminService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _latest_operation_id(self):
        return (select(LongMemoryDocumentOperation.id)
            .where(LongMemoryDocumentOperation.document_id == RAGDocument.id)
            .order_by(LongMemoryDocumentOperation.generation.desc())
            .limit(1).correlate(RAGDocument).scalar_subquery())

    def _filters(self, *, query: str | None, scope_key: str | None, status: str | None) -> list[Any]:
        latest_id = self._latest_operation_id()
        filters: list[Any] = [
            RAGDocument.status != "archived",
            or_(latest_id.is_not(None), RAGDocument.long_memory_generation > 0),
        ]
        if query:
            pattern = f"%{query.strip()}%"
            filters.append(or_(RAGDocument.title.ilike(pattern), RAGDocument.filename.ilike(pattern)))
        if scope_key:
            filters.append(exists(select(1).select_from(DocumentMemoryScope)
                .join(MemoryScope, MemoryScope.id == DocumentMemoryScope.scope_id)
                .where(DocumentMemoryScope.document_id == RAGDocument.id, MemoryScope.key == scope_key)))
        if status == "deleted":
            filters.append(exists(select(1).select_from(LongMemoryDocumentOperation)
                .where(LongMemoryDocumentOperation.id == latest_id,
                       LongMemoryDocumentOperation.action == "delete",
                       LongMemoryDocumentOperation.status == "completed")))
        elif status == "not_registered":
            filters.append(latest_id.is_(None))
        elif status:
            filters.append(exists(select(1).select_from(LongMemoryDocumentOperation)
                .where(LongMemoryDocumentOperation.id == latest_id, LongMemoryDocumentOperation.status == status)))
        return filters

    async def list_documents(self, *, limit: int, offset: int, query: str | None = None,
                             scope_key: str | None = None, status: str | None = None) -> dict[str, Any]:
        filters = self._filters(query=query, scope_key=scope_key, status=status)
        total = int(await self.session.scalar(select(func.count(RAGDocument.id)).where(*filters)) or 0)
        latest_id = self._latest_operation_id()
        rows = (await self.session.execute(select(RAGDocument, LongMemoryDocumentOperation)
            .outerjoin(LongMemoryDocumentOperation, LongMemoryDocumentOperation.id == latest_id)
            .where(*filters)
            .order_by(RAGDocument.date_upload.desc(), RAGDocument.id)
            .offset(offset).limit(limit))).all()
        items = await self._build_items(rows)
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    async def get_document(self, document_id: UUID) -> dict[str, Any] | None:
        latest_id = self._latest_operation_id()
        row = (await self.session.execute(select(RAGDocument, LongMemoryDocumentOperation)
            .outerjoin(LongMemoryDocumentOperation, LongMemoryDocumentOperation.id == latest_id)
            .where(RAGDocument.id == document_id, RAGDocument.status != "archived"))).first()
        if row is None:
            return None
        item = (await self._build_items([row]))[0]
        operation = row[1]
        progress = _progress(operation)
        index_metrics = ((progress.get("steps") or {}).get("index") or {}).get("metrics") or {}
        indexed_scopes = list(index_metrics.get("scope_slugs") or item["scope_keys"])
        index_status = ((progress.get("steps") or {}).get("index") or {}).get("status") or "not_started"
        item.update({
            "operation_id": str(operation.id) if operation else None,
            "generation": operation.generation if operation else None,
            "graphs": [{"scope_key": key, "status": index_status} for key in indexed_scopes],
            "triples_count": item["metrics"].get("extracted_triples", 0),
        })
        return item

    async def get_document_triples(self, document_id: UUID, *, limit: int, offset: int) -> dict[str, Any] | None:
        if await self.get_document(document_id) is None:
            return None
        return await HippoRAGService(self.session).document_triples(
            document_id, limit=limit, offset=offset,
        )

    async def _build_items(self, rows: list[tuple[RAGDocument, LongMemoryDocumentOperation | None]]) -> list[dict[str, Any]]:
        ids = [document.id for document, _ in rows]
        scope_rows = (await self.session.execute(select(DocumentMemoryScope.document_id, MemoryScope.key)
            .join(MemoryScope, MemoryScope.id == DocumentMemoryScope.scope_id)
            .where(DocumentMemoryScope.document_id.in_(ids)))).all() if ids else []
        scopes: dict[UUID, list[str]] = {}
        for document_id, key in scope_rows:
            scopes.setdefault(document_id, []).append(key)
        items = []
        for document, operation in rows:
            items.append({
                "document_id": str(document.id),
                "title": document.title or document.filename,
                "filename": document.filename,
                "status": _status(operation),
                "action": operation.action if operation else None,
                "scope_keys": scopes.get(document.id, []),
                "metrics": _metrics(operation),
                "error": operation.error if operation else None,
                "updated_at": operation.updated_at if operation else document.updated_at,
            })
        return items

    async def search_preview(self, *, scope_key: str, query: str, limit: int) -> dict[str, Any]:
        result = await HippoRAGService(self.session).search_documents(query, scope_keys=[scope_key], limit=limit)
        group = (result.get("groups") or [{}])[0]
        success = bool(group.get("success"))
        hits = []
        if success:
            for hit in (group.get("hits") or [])[:limit]:
                metadata = hit.get("metadata") or {}
                refs = metadata.get("source_refs") or [metadata]
                ref = next((value for value in refs if isinstance(value, dict)), {})
                hits.append({
                    "text": str(hit.get("text") or "")[:1800],
                    "score": float(hit.get("score") or 0),
                    "document_id": ref.get("document_id"),
                    "title": ref.get("document_title"),
                    "filename": ref.get("filename"),
                    "start": ref.get("start") if isinstance(ref.get("start"), int) else None,
                    "end": ref.get("end") if isinstance(ref.get("end"), int) else None,
                })
        return {"scope_key": scope_key, "success": success,
            "error": group.get("error") if not success else None, "hits": hits}
