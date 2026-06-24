"""
Collection Get Document Tool — get metadata and canonical storage reference for a document.

Returns storage_uri that can be passed to file.read or file.analyze to inspect
the actual file content.
"""
from __future__ import annotations

import uuid
from typing import Any, ClassVar, Dict

from sqlalchemy import select, text as sa_text

from app.agents.context import ToolContext, ToolResult
from app.agents.handlers.versioned_tool import VersionedTool, register_tool, tool_version
from app.core.db import get_session_factory
from app.core.logging import get_logger
from app.models.rag import RAGDocument
from app.models.rag_ingest import DocumentCollectionMembership, Source
from app.services.file_delivery_service import FileDeliveryService
from app.core.config import get_settings

logger = get_logger(__name__)

_INPUT_SCHEMA_V1 = {
    "type": "object",
    "properties": {
        "document_id": {
            "type": "string",
            "description": "UUID of the document to retrieve",
        },
    },
    "required": ["document_id"],
}

_OUTPUT_SCHEMA_V1 = {
    "type": "object",
    "properties": {
        "document_id": {"type": "string"},
        "file_id": {"type": "string"},
        "storage_uri": {"type": "string"},
        "filename": {"type": "string"},
        "title": {"type": "string"},
        "status": {"type": "string"},
        "size_bytes": {"type": "integer"},
        "content_type": {"type": "string"},
        "meta_fields": {"type": "object"},
        "collection": {"type": "string"},
    },
}


@register_tool
class CollectionDocumentGetTool(VersionedTool):
    """
    Get a document's metadata and a storage_uri pointing to its original file.

    Pass the returned storage_uri to file.read or file.analyze to inspect the
    actual content (e.g. an Excel template).
    """

    tool_slug: ClassVar[str] = "collection.get_document"
    domains: ClassVar[list] = ["collection.document"]
    name: ClassVar[str] = "Get Collection Document"
    description: ClassVar[str] = (
        "Get a single document's metadata and a storage_uri pointing to its original file. "
        "Pass that storage_uri to file.read or file.analyze to inspect the actual content "
        "(e.g. an Excel template)."
    )

    @tool_version(
        version="1.0.0",
        input_schema=_INPUT_SCHEMA_V1,
        output_schema=_OUTPUT_SCHEMA_V1,
        description="Get document metadata and file_id",
    )
    async def v1_0_0(self, ctx: ToolContext, args: Dict[str, Any]) -> ToolResult:
        log = ctx.tool_logger("collection.get_document")

        doc_id_str = str(args.get("document_id") or "").strip()
        if not doc_id_str:
            log.error("Missing document_id")
            return ToolResult.fail("Missing 'document_id' argument", logs=log.entries_dict())

        log.info("Fetching document", document_id=doc_id_str)

        try:
            session_factory = get_session_factory()
            async with session_factory() as session:
                try:
                    doc_uuid = uuid.UUID(doc_id_str)
                except ValueError:
                    log.error("Invalid document_id UUID")
                    return ToolResult.fail("Invalid document_id format", logs=log.entries_dict())

                # Load document with tenant check
                result = await session.execute(
                    select(RAGDocument).where(
                        RAGDocument.id == doc_uuid,
                        RAGDocument.tenant_id == ctx.tenant_id,
                    )
                )
                doc = result.scalar_one_or_none()
                if not doc:
                    log.error("Document not found")
                    return ToolResult.fail(
                        f"Document '{doc_id_str}' not found or access denied",
                        logs=log.entries_dict(),
                    )

                # Load source meta
                source_result = await session.execute(
                    select(Source).where(Source.source_id == doc.id)
                )
                source = source_result.scalar_one_or_none()

                # Load collection membership
                membership_result = await session.execute(
                    select(DocumentCollectionMembership).where(
                        DocumentCollectionMembership.source_id == doc.id,
                    )
                )
                membership = membership_result.scalar_one_or_none()

                # Enrich with meta_fields from dynamic table
                meta_fields: Dict[str, Any] = {}
                collection_slug: str = ""
                if membership and membership.collection_id:
                    from app.models.collection import Collection
                    coll = await session.execute(
                        select(Collection).where(Collection.id == membership.collection_id)
                    )
                    collection = coll.scalar_one_or_none()
                    if collection:
                        collection_slug = collection.slug
                        if (
                            collection.table_name
                            and collection.fields
                            and membership.collection_row_id
                        ):
                            non_file_fields = [
                                f["name"] for f in collection.fields if f.get("data_type") != "file"
                            ]
                            if non_file_fields:
                                cols = ", ".join(non_file_fields)
                                q = sa_text(
                                    f"SELECT id::text, {cols} FROM {collection.table_name} "
                                    f"WHERE id::text = :rid"
                                )
                                row = (
                                    (await session.execute(
                                        q, {"rid": str(membership.collection_row_id)}
                                    ))
                                    .mappings()
                                    .one_or_none()
                                )
                                if row:
                                    meta_fields = {
                                        fname: row.get(fname)
                                        for fname in non_file_fields
                                        if row.get(fname) is not None
                                    }

                file_id = FileDeliveryService.make_rag_document_file_id(doc_id_str, "original")
                storage_uri = FileDeliveryService.make_storage_uri(
                    get_settings().S3_BUCKET_RAG,
                    str(doc.s3_key_raw or ""),
                )

                log.info("Document fetched", document_id=doc_id_str, collection=collection_slug)

                return ToolResult.ok(
                    data={
                        "document_id": doc_id_str,
                        "file_id": file_id,
                        "storage_uri": storage_uri,
                        "filename": doc.filename,
                        "title": doc.title or doc.filename,
                        "status": doc.status,
                        "size_bytes": doc.size_bytes or doc.size or 0,
                        "content_type": doc.content_type or "application/octet-stream",
                        "meta_fields": meta_fields,
                        "collection": collection_slug,
                    },
                    message=f"Document '{doc.filename}' from collection '{collection_slug}'.",
                    logs=log.entries_dict(),
                )
        except Exception as exc:
            logger.error("Collection get_document failed: %s", exc, exc_info=True)
            log.error("Get failed", error=str(exc))
            return ToolResult.fail(f"Failed to get document: {exc}", logs=log.entries_dict())
