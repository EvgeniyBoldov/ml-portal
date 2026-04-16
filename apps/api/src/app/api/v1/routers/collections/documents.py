"""
Collections document endpoints: upload, list, delete.
"""
from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, HTTPException, UploadFile, File, Depends, Form, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_uow, get_current_user, get_redis_client
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.security import UserCtx
from app.repositories.factory import AsyncRepositoryFactory
from app.services.collection_service import CollectionService
from app.services.collection_document_ingest_service import CollectionDocumentUploadService
from app.services.document_artifacts import normalize_document_source_meta
from app.services.rag_ingest_service import RAGIngestService
from app.services.rag_status_manager import RAGStatusManager
from app.services.status_aggregator import calculate_aggregate_status
from app.adapters.s3_client import s3_manager

from .upload_shared import _resolve_collection

logger = get_logger(__name__)

router = APIRouter()


@router.post("/{collection_id}/upload-document")
async def upload_collection_document(
    collection_id: uuid.UUID,
    file: UploadFile = File(...),
    title: str | None = Form(None),
    source: str | None = Form(None),
    scope: str | None = Form(None),
    tags: str | None = Form(None),
    auto_ingest: bool = Form(True),
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
):
    from app.schemas.rag import IngestRequest
    from app.services.rag_event_publisher import RAGEventPublisher

    file_content = await file.read()
    collection = await _resolve_collection(collection_id, session, user)

    doc_tags = []
    if tags:
        try:
            doc_tags = json.loads(tags)
        except json.JSONDecodeError:
            doc_tags = [t.strip() for t in tags.split(",") if t.strip()]

    redis = get_redis_client()
    event_publisher = RAGEventPublisher(redis) if redis else None
    repo_factory = AsyncRepositoryFactory(session, collection.tenant_id)

    upload_service = CollectionDocumentUploadService(
        session=session,
        repo_factory=repo_factory,
        event_publisher=event_publisher,
    )

    result = await upload_service.upload_document(
        collection_id=collection_id,
        file_content=file_content,
        filename=file.filename or f"upload_{uuid.uuid4()}",
        user_id=user.id,
        content_type=file.content_type,
        title=title,
        source=source,
        scope=scope,
        tags=doc_tags,
    )

    if auto_ingest:
        status_manager = RAGStatusManager(session, repo_factory, event_publisher)
        ingest_service = RAGIngestService(session, repo_factory, status_manager)
        await ingest_service.start_ingest(IngestRequest(document_id=uuid.UUID(result["doc_id"])))

    await session.commit()
    return result


@router.get("/{collection_id}/documents")
async def list_collection_documents(
    collection_id: uuid.UUID,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=500),
    status: str | None = Query(None),
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
):
    from sqlalchemy import func as sa_func
    from app.models.rag import RAGDocument
    from app.models.rag_ingest import Source

    try:
        collection = await _resolve_collection(collection_id, session, user)

        if collection.collection_type != "document":
            raise HTTPException(status_code=400, detail="Not a document collection")

        cid_str = str(collection_id)
        base_q = (
            select(RAGDocument, Source.meta)
            .join(Source, RAGDocument.id == Source.source_id)
            .where(
                or_(
                    Source.meta["collection"]["id"].astext == cid_str,
                    Source.meta["collection_id"].astext == cid_str,
                )
            )
        )
        if status:
            base_q = base_q.where(RAGDocument.status == status)
        base_q = base_q.order_by(RAGDocument.created_at.desc())

        count_q = select(sa_func.count()).select_from(base_q.subquery())
        total = (await session.execute(count_q)).scalar() or 0

        offset = (page - 1) * size
        rows = (await session.execute(base_q.offset(offset).limit(size))).all()

        items = []
        for doc, source_meta in rows:
            meta = normalize_document_source_meta(source_meta)
            document_meta = meta.get("document", {})
            collection_meta = meta.get("collection", {})
            artifacts = meta.get("artifacts", {})

            agg_status = doc.agg_status
            if not agg_status:
                try:
                    from app.repositories.rag_status_repo import AsyncRAGStatusRepository

                    status_repo = AsyncRAGStatusRepository(session)
                    pipeline_nodes = await status_repo.get_pipeline_nodes(doc.id)
                    embedding_nodes = await status_repo.get_embedding_nodes(doc.id)
                    repo_factory_inner = AsyncRepositoryFactory(session, doc.tenant_id)
                    status_manager = RAGStatusManager(session, repo_factory_inner)
                    target_models = await status_manager._get_target_models(doc.id)
                    agg_status, _ = calculate_aggregate_status(
                        doc_id=doc.id,
                        pipeline_nodes=pipeline_nodes,
                        embedding_nodes=embedding_nodes,
                        target_models=target_models,
                    )
                except Exception:
                    agg_status = doc.status

            items.append({
                "id": str(doc.id),
                "name": doc.name or doc.filename,
                "filename": doc.filename,
                "status": doc.status,
                "agg_status": agg_status,
                "scope": document_meta.get("scope") or doc.scope,
                "tags": document_meta.get("tags") or doc.tags or [],
                "size_bytes": document_meta.get("size_bytes") or doc.size_bytes or doc.size,
                "content_type": document_meta.get("content_type") or doc.content_type,
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
                "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
                "collection_row_id": collection_meta.get("row_id"),
                "title": document_meta.get("title") or doc.title,
                "source": document_meta.get("source"),
                "doc_scope": document_meta.get("scope"),
                "s3_key": artifacts.get("original", {}).get("key"),
                "document": document_meta,
                "collection": collection_meta,
                "artifacts": {
                    kind: artifact for kind, artifact in artifacts.items() if artifact.get("key")
                },
                "meta_fields": {},
            })

        if collection.table_name and collection.fields and items:
            row_id_map = {}
            for item in items:
                rid = item.get("collection_row_id")
                if rid:
                    row_id_map[rid] = item

            if row_id_map:
                non_file_fields = [
                    f["name"] for f in collection.fields if f.get("data_type") != "file"
                ]
                if non_file_fields:
                    from sqlalchemy import text as sa_text
                    cols = ", ".join(non_file_fields)
                    placeholders = ", ".join([f":rid_{i}" for i in range(len(row_id_map))])
                    params = {f"rid_{i}": rid for i, rid in enumerate(row_id_map.keys())}
                    q = sa_text(
                        f"SELECT id::text, {cols} FROM {collection.table_name} WHERE id::text IN ({placeholders})"
                    )
                    dyn_rows = (await session.execute(q, params)).mappings().all()
                    for drow in dyn_rows:
                        rid = drow["id"]
                        if rid in row_id_map:
                            meta_fields = {}
                            for fname in non_file_fields:
                                val = drow.get(fname)
                                if val is not None:
                                    meta_fields[fname] = val
                            row_id_map[rid]["meta_fields"] = meta_fields

        return {"items": items, "total": total, "page": page, "size": size, "has_more": offset + size < total}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list collection documents: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{collection_id}/documents")
