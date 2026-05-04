from __future__ import annotations

import asyncio
import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from typing import Dict, Any

from celery import Task

from app.celery_app import app as celery_app
from app.core.logging import get_logger
from app.adapters.embeddings import EmbeddingServiceFactory
from app.adapters.s3_client import s3_manager
from app.repositories.rag_ingest_repos import AsyncChunkRepository, AsyncSourceRepository
from app.services.document_artifacts import normalize_document_source_meta
from app.storage.paths import get_idempotency_key
from app.workers.tasks_rag_ingest.stage_context import IngestStageContext, run_stage
from app.workers.tasks_rag_ingest.stage_results import EmbedResult, IndexResult

logger = get_logger(__name__)

_INDEX_POINT_NAMESPACE = uuid.UUID("4b32c67e-86c7-4efb-8980-1e0570f31d16")


def _build_stable_point_id(tenant_id: str, source_id: str, model_alias: str, chunk_id: str) -> str:
    raw = f"{tenant_id}:{source_id}:{model_alias}:{chunk_id}"
    return str(uuid.uuid5(_INDEX_POINT_NAMESPACE, raw))


@celery_app.task(
    queue="ingest.index",
    bind=True,
    acks_late=True,
    reject_on_worker_lost=True,
)
def index_model(self: Task, embed_result: Dict[str, Any], tenant_id: str) -> Dict[str, Any]:
    """
    Index embeddings into Qdrant vector store.

    Flow:
    1. Read embeddings from S3 (embeddings.jsonl)
    2. Fetch chunk metadata from DB (Postgres)
    3. Upsert payload + vectors to Qdrant
    4. Return IndexResult (terminal)
    """
    prev = EmbedResult.from_dict(embed_result) if isinstance(embed_result, dict) and "source_id" in embed_result else None
    source_id = prev.source_id if prev else embed_result.get("source_id", "")
    model_alias = prev.model_alias if prev else embed_result.get("model_alias", "")
    embeddings_key = prev.embeddings_key if prev else embed_result.get("embeddings_key")

    stage_name = f"index.{model_alias}"

    async def _execute(ctx: IngestStageContext) -> IndexResult:
        current_embeddings_key = embeddings_key
        lock_key = f"lock:index:{source_id}:{model_alias}"

        async with ctx.redis.lock(lock_key, timeout=600, blocking_timeout=5):
            # 1. Mark processing
            await ctx.set_processing()

            chunk_repo = AsyncChunkRepository(ctx.session, ctx.tenant_id)

            # 2. Check idempotency
            cached = await ctx.check_idempotency(model_alias=model_alias)
            if cached:
                logger.info(f"Index already completed for {source_id} with {model_alias}")
                await ctx.set_completed(metrics={"status": "already_processed", "cached": True})
                await ctx.session.commit()
                return IndexResult(source_id=source_id, model_alias=model_alias, indexed_count=cached.get("indexed_count", 0))

            # 3. Validate embeddings key
            if not current_embeddings_key:
                embed_idem_key = get_idempotency_key(ctx.tenant_id, ctx.source_id, "embed", model_alias)
                raw_cached = await ctx.redis.get(embed_idem_key)
                if raw_cached:
                    try:
                        cached_embed = json.loads(raw_cached)
                        current_embeddings_key = cached_embed.get("embeddings_key")
                    except (json.JSONDecodeError, TypeError):
                        current_embeddings_key = None
            if not current_embeddings_key:
                source_repo = AsyncSourceRepository(ctx.session, ctx.tenant_id)
                source = await source_repo.get_by_id(ctx.source_id)
                normalized_meta = normalize_document_source_meta((source.meta or {}) if source else {})
                embedding_artifacts = normalized_meta.get("embedding_artifacts") or {}
                artifact = embedding_artifacts.get(model_alias)
                if isinstance(artifact, dict):
                    current_embeddings_key = artifact.get("key")
                elif isinstance(artifact, str):
                    current_embeddings_key = artifact
            if not current_embeddings_key:
                prefix = f"{ctx.tenant_id_str}/{source_id}/embeddings/{model_alias}/"
                objects = await s3_manager.list_objects(
                    bucket=ctx.settings.S3_BUCKET_RAG,
                    prefix=prefix,
                    max_keys=200,
                )
                candidates = [
                    obj
                    for obj in objects
                    if isinstance(obj, dict) and str(obj.get("Key", "")).endswith(".jsonl")
                ]
                if candidates:
                    candidates.sort(
                        key=lambda obj: (
                            obj.get("LastModified") is not None,
                            obj.get("LastModified") or "",
                            str(obj.get("Key", "")),
                        ),
                        reverse=True,
                    )
                    current_embeddings_key = str(candidates[0].get("Key"))
            if not current_embeddings_key:
                raise ValueError(f"No embeddings_key provided for {source_id}")

            # 4. Fetch Chunks Metadata from DB
            chunks = await chunk_repo.get_by_source_id(ctx.source_id)
            chunk_map = {c.chunk_id: c for c in chunks}

            # 5. Prepare Qdrant Client
            from app.adapters.impl.qdrant import QdrantVectorStore

            vector_store = QdrantVectorStore()
            await EmbeddingServiceFactory.ensure_model_registered_async(ctx.session, model_alias)
            embedding_service = EmbeddingServiceFactory.get_service(model_alias)
            model_info = embedding_service.get_model_info()

            # Resolve Qdrant collection name: use collection's own name if available
            from sqlalchemy import select
            from app.models.collection import Collection
            from app.models.rag_ingest import DocumentCollectionMembership

            membership_row = (
                await ctx.session.execute(
                    select(
                        DocumentCollectionMembership.collection_id,
                        DocumentCollectionMembership.collection_row_id,
                        Collection.qdrant_collection_name,
                    )
                    .join(
                        Collection,
                        Collection.id == DocumentCollectionMembership.collection_id,
                    )
                    .where(
                        DocumentCollectionMembership.source_id == ctx.source_id,
                        DocumentCollectionMembership.tenant_id == ctx.tenant_id,
                    )
                    .limit(1)
                )
            ).first()

            coll_qdrant_name = membership_row.qdrant_collection_name if membership_row else None
            collection_name = coll_qdrant_name or f"{ctx.tenant_id_str}__{model_alias}"

            # Collection context for payload enrichment
            coll_collection_id = str(membership_row.collection_id) if membership_row else None
            coll_row_id = str(membership_row.collection_row_id) if membership_row and membership_row.collection_row_id else None

            # 6. Download embeddings to temp file and batch upsert
            fd, tmp_path = tempfile.mkstemp()
            os.close(fd)

            indexed_count = 0
            try:
                await s3_manager.download_file(
                    bucket=ctx.settings.S3_BUCKET_RAG,
                    key=current_embeddings_key,
                    file_path=tmp_path,
                )

                batch_size = 100
                vectors = []
                payloads = []
                ids = []
                collection_ready = False

                async def _upsert_with_retry(batch_vectors, batch_payloads, batch_ids) -> None:
                    attempts = 3
                    for attempt in range(1, attempts + 1):
                        try:
                            await vector_store.upsert(collection_name, batch_vectors, batch_payloads, batch_ids)
                            return
                        except Exception as exc:
                            if attempt >= attempts:
                                raise
                            logger.warning(
                                "Qdrant upsert retry %s/%s for source=%s model=%s: %s",
                                attempt,
                                attempts,
                                source_id,
                                model_alias,
                                str(exc),
                            )
                            await asyncio.sleep(0.3 * attempt)

                with open(tmp_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue

                        try:
                            record = json.loads(line)
                        except json.JSONDecodeError:
                            logger.warning(f"Skipping invalid JSON line in embeddings for {source_id}")
                            continue

                        chunk_id = record["chunk_id"]
                        chunk = chunk_map.get(chunk_id)
                        if not chunk:
                            continue

                        vector = record["vector"]
                        vectors.append(vector)
                        vector_dim = len(vector) if isinstance(vector, (list, tuple)) else model_info.dimensions
                        if not collection_ready:
                            try:
                                await vector_store.ensure_collection(collection_name, vector_dim)
                            except ValueError as exc:
                                if coll_qdrant_name:
                                    model_specific_collection = f"{coll_qdrant_name}__{model_alias}"
                                    logger.warning(
                                        "Qdrant collection dim mismatch for %s (%s), fallback to %s",
                                        collection_name,
                                        str(exc),
                                        model_specific_collection,
                                    )
                                    collection_name = model_specific_collection
                                    await vector_store.ensure_collection(collection_name, vector_dim)
                                else:
                                    raise
                            collection_ready = True

                        ids.append(
                            _build_stable_point_id(
                                tenant_id=ctx.tenant_id_str,
                                source_id=source_id,
                                model_alias=model_alias,
                                chunk_id=chunk_id,
                            )
                        )

                        payload = {
                            "tenant_id": ctx.tenant_id_str,
                            "source_id": source_id,
                            "chunk_id": chunk_id,
                            "page": chunk.page or 0,
                            "lang": chunk.lang or "en",
                            "mime": "text/plain",
                            "embed_model_alias": model_alias,
                            "version": model_info.version,
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                            "tags": [],
                            "text": chunk.meta.get("text", "") if chunk.meta else "",
                        }
                        # Enrich with collection context if present
                        if coll_collection_id:
                            payload["collection_id"] = coll_collection_id
                        if coll_row_id:
                            payload["row_id"] = coll_row_id

                        payloads.append(payload)

                        if len(vectors) >= batch_size:
                            await _upsert_with_retry(vectors, payloads, ids)
                            indexed_count += len(vectors)
                            vectors, payloads, ids = [], [], []

                if vectors:
                    await _upsert_with_retry(vectors, payloads, ids)
                    indexed_count += len(vectors)
            finally:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)

            # 7. Complete
            await ctx.set_completed(metrics={
                "indexed_count": indexed_count,
                "collection": collection_name,
                "model_version": model_info.version,
                "duration_sec": ctx.elapsed_sec,
            })
            await ctx.save_idempotency(
                {"status": "completed", "indexed_count": indexed_count},
                model_alias=model_alias,
            )
            await ctx.session.commit()

            return IndexResult(
                source_id=source_id,
                model_alias=model_alias,
                indexed_count=indexed_count,
                collection=collection_name,
            )

    return run_stage(
        stage_name=stage_name,
        source_id=source_id,
        tenant_id=tenant_id,
        celery_task=self,
        execute_fn=_execute,
    )
