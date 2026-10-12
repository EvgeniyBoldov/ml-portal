"""Backfill the shared HippoRAG corpus from existing RAG-indexed documents."""
import asyncio
import json
import logging

from sqlalchemy import select
import app.models
from app.adapters.s3_client import s3_manager
from app.core.config import get_settings
from app.core.db import get_session_factory
from app.models.rag import RAGDocument
from app.models.rag_ingest import Source, RAGStatus
from app.workers.tasks_hipporag_document import index_hipporag_document


async def main():
    logging.getLogger("botocore").setLevel(logging.ERROR)
    logging.getLogger("boto3").setLevel(logging.ERROR)
    async with get_session_factory()() as session:
        rows = (await session.execute(select(RAGDocument, Source.tenant_id).join(Source,
            Source.source_id == RAGDocument.id).where(RAGDocument.status != "archived",
            RAGDocument.s3_key_processed.is_not(None), RAGDocument.id.in_(select(RAGStatus.doc_id).where(
                RAGStatus.node_type == "index", RAGStatus.status == "completed"))))).all()
        for document, tenant_id in rows:
            content = await s3_manager.get_object(get_settings().S3_BUCKET_RAG, document.s3_key_processed)
            if content is None:
                print(json.dumps({"document": document.filename, "status": "skipped", "reason": "canonical_file_missing"}), flush=True)
                continue
            task = index_hipporag_document.delay({"source_id": str(document.id)}, str(tenant_id))
            print(json.dumps({"document": document.filename, "document_id": str(document.id),
                              "status": "queued", "task_id": task.id}), flush=True)


asyncio.run(main())
