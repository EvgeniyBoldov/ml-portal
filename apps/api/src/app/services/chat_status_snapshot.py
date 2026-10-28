"""Database-backed, content-free chat lifecycle snapshots."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Iterable

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.chat_lifecycle import ChatExecutionStage, normalize_chat_turn_status
from app.models.chat import Chats
from app.models.chat_turn import ChatTurn


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def project_chat_status(
    turn: ChatTurn,
    *,
    stage_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Project only lifecycle identity and bounded stage taxonomy, never text."""
    valid_stages = {stage.value for stage in ChatExecutionStage}
    stage = stage_snapshot.get("stage") if isinstance(stage_snapshot, dict) else None
    changed_at = turn.completed_at or turn.paused_at or turn.started_at
    stage_updated_at = stage_snapshot.get("updated_at") if isinstance(stage_snapshot, dict) else None
    return {
        "chat_id": str(turn.chat_id),
        "run_id": str(turn.runtime_run_id) if turn.runtime_run_id else None,
        "status": normalize_chat_turn_status(turn.status, turn.pause_status),
        "stage": stage if stage in valid_stages else None,
        "updated_at": _iso(changed_at),
        "stage_updated_at": stage_updated_at if isinstance(stage_updated_at, str) else None,
    }


async def latest_chat_turns_for_owner(
    session: AsyncSession,
    *,
    owner_id: str | uuid.UUID,
) -> list[ChatTurn]:
    """Return the newest turn for each chat owned by this authenticated user."""
    ranked = (
        select(
            ChatTurn.id.label("turn_id"),
            func.row_number()
            .over(
                partition_by=ChatTurn.chat_id,
                order_by=(ChatTurn.started_at.desc(), ChatTurn.id.desc()),
            )
            .label("turn_rank"),
        )
        .join(Chats, Chats.id == ChatTurn.chat_id)
        .where(Chats.owner_id == uuid.UUID(str(owner_id)))
        .subquery()
    )
    result = await session.execute(
        select(ChatTurn)
        .join(ranked, ranked.c.turn_id == ChatTurn.id)
        .where(ranked.c.turn_rank == 1)
        .order_by(ChatTurn.chat_id)
    )
    return list(result.scalars().all())


def build_chat_status_snapshot(
    turns: Iterable[ChatTurn],
    *,
    stages_by_run_id: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    stages = stages_by_run_id or {}
    items = [
        project_chat_status(
            turn,
            stage_snapshot=stages.get(str(turn.runtime_run_id)) if turn.runtime_run_id else None,
        )
        for turn in turns
    ]
    return sorted(items, key=lambda item: item["chat_id"])
