from __future__ import annotations

import asyncio
import csv
import io
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from celery import Task
from sqlalchemy import text as sa_text

from app.adapters.s3_client import s3_manager
from app.celery_app import app as celery_app
from app.core.cache import get_cache
from app.core.config import get_settings
from app.core.logging import get_logger
from app.workers.session_factory import get_worker_session

logger = get_logger(__name__)

EXPORT_TTL_SECONDS = 2 * 60 * 60
EXPORT_META_PREFIX = "collection_export_meta:"


def _meta_key(export_id: str) -> str:
    return f"{EXPORT_META_PREFIX}{export_id}"


@celery_app.task(
    queue="analyze_medium",
    bind=True,
    acks_late=True,
    reject_on_worker_lost=True,
    max_retries=2,
    default_retry_delay=15,
)
def export_collection_csv(
    self: Task,
    *,
    export_id: str,
    tenant_id: str,
    owner_id: str,
    collection_id: str,
    collection_slug: str,
    table_name: str,
    field_names: List[str],
) -> Dict[str, Any]:
    async def _run() -> Dict[str, Any]:
        cache = await get_cache()
        meta = await cache.get(_meta_key(export_id)) or {}
        now = datetime.now(timezone.utc)

        try:
            async with get_worker_session() as session:
                quoted_columns = ", ".join([f'"{name}"' for name in field_names])
                query = sa_text(
                    f'SELECT {quoted_columns} FROM {table_name} ORDER BY "id" ASC'
                )
                result = await session.execute(query)
                rows = [dict(row) for row in result.mappings().all()]

            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=field_names, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow({name: row.get(name) for name in field_names})
            payload = output.getvalue().encode("utf-8")

            settings = get_settings()
            key = (
                f"tenants/{tenant_id}/exports/collections/{collection_id}/"
                f"{export_id}.csv"
            )
            uploaded = await s3_manager.upload_content_sync(
                bucket=settings.S3_BUCKET_ARTIFACTS,
                key=key,
                content=payload,
                content_type="text/csv",
            )
            if not uploaded:
                raise RuntimeError("Failed to upload CSV export artifact")

            expires_at = now + timedelta(seconds=EXPORT_TTL_SECONDS)
            final_meta = {
                **meta,
                "status": "ready",
                "tenant_id": tenant_id,
                "owner_id": owner_id,
                "bucket": settings.S3_BUCKET_ARTIFACTS,
                "key": key,
                "file_name": f"{collection_slug}_export.csv",
                "content_type": "text/csv",
                "size_bytes": len(payload),
                "expires_at": expires_at.isoformat(),
                "updated_at": now.isoformat(),
            }
            await cache.set(_meta_key(export_id), final_meta, ttl=EXPORT_TTL_SECONDS)
            return {"status": "ready", "export_id": export_id}
        except Exception as exc:
            logger.error(
                "collection_csv_export_failed",
                extra={"export_id": export_id, "error": str(exc)},
            )
            failed_meta = {
                **meta,
                "status": "failed",
                "tenant_id": tenant_id,
                "owner_id": owner_id,
                "error": str(exc),
                "updated_at": now.isoformat(),
            }
            await cache.set(_meta_key(export_id), failed_meta, ttl=EXPORT_TTL_SECONDS)
            raise

    return asyncio.run(_run())
