"""MemoryBuilder — query-scoped memory read path at turn start.

The builder assembles a componentized `MemoryBundle` instead of dumping all
stored memory into the prompt. Backward-compatible `TurnMemory.summary` and
`TurnMemory.retrieved_facts` projections remain for planner/synth input
compatibility during the runtime helpers transition.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.memory import FactScope, FactSource
from app.models.sandbox import SandboxBranch
from app.runtime.memory.components import (
    AgentRunMemoryComponent,
    AttachmentMemoryComponent,
    CollectionMemoryComponent,
    ConversationMemoryComponent,
    FactMemoryComponent,
    MemoryAssembler,
    MemoryBudget,
    MemoryBundle,
    MemoryItem,
    MemoryComponentRegistry,
    MemoryQueryContext,
    MemorySection,
    ToolLedgerMemoryComponent,
)
from app.runtime.memory.dto import FactDTO, SummaryDTO
from app.runtime.memory.fact_store import FactStore
from app.runtime.memory.summary_store import SummaryStore
from app.runtime.memory.transport import TurnMemory

logger = get_logger(__name__)


DEFAULT_FACT_RETRIEVAL_LIMIT = 20


class MemoryBuilder:
    """Assemble a turn-level memory snapshot for the current request.

    NOTE(4.1): Stores are created per-builder via __init__. MemoryBuilder is
    fresh per turn (cached_property on assembler), so registry is rebuilt each
    turn. Profiled: cheap (microseconds). If heavy components are added,
    profile here first.
    """

    def __init__(
        self,
        *,
        session: AsyncSession,
        fact_limit: int = DEFAULT_FACT_RETRIEVAL_LIMIT,
        memory_budget: Optional[MemoryBudget] = None,
    ) -> None:
        self._session = session
        self._fact_store = FactStore(session)
        self._summary_store = SummaryStore(session)
        self._fact_limit = fact_limit
        self._memory_budget = memory_budget or MemoryBudget()
        self._memory_registry = MemoryComponentRegistry(
            components=[
                ConversationMemoryComponent(),
                FactMemoryComponent(
                    fact_store=self._fact_store,
                    fact_limit=fact_limit,
                ),
                ToolLedgerMemoryComponent(),
                AgentRunMemoryComponent(),
                AttachmentMemoryComponent(),
                CollectionMemoryComponent(),
            ],
        )
        self._memory_assembler = MemoryAssembler(registry=self._memory_registry)

    async def build(
        self,
        *,
        goal: str,
        chat_id: Optional[UUID],
        user_id: Optional[UUID],
        tenant_id: Optional[UUID],
        messages: Optional[List[Dict[str, Any]]] = None,
        agent_slug: Optional[str] = None,
        available_agents: Optional[List[Dict[str, Any]]] = None,
        resolved_collections: Optional[List[Dict[str, Any]]] = None,
        resolved_operations: Optional[List[Dict[str, Any]]] = None,
        attachment_ids: Optional[List[str]] = None,
        request_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        platform_config: Optional[Dict[str, Any]] = None,
        tool_ledger_entries: Optional[List[Dict[str, Any]]] = None,
        recent_agent_runs: Optional[List[Dict[str, Any]]] = None,
        sandbox_overrides: Optional[Dict[str, Any]] = None,
    ) -> TurnMemory:
        sandbox_branch_id = _resolve_sandbox_branch_id(sandbox_overrides)
        summary = await self._load_summary(
            chat_id,
            sandbox_branch_id=sandbox_branch_id,
            sandbox_overrides=sandbox_overrides,
        )
        effective_budget = MemoryBudget.from_platform_config(
            base=self._memory_budget,
            platform_config=platform_config,
        )
        memory_bundle = await self._memory_assembler.assemble(
            MemoryQueryContext(
                goal=goal,
                chat_id=chat_id,
                user_id=user_id,
                tenant_id=tenant_id,
                summary=summary,
                budget=effective_budget,
                messages=list(messages or []),
                agent_slug=agent_slug,
                available_agents=list(available_agents or []),
                resolved_collections=list(resolved_collections or []),
                resolved_operations=list(resolved_operations or []),
                attachment_ids=[str(item) for item in (attachment_ids or [])],
                request_id=request_id,
                trace_id=trace_id,
                platform_config=dict(platform_config or {}),
                tool_ledger_entries=list(tool_ledger_entries or []),
                recent_agent_runs=list(recent_agent_runs or []),
            )
        )
        if sandbox_branch_id is not None:
            memory_bundle = await self._inject_branch_facts(
                memory_bundle=memory_bundle,
                branch_id=sandbox_branch_id,
                sandbox_overrides=sandbox_overrides,
            )
        facts = self._load_selected_facts_from_bundle(memory_bundle)

        return TurnMemory(
            chat_id=chat_id,
            user_id=user_id,
            tenant_id=tenant_id,
            turn_number=summary.last_updated_turn + 1,
            goal=goal,
            summary=summary,
            retrieved_facts=facts,
            memory_bundle=memory_bundle,
            memory_diagnostics=memory_bundle.compact_view(),
        )

    async def _load_summary(
        self,
        chat_id: Optional[UUID],
        *,
        sandbox_branch_id: Optional[UUID],
        sandbox_overrides: Optional[Dict[str, Any]],
    ) -> SummaryDTO:
        """Load the chat's summary, or a fresh empty one if absent.

        Non-chat contexts (sandbox with no chat_id) get an in-memory
        empty summary whose chat_id is a throwaway — it is never
        persisted because the sandbox code path skips MemoryWriter.
        """
        if chat_id is None:
            if sandbox_branch_id is not None:
                row = await self._session.execute(
                    select(SandboxBranch).where(SandboxBranch.id == sandbox_branch_id)
                )
                branch = row.scalar_one_or_none()
                if branch is not None and isinstance(branch.summary_artifact_json, dict):
                    summary_payload = dict(branch.summary_artifact_json or {})
                    summary = SummaryDTO(
                        chat_id=uuid4(),
                        goals=list(summary_payload.get("goals") or []),
                        done=list(summary_payload.get("done") or []),
                        entities={
                            str(k): str(v)
                            for k, v in dict(summary_payload.get("entities") or {}).items()
                            if str(k).strip() and str(v).strip()
                        },
                        open_questions=list(summary_payload.get("open_questions") or []),
                        raw_tail=str(summary_payload.get("raw_tail") or ""),
                        last_updated_turn=int(summary_payload.get("last_updated_turn") or 0),
                    )
                    return _apply_branch_summary_overrides(summary, sandbox_overrides=sandbox_overrides)
            return _apply_branch_summary_overrides(SummaryDTO.empty(uuid4()), sandbox_overrides=sandbox_overrides)

        existing = await self._summary_store.load(chat_id)
        if existing is not None:
            return existing
        return SummaryDTO.empty(chat_id)

    @staticmethod
    def _load_selected_facts_from_bundle(memory_bundle: MemoryBundle) -> list[FactDTO]:
        """Back-compat projection for legacy planner/synthesizer.

        FactMemoryComponent stores `FactDTO` only in `private_payload`; this keeps
        debug/trace surfaces clean while preserving compatibility projection.
        """
        selected: list[FactDTO] = []
        for item in memory_bundle.items_for("facts"):
            if isinstance(item.private_payload, FactDTO):
                selected.append(item.private_payload)
        return selected

    async def _inject_branch_facts(
        self,
        *,
        memory_bundle: MemoryBundle,
        branch_id: UUID,
        sandbox_overrides: Optional[Dict[str, Any]],
    ) -> MemoryBundle:
        row = await self._session.execute(select(SandboxBranch).where(SandboxBranch.id == branch_id))
        branch = row.scalar_one_or_none()
        if branch is None:
            return memory_bundle
        raw_facts = list(branch.facts_artifact_json or [])
        raw_facts = _apply_branch_facts_overrides(raw_facts, sandbox_overrides)
        items: list[MemoryItem] = []
        for raw in raw_facts[: self._fact_limit]:
            if not isinstance(raw, dict):
                continue
            subject = str(raw.get("subject") or "").strip()
            value = str(raw.get("value") or "").strip()
            if not subject or not value:
                continue
            scope_raw = str(raw.get("scope") or FactScope.CHAT.value)
            source_raw = str(raw.get("source") or FactSource.USER.value)
            scope = FactScope(scope_raw) if scope_raw in {v.value for v in FactScope} else FactScope.CHAT
            source = FactSource(source_raw) if source_raw in {v.value for v in FactSource} else FactSource.USER_UTTERANCE
            fact = FactDTO(
                scope=scope,
                subject=subject,
                value=value,
                source=source,
                confidence=float(raw.get("confidence") or 1.0),
                observed_at=datetime.now(timezone.utc),
            )
            items.append(
                MemoryItem(
                    text=f"{subject}: {value}",
                    source="sandbox_branch",
                    subject=subject,
                    score=1.0,
                    metadata={"artifact_scope": "branch"},
                    private_payload=fact,
                )
            )
        section = MemorySection(
            name="facts",
            priority=40,
            items=items,
            omitted_count=max(0, len(raw_facts) - len(items)),
            budget_used_chars=sum(len(item.text or "") for item in items),
            selection_reason="sandbox_branch_artifacts",
        )
        sections = [sec for sec in memory_bundle.sections if sec.name != "facts"]
        sections.append(section)
        sections.sort(key=lambda sec: (sec.priority, sec.name))
        used = sum(sec.budget_used_chars for sec in sections)
        diagnostics = dict(memory_bundle.diagnostics or {})
        diagnostics["sandbox_branch_facts_count"] = len(items)
        return MemoryBundle(sections=sections, total_budget_used_chars=used, diagnostics=diagnostics)


def _resolve_sandbox_branch_id(sandbox_overrides: Optional[Dict[str, Any]]) -> Optional[UUID]:
    raw = (sandbox_overrides or {}).get("sandbox_branch_id")
    if not raw:
        return None
    try:
        return UUID(str(raw))
    except (TypeError, ValueError):
        return None


def _apply_branch_facts_overrides(
    facts: List[Dict[str, Any]],
    sandbox_overrides: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    overrides = (sandbox_overrides or {}).get("branch_facts_overrides")
    if not isinstance(overrides, dict):
        return facts
    raw = overrides.get("facts")
    if isinstance(raw, list):
        return [dict(item) for item in raw if isinstance(item, dict)]
    return facts


def _apply_branch_summary_overrides(
    summary: SummaryDTO,
    *,
    sandbox_overrides: Optional[Dict[str, Any]],
) -> SummaryDTO:
    overrides = (sandbox_overrides or {}).get("branch_summary_overrides")
    if not isinstance(overrides, dict):
        return summary
    if isinstance(overrides.get("goals"), list):
        summary.goals = [str(item) for item in overrides["goals"]]
    if isinstance(overrides.get("done"), list):
        summary.done = [str(item) for item in overrides["done"]]
    if isinstance(overrides.get("entities"), dict):
        summary.entities = {
            str(key): str(value)
            for key, value in overrides["entities"].items()
            if str(key).strip() and str(value).strip()
        }
    if isinstance(overrides.get("open_questions"), list):
        summary.open_questions = [str(item) for item in overrides["open_questions"]]
    if isinstance(overrides.get("raw_tail"), str):
        summary.raw_tail = overrides["raw_tail"]
    if isinstance(overrides.get("last_updated_turn"), int):
        summary.last_updated_turn = overrides["last_updated_turn"]
    return summary
