"""
Celery task for vectorizing retrieval-enabled text fields in table collections.

Flow:
1. Load collection metadata (fields, qdrant_collection_name)
2. Select rows with _vector_status = 'pending' (batch)
3. For each row: embed text fields → upsert points to Qdrant
4. Update _vector_status per row + collection stats
"""
from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, Dict, List

from celery import Task

from app.celery_app import app as celery_app
from app.core.logging import get_logger

logger = get_logger(__name__)

BATCH_SIZE = 50
MAX_TEXT_LENGTH = 8000  # Max chars per field for embedding
DEFAULT_CHUNK_SIZE = 1200
DEFAULT_CHUNK_OVERLAP = 150
MIN_CHUNK_SIZE = 200
MAX_CHUNK_SIZE = 4000


def _build_point_id(collection_id: str, row_id: str, field_name: str, chunk_idx: int) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{collection_id}:{row_id}:{field_name}:{chunk_idx}"))


def _collection_lock_key(collection_id: str) -> int:
    return int(uuid.UUID(str(collection_id)).int % (2**63 - 1))


def _resolve_chunk_config(vector_config: Any) -> tuple[int, int]:
    if not isinstance(vector_config, dict):
        return DEFAULT_CHUNK_SIZE, DEFAULT_CHUNK_OVERLAP

    raw_size = vector_config.get("chunk_size", DEFAULT_CHUNK_SIZE)
    raw_overlap = vector_config.get("overlap", DEFAULT_CHUNK_OVERLAP)
    try:
        chunk_size = int(raw_size)
    except (TypeError, ValueError):
        chunk_size = DEFAULT_CHUNK_SIZE
    try:
        overlap = int(raw_overlap)
    except (TypeError, ValueError):
        overlap = DEFAULT_CHUNK_OVERLAP

    chunk_size = max(MIN_CHUNK_SIZE, min(MAX_CHUNK_SIZE, chunk_size))
    overlap = max(0, min(chunk_size - 1, overlap))
    return chunk_size, overlap


def _chunk_text_for_embedding(text: str, chunk_size: int, overlap: int) -> list[str]:
    normalized = (text or "").strip()
    if not normalized:
        return []
    if len(normalized) <= chunk_size:
        return [normalized]

    chunks: list[str] = []
    step = max(1, chunk_size - overlap)
    start = 0
    while start < len(normalized):
        end = min(len(normalized), start + chunk_size)
        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(normalized):
            break
        start += step
    return chunks


def _needs_revectorization_for_model(vector_config: Any, model_alias: str) -> bool:
    if not isinstance(vector_config, dict):
        return True
    current = str(vector_config.get("embed_model_alias") or "").strip()
    return current != str(model_alias).strip()


