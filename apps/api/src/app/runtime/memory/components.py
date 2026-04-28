"""Componentized, query-scoped runtime memory assembly.

The runtime should not pour every remembered item into the prompt. Each
component owns one memory surface, selects only data relevant to the current
turn, and returns a bounded, explainable section.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Protocol, Sequence, Tuple
from uuid import UUID

from app.models.memory import FactScope
from app.runtime.memory.dto import FactDTO, SummaryDTO
from app.runtime.memory.fact_selection import FactSelectionPolicy, LexicalFactRanker
from app.runtime.memory.fact_store import FactStore
from app.runtime.memory.user_facts_service import LongTermFactsService


DEFAULT_TOTAL_MEMORY_BUDGET_CHARS = 8_000
DEFAULT_SECTION_BUDGET_CHARS = 2_000
DEFAULT_SECTION_ITEMS = 12
FACT_RETRIEVAL_POOL_MULTIPLIER = 4
PROMPT_ITEM_PREVIEW_CHARS = 500


@dataclass(frozen=True)
class MemorySectionBudget:
    """Per-section budget override."""

    max_chars: Optional[int] = None
    max_items: Optional[int] = None


@dataclass(frozen=True)
class MemoryBudget:
    """Prompt-facing memory budget for one turn."""

    total_chars: int = DEFAULT_TOTAL_MEMORY_BUDGET_CHARS
    default_section_chars: int = DEFAULT_SECTION_BUDGET_CHARS
    max_items_per_section: int = DEFAULT_SECTION_ITEMS
    section_overrides: Dict[str, MemorySectionBudget] = field(default_factory=dict)

    @classmethod
    def from_platform_config(
        cls,
        *,
        base: "MemoryBudget",
        platform_config: Optional[Dict[str, Any]],
    ) -> "MemoryBudget":
        memory_cfg = (platform_config or {}).get("memory")
        if not isinstance(memory_cfg, dict):
            return base

        total_chars = _int_or_default(memory_cfg.get("total_chars"), base.total_chars)
        section_chars = _int_or_default(
            memory_cfg.get("default_section_chars"),
            _int_or_default(memory_cfg.get("section_chars"), base.default_section_chars),
        )
        section_items = _int_or_default(
            memory_cfg.get("max_items_per_section"),
            _int_or_default(memory_cfg.get("section_items"), base.max_items_per_section),
        )

        overrides: Dict[str, MemorySectionBudget] = dict(base.section_overrides)
        comp_cfg = memory_cfg.get("components")
        if isinstance(comp_cfg, dict):
            for name, raw in comp_cfg.items():
                if not isinstance(raw, dict):
                    continue
                override_chars = _int_or_none(raw.get("max_chars"))
                if override_chars is None:
                    override_chars = _int_or_none(raw.get("section_chars"))
                override_items = _int_or_none(raw.get("max_items"))
                if override_items is None:
                    override_items = _int_or_none(raw.get("section_items"))
                if override_chars is None and override_items is None:
                    continue
                overrides[str(name)] = MemorySectionBudget(
                    max_chars=override_chars,
                    max_items=override_items,
                )

        return cls(
            total_chars=total_chars,
            default_section_chars=section_chars,
            max_items_per_section=section_items,
            section_overrides=overrides,
        )

    def for_section(
        self,
        name: str,
        *,
        default_chars: Optional[int] = None,
        default_items: Optional[int] = None,
    ) -> MemorySectionBudget:
        base = self.section_overrides.get(name)
        return MemorySectionBudget(
            max_chars=base.max_chars if base and base.max_chars is not None else default_chars,
            max_items=base.max_items if base and base.max_items is not None else default_items,
        )


@dataclass(frozen=True)
class MemoryQueryContext:
    """Inputs every memory component may use to select relevant context."""

    goal: str
    chat_id: Optional[UUID]
    user_id: Optional[UUID]
    tenant_id: Optional[UUID]
    summary: SummaryDTO
    budget: MemoryBudget = field(default_factory=MemoryBudget)
    messages: List[Dict[str, Any]] = field(default_factory=list)
    agent_slug: Optional[str] = None
    available_agents: List[Dict[str, Any]] = field(default_factory=list)
    resolved_collections: List[Dict[str, Any]] = field(default_factory=list)
    resolved_operations: List[Dict[str, Any]] = field(default_factory=list)
    attachment_ids: List[str] = field(default_factory=list)
    request_id: Optional[str] = None
    trace_id: Optional[str] = None
    platform_config: Dict[str, Any] = field(default_factory=dict)
    tool_ledger_entries: List[Dict[str, Any]] = field(default_factory=list)
    recent_agent_runs: List[Dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class MemoryItem:
    """One selected memory atom with traceable provenance."""

    text: str
    source: str
    subject: Optional[str] = None
    score: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    redaction_level: str = "safe"
    private_payload: Any = None

    @property
    def size_chars(self) -> int:
        return len(self.text or "")


@dataclass
class MemorySection:
    """Output of one memory component."""

    name: str
    priority: int
    items: List[MemoryItem] = field(default_factory=list)
    omitted_count: int = 0
    budget_used_chars: int = 0
    selection_reason: str = ""
    redaction_level: str = "safe"
    status: str = "ok"
    error: Optional[str] = None

    def compact_view(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "priority": self.priority,
            "status": self.status,
            "items": len(self.items),
            "omitted_count": self.omitted_count,
            "budget_used_chars": self.budget_used_chars,
            "selection_reason": self.selection_reason,
            "redaction_level": self.redaction_level,
            "error": self.error,
        }


@dataclass
class MemoryBundle:
    """All selected memory for one runtime turn."""

    sections: List[MemorySection] = field(default_factory=list)
    total_budget_used_chars: int = 0
    diagnostics: Dict[str, Any] = field(default_factory=dict)

    def section(self, name: str) -> Optional[MemorySection]:
        for item in self.sections:
            if item.name == name:
                return item
        return None

    def items_for(self, name: str) -> List[MemoryItem]:
        section = self.section(name)
        return list(section.items) if section else []

    def compact_view(self) -> Dict[str, Any]:
        return {
            "total_budget_used_chars": self.total_budget_used_chars,
            "sections": [section.compact_view() for section in self.sections],
            "diagnostics": dict(self.diagnostics),
        }


class MemoryComponent(Protocol):
    """Read-side component contract."""

    name: str
    priority: int

    async def collect(self, ctx: MemoryQueryContext) -> MemorySection: ...


@dataclass(frozen=True)
class MemoryComponentBinding:
    component: MemoryComponent
    enabled: bool
    priority: int


class MemoryComponentRegistry:
    """Deterministic component selection with config-driven toggles."""

    def __init__(self, components: Sequence[MemoryComponent]) -> None:
        self._components = {item.name: item for item in components}

    def resolve(self, platform_config: Optional[Dict[str, Any]]) -> List[MemoryComponentBinding]:
        memory_cfg = (platform_config or {}).get("memory")
        component_cfg = memory_cfg.get("components") if isinstance(memory_cfg, dict) else {}
        disabled = set(memory_cfg.get("disabled_components") or []) if isinstance(memory_cfg, dict) else set()

        bindings: List[MemoryComponentBinding] = []
        for name, component in self._components.items():
            raw_cfg = component_cfg.get(name) if isinstance(component_cfg, dict) else None
            enabled = True
            priority = int(getattr(component, "priority", 100))
            if isinstance(raw_cfg, dict):
                enabled = bool(raw_cfg.get("enabled", True))
                priority = _int_or_default(raw_cfg.get("priority"), priority)
            if name in disabled:
                enabled = False
            bindings.append(MemoryComponentBinding(component=component, enabled=enabled, priority=priority))

        bindings.sort(key=lambda item: (item.priority, item.component.name))
        return bindings


class MemoryAssembler:
    """Runs memory components and enforces a total prompt budget."""

    def __init__(self, *, registry: MemoryComponentRegistry) -> None:
        self._registry = registry

    async def assemble(self, ctx: MemoryQueryContext) -> MemoryBundle:
        sections: List[MemorySection] = []
        diagnostics: Dict[str, Any] = {}
        used = 0

        bindings = self._registry.resolve(ctx.platform_config)
        diagnostics["component_count"] = len(bindings)
        diagnostics["enabled_components"] = [b.component.name for b in bindings if b.enabled]
        diagnostics["disabled_components"] = [b.component.name for b in bindings if not b.enabled]

        for binding in bindings:
            if not binding.enabled:
                continue
            try:
                section = await binding.component.collect(ctx)
                section.priority = binding.priority
            except Exception as exc:  # noqa: BLE001 - component failure must degrade the turn
                section = MemorySection(
                    name=getattr(binding.component, "name", binding.component.__class__.__name__),
                    priority=binding.priority,
                    status="degraded",
                    error=str(exc),
                    selection_reason="component_failed",
                )
            used += section.budget_used_chars
            sections.append(section)

        if used > ctx.budget.total_chars:
            used = self._trim_to_total_budget(sections, ctx.budget.total_chars)

        diagnostics["degraded_components"] = [
            section.name for section in sections if section.status != "ok"
        ]
        return MemoryBundle(
            sections=sections,
            total_budget_used_chars=used,
            diagnostics=diagnostics,
        )

    @staticmethod
    def _trim_to_total_budget(sections: List[MemorySection], limit: int) -> int:
        used = 0
        for section in sections:
            kept: List[MemoryItem] = []
            section_used = 0
            for item in section.items:
                item_size = item.size_chars
                if used + item_size > limit:
                    section.omitted_count += 1
                    continue
                kept.append(item)
                used += item_size
                section_used += item_size
            section.items = kept
            section.budget_used_chars = section_used
        return used


class MemoryPromptRenderer:
    """Render bounded prompt context from MemoryBundle sections."""

    def render(
        self,
        *,
        bundle: MemoryBundle,
        max_chars: int,
        allow_internal: bool = False,
        include_section_headers: bool = True,
    ) -> str:
        allowed_levels = {"safe"}
        if allow_internal:
            allowed_levels.add("internal")

        chunks: List[str] = []
        used = 0
        ordered_sections = sorted(bundle.sections, key=lambda item: (item.priority, item.name))
        for section in ordered_sections:
            if section.redaction_level not in allowed_levels:
                continue
            lines: List[str] = []
            if include_section_headers:
                lines.append(f"[{section.name}]")
            for item in section.items:
                if item.redaction_level not in allowed_levels:
                    continue
                text = _trim_text(item.text, PROMPT_ITEM_PREVIEW_CHARS)
                lines.append(f"- {text}")
            if not lines:
                continue
            section_text = "\n".join(lines)
            if used + len(section_text) > max_chars:
                available = max_chars - used
                if available <= 0:
                    break
                chunks.append(section_text[:available])
                used += available
                break
            chunks.append(section_text)
            used += len(section_text)

        return "\n\n".join(chunks)


class ConversationMemoryComponent:
    """Structured per-chat summary, selected by explicit facets."""

    name = "conversation"
    priority = 10

    async def collect(self, ctx: MemoryQueryContext) -> MemorySection:
        items: List[MemoryItem] = []
        summary = ctx.summary

        for goal in summary.goals[:5]:
            items.append(MemoryItem(text=f"goal: {goal}", source="dialogue_summary", subject="goal", score=1.0))
        for done in summary.done[:5]:
            items.append(MemoryItem(text=f"done: {done}", source="dialogue_summary", subject="done", score=0.8))
        for question in summary.open_questions[:5]:
            items.append(
                MemoryItem(
                    text=f"open_question: {question}",
                    source="dialogue_summary",
                    subject="open_question",
                    score=1.0,
                )
            )
        for key, value in list(summary.entities.items())[:8]:
            items.append(
                MemoryItem(
                    text=f"entity {key}: {value}",
                    source="dialogue_summary",
                    subject=f"entity.{key}",
                    score=0.6,
                )
            )
        if summary.raw_tail:
            items.append(
                MemoryItem(
                    text=summary.raw_tail[-min(len(summary.raw_tail), 600):],
                    source="dialogue_summary",
                    subject="raw_tail",
                    score=0.4,
                    redaction_level="internal",
                )
            )

        budget = ctx.budget.for_section(
            self.name,
            default_chars=min(ctx.budget.default_section_chars, 1_600),
            default_items=min(ctx.budget.max_items_per_section, 12),
        )
        return _fit_section(
            name=self.name,
            priority=self.priority,
            items=items,
            max_chars=budget.max_chars or min(ctx.budget.default_section_chars, 1_600),
            max_items=budget.max_items or min(ctx.budget.max_items_per_section, 12),
            selection_reason="structured_summary_facets",
        )


class FactMemoryComponent:
    """Query-ranked long-term facts across user / department / company scopes."""

    name = "facts"
    priority = 20

    def __init__(
        self,
        *,
        fact_store: FactStore,
        fact_limit: int,
    ) -> None:
        self._fact_store = fact_store
        self._fact_limit = fact_limit

    async def collect(self, ctx: MemoryQueryContext) -> MemorySection:
        service = LongTermFactsService(
            fact_store=self._fact_store,
            user_id=ctx.user_id,
            tenant_id=ctx.tenant_id,
        )
        pool_limit = max(self._fact_limit, ctx.budget.max_items_per_section) * FACT_RETRIEVAL_POOL_MULTIPLIER
        facts = await service.load_for_runtime(limit=pool_limit)
        facts_cfg = ((ctx.platform_config or {}).get("memory") or {}).get("facts")
        ranker_name = "lexical"
        if isinstance(facts_cfg, dict):
            ranker_name = str(facts_cfg.get("ranker") or "lexical").strip().lower()
        # Embedding ranker can be plugged later; for now config is explicit and
        # deterministic: unknown/embedding values degrade to lexical.
        ranker = LexicalFactRanker()
        policy = FactSelectionPolicy(ranker=ranker)
        selection = policy.select(
            query=ctx.goal,
            facts=facts,
            limit=pool_limit,
        )
        contradiction_subjects = set(selection.diagnostics.get("contradiction_subjects") or [])
        selected_items = [
            MemoryItem(
                text=f"[{_fact_scope_human_label(ranked_item.fact)}] {ranked_item.fact.subject}: {ranked_item.fact.value}",
                source=_fact_scope_label(ranked_item.fact),
                subject=ranked_item.fact.subject,
                score=ranked_item.score,
                metadata={
                    "fact_id": str(ranked_item.fact.id),
                    "scope": ranked_item.fact.scope.value,
                    "confidence": ranked_item.fact.confidence,
                    "observed_at": (
                        ranked_item.fact.observed_at.isoformat()
                        if ranked_item.fact.observed_at else None
                    ),
                    "lexical_hits": ranked_item.lexical_hits,
                    "ranker": ranker.__class__.__name__,
                    "ranker_requested": ranker_name,
                    "ranker_degraded_to_lexical": ranker_name not in {"", "lexical"},
                    "contradiction": ranked_item.fact.subject in contradiction_subjects,
                },
                private_payload=ranked_item.fact,
            )
            for ranked_item in selection.selected
        ]
        if contradiction_subjects:
            conflict_items = [
                MemoryItem(
                    text=(
                        f"conflict: {subject} has different values across scopes; "
                        "use scope labels and do not merge silently"
                    ),
                    source="memory.conflict",
                    subject=subject,
                    score=10.0,
                    metadata={"kind": "fact_contradiction_notice"},
                )
                for subject in sorted(contradiction_subjects)
            ]
            selected_items = conflict_items + selected_items
        budget = ctx.budget.for_section(
            self.name,
            default_chars=ctx.budget.default_section_chars,
            default_items=min(self._fact_limit, ctx.budget.max_items_per_section),
        )
        return _fit_section(
            name=self.name,
            priority=self.priority,
            items=selected_items,
            max_chars=budget.max_chars or ctx.budget.default_section_chars,
            max_items=budget.max_items or min(self._fact_limit, ctx.budget.max_items_per_section),
            selection_reason=(
                f"query_ranked_long_term_facts"
                f";selected={selection.diagnostics.get('selected_facts', 0)}"
                f";omitted_stale={selection.diagnostics.get('omitted_stale', 0)}"
                f";omitted_low_confidence={selection.diagnostics.get('omitted_low_confidence', 0)}"
                f";contradictions={len(contradiction_subjects)}"
            ),
        )


class ToolLedgerMemoryComponent:
    """Turn-local tool call history for duplicate avoidance context."""

    name = "tool_ledger"
    priority = 30

    async def collect(self, ctx: MemoryQueryContext) -> MemorySection:
        items: List[MemoryItem] = []
        for entry in (ctx.tool_ledger_entries or [])[:20]:
            operation = str(entry.get("operation") or "operation")
            status = str(entry.get("status") or "called")
            result_preview = str(entry.get("result_preview") or "")
            args_preview = str(entry.get("args_preview") or "")
            text = f"{operation} [{status}] args={args_preview} result={result_preview}".strip()
            items.append(
                MemoryItem(
                    text=_trim_text(text, 320),
                    source="runtime.tool_ledger",
                    subject=operation,
                    score=0.4,
                    redaction_level="internal",
                )
            )

        budget = ctx.budget.for_section(
            self.name,
            default_chars=min(ctx.budget.default_section_chars, 800),
            default_items=min(ctx.budget.max_items_per_section, 8),
        )
        return _fit_section(
            name=self.name,
            priority=self.priority,
            items=items,
            max_chars=budget.max_chars or min(ctx.budget.default_section_chars, 800),
            max_items=budget.max_items or min(ctx.budget.max_items_per_section, 8),
            selection_reason="recent_tool_calls",
            redaction_level="internal",
        )


class AgentRunMemoryComponent:
    """Recent sub-agent outcomes from prior turns/runs."""

    name = "agent_runs"
    priority = 35

    async def collect(self, ctx: MemoryQueryContext) -> MemorySection:
        items: List[MemoryItem] = []
        for run in (ctx.recent_agent_runs or [])[:10]:
            slug = str(run.get("agent_slug") or run.get("agent") or "agent")
            success = run.get("success")
            summary = str(run.get("summary") or run.get("result") or "")
            label = "success" if success is True else "failed" if success is False else "unknown"
            items.append(
                MemoryItem(
                    text=f"{slug} [{label}]: {_trim_text(summary, 260)}",
                    source="runtime.agent_runs",
                    subject=slug,
                    score=0.35,
                    redaction_level="internal",
                )
            )

        budget = ctx.budget.for_section(
            self.name,
            default_chars=min(ctx.budget.default_section_chars, 800),
            default_items=min(ctx.budget.max_items_per_section, 6),
        )
        return _fit_section(
            name=self.name,
            priority=self.priority,
            items=items,
            max_chars=budget.max_chars or min(ctx.budget.default_section_chars, 800),
            max_items=budget.max_items or min(ctx.budget.max_items_per_section, 6),
            selection_reason="recent_agent_run_outcomes",
            redaction_level="internal",
        )


class AttachmentMemoryComponent:
    """Reference attachment ids when user supplied files."""

    name = "attachments"
    priority = 40

    async def collect(self, ctx: MemoryQueryContext) -> MemorySection:
        items = [
            MemoryItem(
                text=f"attachment: {att_id}",
                source="chat.attachments",
                subject=str(att_id),
                score=0.5,
            )
            for att_id in (ctx.attachment_ids or [])
        ]
        budget = ctx.budget.for_section(
            self.name,
            default_chars=min(ctx.budget.default_section_chars, 600),
            default_items=min(ctx.budget.max_items_per_section, 8),
        )
        return _fit_section(
            name=self.name,
            priority=self.priority,
            items=items,
            max_chars=budget.max_chars or min(ctx.budget.default_section_chars, 600),
            max_items=budget.max_items or min(ctx.budget.max_items_per_section, 8),
            selection_reason="request_attachment_refs",
        )


class CollectionMemoryComponent:
    """Resolved collection and operation context for planner/synthesizer."""

    name = "collections"
    priority = 45

    async def collect(self, ctx: MemoryQueryContext) -> MemorySection:
        items: List[MemoryItem] = []
        for item in (ctx.resolved_collections or [])[:10]:
            slug = str(item.get("slug") or item.get("collection_slug") or item.get("id") or "collection")
            typ = str(item.get("type") or "unknown")
            status = str(item.get("status") or item.get("readiness") or "ready")
            items.append(
                MemoryItem(
                    text=f"collection {slug} type={typ} status={status}",
                    source="runtime.collections",
                    subject=slug,
                    score=0.3,
                )
            )

        op_slugs = []
        for op in (ctx.resolved_operations or [])[:12]:
            slug = str(op.get("operation_slug") or op.get("slug") or "")
            if slug:
                op_slugs.append(slug)
        if op_slugs:
            items.append(
                MemoryItem(
                    text="available_operations: " + ", ".join(op_slugs),
                    source="runtime.operations",
                    subject="operations",
                    score=0.25,
                )
            )

        budget = ctx.budget.for_section(
            self.name,
            default_chars=min(ctx.budget.default_section_chars, 900),
            default_items=min(ctx.budget.max_items_per_section, 10),
        )
        return _fit_section(
            name=self.name,
            priority=self.priority,
            items=items,
            max_chars=budget.max_chars or min(ctx.budget.default_section_chars, 900),
            max_items=budget.max_items or min(ctx.budget.max_items_per_section, 10),
            selection_reason="resolved_collections_and_operations",
        )


def _fit_section(
    *,
    name: str,
    priority: int,
    items: List[MemoryItem],
    max_chars: int,
    max_items: int,
    selection_reason: str,
    redaction_level: str = "safe",
) -> MemorySection:
    kept: List[MemoryItem] = []
    used = 0
    omitted = 0
    for item in items:
        if len(kept) >= max_items:
            omitted += 1
            continue
        item_size = item.size_chars
        if used + item_size > max_chars:
            omitted += 1
            continue
        kept.append(item)
        used += item_size
    return MemorySection(
        name=name,
        priority=priority,
        items=kept,
        omitted_count=omitted,
        budget_used_chars=used,
        selection_reason=selection_reason,
        redaction_level=redaction_level,
    )


def _fact_scope_label(fact: FactDTO) -> str:
    if fact.scope == FactScope.USER:
        return "memory.user"
    if fact.scope == FactScope.TENANT and fact.tenant_id is None:
        return "memory.company"
    if fact.scope == FactScope.TENANT:
        return "memory.department"
    return "memory.chat"


def _fact_scope_human_label(fact: FactDTO) -> str:
    if fact.scope == FactScope.USER:
        return "user"
    if fact.scope == FactScope.TENANT and fact.tenant_id is None:
        return "company"
    if fact.scope == FactScope.TENANT:
        return "department"
    return "chat"


def _trim_text(value: str, limit: int) -> str:
    value = str(value or "")
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)] + "…"


def _int_or_none(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        return max(1, int(value))
    except (TypeError, ValueError):
        return None


def _int_or_default(value: Any, default: int) -> int:
    parsed = _int_or_none(value)
    return parsed if parsed is not None else default
