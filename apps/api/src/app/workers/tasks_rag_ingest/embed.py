from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Dict, Any

from celery import Task

from app.celery_app import app as celery_app
from app.core.logging import get_logger
from app.adapters.embeddings import EmbeddingServiceFactory
from app.repositories.rag_ingest_repos import AsyncSourceRepository, AsyncEmbStatusRepository
from app.storage.paths import get_embeddings_path, calculate_text_checksum
from app.services.document_artifacts import get_document_artifact_key, normalize_document_source_meta
from app.workers.tasks_rag_ingest.error_utils import notify_embed_error
from app.workers.tasks_rag_ingest.stage_context import IngestStageContext, run_stage
from app.workers.tasks_rag_ingest.stage_results import ChunkResult, EmbedResult

logger = get_logger(__name__)


@celery_app.task(
    queue="ingest.embed",
    bind=True,
    acks_late=True,
    reject_on_worker_lost=True,
)
def embed_chunks_model(self: Task, chunk_result: Dict[str, Any], tenant_id: str, model_alias: str = "all-MiniLM-L6-v2") -> Dict[str, Any]:
    """
    Generate embeddings for chunks using specified model.

    Flow:
    1. Read chunks from S3 (chunks.jsonl)
    2. Generate embeddings in batches
    3. Write embeddings to S3 (embeddings.jsonl)
    4. Return EmbedResult for index stage
    """
    prev = ChunkResult.from_dict(chunk_result) if isinstance(chunk_result, dict) and "source_id" in chunk_result else None
    source_id = prev.source_id if prev else str(chunk_result)
    chunks_key = prev.chunks_key if prev else None

    stage_name = f"embed.{model_alias}"

    async def _execute(ctx: IngestStageContext) -> EmbedResult:
        # Lock to prevent duplicate embedding of the same model/doc
        lock_key = f"lock:embed:{source_id}:{model_alias}"

        async with ctx.redis.lock(lock_key, timeout=600, blocking_timeout=5):
            # 1. Mark processing
            await ctx.set_processing()

            source_repo = AsyncSourceRepository(ctx.session, ctx.tenant_id)
            emb_status_repo = AsyncEmbStatusRepository(ctx.session, ctx.tenant_id)

            source = await source_repo.get_by_id(ctx.source_id)
            if not source:
                raise ValueError(f"Source {source_id} not found")

            # 2. Check idempotency
            cached = await ctx.check_idempotency(model_alias=model_alias, s3_key_field="embeddings_key")
            if cached:
                logger.info(f"Embedding cached for {source_id}:{model_alias}")
                await ctx.set_completed(metrics={"status": "already_processed", "cached": True})
                await ctx.session.commit()
                return EmbedResult(
                    source_id=source_id,
                    model_alias=model_alias,
                    embeddings_key=cached["embeddings_key"],
                    count=cached.get("count", 0),
                )

            # 3. Read Chunks
            resolved_chunks_key = chunks_key
            if not resolved_chunks_key:
                normalized_meta = normalize_document_source_meta(source.meta)
                resolved_chunks_key = get_document_artifact_key(normalized_meta, "chunks")
            if not resolved_chunks_key:
                raise ValueError(f"No chunks_key provided for source {source_id}")

            chunks_content = await ctx.s3_get(resolved_chunks_key)
            chunks = [json.loads(line) for line in chunks_content.decode("utf-8").splitlines() if line.strip()]

            if not chunks:
                raise ValueError(f"No chunks found in file for {source_id}")

            # 4. Prepare Embedding Service
            await EmbeddingServiceFactory.ensure_model_registered_async(ctx.session, model_alias)
            embedding_service = EmbeddingServiceFactory.get_service(model_alias)
            model_info = embedding_service.get_model_info()
            max_chars = int(getattr(model_info, "max_tokens", 0) or 0)
            if max_chars <= 0:
                max_chars = 512

            await emb_status_repo.create_or_update(
                source_id=ctx.source_id,
                model_alias=model_alias,
                total_count=len(chunks),
                model_version=model_info.version,
            )
            await ctx.session.flush()

            # 5. Generate Embeddings (Batch Processing)
            batch_size = 32
            embeddings_data = []
            processed_count = 0
            truncated_chunks = 0

            for i in range(0, len(chunks), batch_size):
                batch_chunks = chunks[i : i + batch_size]
                batch_texts = []
                for chunk in batch_chunks:
                    raw_text = str(chunk.get("text", "") or "")
                    if len(raw_text) > max_chars:
                        truncated_chunks += 1
                        raw_text = raw_text[:max_chars]
                    batch_texts.append(raw_text)

                batch_vectors = await asyncio.to_thread(embedding_service.embed_texts, batch_texts)

                for chunk, vector in zip(batch_chunks, batch_vectors):
                    embeddings_data.append({
                        "chunk_id": chunk["chunk_id"],
                        "vector": vector,
                        "index": chunk.get("index", 0),
                    })

                processed_count += len(batch_chunks)

                await emb_status_repo.update_done_count(ctx.source_id, model_alias, processed_count)

                from app.services.outbox_helper import emit_embed_progress

                await emit_embed_progress(
                    ctx.session,
                    ctx.repo_factory,
                    ctx.source_id,
                    model_alias,
                    done=processed_count,
                    total=len(chunks),
                    last_error=None,
                )
                await ctx.session.flush()

            # 6. Save Embeddings to S3 (JSONL)
            embeddings_jsonl = "\n".join(json.dumps(e, ensure_ascii=False) for e in embeddings_data)
            embeddings_checksum = calculate_text_checksum(
                f"{resolved_chunks_key}:{model_alias}:{len(embeddings_data)}"
            )

            embeddings_key = get_embeddings_path(
                ctx.tenant_id, ctx.source_id, model_alias, embeddings_checksum, "v1", 0
            ).replace(".npy", ".jsonl")

            await ctx.s3_put(
                key=embeddings_key,
                content=embeddings_jsonl.encode("utf-8"),
                content_type="application/x-ndjson",
            )

            # Persist embedding artifact key in source.meta so index retry can recover
            # even if Redis idempotency cache was evicted.
            normalized_meta = normalize_document_source_meta(source.meta if source else None)
            embedding_artifacts = dict(normalized_meta.get("embedding_artifacts") or {})
            embedding_artifacts[model_alias] = {
                "key": embeddings_key,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            normalized_meta["embedding_artifacts"] = embedding_artifacts
            source.meta = normalized_meta
            await ctx.session.flush()

            # 7. Complete
            duration = ctx.elapsed_sec
            await ctx.set_completed(metrics={
                "vectors": len(embeddings_data),
                "model_version": model_info.version,
                "dimensions": model_info.dimensions,
                "max_chars": max_chars,
                "truncated_chunks": truncated_chunks,
                "duration_sec": duration,
                "vectors_per_sec": round(len(embeddings_data) / duration, 1) if duration > 0 else 0,
            })

            # Emit final 100% progress
            from app.services.outbox_helper import emit_embed_progress as _emit

            await _emit(
                ctx.session,
                ctx.repo_factory,
                ctx.source_id,
                model_alias,
                done=len(chunks),
                total=len(chunks),
                last_error=None,
            )
            await ctx.session.flush()

            await ctx.save_idempotency(
                {"status": "completed", "embeddings_key": embeddings_key, "count": len(embeddings_data)},
                model_alias=model_alias,
            )
            await ctx.session.commit()

            return EmbedResult(
                source_id=source_id,
                model_alias=model_alias,
                embeddings_key=embeddings_key,
                count=len(embeddings_data),
            )

    async def _error_notify(src_id: str, t_id: str, _stage: str, exc: Exception) -> None:
        await notify_embed_error(src_id, t_id, model_alias, exc)

    return run_stage(
        stage_name=stage_name,
        source_id=source_id,
        tenant_id=tenant_id,
        celery_task=self,
        execute_fn=_execute,
        error_notify_fn=_error_notify,
    )