@celery_app.task(
    queue="ingest.embed",
    bind=True,
    acks_late=True,
    reject_on_worker_lost=True,
    max_retries=3,
    default_retry_delay=30,
)
def vectorize_collection_rows(
    self: Task,
    collection_id: str,
    tenant_id: str,
    row_ids: List[str] | None = None,
) -> Dict[str, Any]:
    """
    Vectorize pending rows in a table collection.

    Args:
        collection_id: UUID of the collection
        tenant_id: UUID of the tenant
        row_ids: Optional list of specific row UUIDs to vectorize.
                 If None, picks BATCH_SIZE rows with _vector_status='pending'.
    """

    async def _execute() -> Dict[str, Any]:
        from sqlalchemy import text as sa_text

        from app.adapters.embeddings import EmbeddingServiceFactory
        from app.adapters.impl.qdrant import QdrantVectorStore
        from app.services.collection_service import CollectionService
        from app.workers.session_factory import get_worker_session

        async with get_worker_session() as session:
            lock_key = _collection_lock_key(collection_id)
            lock_result = await session.execute(
                sa_text("SELECT pg_try_advisory_lock(:lock_key)"),
                {"lock_key": lock_key},
            )
            lock_acquired = bool(lock_result.scalar())
            if not lock_acquired:
                logger.info(
                    "collection_vectorization_already_running",
                    extra={"collection_id": collection_id},
                )
                return {"status": "skipped", "message": "already_running"}

            try:
                # 1. Load collection
                result = await session.execute(
                    sa_text(
                        "SELECT id, slug, table_name, fields, qdrant_collection_name, "
                        "vector_config, tenant_id "
                        "FROM collections WHERE id = :cid AND tenant_id = :tid"
                    ),
                    {"cid": collection_id, "tid": tenant_id},
                )
                row = result.mappings().first()
                if not row:
                    logger.error(f"Collection {collection_id} not found for tenant {tenant_id}")
                    return {"status": "error", "message": "collection_not_found"}

                table_name = row["table_name"]
                fields = row["fields"]
                qdrant_name = row["qdrant_collection_name"]
                vector_config = row.get("vector_config")
                chunk_size, chunk_overlap = _resolve_chunk_config(vector_config)

                if not qdrant_name:
                    logger.warning(f"Collection {collection_id} has no qdrant_collection_name")
                    return {"status": "skipped", "message": "no_qdrant_collection"}

                # 2. Determine vector fields
                vector_field_names = [
                    f["name"]
                    for f in fields
                    if f.get("used_in_retrieval", False)
                    and f.get("data_type") == "text"
                ]
                if not vector_field_names:
                    logger.info(f"Collection {collection_id} has no vector text fields")
                    return {"status": "skipped", "message": "no_vector_fields"}

                # 3. Select pending rows
                if row_ids:
                    placeholders = ", ".join([f":rid_{i}" for i in range(len(row_ids))])
                    params: Dict[str, Any] = {f"rid_{i}": rid for i, rid in enumerate(row_ids)}
                    where = f"id::text IN ({placeholders}) AND _vector_status = 'pending'"
                else:
                    params = {}
                    where = "_vector_status = 'pending'"

                cols = ", ".join(["id::text AS id"] + vector_field_names)
                q = sa_text(
                    f"SELECT {cols} FROM {table_name} WHERE {where} LIMIT :lim"
                )
                params["lim"] = BATCH_SIZE
                rows_result = await session.execute(q, params)
                pending_rows = [dict(r) for r in rows_result.mappings().all()]

                if not pending_rows:
                    return {"status": "ok", "vectorized": 0, "message": "no_pending_rows"}

                # 4. Resolve embedding model from DB
                emb_row = await session.execute(
                    sa_text(
                        "SELECT alias FROM models "
                        "WHERE type = 'EMBEDDING' AND enabled = true "
                        "AND status = 'AVAILABLE' "
                        "ORDER BY created_at LIMIT 1"
                    )
                )
                model_alias = emb_row.scalar_one_or_none()
                if not model_alias:
                    logger.error("No embedding models available in model_registry")
                    return {"status": "error", "message": "no_embedding_models"}

                if _needs_revectorization_for_model(vector_config, model_alias):
                    logger.info(
                        "collection_vectorization_model_changed_revectorize",
                        extra={
                            "collection_id": collection_id,
                            "previous_model_alias": (
                                vector_config.get("embed_model_alias")
                                if isinstance(vector_config, dict)
                                else None
                            ),
                            "new_model_alias": model_alias,
                        },
                    )
                    await session.execute(
                        sa_text(
                            f"UPDATE {table_name} "
                            f"SET _vector_status = 'pending', _vector_chunk_count = 0, _vector_error = NULL"
                        )
                    )
                    await session.execute(
                        sa_text(
                            "UPDATE collections SET "
                            "vectorized_rows = 0, total_chunks = 0, failed_rows = 0 "
                            "WHERE id = :cid"
                        ),
                        {"cid": collection_id},
                    )
                    next_vector_config = (
                        dict(vector_config)
                        if isinstance(vector_config, dict)
                        else {}
                    )
                    next_vector_config["embed_model_alias"] = str(model_alias)
                    await session.execute(
                        sa_text(
                            "UPDATE collections SET vector_config = CAST(:vconf AS JSONB) "
                            "WHERE id = :cid"
                        ),
                        {"vconf": json.dumps(next_vector_config), "cid": collection_id},
                    )

                await EmbeddingServiceFactory.ensure_model_registered_async(session, model_alias)
                embedding_service = EmbeddingServiceFactory.get_service(model_alias)
                model_info = embedding_service.get_model_info()

                # 5. Ensure Qdrant collection
                vector_store = QdrantVectorStore()
                if _needs_revectorization_for_model(vector_config, model_alias):
                    if await vector_store.collection_exists(qdrant_name):
                        await vector_store.delete_collection(qdrant_name)
                await vector_store.ensure_collection(qdrant_name, model_info.dimensions)

                # 6. Process rows
                vectorized = 0
                failed = 0
                total_chunks = 0

                for prow in pending_rows:
                    rid = prow["id"]
                    try:
                        points_vectors: List[List[float]] = []
                        points_payloads: List[Dict[str, Any]] = []
                        points_ids: List[str] = []

                        # Drop previous points for this row before writing the current state.
                        await vector_store.delete_by_filter(
                            qdrant_name,
                            {"row_id": rid},
                        )

                        for fname in vector_field_names:
                            text_val = prow.get(fname)
                            if not text_val or not str(text_val).strip():
                                continue

                            text_val = str(text_val).strip()[:MAX_TEXT_LENGTH]
                            chunks = _chunk_text_for_embedding(
                                text_val,
                                chunk_size=chunk_size,
                                overlap=chunk_overlap,
                            )
                            if not chunks:
                                continue

                            # Embed all chunks for this retrieval-enabled field.
                            vectors = await asyncio.to_thread(
                                embedding_service.embed_texts, chunks
                            )

                            for chunk_idx, chunk_text in enumerate(chunks):
                                point_id = _build_point_id(collection_id, rid, fname, chunk_idx)
                                points_vectors.append(vectors[chunk_idx])
                                points_ids.append(point_id)
                                points_payloads.append({
                                    "row_id": rid,
                                    "field_name": fname,
                                    "chunk_idx": chunk_idx,
                                    "text": chunk_text[:2000],
                                    "embed_model_alias": model_alias,
                                    "tenant_id": tenant_id,
                                    "collection_id": collection_id,
                                })

                        if points_vectors:
                            await vector_store.upsert(
                                qdrant_name, points_vectors, points_payloads, points_ids
                            )
                            total_chunks += len(points_vectors)

                        # Mark row as vectorized
                        await session.execute(
                            sa_text(
                                f"UPDATE {table_name} SET _vector_status = 'done', "
                                f"_vector_chunk_count = :cnt, _vector_error = NULL "
                                f"WHERE id::text = :rid"
                            ),
                            {"cnt": len(points_vectors), "rid": rid},
                        )
                        vectorized += 1

                    except Exception as e:
                        logger.error(
                            f"Failed to vectorize row {rid} in {table_name}: {e}",
                            exc_info=True,
                        )
                        await session.execute(
                            sa_text(
                                f"UPDATE {table_name} SET _vector_status = 'error', "
                                f"_vector_chunk_count = 0, _vector_error = :err "
                                f"WHERE id::text = :rid"
                            ),
                            {"err": str(e)[:500], "rid": rid},
                        )
                        failed += 1

                # 7. Update collection stats
                stats_result = await session.execute(
                    sa_text(
                        f"SELECT "
                        f"COUNT(*) FILTER (WHERE _vector_status = 'done') AS vectorized_rows, "
                        f"COUNT(*) FILTER (WHERE _vector_status = 'error') AS failed_rows, "
                        f"COALESCE(SUM(_vector_chunk_count), 0) AS total_chunks "
                        f"FROM {table_name}"
                    )
                )
                stats = stats_result.mappings().one()
                await session.execute(
                    sa_text(
                        "UPDATE collections SET "
                        "vectorized_rows = :vectorized_rows, "
                        "total_chunks = :total_chunks, "
                        "failed_rows = :failed_rows "
                        "WHERE id = :cid"
                    ),
                    {
                        "vectorized_rows": int(stats["vectorized_rows"] or 0),
                        "total_chunks": int(stats["total_chunks"] or 0),
                        "failed_rows": int(stats["failed_rows"] or 0),
                        "cid": collection_id,
                    },
                )
                collection_service = CollectionService(session)
                collection = await collection_service.get_by_id(uuid.UUID(collection_id))
                if collection:
                    await collection_service.sync_collection_status(collection, persist=False)
                await session.commit()

                logger.info(
                    "collection_vectorization_batch_done",
                    extra={
                        "collection_id": collection_id,
                        "vectorized": vectorized,
                        "failed": failed,
                        "total_chunks": total_chunks,
                    },
                )

                # 8. Check if more pending rows remain — schedule continuation
                remain = await session.execute(
                    sa_text(
                        f"SELECT COUNT(*) FROM {table_name} WHERE _vector_status = 'pending'"
                    )
                )
                remaining = remain.scalar() or 0

                if remaining > 0:
                    from app.services.collection_vectorization_orchestrator import (
                        CollectionVectorizationOrchestrator,
                    )
                    CollectionVectorizationOrchestrator.enqueue(
                        collection_id=collection_id,
                        tenant_id=tenant_id,
                        countdown=2,
                    )

                return {
                    "status": "ok",
                    "vectorized": vectorized,
                    "failed": failed,
                    "total_chunks": total_chunks,
                    "remaining": remaining,
                }
            finally:
                try:
                    await session.execute(
                        sa_text("SELECT pg_advisory_unlock(:lock_key)"),
                        {"lock_key": lock_key},
                    )
                except Exception:
                    logger.warning(
                        "collection_vectorization_unlock_failed",
                        extra={"collection_id": collection_id},
                        exc_info=True,
                    )

    return asyncio.run(_execute())


@celery_app.task(
    queue="maintenance.default",
    bind=True,
    acks_late=True,
    max_retries=0,
)
def reconcile_collection_vectorization(
    self: Task,
    limit: int = 20,
) -> Dict[str, Any]:
    """Periodic recovery task for table collections that still have pending vectorization."""

    async def _execute() -> Dict[str, Any]:
        from app.services.collection_vectorization_orchestrator import (
            CollectionVectorizationOrchestrator,
        )
        from app.workers.session_factory import get_worker_session

        async with get_worker_session() as session:
            orchestrator = CollectionVectorizationOrchestrator(session)
            result = await orchestrator.reconcile_pending_collections(
                limit=limit,
                countdown=1,
            )
            await session.commit()
            return result

    return asyncio.run(_execute())
