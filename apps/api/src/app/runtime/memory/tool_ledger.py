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
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


REUSE_MAX_AGE_SECONDS = 300  # retained for callers that request bounded reuse
MAX_TOOL_PREVIEW_CHARS = 220
MAX_RESULT_CACHE_CHARS = 24_000


def canonical_operation_name(operation: str) -> str:
    """Return a stable operation identity for runtime and policy checks.

    Published operations are instance-bound (``instance.<slug>.<operation>``),
    while policy is defined against their canonical operation names.
    """
    value = str(operation or "").strip()
    if value.startswith("instance."):
        parts = value.split(".", 2)
        if len(parts) == 3:
            return parts[2]
    return value


def document_search_evidence_document_ids(result: Any) -> set[str]:
    """Extract document identities from a bounded document-search result."""
    if not isinstance(result, dict):
        return set()
    hits = result.get("hits")
    if not isinstance(hits, list):
        return set()
    return {
        str(hit.get("document_id") or hit.get("artifact_id") or "").strip()
        for hit in hits
        if isinstance(hit, dict) and str(hit.get("document_id") or hit.get("artifact_id") or "").strip()
    }


class ToolLedgerEntry(BaseModel):
    call_id: str
    result_ref: str
    operation: str
    args_fingerprint: str
    args_preview: str
    iteration: int = 0
    agent_slug: Optional[str] = None
    phase_id: Optional[str] = None
    target_identity: Optional[str] = None
    execution_id: Optional[str] = None

    duplicate_of_call_id: Optional[str] = None

    status: str = "called"  # called | succeeded | failed
    success: Optional[bool] = None
    result_fingerprint: Optional[str] = None
    result_preview: Optional[str] = None
    result_data: Any = None
    result_data_available: bool = False
    stored_result_id: Optional[str] = None
    result_inline_complete: Optional[bool] = None
    result_source_complete: Optional[bool] = None
    result_delivery: Literal["stored", "direct"] = "stored"
    sources: List[Dict[str, Any]] = Field(default_factory=list)
    called_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: Optional[datetime] = None

    @property
    def signature(self) -> str:
        return f"{self.operation}:{self.target_identity or ''}:{self.args_fingerprint}"


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
        target_identity: Optional[str] = None,
    ) -> ToolLedgerEntry:
        args_fingerprint, args_preview = _fingerprint_and_preview(arguments)
        signature = f"{operation}:{target_identity or ''}:{args_fingerprint}"
        duplicate_of = self._find_completed_duplicate(signature)

        entry = ToolLedgerEntry(
            call_id=call_id,
            result_ref=f"result_{len(self.entries) + 1}",
            operation=operation,
            args_fingerprint=args_fingerprint,
            args_preview=args_preview,
            iteration=iteration,
            agent_slug=agent_slug,
            phase_id=phase_id,
            target_identity=target_identity,
            duplicate_of_call_id=duplicate_of,
        )
        self.entries.append(entry)
        return entry

    def register_result(
        self,
        *,
        call_id: str,
        success: bool,
        data: Any,
        sources: Optional[List[Dict[str, Any]]] = None,
        result_id: Optional[str] = None,
        result_inline_complete: Optional[bool] = None,
        result_source_complete: Optional[bool] = None,
        result_delivery: Literal["stored", "direct"] = "stored",
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
        cached_data = _cacheable_result_data(data) if success else None
        target.result_data = cached_data
        target.result_data_available = success and (cached_data is not None or data is None)
        target.stored_result_id = result_id
        target.result_inline_complete = result_inline_complete
        target.result_source_complete = result_source_complete
        target.result_delivery = result_delivery
        target.sources = [dict(source) for source in (sources or []) if isinstance(source, dict)]
        target.finished_at = datetime.now(timezone.utc)

    def update_result_presentation(self, *, call_id: str, inline_complete: Optional[bool]) -> None:
        """Update only the final model-delivery completeness for an existing result."""
        target = next((entry for entry in reversed(self.entries) if entry.call_id == call_id), None)
        if target is not None:
            target.result_inline_complete = inline_complete

    def set_call_target(self, *, call_id: str, target_identity: str,
                        arguments: Optional[Dict[str, Any]] = None,
                        execution_id: Optional[str] = None) -> None:
        """Attach resolved target and effective arguments before execution."""
        target = next((entry for entry in reversed(self.entries) if entry.call_id == call_id), None)
        if target is not None:
            target.target_identity = target_identity
            if execution_id is not None:
                target.execution_id = execution_id
            if arguments is not None:
                target.args_fingerprint, target.args_preview = _fingerprint_and_preview(arguments)

    def compact_view(self, *, max_items: int = 8) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for item in self.entries[-max_items:]:
            out.append(
                {
                    "operation": item.operation,
                    "call_id": item.call_id,
                    "result_ref": item.result_ref,
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
        phase_id: Optional[str] = None,
        execution_id: Optional[str] = None,
        target_identity: Optional[str] = None,
        max_age_seconds: Optional[int] = REUSE_MAX_AGE_SECONDS,
    ) -> Optional[ToolLedgerEntry]:
        args_fingerprint, _ = _fingerprint_and_preview(arguments)
        signature = f"{operation}:{target_identity or ''}:{args_fingerprint}"
        now = datetime.now(timezone.utc)
        for entry in reversed(self.entries):
            if entry.signature != signature:
                continue
            if phase_id is not None and entry.phase_id != phase_id:
                continue
            if execution_id is not None and entry.execution_id != execution_id:
                continue
            if entry.status != "succeeded":
                continue
            finished = entry.finished_at or entry.called_at
            age_seconds = (now - finished).total_seconds()
            if max_age_seconds is not None and age_seconds > max_age_seconds:
                continue
            return entry
        return None

    def find_execution_guard(self, *, operation: str, arguments: Dict[str, Any],
                             phase_id: Optional[str], target_identity: Optional[str],
                             execution_id: Optional[str] = None,
                             exclude_call_id: Optional[str] = None) -> Optional[ToolLedgerEntry]:
        """Return a matching prior attempt, including in-flight/failed attempts."""
        args_fingerprint, _ = _fingerprint_and_preview(arguments)
        signature = f"{operation}:{target_identity or ''}:{args_fingerprint}"
        for entry in reversed(self.entries):
            same_scope = (entry.execution_id == execution_id) if execution_id else (entry.phase_id == phase_id)
            if (entry.call_id != exclude_call_id and entry.signature == signature and same_scope
                    and entry.status in {"called", "succeeded"}):
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
    if len(_stable_json(value)) > MAX_RESULT_CACHE_CHARS:
        return None
    return value
