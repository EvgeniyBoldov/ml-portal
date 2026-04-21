"""Domain DTOs for the memory layer.

These are the only shapes the rest of the runtime (MemoryBuilder,
MemoryWriter, Planner, Synthesizer) should ever touch. The ORM models
`app.models.memory.Fact` / `app.models.memory.DialogueSummary` stay
behind the store boundary.

Kept as frozen dataclasses (not pydantic) because this is on the hot
read path of every turn and we don't need validation every time we
shuttle these through in-memory — validation happens once at the
boundary (Fact extractor output, HTTP admin API).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import UUID, uuid4

from app.models.memory import FactScope, FactSource


@dataclass(frozen=True)
class FactDTO:
    """Immutable domain representation of a Fact row."""
    scope: FactScope
    subject: str
    value: str
    source: FactSource

    # Optional scoping context — required-ness depends on scope and is
    # enforced by FactStore.upsert_with_supersede, not here.
    tenant_id: Optional[UUID] = None
    user_id: Optional[UUID] = None
    chat_id: Optional[UUID] = None

    confidence: float = 1.0
    source_ref: Optional[str] = None
    observed_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    # Lifecycle — populated by the store when reading back, or left
    # defaulted on construction for writes.
    id: UUID = field(default_factory=uuid4)
    superseded_by: Optional[UUID] = None
    user_visible: bool = True

    def matches_key(self, other: "FactDTO") -> bool:
        """Two DTOs identify the same 'slot' iff scope, subject and the
        scope-relevant owner id match. Used by upsert_with_supersede to
        find the active row that a new fact would replace.
        """
        if self.scope != other.scope or self.subject != other.subject:
            return False
        if self.scope == FactScope.CHAT:
            return self.chat_id == other.chat_id
        if self.scope == FactScope.USER:
            return self.user_id == other.user_id
        if self.scope == FactScope.TENANT:
            return self.tenant_id == other.tenant_id
        return False


@dataclass
class SummaryDTO:
    """Mutable domain representation of a DialogueSummary row.

    Mutable because MemoryWriter updates it in place before calling
    SummaryStore.save — there is no benefit in creating a frozen copy
    for every field tweak during compaction.
    """
    chat_id: UUID
    goals: List[str] = field(default_factory=list)
    done: List[str] = field(default_factory=list)
    entities: Dict[str, str] = field(default_factory=dict)
    open_questions: List[str] = field(default_factory=list)
    raw_tail: str = ""
    last_updated_turn: int = 0
    updated_at: Optional[datetime] = None

    @classmethod
    def empty(cls, chat_id: UUID) -> "SummaryDTO":
        """Zero-valued summary — used when MemoryBuilder finds no row."""
        return cls(chat_id=chat_id)
