"""SummaryStore — persistence for per-chat DialogueSummary.

One row per chat, keyed by `chat_id`. Upsert semantics: the caller
(MemoryWriter) mutates a `SummaryDTO` and asks us to persist it; we
INSERT on first turn, UPDATE thereafter.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import DialogueSummary
from app.runtime.memory.dto import SummaryDTO


class SummaryStore:
    """Repository for the `dialogue_summaries` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def load(self, chat_id: UUID) -> Optional[SummaryDTO]:
        """Return the chat's summary or None if the chat has no turns yet."""
        result = await self._session.execute(
            select(DialogueSummary).where(DialogueSummary.chat_id == chat_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        payload = _load_v2_payload(row)
        return SummaryDTO(
            chat_id=row.chat_id,
            goals=list(payload.get("goals") or []),
            done=list(payload.get("done") or []),
            entities=dict(payload.get("entities") or {}),
            open_questions=list(payload.get("open_questions") or []),
            raw_tail=str(payload.get("raw_tail") or ""),
            last_updated_turn=int(payload.get("last_updated_turn") or 0),
            updated_at=row.updated_at,
        )

    async def save(self, summary: SummaryDTO) -> None:
        """INSERT-or-UPDATE (PostgreSQL ON CONFLICT on the chat_id PK).

        We use PG's native upsert here instead of fetch-then-branch to
        avoid a read + write round trip: MemoryWriter writes once per
        turn and this is on the end-of-turn hot path.
        """
        now = datetime.now(timezone.utc)
        stmt = pg_insert(DialogueSummary).values(
            chat_id=summary.chat_id,
            goals=summary.goals,
            done=summary.done,
            entities=summary.entities,
            open_questions=summary.open_questions,
            raw_tail=summary.raw_tail,
            summary_v2=_to_v2_payload(summary),
            last_updated_turn=summary.last_updated_turn,
            updated_at=now,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[DialogueSummary.chat_id],
            set_={
                "goals": stmt.excluded.goals,
                "done": stmt.excluded.done,
                "entities": stmt.excluded.entities,
                "open_questions": stmt.excluded.open_questions,
                "raw_tail": stmt.excluded.raw_tail,
                "summary_v2": stmt.excluded.summary_v2,
                "last_updated_turn": stmt.excluded.last_updated_turn,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        await self._session.execute(stmt)
        await self._session.flush()


def _to_v2_payload(summary: SummaryDTO) -> dict:
    turn = int(summary.last_updated_turn or 0)
    return {
        "version": 2,
        "summary": {
            "goals": [
                {
                    "text": text,
                    "status": "active",
                    "introduced_turn": turn,
                    "last_seen_turn": turn,
                    "weight": 1.0,
                }
                for text in list(summary.goals or [])
                if str(text or "").strip()
            ],
            "done": [
                {
                    "text": text,
                    "status": "completed",
                    "introduced_turn": turn,
                    "last_seen_turn": turn,
                    "weight": 1.0,
                }
                for text in list(summary.done or [])
                if str(text or "").strip()
            ],
            "entities": {
                str(key): {
                    "text": str(value),
                    "category": "other",
                    "introduced_turn": turn,
                    "last_seen_turn": turn,
                    "weight": 1.0,
                }
                for key, value in dict(summary.entities or {}).items()
                if str(key or "").strip() and str(value or "").strip()
            },
            "open_questions": [
                {
                    "text": text,
                    "status": "open",
                    "introduced_turn": turn,
                    "last_seen_turn": turn,
                    "weight": 1.0,
                }
                for text in list(summary.open_questions or [])
                if str(text or "").strip()
            ],
        },
        "raw": {
            "tail_text": summary.raw_tail or "",
            "turns": _tail_to_turns(summary.raw_tail or ""),
        },
        "last_updated_turn": turn,
    }


def _load_v2_payload(row: DialogueSummary) -> dict:
    payload = row.summary_v2 or {}
    if isinstance(payload, dict) and payload:
        # New structured payload
        if int(payload.get("version") or 0) >= 2:
            return _from_v2_structured_payload(payload, row)
        # Legacy mirror payload
        return {
            "goals": list(payload.get("goals") or []),
            "done": list(payload.get("done") or []),
            "entities": dict(payload.get("entities") or {}),
            "open_questions": list(payload.get("open_questions") or []),
            "raw_tail": str(payload.get("raw_tail") or ""),
            "last_updated_turn": int(payload.get("last_updated_turn") or 0),
        }
    return {
        "goals": list(row.goals or []),
        "done": list(row.done or []),
        "entities": dict(row.entities or {}),
        "open_questions": list(row.open_questions or []),
        "raw_tail": row.raw_tail or "",
        "last_updated_turn": row.last_updated_turn,
    }


def _from_v2_structured_payload(payload: dict[str, Any], row: DialogueSummary) -> dict:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    raw = payload.get("raw") if isinstance(payload.get("raw"), dict) else {}
    return {
        "goals": _extract_text_items(summary.get("goals")),
        "done": _extract_text_items(summary.get("done")),
        "entities": _extract_entity_items(summary.get("entities")),
        "open_questions": _extract_text_items(summary.get("open_questions")),
        "raw_tail": str(raw.get("tail_text") or row.raw_tail or ""),
        "last_updated_turn": int(payload.get("last_updated_turn") or row.last_updated_turn or 0),
    }


def _extract_text_items(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if isinstance(item, str):
            text = item.strip()
        elif isinstance(item, dict):
            text = str(item.get("text") or "").strip()
        else:
            text = ""
        if text:
            out.append(text)
    return out


def _extract_entity_items(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, str] = {}
    for key, item in value.items():
        name = str(key or "").strip()
        if not name:
            continue
        if isinstance(item, str):
            text = item.strip()
        elif isinstance(item, dict):
            text = str(item.get("text") or "").strip()
        else:
            text = ""
        if text:
            out[name] = text
    return out


def _tail_to_turns(raw_tail: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for line in (raw_tail or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("user:"):
            out.append({"role": "user", "text": stripped[5:].strip()})
            continue
        if stripped.startswith("assistant:"):
            out.append({"role": "assistant", "text": stripped[10:].strip()})
            continue
        out.append({"role": "unknown", "text": stripped})
    return out
