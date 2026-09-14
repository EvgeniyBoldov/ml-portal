"""Safe, typed journal projections for conversational memory writeback."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from app.runtime.memory.dto import FactDTO


JOURNAL_CANDIDATE_IDS = "_journal_candidate_ids"


def candidate_ids(fact: FactDTO) -> tuple[str, ...]:
    raw = fact.metadata.get(JOURNAL_CANDIDATE_IDS) if isinstance(fact.metadata, dict) else None
    return tuple(str(item) for item in raw if isinstance(item, str)) if isinstance(raw, (list, tuple)) else ()


def evidence_view(fact: FactDTO) -> dict[str, Any]:
    refs: list[dict[str, str]] = []
    for item in fact.metadata.get("evidence", []) if isinstance(fact.metadata, dict) else []:
        if not isinstance(item, dict):
            continue
        source_type = str(item.get("source_type") or "").strip()
        source_ref = str(item.get("support_ref") or item.get("source_ref") or "").strip()
        if source_type and source_ref:
            value = {"source_type": source_type, "source_ref": source_ref}
            label = str(item.get("label") or "").strip()
            if label:
                value["label"] = label[:120]
            refs.append(value)
    return {"count": len(refs), "refs": refs}


@dataclass(frozen=True)
class MemoryDecision:
    """One bounded, operator-facing decision about an extracted candidate."""

    component_name: str
    decision_phase: str
    outcome: str
    reason_code: str
    facts: tuple[FactDTO, ...] = ()
    action: str | None = None
    status_before: str | None = None
    status_after: str | None = None
    support_before: int | None = None
    support_after: int | None = None
    support_delta: int | None = None

    def compact_view(self) -> dict[str, Any]:
        primary = self.facts[0] if self.facts else None
        result: dict[str, Any] = {
            "stage": "memory_candidate_decision",
            "memory_contract_version": 1,
            "component_name": self.component_name,
            "decision_phase": self.decision_phase,
            "outcome": self.outcome,
            "reason_code": self.reason_code,
            "candidate_ids": [candidate_id for fact in self.facts for candidate_id in candidate_ids(fact)],
        }
        if primary is not None:
            result["candidate"] = {
                "scope": primary.scope.value,
                "kind": primary.kind,
                "subject": primary.subject,
                "value": primary.value,
                "confidence": primary.confidence,
            }
            result["evidence"] = evidence_view(primary)
        if self.action:
            result["action"] = self.action
        transition = {
            "status_before": self.status_before,
            "status_after": self.status_after,
            "support_before": self.support_before,
            "support_after": self.support_after,
            "support_delta": self.support_delta,
        }
        if any(value is not None for value in transition.values()):
            result["transition"] = transition
        return result


def decision_counts(decisions: Iterable[MemoryDecision]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for decision in decisions:
        counts[decision.outcome] = counts.get(decision.outcome, 0) + 1
    return counts
