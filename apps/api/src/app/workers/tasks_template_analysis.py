from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

from celery import shared_task

from app.core.logging import get_logger
from app.services.collection.template_contract import TemplateContract
from app.services.collection.template_description_builder import TemplateDescriptionBuilder
from app.services.collection.template_layout_parser import TemplateLayoutParser
from app.services.collection.template_schema_builder import TemplateSchemaBuilder
from app.services.collection.template_status_stream import (
    TemplateStatusPublisher,
    build_template_status_graph,
)
from app.repositories.template_analysis_status_repo import AsyncTemplateAnalysisStatusRepository
from app.services.collection_vectorization_orchestrator import CollectionVectorizationOrchestrator
from app.workers.session_factory import get_worker_session

logger = get_logger(__name__)

TEMPLATE_STATUS_UPLOADED = "uploaded"
TEMPLATE_STATUS_ANALYZED = "analyzed"
TEMPLATE_STATUS_READY = "ready"
TEMPLATE_STATUS_ARCHIVED = "archived"

_TASK_NODE_KEYS = {"description", "schema"}


def _resolve_template_status(current_row: dict[str, Any], nodes: list[Any]) -> str:
    current_status = str(current_row.get("status") or TEMPLATE_STATUS_UPLOADED).strip().lower()
    if current_status in {TEMPLATE_STATUS_READY, TEMPLATE_STATUS_ARCHIVED, TEMPLATE_STATUS_ANALYZED}:
        return current_status

    node_map = {str(node.node_key): node for node in nodes if getattr(node, "node_key", None) in _TASK_NODE_KEYS}
    if all(str(node_map.get(key).status if node_map.get(key) else "").strip().lower() == "completed" for key in _TASK_NODE_KEYS):
        return TEMPLATE_STATUS_ANALYZED
    return TEMPLATE_STATUS_UPLOADED


async def _run_with_context(collection_id: str, row_id: str, handler):
    from app.services.collection_service import CollectionService

    async with get_worker_session() as session:
        service = CollectionService(session)
        collection = await service.get_by_id(uuid.UUID(collection_id))
        if collection is None:
            raise ValueError(f"Collection {collection_id} not found")

        await service.ensure_contract_fields_present(collection, ensure_vector_infra=False)

        row = await service.get_row_by_id(collection, uuid.UUID(row_id))
        if row is None:
            raise ValueError(f"Template row {row_id} not found")

        status_repo = AsyncTemplateAnalysisStatusRepository(session)
        return await handler(session, service, status_repo, collection, row)


async def _load_template_file(row: dict[str, Any]) -> tuple[bytes, str]:
    file_meta = row.get("file") or {}
    if not isinstance(file_meta, dict):
        raise ValueError("Template file metadata is missing")

    bucket = str(file_meta.get("bucket") or "").strip()
    s3_key = str(file_meta.get("s3_key") or "").strip()
    filename = str(file_meta.get("filename") or "template.bin").strip()
    if not bucket or not s3_key:
        raise ValueError("Template file metadata is incomplete")

    from app.adapters.s3_client import s3_manager

    payload = await s3_manager.get_object(bucket=bucket, key=s3_key)
    if payload is None:
        raise ValueError(f"Failed to load template file s3://{bucket}/{s3_key}")
    return payload, filename


async def _publish_snapshot(
    *,
    collection_id: str,
    row: dict[str, Any],
    status_repo: AsyncTemplateAnalysisStatusRepository,
) -> None:
    from app.core.config import get_settings
    import redis.asyncio as aioredis

    settings = get_settings()
    if not settings.REDIS_URL:
        return
    redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        publisher = TemplateStatusPublisher(redis_client)
        nodes = await status_repo.get_nodes_by_row_id(uuid.UUID(str(row["id"])))
        await publisher.publish_snapshot(
            row_id=uuid.UUID(str(row["id"])),
            payload=build_template_status_graph(
                row,
                collection_id=collection_id,
                analysis_nodes=[
                    {
                        "node_key": node.node_key,
                        "status": node.status,
                        "error_short": node.error_short,
                        "metrics_json": node.metrics_json,
                    }
                    for node in nodes
                ],
            ),
        )
    finally:
        try:
            await redis_client.aclose()
        except Exception:
            pass


