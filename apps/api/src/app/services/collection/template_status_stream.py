from __future__ import annotations

import json
from typing import Any, Optional
from uuid import UUID

from app.core.logging import get_logger

logger = get_logger(__name__)


def _node_metrics(node: dict[str, Any] | None) -> dict[str, Any] | None:
    metrics = (node or {}).get("metrics_json")
    return metrics if isinstance(metrics, dict) else None


def _stage_payload(
    *,
    key: str,
    label: str,
    state: str,
    error: str | None = None,
    metrics: dict[str, Any] | None = None,
    node: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "state": state,
        "error": error,
        "metrics": metrics,
        "started_at": (node or {}).get("started_at"),
        "finished_at": (node or {}).get("finished_at"),
    }


class TemplateStatusPublisher:
    CHANNEL_ROW_FMT = "template:row:{row_id}"
    CHANNEL_COLLECTION_FMT = "template:collection:{collection_id}"

    def __init__(self, redis_client: Optional[Any] = None):
        self.redis = redis_client

    async def publish_snapshot(self, *, row_id: UUID, payload: dict[str, Any]) -> None:
        if not self.redis:
            return
        event = {
            "event_type": "snapshot",
            "row_id": str(row_id),
            **payload,
        }
        try:
            await self.redis.publish(self.CHANNEL_ROW_FMT.format(row_id=str(row_id)), json.dumps(event))
        except Exception as exc:
            logger.error("Failed to publish template snapshot: %s", exc)

    async def publish_collection_snapshot(
        self,
        *,
        collection_id: UUID,
        row_id: UUID,
        payload: dict[str, Any],
    ) -> None:
        if not self.redis:
            return
        event = {
            "event_type": "snapshot",
            "collection_id": str(collection_id),
            "row_id": str(row_id),
            "item": payload,
        }
        try:
            await self.redis.publish(
                self.CHANNEL_COLLECTION_FMT.format(collection_id=str(collection_id)),
                json.dumps(event),
            )
        except Exception as exc:
            logger.error("Failed to publish template collection snapshot: %s", exc)


class TemplateStatusSubscriber:
    def __init__(self, redis_client: Any, row_id: UUID):
        self.redis = redis_client
        self.row_id = str(row_id)
        self._channel = TemplateStatusPublisher.CHANNEL_ROW_FMT.format(row_id=self.row_id)
        self.pubsub = None

    async def subscribe(self) -> None:
        self.pubsub = self.redis.pubsub()
        await self.pubsub.subscribe(self._channel)

    async def listen(self):
        if not self.pubsub:
            await self.subscribe()

        async for message in self.pubsub.listen():
            if message.get("type") != "message":
                continue
            try:
                yield json.loads(message["data"])
            except json.JSONDecodeError as exc:
                logger.error("Failed to decode template SSE event: %s", exc)

    async def unsubscribe(self) -> None:
        if self.pubsub:
            await self.pubsub.unsubscribe(self._channel)
            await self.pubsub.close()


class TemplateCollectionStatusSubscriber:
    def __init__(self, redis_client: Any, collection_id: UUID):
        self.redis = redis_client
        self.collection_id = str(collection_id)
        self._channel = TemplateStatusPublisher.CHANNEL_COLLECTION_FMT.format(collection_id=self.collection_id)
        self.pubsub = None

    async def subscribe(self) -> None:
        self.pubsub = self.redis.pubsub()
        await self.pubsub.subscribe(self._channel)

    async def listen(self):
        if not self.pubsub:
            await self.subscribe()

        async for message in self.pubsub.listen():
            if message.get("type") != "message":
                continue
            try:
                yield json.loads(message["data"])
            except json.JSONDecodeError as exc:
                logger.error("Failed to decode template collection SSE event: %s", exc)

    async def unsubscribe(self) -> None:
        if self.pubsub:
            await self.pubsub.unsubscribe(self._channel)
            await self.pubsub.close()


def _normalized_node_map(analysis_nodes: list[dict[str, Any]] | None = None) -> dict[str, dict[str, Any]]:
    return {
        str(node.get("node_key") or "").strip(): node
        for node in (analysis_nodes or [])
        if str(node.get("node_key") or "").strip()
    }


