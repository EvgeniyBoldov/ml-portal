from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Dict, Any

from celery import Task
from sqlalchemy import select

from app.celery_app import app as celery_app
from app.core.logging import get_logger
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
def embed_chunks_model(
    self: Task, chunk_result: Dict[str, Any], tenant_id: str, model_alias: str = "all-MiniLM-L6-v2",
    run_id: str | None = None, generation: int | None = None,
) -> Dict[str, Any]:
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

        # Celery's soft task limit is 55 minutes; keep the lease alive beyond
        # that bound so context exit cannot turn completed work into failure.
        async with ctx.redis.lock(lock_key, timeout=60 * 60, blocking_timeout=5):
            # 1. Mark processing
            await ctx.set_processing()

            source_repo = AsyncSourceRepository(ctx.session, ctx.tenant_id)
            emb_status_repo = AsyncEmbStatusRepository(ctx.session, ctx.tenant_id)

            source = await source_repo.get_by_id(ctx.source_id)
            if not source:
                raise ValueError(f"Source {source_id} not found")

            from app.services.vector_index_service import VectorIndexService
            target = await VectorIndexService(ctx.session).resolve("embedding", model_alias)
            await ctx.session.commit()
            embedding_service = target.embedding_service
            model_info = await asyncio.to_thread(embedding_service.get_model_info)

            normalized_meta = normalize_document_source_meta(source.meta)
            resolved_chunks_key = chunks_key or get_document_artifact_key(normalized_meta, "chunks")
            if not resolved_chunks_key:
                raise ValueError(f"No chunks_key provided for source {source_id}")
            chunks_content = await ctx.s3_get(resolved_chunks_key)
            chunks = [json.loads(line) for line in chunks_content.decode("utf-8").splitlines() if line.strip()]

            if not chunks:
                raise ValueError(f"No chunks found in file for {source_id}")

            # 4. Model identity was resolved before the cache check. It is
            # part of both the artifact fingerprint and the cache record.
            max_tokens = int(getattr(model_info, "max_tokens", 0) or 0)
            if max_tokens <= 0:
                raise ValueError(f"Embedding token limit is unknown for {model_alias}")

            await emb_status_repo.create_or_update(
                source_id=ctx.source_id,
                model_alias=model_alias,
                total_count=len(chunks),
                model_version=model_info.version,
            )
            await ctx.session.flush()
            await ctx.session.commit()

            # 5. Generate Embeddings (Batch Processing)
            batch_size = 32
            embeddings_data = []
            processed_count = 0

            for i in range(0, len(chunks), batch_size):
                batch_chunks = chunks[i : i + batch_size]
                batch_texts = [str(chunk.get("text", "") or "") for chunk in batch_chunks]
                from app.services.bounded_embeddings import embed_texts_bounded
                batch_vectors = await asyncio.to_thread(embed_texts_bounded, embedding_service, batch_texts)

                for chunk, vector in zip(batch_chunks, batch_vectors):
                    embeddings_data.append({
                        "chunk_id": chunk["chunk_id"],
                        "vector": vector,
                        "embedding_fingerprint": target.fingerprint,
                        "chunks_key": resolved_chunks_key,
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
                await ctx.session.commit()

            # 6. Save Embeddings to S3 (JSONL)
            embeddings_jsonl = "\n".join(json.dumps(e, ensure_ascii=False) for e in embeddings_data)
            embeddings_checksum = calculate_text_checksum(
                f"{resolved_chunks_key}:{model_alias}:{target.fingerprint}:{len(embeddings_data)}"
            )

            embeddings_key = get_embeddings_path(
                ctx.tenant_id, ctx.source_id, model_alias, embeddings_checksum, "v1", 0
            )

            await ctx.s3_put(
                key=embeddings_key,
                content=embeddings_jsonl.encode("utf-8"),
                content_type="application/x-ndjson",
            )

            # Persist embedding artifact key in source.meta so index retry can recover
            # even if Redis idempotency cache was evicted.
            from app.models.rag_ingest import Source
            latest_meta = await ctx.session.scalar(
                select(Source.meta).where(
                    Source.source_id == ctx.source_id,
                    Source.tenant_id == ctx.tenant_id,
                ).with_for_update()
            )
            normalized_meta = normalize_document_source_meta(latest_meta)
            embedding_artifacts = dict(normalized_meta.get("embedding_artifacts") or {})
            embedding_artifacts[model_alias] = {
                "key": embeddings_key,
                "embedding_fingerprint": target.fingerprint,
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
                "max_tokens": max_tokens,
                "embedding_fingerprint": target.fingerprint,
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
                {"status": "completed", "embeddings_key": embeddings_key, "count": len(embeddings_data), "model_version": model_info.version, "embedding_fingerprint": target.fingerprint, "chunks_key": resolved_chunks_key},
                model_alias=model_alias,
            )

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
        run_id=run_id,
        generation=generation,
    )
