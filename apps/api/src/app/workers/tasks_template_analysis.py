from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

from celery import shared_task

from app.core.logging import get_logger
from app.services.collection.template_contract import TemplateContract, TableField
from app.services.collection.template_description_builder import TemplateDescriptionBuilder
from app.services.collection.template_layout_parser import TemplateLayoutParser
from app.services.collection.template_schema_builder import TemplateSchemaBuilder
from app.services.collection.template_status_stream import (
    TemplateStatusPublisher,
    build_template_row_runtime_payload,
    build_template_status_graph,
)
from app.repositories.template_analysis_status_repo import AsyncTemplateAnalysisStatusRepository
from app.services.collection.template_analysis_orchestrator import TemplateAnalysisOrchestrator
from app.workers.session_factory import get_worker_session

logger = get_logger(__name__)

TEMPLATE_STATUS_UPLOADED = "uploaded"
TEMPLATE_STATUS_APPROVAL_REQUIRED = "approval_required"
TEMPLATE_STATUS_READY = "ready"
TEMPLATE_STATUS_ARCHIVED = "archived"

_TASK_NODE_KEYS = {"description", "schema", "approval"}


def _serialize_analysis_nodes(nodes: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "node_key": node.node_key,
            "status": node.status,
            "error_short": node.error_short,
            "metrics_json": node.metrics_json,
            "started_at": getattr(node, "started_at", None).isoformat() if getattr(node, "started_at", None) else None,
            "finished_at": getattr(node, "finished_at", None).isoformat() if getattr(node, "finished_at", None) else None,
        }
        for node in nodes
    ]


def _build_schema_metrics(*, row: dict[str, Any], filename: str, layout: Any, contract: TemplateContract) -> dict[str, Any]:
    scalar_field_count = sum(1 for field in contract.fields if not isinstance(field, TableField))
    table_fields = [field for field in contract.fields if isinstance(field, TableField)]
    table_field_count = len(table_fields)
    schema_preview = [field.key for field in contract.fields[:10]]
    return {
        "filename": filename,
        "title": layout.title or row.get("title") or filename,
        "version": layout.version or row.get("template_version"),
        "format": layout.format,
        "sheet_count": len(layout.sheets),
        "sheet_names": layout.sheets,
        "token_count": len(layout.tokens),
        "scalar_key_count": len(layout.scalar_keys),
        "table_prefix_count": len(layout.table_prefixes),
        "table_region_count": len(layout.table_regions),
        "fence_block_count": len(layout.fence_blocks),
        "field_count": len(contract.fields),
        "scalar_field_count": scalar_field_count,
        "table_field_count": table_field_count,
        "schema_summary": f"{len(contract.fields)} fields, {table_field_count} tables",
        "schema_preview": schema_preview,
    }


def _build_description_metrics(
    *,
    title: str | None,
    version: str | None,
    contract: TemplateContract,
    description: str,
) -> dict[str, Any]:
    scalar_field_count = sum(1 for field in contract.fields if not isinstance(field, TableField))
    table_field_count = sum(1 for field in contract.fields if isinstance(field, TableField))
    return {
        "title": title,
        "version": version,
        "field_count": len(contract.fields),
        "scalar_field_count": scalar_field_count,
        "table_field_count": table_field_count,
        "description_text": description,
        "description_source": "llm_or_deterministic_fallback",
    }