def _normalize_node_state(node: dict[str, Any] | None) -> str:
    return str((node or {}).get("status") or "pending").strip().lower()


def _normalize_vector_state(row: dict[str, Any]) -> str:
    vector_state = str(row.get("_vector_status") or "").strip().lower()
    if vector_state in {"done", "completed"}:
        return "completed"
    if vector_state in {"error", "failed"}:
        return "failed"
    if vector_state in {"queued", "processing"}:
        return "processing"
    if vector_state == "pending":
        return "pending"
    return "pending"


def _has_completed(node: dict[str, Any] | None) -> bool:
    return _normalize_node_state(node) == "completed"


def _has_failed(node: dict[str, Any] | None) -> bool:
    return _normalize_node_state(node) == "failed"


def _has_active(node: dict[str, Any] | None) -> bool:
    return _normalize_node_state(node) in {"queued", "processing"}


def _resolve_runtime(row: dict[str, Any], analysis_nodes: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    status = str(row.get("status") or "uploaded").strip().lower()
    has_vector_search = bool(row.get("has_vector_search"))
    node_map = _normalized_node_map(analysis_nodes)
    schema_node = node_map.get("schema")
    description_node = node_map.get("description")
    approval_node = node_map.get("approval")
    vectorization_node = node_map.get("vectorization")
    indexing_node = node_map.get("indexing")
    schema_state = _normalize_node_state(schema_node)
    description_state = _normalize_node_state(description_node)
    vectorization_state = _normalize_node_state(vectorization_node)
    indexing_state = _normalize_node_state(indexing_node)
    fallback_vector_state = _normalize_vector_state(row)
    vector_error = str(row.get("_vector_error") or "").strip() or None

    has_schema = row.get("template_schema") is not None
    has_description = bool(str(row.get("description") or "").strip())

    schema_ready = _has_completed(schema_node) or (has_schema and schema_state == "pending")
    description_ready = _has_completed(description_node) or (has_description and description_state == "pending")
    approval_ready = _has_completed(approval_node)
    analysis_ready = schema_ready and description_ready
    vectorization_ready = _has_completed(vectorization_node) or (
        not vectorization_node and fallback_vector_state == "completed"
    )
    indexing_ready = _has_completed(indexing_node) or (
        not indexing_node and fallback_vector_state == "completed"
    )
    # A template is searchable only after its approved description is indexed.
    retrieval_ready = has_vector_search and vectorization_ready and indexing_ready

    has_error = any(
        (
            _has_failed(schema_node),
            _has_failed(description_node),
            _has_failed(approval_node),
            _has_failed(vectorization_node),
            _has_failed(indexing_node),
            fallback_vector_state == "failed",
        )
    )
    error_message = next(
        (
            str(candidate).strip()
            for candidate in (
                (schema_node or {}).get("error_short"),
                (description_node or {}).get("error_short"),
                (approval_node or {}).get("error_short"),
                (vectorization_node or {}).get("error_short"),
                (indexing_node or {}).get("error_short"),
                vector_error,
            )
            if str(candidate or "").strip()
        ),
        None,
    )

    if status == "archived":
        runtime_status = "archived"
        runtime_stage = "done"
    elif has_error:
        runtime_status = "failed"
        runtime_stage = "indexing" if _has_failed(indexing_node) else "vectorization"
        if _has_failed(schema_node):
            runtime_stage = "schema"
        elif _has_failed(description_node):
            runtime_stage = "description"
        elif _has_failed(approval_node):
            runtime_stage = "approval"
        elif _has_failed(vectorization_node) or fallback_vector_state == "failed":
            runtime_stage = "vectorization"
    elif approval_ready and retrieval_ready:
        runtime_status = "ready"
        runtime_stage = "done"
    elif analysis_ready and not approval_ready:
        runtime_status = "approval_required"
        runtime_stage = "approval"
    elif (
        _has_active(schema_node)
        or _has_active(description_node)
        or _has_active(approval_node)
        or _has_active(vectorization_node)
        or _has_active(indexing_node)
    ):
        runtime_status = "processing"
        runtime_stage = "schema" if _has_active(schema_node) else "description"
        if _has_active(approval_node):
            runtime_stage = "approval"
        elif _has_active(vectorization_node):
            runtime_stage = "vectorization"
        elif _has_active(indexing_node):
            runtime_stage = "indexing"
    elif approval_ready and has_vector_search and (
        vectorization_state in {"pending", "queued", "processing"}
        or indexing_state in {"pending", "queued", "processing"}
        or fallback_vector_state in {"pending", "processing"}
    ):
        runtime_status = "processing"
        runtime_stage = "indexing" if indexing_state in {"pending", "queued", "processing"} else "vectorization"
    elif status == "uploaded":
        runtime_status = "uploaded"
        runtime_stage = "upload"
    else:
        runtime_status = "processing"
        runtime_stage = "schema" if not schema_ready else "description"

    approval_required = analysis_ready and not approval_ready and status != "archived"

    vectorization_status = (
        "disabled"
        if not has_vector_search
        else (
            vectorization_state
            if vectorization_node
            else fallback_vector_state
        )
    )
    indexing_status = (
        "disabled"
        if not has_vector_search
        else (
            indexing_state
            if indexing_node
            else fallback_vector_state
        )
    )

    return {
        "runtime_status": runtime_status,
        "runtime_stage": runtime_stage,
        "approval_required": approval_required,
        "approved_at": (approval_node or {}).get("finished_at"),
        "approved_by": ((approval_node or {}).get("metrics_json") or {}).get("approved_by"),
        "has_error": has_error,
        "error_message": error_message,
        "vectorization_status": vectorization_status,
        "indexing_status": indexing_status,
        "schema_ready": schema_ready,
        "description_ready": description_ready,
        "approval_ready": approval_ready,
        "has_vector_search": has_vector_search,
    }


def build_template_row_runtime_payload(
    row: dict[str, Any],
    *,
    collection_id: str,
    analysis_nodes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    runtime = _resolve_runtime(row, analysis_nodes)
    payload = {
        **row,
        **runtime,
        "collection_id": collection_id,
        "status_reason": runtime["runtime_stage"],
    }
    return payload


def build_template_status_graph(
    row: dict[str, Any],
    *,
    collection_id: str,
    analysis_nodes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    status = str(row.get("status") or "uploaded").strip().lower()
    payload = build_template_row_runtime_payload(
        row,
        collection_id=collection_id,
        analysis_nodes=analysis_nodes,
    )
    node_map = _normalized_node_map(analysis_nodes)
    description_node = node_map.get("description")
    schema_node = node_map.get("schema")
    approval_node = node_map.get("approval")
    vectorization_node = node_map.get("vectorization")
    indexing_node = node_map.get("indexing")

    def _stage_state(node: dict[str, Any] | None) -> str:
        normalized = _normalize_node_state(node)
        if normalized in {"completed", "processing", "queued", "failed"}:
            return "processing" if normalized == "queued" else normalized
        return "pending"

    vector_state = payload["vectorization_status"]
    indexing_state = payload["indexing_status"]
    if vector_state == "disabled":
        vector_state = "completed"
    if indexing_state == "disabled":
        indexing_state = "completed"

    file_meta = row.get("file") if isinstance(row.get("file"), dict) else {}
    uploaded_metrics = {
        "filename": file_meta.get("filename"),
        "content_type": file_meta.get("content_type"),
        "file_size": file_meta.get("size"),
        "source": row.get("source"),
        "format": (_node_metrics(schema_node) or {}).get("format"),
        "sheet_count": (_node_metrics(schema_node) or {}).get("sheet_count"),
        "sheet_names": (_node_metrics(schema_node) or {}).get("sheet_names"),
    }

    stages = [
        _stage_payload(
            key="uploaded",
            label="Загружен",
            state="completed",
            metrics={key: value for key, value in uploaded_metrics.items() if value not in (None, "", [])},
        ),
        _stage_payload(
            key="schema",
            label="Чтение схемы",
            state=_stage_state(schema_node),
            error=(schema_node or {}).get("error_short"),
            metrics=_node_metrics(schema_node),
            node=schema_node,
        ),
        _stage_payload(
            key="description",
            label="Создание описания",
            state=_stage_state(description_node),
            error=(description_node or {}).get("error_short"),
            metrics=_node_metrics(description_node),
            node=description_node,
        ),
        _stage_payload(
            key="approval",
            label="Утверждение",
            state="completed" if payload["approval_ready"] else ("failed" if _has_failed(approval_node) else ("processing" if _has_active(approval_node) else "pending")),
            error=(approval_node or {}).get("error_short"),
            metrics=_node_metrics(approval_node),
            node=approval_node,
        ),
        _stage_payload(
            key="vectorization",
            label="Векторизация",
            state=vector_state,
            error=(vectorization_node or {}).get("error_short") or row.get("_vector_error"),
            metrics=_node_metrics(vectorization_node) or {
                "vector_status": row.get("_vector_status"),
                "chunk_count": row.get("_vector_chunk_count"),
            },
            node=vectorization_node,
        ),
        _stage_payload(
            key="indexing",
            label="Индексация",
            state=indexing_state,
            error=(indexing_node or {}).get("error_short") or row.get("_vector_error"),
            metrics=_node_metrics(indexing_node) or {
                "vector_status": row.get("_vector_status"),
                "chunk_count": row.get("_vector_chunk_count"),
            },
            node=indexing_node,
        ),
        _stage_payload(
            key="ready",
            label="Готово",
            state="completed" if payload["runtime_status"] == "ready" or status == "archived" else "pending",
            metrics={
                "runtime_status": payload["runtime_status"],
                "title": row.get("title"),
                "version": row.get("template_version"),
                "approved_by": payload["approved_by"],
                "approved_at": payload["approved_at"],
            },
        ),
    ]

    return {
        "row_id": str(row.get("id") or ""),
        "collection_id": collection_id,
        "title": row.get("title"),
        "status": status,
        "runtime_status": payload["runtime_status"],
        "runtime_stage": payload["runtime_stage"],
        "approval_required": payload["approval_required"],
        "approved_at": payload["approved_at"],
        "approved_by": payload["approved_by"],
        "vectorization_status": payload["vectorization_status"],
        "indexing_status": payload["indexing_status"],
        "has_error": payload["has_error"],
        "error_message": payload["error_message"],
        "description": row.get("description"),
        "template_version": row.get("template_version"),
        "template_schema": row.get("template_schema"),
        "stages": stages,
        "analysis_nodes": {
            "description": {
                "status": (description_node or {}).get("status") or "pending",
                "error": (description_node or {}).get("error_short"),
                "metrics": (description_node or {}).get("metrics_json"),
                "started_at": (description_node or {}).get("started_at"),
                "finished_at": (description_node or {}).get("finished_at"),
            },
            "schema": {
                "status": (schema_node or {}).get("status") or "pending",
                "error": (schema_node or {}).get("error_short"),
                "metrics": (schema_node or {}).get("metrics_json"),
                "started_at": (schema_node or {}).get("started_at"),
                "finished_at": (schema_node or {}).get("finished_at"),
            },
            "approval": {
                "status": (approval_node or {}).get("status") or "pending",
                "error": (approval_node or {}).get("error_short"),
                "metrics": (approval_node or {}).get("metrics_json"),
                "started_at": (approval_node or {}).get("started_at"),
                "finished_at": (approval_node or {}).get("finished_at"),
            },
            "vectorization": {
                "status": (vectorization_node or {}).get("status") or "pending",
                "error": (vectorization_node or {}).get("error_short"),
                "metrics": (vectorization_node or {}).get("metrics_json"),
                "started_at": (vectorization_node or {}).get("started_at"),
                "finished_at": (vectorization_node or {}).get("finished_at"),
            },
            "indexing": {
                "status": (indexing_node or {}).get("status") or "pending",
                "error": (indexing_node or {}).get("error_short"),
                "metrics": (indexing_node or {}).get("metrics_json"),
                "started_at": (indexing_node or {}).get("started_at"),
                "finished_at": (indexing_node or {}).get("finished_at"),
            },
        },
    }
