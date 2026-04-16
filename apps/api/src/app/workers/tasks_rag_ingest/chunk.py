from __future__ import annotations

import json
from typing import Any, Dict, Tuple

from celery import Task
from sqlalchemy import select

from app.celery_app import app as celery_app
from app.core.logging import get_logger
from app.models.tenant import Tenants
from app.repositories.rag_ingest_repos import AsyncSourceRepository, AsyncChunkRepository
from app.schemas.common import ChunkProfile
from app.services.document_artifacts import normalize_document_source_meta, upsert_document_artifact
from app.storage.paths import get_chunks_path, calculate_text_checksum
from app.workers.helpers import chunker, create_chunk_payload, generate_chunk_id
from app.workers.tasks_rag_ingest.stage_context import IngestStageContext, run_stage
from app.workers.tasks_rag_ingest.stage_results import NormalizeResult, ChunkResult

logger = get_logger(__name__)

# Defaults
_DEFAULT_PROFILE = ChunkProfile.BY_TOKENS
_DEFAULT_CHUNK_SIZE = 512
_DEFAULT_OVERLAP = 50

_PROFILE_MAP = {v.value: v for v in ChunkProfile}


async def _resolve_chunk_config(
    ctx: IngestStageContext, source: Any
) -> Tuple[ChunkProfile, int, int]:
    """
    Resolve chunk config with priority: source.meta > tenant settings > defaults.
    """
    meta = source.meta or {}

    # 1. Source-level override (per-document)
    src_profile = meta.get("chunk_strategy") or meta.get("chunk_profile")
    src_size = meta.get("chunk_size")
    src_overlap = meta.get("chunk_overlap")

    # 2. Tenant-level defaults
    result = await ctx.session.execute(
        select(Tenants).where(Tenants.id == ctx.tenant_id)
    )
    tenant = result.scalar_one_or_none()

    t_profile = tenant.chunk_profile if tenant else None
    t_size = tenant.chunk_size if tenant else None
    t_overlap = tenant.chunk_overlap if tenant else None

    # 3. Merge: source > tenant > hardcoded defaults
    profile_str = src_profile or t_profile
    profile = _PROFILE_MAP.get(profile_str, _DEFAULT_PROFILE) if profile_str else _DEFAULT_PROFILE
    chunk_size = src_size or t_size or _DEFAULT_CHUNK_SIZE
    overlap = src_overlap or t_overlap or _DEFAULT_OVERLAP

    logger.debug(
        f"Chunk config for {ctx.source_id}: profile={profile.value}, "
        f"size={chunk_size}, overlap={overlap} "
        f"(source={'yes' if src_profile else 'no'}, tenant={'yes' if t_profile else 'no'})"
    )

    return profile, chunk_size, overlap


@celery_app.task(
    queue="ingest.chunk",
    bind=True,
    acks_late=True,
    reject_on_worker_lost=True,
)
def chunk_document(self: Task, normalize_result: Dict[str, Any], tenant_id: str) -> Dict[str, Any]:
    """
    Chunk document text.

    Flow:
    1. Read canonical document from S3
    2. Split text into chunks (smart chunking)
    3. Save chunks to Database (for management)
    4. Upload chunks dump to S3 (for efficient embedding iteration)
    5. Return ChunkResult for embed stage
    """
    prev = NormalizeResult.from_dict(normalize_result) if isinstance(normalize_result, dict) and "source_id" in normalize_result else None
    source_id = prev.source_id if prev else str(normalize_result)
    canonical_key = prev.canonical_key if prev else None

    async def _execute(ctx: IngestStageContext) -> ChunkResult:
        # 1. Mark processing
        await ctx.set_processing()

        source_repo = AsyncSourceRepository(ctx.session, ctx.tenant_id)
        source = await source_repo.get_by_id(ctx.source_id)
        if not source:
            raise ValueError(f"Source {source_id} not found")

        # 2. Check idempotency
        cached = await ctx.check_idempotency(s3_key_field="chunks_key")
        if cached:
            logger.info(f"Chunk cached for {source_id}")
            await ctx.set_completed(metrics={"status": "already_processed", "cached": True})
            await ctx.session.commit()
            return ChunkResult(
                source_id=source_id,
                chunks_key=cached["chunks_key"],
                chunk_count=cached.get("chunk_count", 0),
            )

        # 3. Read Canonical Document
        if not canonical_key:
            raise ValueError(f"No canonical_key provided for source {source_id}")

        canonical_doc = json.loads(await ctx.s3_get(canonical_key))
        text = canonical_doc.get("text", "")

        if not text:
            logger.warning(f"Empty text in canonical doc for {source_id}")
            chunks_data = []
        else:
            # 4. Resolve chunk config: source.meta > tenant settings > defaults
            profile, chunk_size, overlap = await _resolve_chunk_config(ctx, source)

            raw_chunks = chunker(text, profile=profile, chunk_size=chunk_size, overlap=overlap)

            # Format chunks
            chunks_data = []
            for i, rc in enumerate(raw_chunks):
                chunk_id = generate_chunk_id(ctx.source_id, rc["start_pos"], rc["end_pos"])
                payload = create_chunk_payload(
                    tenant_id=ctx.tenant_id,
                    document_id=ctx.source_id,
                    chunk_id=chunk_id,
                    text=rc["text"],
                    start_pos=rc["start_pos"],
                    end_pos=rc["end_pos"],
                    metadata=canonical_doc.get("metadata"),
                )
                payload["index"] = i
                chunks_data.append(payload)

        # 5. Save to DB (bulk insert)
        chunk_repo = AsyncChunkRepository(ctx.session, ctx.tenant_id)
        await chunk_repo.delete_by_document_id(ctx.source_id)

        if chunks_data:
            await chunk_repo.create_batch(chunks_data)

        # 6. Upload Chunks Dump to S3 (JSONL)
        chunks_jsonl = "\n".join(json.dumps(c, ensure_ascii=False) for c in chunks_data)
        chunks_checksum = calculate_text_checksum(text + str(len(chunks_data)))
        chunks_key = get_chunks_path(ctx.tenant_id, ctx.source_id, chunks_checksum)

        await ctx.s3_put(
            key=chunks_key,
            content=chunks_jsonl.encode("utf-8"),
            content_type="application/x-ndjson",
        )

        # Update Source meta with chunks_key for reindexing capability
        source.meta = upsert_document_artifact(
            normalize_document_source_meta(source.meta),
            "chunks",
            {
                "key": chunks_key,
                "content_type": "application/x-ndjson",
                "checksum": chunks_checksum,
                "chunk_count": len(chunks_data),
            },
        )

        # 7. Complete
        await ctx.set_completed(metrics={
            "chunk_count": len(chunks_data),
            "strategy": str(profile) if text else "empty",
            "avg_chunk_size": round(sum(len(c["text"]) for c in chunks_data) / len(chunks_data), 1) if chunks_data else 0,
            "duration_sec": ctx.elapsed_sec,
        })
        await ctx.save_idempotency({
            "status": "completed",
            "chunks_key": chunks_key,
            "chunk_count": len(chunks_data),
        })
        await ctx.session.commit()

        return ChunkResult(source_id=source_id, chunks_key=chunks_key, chunk_count=len(chunks_data))

    return run_stage(
        stage_name="chunk",
        source_id=source_id,
        tenant_id=tenant_id,
        celery_task=self,
        execute_fn=_execute,
    )