def _resolve_template_status(current_row: dict[str, Any], nodes: list[Any]) -> str:
    current_status = str(current_row.get("status") or TEMPLATE_STATUS_UPLOADED).strip().lower()
    if current_status == TEMPLATE_STATUS_ARCHIVED:
        return current_status

    node_map = {str(node.node_key): node for node in nodes if getattr(node, "node_key", None) in _TASK_NODE_KEYS}
    schema_completed = str(getattr(node_map.get("schema"), "status", "") or "").strip().lower() == "completed"
    description_completed = str(getattr(node_map.get("description"), "status", "") or "").strip().lower() == "completed"
    approval_completed = str(getattr(node_map.get("approval"), "status", "") or "").strip().lower() == "completed"
    vector_state = str(current_row.get("_vector_status") or "").strip().lower()

    if approval_completed and vector_state in {"completed", "done"}:
        return TEMPLATE_STATUS_READY
    if schema_completed and description_completed:
        return TEMPLATE_STATUS_APPROVAL_REQUIRED
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
    collection_uuid: uuid.UUID,
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
        serialized_nodes = _serialize_analysis_nodes(nodes)
        payload = build_template_row_runtime_payload(
            {
                **row,
                "has_vector_search": bool(row.get("has_vector_search")),
            },
            collection_id=collection_id,
            analysis_nodes=serialized_nodes,
        )
        await publisher.publish_snapshot(
            row_id=uuid.UUID(str(row["id"])),
            payload=build_template_status_graph(
                payload,
                collection_id=collection_id,
                analysis_nodes=serialized_nodes,
            ),
        )
        await publisher.publish_collection_snapshot(
            collection_id=collection_uuid,
            row_id=uuid.UUID(str(row["id"])),
            payload=payload,
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
            logger.info("template_description_started", extra={"collection_id": collection_id, "row_id": row_id})

            # Description is a downstream stage: it consumes the parsed contract.
            raw_schema = row.get("template_schema") or {}
            contract = TemplateContract.from_jsonb(raw_schema)
            if not contract.fields:
                raise ValueError("Template schema is not ready; run schema analysis before description")

            resolved_title = row.get("title")
            resolved_version = row.get("template_version")

            # Build description from contract (S3)
            # The description is semantic metadata: use the configured LLM,
            # while the builder retains its deterministic failure fallback.
            from app.core.di import get_llm_client
            desc_builder = TemplateDescriptionBuilder(llm=get_llm_client())
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
                metrics_json=_build_description_metrics(
                    title=resolved_title,
                    version=resolved_version,
                    contract=contract,
                    description=description,
                ),
                finished_at=datetime.now(timezone.utc),
            )
            await session.commit()
            logger.info(
                "template_description_completed",
                extra={
                    "collection_id": collection_id,
                    "row_id": row_id,
                    "title": resolved_title,
                    "version": resolved_version,
                    "field_count": len(contract.fields),
                },
            )
            updated_row = await service.update_row(collection, row_uuid, updates, skip_vectorization=True)
            nodes = await status_repo.get_nodes_by_row_id(row_uuid)
            updates_status = _resolve_template_status(updated_row or row, nodes)
            if updates_status != str((updated_row or row).get("status") or "").strip().lower():
                updated_row = await service.update_row(collection, row_uuid, {"status": updates_status}, skip_vectorization=True)
                await session.commit()
            updated_row = await service.get_row_by_id(collection, row_uuid)
            if updated_row is not None:
                await _publish_snapshot(
                    collection_id=collection_id,
                    collection_uuid=collection_uuid,
                    row={**updated_row, "has_vector_search": bool(collection.has_vector_search)},
                    status_repo=status_repo,
                )

            return {
                "status": "ok",
                "collection_id": collection_id,
                "row_id": row_id,
                "template_status": str((updated_row or row).get("status") or TEMPLATE_STATUS_UPLOADED),
                "vectorization_task_id": None,
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
            logger.error(
                "template_analysis_failed",
                extra={
                    "stage": "description",
                    "collection_id": collection_id,
                    "row_id": row_id,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                },
            )
            updated_row = await service.get_row_by_id(collection, row_uuid)
            if updated_row is not None:
                await _publish_snapshot(
                    collection_id=collection_id,
                    collection_uuid=collection_uuid,
                    row={**updated_row, "has_vector_search": bool(collection.has_vector_search)},
                    status_repo=status_repo,
                )
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
            file_meta = row.get("file") if isinstance(row.get("file"), dict) else {}
            logger.info(
                "template_schema_started",
                extra={
                    "collection_id": collection_id,
                    "row_id": row_id,
                    "template_filename": filename,
                    "content_type": file_meta.get("content_type"),
                    "file_size": file_meta.get("size"),
                },
            )
            
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
            schema_metrics = _build_schema_metrics(
                row=row,
                filename=filename,
                layout=layout,
                contract=contract,
            )

            updated_row = await service.update_row(collection, row_uuid, updates, skip_vectorization=True)
            await session.commit()
            await _update_analysis_node(
                status_repo=status_repo,
                collection_id=collection_uuid,
                row_id=row_uuid,
                node_key="schema",
                status="completed",
                metrics_json=schema_metrics,
                finished_at=datetime.now(timezone.utc),
            )
            await session.commit()
            logger.info(
                "template_schema_completed",
                extra={
                    "collection_id": collection_id,
                    "row_id": row_id,
                    "template_filename": filename,
                    "format": layout.format,
                    "sheet_count": len(layout.sheets),
                    "sheet_names": layout.sheets,
                    "token_count": len(layout.tokens),
                    "table_region_count": len(layout.table_regions),
                    "field_count": len(contract.fields),
                },
            )
            description_task_id = TemplateAnalysisOrchestrator.enqueue_description(
                collection_id=collection_uuid,
                row_id=row_uuid,
                countdown=1,
            )
            nodes = await status_repo.get_nodes_by_row_id(row_uuid)
            updates_status = _resolve_template_status(updated_row or row, nodes)
            if updates_status != str((updated_row or row).get("status") or "").strip().lower():
                updated_row = await service.update_row(collection, row_uuid, {"status": updates_status}, skip_vectorization=True)
                await session.commit()
            updated_row = await service.get_row_by_id(collection, row_uuid)
            if updated_row is not None:
                await _publish_snapshot(
                    collection_id=collection_id,
                    collection_uuid=collection_uuid,
                    row={**updated_row, "has_vector_search": bool(collection.has_vector_search)},
                    status_repo=status_repo,
                )
            return {
                "status": "ok",
                "collection_id": collection_id,
                "row_id": row_id,
                "template_status": str((updated_row or row).get("status") or TEMPLATE_STATUS_UPLOADED),
                "description_task_id": description_task_id,
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
            logger.error(
                "template_analysis_failed",
                extra={
                    "stage": "schema",
                    "collection_id": collection_id,
                    "row_id": row_id,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                },
            )
            updated_row = await service.get_row_by_id(collection, row_uuid)
            if updated_row is not None:
                await _publish_snapshot(
                    collection_id=collection_id,
                    collection_uuid=collection_uuid,
                    row={**updated_row, "has_vector_search": bool(collection.has_vector_search)},
                    status_repo=status_repo,
                )
            raise

    try:
        return asyncio.run(_run_with_context(collection_id, row_id, _handler))
    except Exception as exc:
        raise self.retry(exc=exc)