async def _update_analysis_node(
    *,
    status_repo: AsyncTemplateAnalysisStatusRepository,
    collection_id: uuid.UUID,
    row_id: uuid.UUID,
    node_key: str,
    status: str,
    error_short: str | None = None,
    metrics_json: dict[str, Any] | None = None,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
) -> None:
    await status_repo.upsert_node(
        collection_id=collection_id,
        row_id=row_id,
        node_key=node_key,
        status=status,
        error_short=error_short,
        metrics_json=metrics_json,
        started_at=started_at,
        finished_at=finished_at,
    )


@shared_task(
    name="app.workers.tasks_template_analysis.generate_template_description",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
)
def generate_template_description(self, collection_id: str, row_id: str) -> dict[str, Any]:
    async def _handler(session, service, status_repo, collection, row) -> dict[str, Any]:
        row_uuid = uuid.UUID(row_id)
        collection_uuid = uuid.UUID(collection_id)
        try:
            await _update_analysis_node(
                status_repo=status_repo,
                collection_id=collection_uuid,
                row_id=row_uuid,
                node_key="description",
                status="processing",
                started_at=datetime.now(timezone.utc),
            )
            await session.commit()

            # Load contract (either existing or parse new)
            raw_schema = row.get("template_schema") or {}
            contract = TemplateContract.from_jsonb(raw_schema)

            resolved_title = row.get("title")
            resolved_version = row.get("template_version")

            if not contract.fields:
                # Need to parse and build schema first
                payload, filename = await _load_template_file(row)
                parser = TemplateLayoutParser()
                layout = parser.parse(payload, filename)
                schema_builder = TemplateSchemaBuilder(llm=None)
                contract = await schema_builder.build(layout, title=layout.title)
                resolved_title = resolved_title or layout.title or filename
                resolved_version = resolved_version or layout.version

            # Build description from contract (S3)
            desc_builder = TemplateDescriptionBuilder(llm=None)  # Can be configured with LLM
            description = await desc_builder.build(
                contract,
                title=resolved_title,
                version=resolved_version,
            )

            updates = {
                "title": resolved_title or "Template",
                "template_version": resolved_version,
                "description": description,
            }

            await _update_analysis_node(
                status_repo=status_repo,
                collection_id=collection_uuid,
                row_id=row_uuid,
                node_key="description",
                status="completed",
                metrics_json={
                    "title": resolved_title,
                    "version": resolved_version,
                },
                finished_at=datetime.now(timezone.utc),
            )
            await session.commit()
            updated_row = await service.update_row(collection, row_uuid, updates)
            nodes = await status_repo.get_nodes_by_row_id(row_uuid)
            updates_status = _resolve_template_status(updated_row or row, nodes)
            if updates_status != str((updated_row or row).get("status") or "").strip().lower():
                updated_row = await service.update_row(collection, row_uuid, {"status": updates_status}, skip_vectorization=True)
                await session.commit()
            updated_row = await service.get_row_by_id(collection, row_uuid)
            if updated_row is not None:
                await _publish_snapshot(collection_id=collection_id, row=updated_row, status_repo=status_repo)

            vectorization_task_id = None
            if updated_row is not None and collection.has_vector_search:
                vectorization_task_id = CollectionVectorizationOrchestrator.enqueue(
                    collection_id=collection.id,
                    tenant_id=collection.tenant_id,
                    row_ids=[row_id],
                    countdown=1,
                )

            return {
                "status": "ok",
                "collection_id": collection_id,
                "row_id": row_id,
                "template_status": str((updated_row or row).get("status") or TEMPLATE_STATUS_UPLOADED),
                "vectorization_task_id": vectorization_task_id,
            }
        except Exception as exc:
            logger.error("template_description_generation_failed: %s", exc, exc_info=True)
            await _update_analysis_node(
                status_repo=status_repo,
                collection_id=collection_uuid,
                row_id=row_uuid,
                node_key="description",
                status="failed",
                error_short=str(exc)[:2000],
                finished_at=datetime.now(timezone.utc),
            )
            await session.commit()
            updated_row = await service.get_row_by_id(collection, row_uuid)
            if updated_row is not None:
                await _publish_snapshot(collection_id=collection_id, row=updated_row, status_repo=status_repo)
            raise

    try:
        return asyncio.run(_run_with_context(collection_id, row_id, _handler))
    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task(
    name="app.workers.tasks_template_analysis.generate_template_schema",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
)
def generate_template_schema(self, collection_id: str, row_id: str) -> dict[str, Any]:
    async def _handler(session, service, status_repo, collection, row) -> dict[str, Any]:
        row_uuid = uuid.UUID(row_id)
        collection_uuid = uuid.UUID(collection_id)
        try:
            await _update_analysis_node(
                status_repo=status_repo,
                collection_id=collection_uuid,
                row_id=row_uuid,
                node_key="schema",
                status="processing",
                started_at=datetime.now(timezone.utc),
            )
            await session.commit()

            payload, filename = await _load_template_file(row)
            
            # Step 1: Parse layout (S1)
            parser = TemplateLayoutParser()
            layout = parser.parse(payload, filename)
            
            # Step 2: Build schema from layout (S2)
            existing_contract = TemplateContract.from_jsonb(row.get("template_schema") or {})
            schema_builder = TemplateSchemaBuilder(llm=None)  # Can be configured with LLM
            contract = await schema_builder.build(layout, existing_contract=existing_contract, title=layout.title)
            
            updates = {
                "title": layout.title or row.get("title") or filename,
                "template_version": layout.version or row.get("template_version"),
                "template_schema": contract.to_jsonb(),
            }

            await _update_analysis_node(
                status_repo=status_repo,
                collection_id=collection_uuid,
                row_id=row_uuid,
                node_key="schema",
                status="completed",
                metrics_json={
                    "title": layout.title or row.get("title") or filename,
                    "version": layout.version or row.get("template_version"),
                },
                finished_at=datetime.now(timezone.utc),
            )
            await session.commit()
            updated_row = await service.update_row(collection, row_uuid, updates, skip_vectorization=True)
            nodes = await status_repo.get_nodes_by_row_id(row_uuid)
            updates_status = _resolve_template_status(updated_row or row, nodes)
            if updates_status != str((updated_row or row).get("status") or "").strip().lower():
                updated_row = await service.update_row(collection, row_uuid, {"status": updates_status}, skip_vectorization=True)
                await session.commit()
            updated_row = await service.get_row_by_id(collection, row_uuid)
            if updated_row is not None:
                await _publish_snapshot(collection_id=collection_id, row=updated_row, status_repo=status_repo)
            return {
                "status": "ok",
                "collection_id": collection_id,
                "row_id": row_id,
                "template_status": str((updated_row or row).get("status") or TEMPLATE_STATUS_UPLOADED),
            }
        except Exception as exc:
            logger.error("template_schema_generation_failed: %s", exc, exc_info=True)
            await _update_analysis_node(
                status_repo=status_repo,
                collection_id=collection_uuid,
                row_id=row_uuid,
                node_key="schema",
                status="failed",
                error_short=str(exc)[:2000],
                finished_at=datetime.now(timezone.utc),
            )
            await session.commit()
            updated_row = await service.get_row_by_id(collection, row_uuid)
            if updated_row is not None:
                await _publish_snapshot(collection_id=collection_id, row=updated_row, status_repo=status_repo)
            raise

    try:
        return asyncio.run(_run_with_context(collection_id, row_id, _handler))
    except Exception as exc:
        raise self.retry(exc=exc)
