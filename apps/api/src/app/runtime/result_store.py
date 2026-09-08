"""Access-controlled runtime tool-result storage."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.s3_client import s3_manager
from app.models.runtime_plan import RuntimePlanTask, RuntimeTaskAttempt, RuntimeToolResult


class RuntimeToolResultStore:
    """Reads results only inside the owning plan/task attempt boundary."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def read(self, *, plan_id: UUID, task_id: str, result_ref: str) -> dict[str, Any]:
        row = await self.session.scalar(
            select(RuntimeToolResult)
            .join(RuntimeTaskAttempt, RuntimeTaskAttempt.id == RuntimeToolResult.attempt_id)
            .join(RuntimePlanTask, RuntimePlanTask.id == RuntimeTaskAttempt.task_row_id)
            .where(RuntimePlanTask.plan_id == plan_id, RuntimePlanTask.task_id == task_id, RuntimeToolResult.result_ref == result_ref)
        )
        if row is None or row.expires_at <= datetime.now(timezone.utc):
            raise KeyError("runtime result is unavailable or expired")
        if row.payload is not None:
            return dict(row.payload) if isinstance(row.payload, dict) else {"value": row.payload}
        ref = row.payload_ref or {}
        if not ref.get("bucket") or not ref.get("key"):
            raise KeyError("runtime result payload is unavailable")
        body = await s3_manager.get_object(str(ref["bucket"]), str(ref["key"]))
        if body is None:
            raise KeyError("runtime result payload is unavailable")
        value = json.loads(body.decode("utf-8"))
        return dict(value) if isinstance(value, dict) else {"value": value}
