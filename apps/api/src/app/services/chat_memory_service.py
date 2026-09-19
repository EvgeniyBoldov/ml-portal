"""Read/write projections for typed, chat-local working context."""
from __future__ import annotations

import uuid
from typing import Any, Iterable, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat_memory import ChatMemoryItem


class ChatMemoryService:
    """Keeps only compact, source-linked context; source data stays elsewhere."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _uuid(value: str | uuid.UUID | None) -> uuid.UUID | None:
        if value is None:
            return None
        try:
            return uuid.UUID(str(value))
        except (TypeError, ValueError):
            return None

    def _base_stmt(self, *, chat_id: str | uuid.UUID, branch_id: str | uuid.UUID | None):
        stmt = select(ChatMemoryItem).where(ChatMemoryItem.chat_id == uuid.UUID(str(chat_id)))
        branch_uuid = self._uuid(branch_id)
        return stmt.where(
            ChatMemoryItem.sandbox_branch_id == branch_uuid
            if branch_uuid is not None
            else ChatMemoryItem.sandbox_branch_id.is_(None)
        )

    async def projection(self, *, chat_id: str | uuid.UUID | None, branch_id: str | uuid.UUID | None = None) -> dict[str, Any]:
        if chat_id is None:
            return self.empty_projection()
        rows = (await self._session.execute(
            self._base_stmt(chat_id=chat_id, branch_id=branch_id)
            .where(ChatMemoryItem.status == "active")
            .order_by(ChatMemoryItem.updated_at.desc())
            .limit(80)
        )).scalars().all()
        result = self.empty_projection()
        for row in rows:
            payload = dict(row.payload or {})
            payload.update({"confidence": float(row.confidence), "source_turn_id": str(row.source_turn_id) if row.source_turn_id else None})
            if row.kind == "scope" and result["scope"] is None:
                result["scope"] = payload
            elif row.kind == "term_binding":
                result["term_bindings"].append(payload)
            elif row.kind == "artifact_ref":
                result["artifacts"].append(payload)
            elif row.kind == "decision":
                result["decisions"].append(payload)
            elif row.kind == "open_question":
                result["open_questions"].append(payload)
        return result

    @staticmethod
    def empty_projection() -> dict[str, Any]:
        return {"scope": None, "term_bindings": [], "artifacts": [], "decisions": [], "open_questions": []}

    async def record_scope(
        self, *, chat_id: str | uuid.UUID, project_keys: Iterable[str], selection: str,
        source_turn_id: str | uuid.UUID | None = None, branch_id: str | uuid.UUID | None = None,
    ) -> None:
        keys = list(dict.fromkeys(str(key).strip().casefold() for key in project_keys if str(key).strip()))
        if not keys:
            return
        await self._supersede(chat_id=chat_id, branch_id=branch_id, kind="scope", item_key="project_scope")
        self._session.add(ChatMemoryItem(
            chat_id=uuid.UUID(str(chat_id)), sandbox_branch_id=self._uuid(branch_id), kind="scope", item_key="project_scope",
            payload={"project_keys": keys, "selection": selection}, source_turn_id=self._uuid(source_turn_id), confidence=1.0 if selection == "explicit" else 0.7,
        ))
        await self._session.flush()

    async def record_term_bindings(
        self, *, chat_id: str | uuid.UUID, matches: Iterable[dict[str, Any]], source_turn_id: str | uuid.UUID | None = None,
        branch_id: str | uuid.UUID | None = None,
    ) -> None:
        for match in matches:
            entry_id = str(match.get("id") or "").strip()
            term = str(match.get("term") or "").strip()
            if not entry_id or not term:
                continue
            aliases = [str(item).strip() for item in match.get("matched_aliases") or [] if str(item).strip()]
            key = entry_id
            existing = (await self._session.execute(
                self._base_stmt(chat_id=chat_id, branch_id=branch_id).where(
                    ChatMemoryItem.kind == "term_binding", ChatMemoryItem.item_key == key, ChatMemoryItem.status == "active",
                )
            )).scalar_one_or_none()
            payload = {"glossary_entry_id": entry_id, "term": term, "aliases": aliases, "description": str(match.get("description") or "")[:600]}
            if existing is None:
                self._session.add(ChatMemoryItem(chat_id=uuid.UUID(str(chat_id)), sandbox_branch_id=self._uuid(branch_id), kind="term_binding", item_key=key, payload=payload, source_turn_id=self._uuid(source_turn_id), confidence=1.0))
            else:
                existing.payload = payload
                existing.source_turn_id = self._uuid(source_turn_id)
        await self._session.flush()

    async def record_artifacts(
        self, *, chat_id: str | uuid.UUID, artifacts: Iterable[dict[str, Any]], source_turn_id: str | uuid.UUID | None = None,
        branch_id: str | uuid.UUID | None = None,
    ) -> None:
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            artifact_id = str(artifact.get("artifact_id") or artifact.get("id") or "").strip()
            if not artifact_id:
                continue
            existing = (await self._session.execute(
                self._base_stmt(chat_id=chat_id, branch_id=branch_id).where(
                    ChatMemoryItem.kind == "artifact_ref", ChatMemoryItem.item_key == artifact_id, ChatMemoryItem.status == "active",
                )
            )).scalar_one_or_none()
            payload = {key: artifact.get(key) for key in ("artifact_id", "file_name", "content_type", "size_bytes", "snippet", "snippet_status", "readable", "truncated") if artifact.get(key) is not None}
            payload["artifact_id"] = artifact_id
            if existing is None:
                self._session.add(ChatMemoryItem(chat_id=uuid.UUID(str(chat_id)), sandbox_branch_id=self._uuid(branch_id), kind="artifact_ref", item_key=artifact_id, payload=payload, source_turn_id=self._uuid(source_turn_id), confidence=1.0))
            else:
                existing.payload = {**dict(existing.payload or {}), **payload}
                existing.source_turn_id = self._uuid(source_turn_id)
        await self._session.flush()

    async def _supersede(self, *, chat_id: str | uuid.UUID, branch_id: str | uuid.UUID | None, kind: str, item_key: str) -> None:
        branch_uuid = self._uuid(branch_id)
        await self._session.execute(
            update(ChatMemoryItem).where(
                ChatMemoryItem.chat_id == uuid.UUID(str(chat_id)), ChatMemoryItem.sandbox_branch_id == branch_uuid if branch_uuid else ChatMemoryItem.sandbox_branch_id.is_(None),
                ChatMemoryItem.kind == kind, ChatMemoryItem.item_key == item_key, ChatMemoryItem.status == "active",
            ).values(status="superseded")
        )