async def delete_collection_documents(
    collection_id: uuid.UUID,
    doc_ids: list[str] = Query(..., alias="ids"),
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
):
    from sqlalchemy import delete as sa_delete, text
    from app.models.rag import RAGDocument
    from app.models.rag_ingest import RAGStatus, Source

    try:
        collection = await _resolve_collection(collection_id, session, user)

        if collection.collection_type != "document":
            raise HTTPException(status_code=400, detail="Not a document collection")

        settings = get_settings()
        deleted_count = 0

        for did_str in doc_ids:
            did = uuid.UUID(did_str)
            source_q = select(Source).where(
                Source.source_id == did,
                or_(
                    Source.meta["collection"]["id"].astext == str(collection_id),
                    Source.meta["collection_id"].astext == str(collection_id),
                ),
            )
            source = (await session.execute(source_q)).scalar_one_or_none()
            if not source:
                raise HTTPException(status_code=404, detail=f"Document {did} not found in collection")

            meta = normalize_document_source_meta((source.meta or {}) if source else {})
            original_key = meta.get("artifacts", {}).get("original", {}).get("key")
            if original_key:
                try:
                    await s3_manager.delete_object(settings.S3_BUCKET_RAG, original_key)
                except Exception as exc:
                    logger.warning(f"S3 object delete failed for {original_key}: {exc}")

            doc_prefix = f"{collection.tenant_id}/{did}"
            try:
                await s3_manager.delete_folder(settings.S3_BUCKET_RAG, doc_prefix)
            except Exception as exc:
                logger.warning(f"S3 folder delete failed for {doc_prefix}: {exc}")

            row_id = meta.get("collection", {}).get("row_id")
            if row_id and collection.table_name:
                try:
                    await session.execute(
                        text(f"DELETE FROM {collection.table_name} WHERE id = :rid"),
                        {"rid": row_id},
                    )
                except Exception as exc:
                    logger.warning(f"Row delete failed for {row_id}: {exc}")

            await session.execute(sa_delete(RAGStatus).where(RAGStatus.doc_id == did))
            if source:
                await session.delete(source)

            doc_q = select(RAGDocument).where(RAGDocument.id == did)
            doc = (await session.execute(doc_q)).scalar_one_or_none()
            if doc:
                await session.delete(doc)

            deleted_count += 1

        if deleted_count > 0:
            collection.total_rows = max(0, (collection.total_rows or 0) - deleted_count)
            await CollectionService(session).sync_collection_status(collection, persist=False)

        await session.commit()
        return {"deleted": deleted_count, "collection_id": str(collection_id)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete collection documents: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
