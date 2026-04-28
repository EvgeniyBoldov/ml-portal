"""ToolLedger — turn-scoped registry of operation calls/results.

Keeps a bounded in-memory journal of tool interactions for one runtime turn.
Used for:
  * planner context (what was already called),
  * duplicate-call hints,
  * deterministic accounting (`used_tool_calls`).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


MAX_TOOL_LEDGER_ENTRIES = 120
REUSE_MAX_AGE_SECONDS = 300  # results older than 5 min are not reused
MAX_TOOL_PREVIEW_CHARS = 220
MAX_RESULT_CACHE_CHARS = 24_000


class ToolLedgerEntry(BaseModel):
    call_id: str
    operation: str
    args_fingerprint: str
    args_preview: str
    iteration: int = 0
    agent_slug: Optional[str] = None
    phase_id: Optional[str] = None

    duplicate_of_call_id: Optional[str] = None

    status: str = "called"  # called | succeeded | failed
    success: Optional[bool] = None
    result_fingerprint: Optional[str] = None
    result_preview: Optional[str] = None
    result_data: Any = None
    called_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: Optional[datetime] = None

    @property
    def signature(self) -> str:
        return f"{self.operation}:{self.args_fingerprint}"


class ToolLedger(BaseModel):
    entries: List[ToolLedgerEntry] = Field(default_factory=list)

    def register_call(
        self,
        *,
        operation: str,
        call_id: str,
        arguments: Dict[str, Any],
        iteration: int,
        agent_slug: Optional[str],
        phase_id: Optional[str],
    ) -> ToolLedgerEntry:
        args_fingerprint, args_preview = _fingerprint_and_preview(arguments)
        signature = f"{operation}:{args_fingerprint}"
        duplicate_of = self._find_completed_duplicate(signature)

        entry = ToolLedgerEntry(
            call_id=call_id,
            operation=operation,
            args_fingerprint=args_fingerprint,
            args_preview=args_preview,
            iteration=iteration,
            agent_slug=agent_slug,
            phase_id=phase_id,
            duplicate_of_call_id=duplicate_of,
        )
        self.entries.append(entry)
        if len(self.entries) > MAX_TOOL_LEDGER_ENTRIES:
            self.entries = self.entries[-MAX_TOOL_LEDGER_ENTRIES:]
        return entry

    def register_result(
        self,
        *,
        call_id: str,
        success: bool,
        data: Any,
    ) -> None:
        target = None
        for entry in reversed(self.entries):
            if entry.call_id == call_id:
                target = entry
                break
        if target is None:
            # Defensive: result without prior call event.
            return

        result_fingerprint, result_preview = _fingerprint_and_preview(data)
        target.success = success
        target.status = "succeeded" if success else "failed"
        target.result_fingerprint = result_fingerprint
        target.result_preview = result_preview
        target.result_data = _cacheable_result_data(data) if success else None
        target.finished_at = datetime.now(timezone.utc)

    def compact_view(self, *, max_items: int = 8) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for item in self.entries[-max_items:]:
            out.append(
                {
                    "operation": item.operation,
                    "call_id": item.call_id,
                    "status": item.status,
                    "success": item.success,
                    "duplicate_of_call_id": item.duplicate_of_call_id,
                    "args_preview": item.args_preview,
                    "result_preview": item.result_preview,
                }
            )
        return out

    def find_successful_result(
        self,
        *,
        operation: str,
        arguments: Dict[str, Any],
        max_age_seconds: int = REUSE_MAX_AGE_SECONDS,
    ) -> Optional[ToolLedgerEntry]:
        args_fingerprint, _ = _fingerprint_and_preview(arguments)
        signature = f"{operation}:{args_fingerprint}"
        now = datetime.now(timezone.utc)
        for entry in reversed(self.entries):
            if entry.signature != signature:
                continue
            if entry.status != "succeeded" or entry.result_data is None:
                continue
            finished = entry.finished_at or entry.called_at
            age_seconds = (now - finished).total_seconds()
            if age_seconds > max_age_seconds:
                continue
            return entry
        return None

    def _find_completed_duplicate(self, signature: str) -> Optional[str]:
        for entry in reversed(self.entries):
            if entry.signature != signature:
                continue
            if entry.status in {"succeeded", "failed"}:
                return entry.call_id
        return None


def _fingerprint_and_preview(value: Any) -> tuple[str, str]:
    text = _stable_json(value)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    preview = text[:MAX_TOOL_PREVIEW_CHARS]
    return digest, preview


def _stable_json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except TypeError:
        return str(value)


def _cacheable_result_data(value: Any) -> Any:
    text = _stable_json(value)
    if len(text) > MAX_RESULT_CACHE_CHARS:
        return None
    return value
