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
from app.adapters.s3_client import s3_manager
from app.repositories.rag_ingest_repos import AsyncChunkRepository, AsyncSourceRepository
from app.services.document_artifacts import normalize_document_source_meta, get_document_artifact_key
from app.storage.paths import get_idempotency_key
from app.workers.tasks_rag_ingest.stage_context import IngestStageContext, run_stage
from app.workers.tasks_rag_ingest.stage_results import EmbedResult, IndexResult

logger = get_logger(__name__)

_INDEX_POINT_NAMESPACE = uuid.UUID("4b32c67e-86c7-4efb-8980-1e0570f31d16")
_DOC_INDEX_VERSION = "doc-v5-generation-fenced"


def _build_stable_point_id(tenant_id: str, source_id: str, model_alias: str, chunk_id: str,
                           generation: int | None = None, attempt_id: str = "") -> str:
    raw = f"{tenant_id}:{source_id}:{model_alias}:{generation or 0}:{attempt_id}:{chunk_id}"
    return str(uuid.uuid5(_INDEX_POINT_NAMESPACE, raw))


def _prefilter_payload_key(field_name: str) -> str:
    safe = "".join(ch if ch.isalnum() else "_" for ch in str(field_name))
    return f"pf_{safe.lower()}"


@celery_app.task(
    queue="ingest.index",
    bind=True,
    acks_late=True,
    reject_on_worker_lost=True,
)
def index_model(
    self: Task, embed_result: Dict[str, Any], tenant_id: str, run_id: str | None = None, generation: int | None = None,
) -> Dict[str, Any]:
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

        # Match the one-hour Celery hard limit; the soft limit exits earlier.
        async with ctx.redis.lock(lock_key, timeout=60 * 60, blocking_timeout=5):
            # 1. Mark processing
            await ctx.set_processing()

            chunk_repo = AsyncChunkRepository(ctx.session, ctx.tenant_id)
            source_repo = AsyncSourceRepository(ctx.session, ctx.tenant_id)

            # 2. Check idempotency
            cached = await ctx.check_idempotency(model_alias=model_alias)
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
            if not chunk_map:
                raise ValueError(f"No canonical chunks found for {source_id}; refusing to mark an empty index ready")
            source = await source_repo.get_by_id(ctx.source_id)
            normalized_meta = normalize_document_source_meta((source.meta or {}) if source else {})
            canonical_chunks_key = get_document_artifact_key(normalized_meta, "chunks")
            if not canonical_chunks_key:
                raise ValueError(f"No canonical chunks artifact is recorded for {source_id}")
            collection_meta = normalized_meta.get("collection") or {}
            raw_prefilter = collection_meta.get("prefilter") or {}
            if not isinstance(raw_prefilter, dict):
                raw_prefilter = {}

            # 5. Prepare Qdrant Client
            from app.adapters.impl.qdrant import QdrantVectorStore

            vector_store = QdrantVectorStore()
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
                        Collection.vector_config,
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
            base_collection_name = coll_qdrant_name or f"{ctx.tenant_id_str}__documents"
            from app.services.vector_index_service import VectorIndexService
            target = await VectorIndexService(ctx.session).resolve(base_collection_name, model_alias)
            collection_name = target.collection_name
            await ctx.session.commit()
            if await VectorIndexService.cache_is_current(
                target, cached, current_embeddings_key, vector_store, source_id,
                ctx.tenant_id_str, expected_count=len(chunk_map),
            ):
                await ctx.set_completed(metrics={
                    "status": "already_processed", "cached": True,
                    "embedding_fingerprint": target.fingerprint,
                    "model_version": target.version, "collection": collection_name,
                    "indexed_count": cached.get("indexed_count", 0),
                })
                return IndexResult(source_id=source_id, model_alias=model_alias, indexed_count=cached.get("indexed_count", 0), collection=collection_name)

            # Collection context for payload enrichment
            coll_collection_id = str(membership_row.collection_id) if membership_row else None
            coll_row_id = str(membership_row.collection_row_id) if membership_row and membership_row.collection_row_id else None

            # 6. Download embeddings to temp file and batch upsert
            fd, tmp_path = tempfile.mkstemp()
            os.close(fd)

            indexed_count = 0
            upsert_started = False
            attempt_id = ctx.celery_task_id or str(uuid.uuid4())
            try:
                downloaded = await s3_manager.download_file(
                    bucket=ctx.settings.S3_BUCKET_RAG,
                    key=current_embeddings_key,
                    file_path=tmp_path,
                )
                if not downloaded:
                    raise IOError(f"Failed to download embeddings artifact {current_embeddings_key}")

                batch_size = 100
                vectors = []
                payloads = []
                ids = []
                seen_chunk_ids: set[str] = set()

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

                        record = json.loads(line)
                        if not isinstance(record, dict):
                            raise ValueError("Embedding artifact contains a non-object record")
                        chunk_id = record.get("chunk_id")
                        if not isinstance(chunk_id, str) or not chunk_id:
                            raise ValueError("Embedding artifact contains a missing or invalid chunk_id")
                        if chunk_id in seen_chunk_ids:
                            raise ValueError(f"Embedding artifact contains duplicate chunk_id {chunk_id}")
                        seen_chunk_ids.add(chunk_id)
                        chunk = chunk_map.get(chunk_id)
                        if not chunk:
                            raise ValueError(f"Embedding artifact references unknown chunk_id {chunk_id}")

                        vector = record.get("vector")
                        if record.get("chunks_key") != canonical_chunks_key:
                            raise ValueError("Embedding artifact belongs to another canonical input; rerun embedding")
                        if record.get("embedding_fingerprint") != target.fingerprint:
                            raise ValueError("Embedding artifact belongs to another or unknown vector space; rerun embedding before indexing")
                        from app.adapters.embeddings import validate_embedding_batch
                        validate_embedding_batch([vector], 1, target.dimensions)
                        vectors.append(vector)

                        ids.append(
                            _build_stable_point_id(
                                tenant_id=ctx.tenant_id_str,
                                source_id=source_id,
                                model_alias=model_alias,
                                chunk_id=chunk_id,
                                generation=ctx.generation,
                                attempt_id=attempt_id,
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
                            "embedding_fingerprint": target.fingerprint,
                            "index_version": _DOC_INDEX_VERSION,
                            "version": target.version,
                            "index_revision": _DOC_INDEX_VERSION,
                            "ingest_generation": int(ctx.generation or 0),
                            "ingest_attempt_id": attempt_id,
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                            "tags": [],
                            "text": chunk.meta.get("text", "") if chunk.meta else "",
                        }
                        # Add normalized prefilter keys to allow Qdrant-side metadata prefilter.
                        for field_name, field_value in raw_prefilter.items():
                            key = _prefilter_payload_key(field_name)
                            if isinstance(field_value, (str, int, float, bool)):
                                payload[key] = field_value
                            elif isinstance(field_value, list):
                                scalar_values = [
                                    v for v in field_value if isinstance(v, (str, int, float, bool))
                                ]
                                if scalar_values:
                                    payload[key] = scalar_values
                        # Enrich with collection context if present
                        if coll_collection_id:
                            payload["collection_id"] = coll_collection_id
                        if coll_row_id:
                            payload["row_id"] = coll_row_id

                        payloads.append(payload)
                if seen_chunk_ids != set(chunk_map):
                    missing = sorted(set(chunk_map) - seen_chunk_ids)
                    extra = sorted(seen_chunk_ids - set(chunk_map))
                    raise ValueError(
                        f"Embedding artifact is incomplete for {source_id}: "
                        f"expected={len(chunk_map)} seen={len(seen_chunk_ids)} "
                        f"missing={missing[:5]} extra={extra[:5]}"
                    )
                await vector_store.ensure_collection(collection_name, target.dimensions)
                # Validate the complete artifact before touching the prior index.
                # A failed/retried reindex can therefore never leave old points
                # mixed with a silently truncated new embedding file.
                for start in range(0, len(vectors), batch_size):
                    if not await ctx.is_current_generation():
                        await ctx.session.commit()
                        raise RuntimeError("Ingest generation changed before vector upsert")
                    await ctx.session.commit()
                    end = start + batch_size
                    upsert_started = True
                    await _upsert_with_retry(vectors[start:end], payloads[start:end], ids[start:end])
                    indexed_count += len(vectors[start:end])
                if not await ctx.is_current_generation():
                    await ctx.session.commit()
                    await vector_store.delete_points(collection_name, ids)
                    raise RuntimeError("Ingest generation changed while vectors were being indexed")
                await ctx.session.commit()
                # New generation points are complete before old points are
                # removed, so a failed reindex keeps the prior index available.
                await vector_store.delete_document_points_before_generation(
                    collection_name, source_id, ctx.tenant_id_str,
                    int(ctx.generation or 0), attempt_id,
                )
            except Exception:
                # Remove only points written by this task attempt. Other runs
                # may already have published their own points for the source.
                if upsert_started and await vector_store.collection_exists(collection_name):
                    try:
                        await vector_store.delete_points(collection_name, ids)
                    except Exception:
                        logger.exception("Failed to clean partial vector index source=%s model=%s", source_id, model_alias)
                raise
            finally:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)

            # 7. Complete
            await ctx.set_completed(metrics={
                "indexed_count": indexed_count,
                "collection": collection_name,
                "model_version": target.version,
                "embedding_fingerprint": target.fingerprint,
                "duration_sec": ctx.elapsed_sec,
            })
            await ctx.save_idempotency(
                {"status": "completed", "indexed_count": indexed_count, "embedding_fingerprint": target.fingerprint, "collection": collection_name, "embeddings_key": current_embeddings_key},
                model_alias=model_alias,
            )

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
        run_id=run_id,
        generation=generation,
    )
