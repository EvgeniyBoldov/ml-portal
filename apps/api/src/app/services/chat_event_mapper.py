"""Map runtime events to the deliberately small chat transport surface."""
from __future__ import annotations

from typing import Any, Optional

from app.runtime import RuntimeEvent, RuntimeEventType
from app.runtime.error_surface import build_user_safe_error_message


class ChatEventMapper:
    def map_runtime_event(self, event: RuntimeEvent) -> Optional[dict[str, Any]]:
        progress = event.data.get("_progress")
        if isinstance(progress, dict):
            return {"type": "status", "stage": "runtime_progress", "progress": progress}
        if event.type is RuntimeEventType.DELTA:
            return {"type": "delta", "content": event.data.get("content", "")}
        if event.type is RuntimeEventType.STOP:
            return {"type": "stop", **dict(event.data or {})}
        if event.type is RuntimeEventType.ERROR:
            error_code = event.data.get("error_code")
            retryable = event.data.get("retryable")
            return {
                "type": "error",
                "error": build_user_safe_error_message(retryable=retryable, error_code=error_code),
                "code": error_code,
                "recoverable": event.data.get("recoverable", retryable if retryable is not None else False),
            }
        return None
