"""
Collection List Documents Tool — lists files in a document collection.

The agent uses this to enumerate available files (e.g. templates, registers)
within a collection after discovering the collection via collection.doc_search.
Each result carries a file_id that can be passed to file.read or file.analyze.
"""
from __future__ import annotations

import uuid
from typing import Any, ClassVar, Dict, List, Optional

from sqlalchemy import select, func, text as sa_text

from app.agents.context import ToolContext, ToolResult
from app.agents.handlers.versioned_tool import VersionedTool, register_tool, tool_version
from app.core.db import get_session_factory
from app.core.logging import get_logger
from app.models.rag import RAGDocument
from app.models.rag_ingest import DocumentCollectionMembership, Source
from app.services.collection_service import CollectionService
from app.services.file_delivery_service import FileDeliveryService

logger = get_logger(__name__)

_MAX_LIMIT = 50

_INPUT_SCHEMA_V1 = {
    "type": "object",
    "properties": {
        "collection_slug": {
            "type": "string",
            "description": "Slug of the document collection to list files from",
        },
        "query": {
            "type": "string",
            "description": "Optional filter by filename or title (case-insensitive substring match)",
            "default": "",
        },
        "status": {
            "type": "string",
            "description": "Optional filter by document status (uploaded, ready, failed, etc.)",
            "default": "",
        },
        "limit": {
            "type": "integer",
            "description": f"Max results to return (default: 20, max: {_MAX_LIMIT})",
            "default": 20,
            "minimum": 1,
            "maximum": _MAX_LIMIT,
        },
    },
    "required": ["collection_slug"],
}

_OUTPUT_SCHEMA_V1 = {
    "type": "object",
    "properties": {
        "documents": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "document_id": {"type": "string"},
                    "file_id": {"type": "string"},
                    "filename": {"type": "string"},
                    "title": {"type": "string"},
                    "status": {"type": "string"},
                    "size_bytes": {"type": "integer"},
                    "content_type": {"type": "string"},
                    "meta_fields": {"type": "object"},
                    "created_at": {"type": "string"},
                },
            },
        },
        "total": {"type": "integer"},
        "collection": {"type": "string"},
    },
}


