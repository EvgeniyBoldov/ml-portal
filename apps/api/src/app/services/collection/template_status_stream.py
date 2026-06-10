from __future__ import annotations

import json
from typing import Any, Optional
from uuid import UUID

from app.core.logging import get_logger

logger = get_logger(__name__)


class TemplateStatusPublisher:
    CHANNEL_ROW_FMT = "template:row:{row_id}"

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


def build_template_status_graph(
    row: dict[str, Any],
    *,
    collection_id: str,
    analysis_nodes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    status = str(row.get("status") or "uploaded").strip().lower()
    has_description = bool(str(row.get("description") or "").strip())
    has_schema = row.get("template_schema") is not None

    node_map = {str(node.get("node_key") or "").strip(): node for node in (analysis_nodes or []) if str(node.get("node_key") or "").strip()}
    description_node = node_map.get("description")
    schema_node = node_map.get("schema")

    node_statuses = [
        str((description_node or {}).get("status") or "").strip().lower(),
        str((schema_node or {}).get("status") or "").strip().lower(),
    ]
    node_errors = [
        str((description_node or {}).get("error_short") or "").strip() or None,
        str((schema_node or {}).get("error_short") or "").strip() or None,
    ]
    has_error = any(node_errors)
    active_states = {"queued", "processing"}

    if has_error and not (status == "ready"):
        analysis_state = "failed"
    elif any(state in active_states for state in node_statuses):
        analysis_state = "processing"
    elif any(state == "failed" for state in node_statuses):
        analysis_state = "failed"
    elif description_node and schema_node and all(state == "completed" for state in node_statuses):
        analysis_state = "completed"
    elif not description_node and not schema_node:
        analysis_state = "pending"
    elif status in {"ready", "analyzed"}:
        analysis_state = "completed"
    else:
        analysis_state = "processing"

    stages = [
        {
            "key": "uploaded",
            "label": "Загружен",
            "state": "completed",
            "error": None,
        },
        {
            "key": "analysis",
            "label": "Анализ",
            "state": analysis_state,
            "error": next((err for err in node_errors if err), None),
            "metrics": {
                "description_ready": has_description,
                "schema_ready": has_schema,
                "description_status": (description_node or {}).get("status") or "pending",
                "schema_status": (schema_node or {}).get("status") or "pending",
            },
        },
        {
            "key": "ready",
            "label": "Готово",
            "state": "completed" if status in {"ready", "archived"} and not has_error else "pending",
            "error": None,
        },
    ]

    return {
        "row_id": str(row.get("id") or ""),
        "collection_id": collection_id,
        "title": row.get("title"),
        "status": status,
        "description": row.get("description"),
        "template_version": row.get("template_version"),
        "template_schema": row.get("template_schema"),
        "stages": stages,
        "analysis_nodes": {
            "description": {
                "status": (description_node or {}).get("status") or "pending",
                "error": (description_node or {}).get("error_short"),
                "metrics": (description_node or {}).get("metrics_json"),
            },
            "schema": {
                "status": (schema_node or {}).get("status") or "pending",
                "error": (schema_node or {}).get("error_short"),
                "metrics": (schema_node or {}).get("metrics_json"),
            },
        },
    }