@register_tool
class CollectionDocumentListTool(VersionedTool):
    """
    List files in a document collection with their metadata.

    Use this AFTER collection.doc_search found a relevant collection to
    enumerate available files (e.g. find an Excel template by filename).
    For each document a file_id is returned — pass it to file.read or file.analyze
    to inspect the actual file content.
    """

    tool_slug: ClassVar[str] = "collection.list_documents"
    domains: ClassVar[list] = ["collection.document"]
    name: ClassVar[str] = "List Collection Documents"
    description: ClassVar[str] = (
        "List all files in a document collection with their names and metadata. "
        "Use to enumerate available files (e.g. find a template by name). "
        "For content search use collection.doc_search. "
        "Returns a file_id for each document that can be passed to file.read or file.analyze."
    )

    @tool_version(
        version="1.0.0",
        input_schema=_INPUT_SCHEMA_V1,
        output_schema=_OUTPUT_SCHEMA_V1,
        description="List document files in a document collection with metadata",
    )
    async def v1_0_0(self, ctx: ToolContext, args: Dict[str, Any]) -> ToolResult:
        log = ctx.tool_logger("collection.list_documents")

        collection_slug = str(args.get("collection_slug") or "").strip()
        if not collection_slug:
            log.error("Missing collection_slug")
            return ToolResult.fail("Missing 'collection_slug' argument", logs=log.entries_dict())

        query_filter = str(args.get("query") or "").strip().lower() or None
        status_filter = str(args.get("status") or "").strip().lower() or None
        try:
            limit = min(int(args.get("limit", 20)), _MAX_LIMIT)
        except (TypeError, ValueError):
            limit = 20

        log.info(
            "Listing collection documents",
            collection=collection_slug,
            query=query_filter,
            status=status_filter,
            limit=limit,
        )

        try:
            session_factory = get_session_factory()
            async with session_factory() as session:
                service = CollectionService(session)
                collection = await service.get_by_slug(collection_slug)
                if not collection:
                    log.error("Collection not found", collection=collection_slug)
                    return ToolResult.fail(
                        f"Collection '{collection_slug}' not found",
                        logs=log.entries_dict(),
                    )

                if collection.collection_type != "document":
                    log.error("Not a document collection", type=collection.collection_type)
                    return ToolResult.fail(
                        f"Collection '{collection_slug}' is not a document collection "
                        f"(type={collection.collection_type}).",
                        logs=log.entries_dict(),
                    )

                tenant_id = ctx.tenant_id
                if str(collection.tenant_id) != str(tenant_id):
                    log.error("Collection tenant mismatch")
                    return ToolResult.fail(
                        "Collection not found or access denied.",
                        logs=log.entries_dict(),
                    )

                base_q = (
                    select(RAGDocument, Source.meta)
                    .join(Source, RAGDocument.id == Source.source_id)
                    .join(
                        DocumentCollectionMembership,
                        DocumentCollectionMembership.source_id == Source.source_id,
                    )
                    .where(
                        DocumentCollectionMembership.collection_id == collection.id,
                        DocumentCollectionMembership.tenant_id == tenant_id,
                    )
                )

                if status_filter:
                    base_q = base_q.where(RAGDocument.status == status_filter)
                if query_filter:
                    base_q = base_q.where(
                        (RAGDocument.filename.ilike(f"%{query_filter}%"))
                        | (RAGDocument.title.ilike(f"%{query_filter}%"))
                    )

                base_q = base_q.order_by(RAGDocument.created_at.desc())

                count_q = select(func.count()).select_from(base_q.subquery())
                total = (await session.execute(count_q)).scalar() or 0

                rows = (await session.execute(base_q.limit(limit))).all()

                # Enrich with meta_fields from dynamic table
                row_id_map: Dict[str, Dict[str, Any]] = {}
                for doc, _ in rows:
                    # Find the collection_row_id from the membership (do a separate query for all rows at once)
                    pass  # We'll fetch memberships in batch below

                # Batch-fetch collection_row_ids
                doc_ids = [str(doc.id) for doc, _ in rows]
                row_id_map = {}
                if doc_ids:
                    membership_q = select(
                        DocumentCollectionMembership.source_id,
                        DocumentCollectionMembership.collection_row_id,
                    ).where(
                        DocumentCollectionMembership.collection_id == collection.id,
                        DocumentCollectionMembership.source_id.in_(
                            [uuid.UUID(did) for did in doc_ids]
                        ),
                    )
                    m_rows = (await session.execute(membership_q)).all()
                    for m in m_rows:
                        row_id_map[str(m.source_id)] = str(m.collection_row_id) if m.collection_row_id else None

                # Batch-fetch meta_fields from dynamic table
                meta_fields_map: Dict[str, Dict[str, Any]] = {}
                if collection.table_name and collection.fields:
                    non_file_fields = [
                        f["name"] for f in collection.fields if f.get("data_type") != "file"
                    ]
                    if non_file_fields:
                        valid_row_ids = {
                            rid for rid in row_id_map.values() if rid
                        }
                        if valid_row_ids:
                            cols = ", ".join(non_file_fields)
                            placeholders = ", ".join([f":rid_{i}" for i in range(len(valid_row_ids))])
                            params = {f"rid_{i}": rid for i, rid in enumerate(valid_row_ids)}
                            q = sa_text(
                                f"SELECT id::text, {cols} FROM {collection.table_name} "
                                f"WHERE id::text IN ({placeholders})"
                            )
                            dyn_rows = (await session.execute(q, params)).mappings().all()
                            for drow in dyn_rows:
                                rid = drow["id"]
                                meta_fields_map[rid] = {
                                    fname: drow.get(fname)
                                    for fname in non_file_fields
                                    if drow.get(fname) is not None
                                }

                documents: List[Dict[str, Any]] = []
                for doc, _ in rows:
                    doc_id_str = str(doc.id)
                    collection_row_id = row_id_map.get(doc_id_str)
                    file_id = FileDeliveryService.make_rag_document_file_id(doc_id_str, "original")
                    meta = meta_fields_map.get(collection_row_id) if collection_row_id else None

                    documents.append({
                        "document_id": doc_id_str,
                        "file_id": file_id,
                        "filename": doc.filename,
                        "title": doc.title or doc.filename,
                        "status": doc.status,
                        "size_bytes": doc.size_bytes or doc.size or 0,
                        "content_type": doc.content_type or "application/octet-stream",
                        "meta_fields": meta or {},
                        "created_at": doc.created_at.isoformat() if doc.created_at else None,
                    })

                log.info(
                    "Collection documents listed",
                    collection=collection_slug,
                    count=len(documents),
                    total=total,
                )

                return ToolResult.ok(
                    data={
                        "documents": documents,
                        "total": total,
                        "collection": collection.slug,
                    },
                    message=f"Found {len(documents)} file(s) in collection '{collection.slug}' (total {total}).",
                    logs=log.entries_dict(),
                )
        except Exception as exc:
            logger.error("Collection list_documents failed: %s", exc, exc_info=True)
            log.error("List failed", error=str(exc))
            return ToolResult.fail(f"Failed to list documents: {exc}", logs=log.entries_dict())
