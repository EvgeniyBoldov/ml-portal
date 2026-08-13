"""MemoryBuilder — query-scoped memory read path at turn start.

The builder assembles a componentized `MemoryBundle` instead of dumping all
stored memory into the prompt. Backward-compatible `TurnMemory.summary` and
`TurnMemory.retrieved_facts` projections remain for planner/synth input
compatibility during the runtime helpers transition.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.memory import FactScope
from app.models.sandbox import SandboxBranch
from app.runtime.memory.components import (
    AgentExecutionMemoryComponent,
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
from app.runtime.memory.service import MemoryService
from app.runtime.memory.summary_store import SummaryStore
from app.runtime.memory.sandbox_overlays import apply_overrides
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
        self._memory_service = MemoryService(fact_store=self._fact_store)
        self._summary_store = SummaryStore(session)
        self._fact_limit = fact_limit
        self._memory_budget = memory_budget or MemoryBudget()
        self._memory_registry = MemoryComponentRegistry(
            components=[
                FactMemoryComponent(
                    memory_service=self._memory_service,
                    fact_limit=fact_limit,
                ),
                ToolLedgerMemoryComponent(),
                AgentExecutionMemoryComponent(),
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
        attachments: Optional[List[Any]] = None,
        request_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        platform_config: Optional[Dict[str, Any]] = None,
        tool_ledger_entries: Optional[List[Dict[str, Any]]] = None,
        recent_agent_runs: Optional[List[Dict[str, Any]]] = None,
        sandbox_overrides: Optional[Dict[str, Any]] = None,
    ) -> TurnMemory:
        sandbox_branch_id = _resolve_sandbox_branch_id(sandbox_overrides)
        # Conversation summary is retained in storage for compatibility but is
        # deliberately not part of runtime memory at this stage.
        summary = SummaryDTO.empty(chat_id or uuid4())
        effective_budget = MemoryBudget.from_platform_config(
            base=self._memory_budget,
            platform_config=platform_config,
        )
        durable_snapshot = await self._memory_service.read_snapshot(
            user_id=user_id,
            tenant_id=tenant_id,
            limit=max(self._fact_limit, effective_budget.max_items_per_section) * 4,
        )
        if sandbox_branch_id is not None:
            durable_snapshot = self._apply_snapshot_fact_overrides(
                durable_snapshot,
                sandbox_overrides=sandbox_overrides,
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
                attachments=list(attachments or []),
                request_id=request_id,
                trace_id=trace_id,
                platform_config=dict(platform_config or {}),
                tool_ledger_entries=list(tool_ledger_entries or []),
                recent_agent_runs=list(recent_agent_runs or []),
                durable_snapshot=durable_snapshot,
            )
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
            planner_memory_context=durable_snapshot.planner_context(limit=self._fact_limit),
            durable_snapshot=durable_snapshot,
            artifacts=[
                item.model_dump(mode="json") if hasattr(item, "model_dump") else dict(item)
                for item in (attachments or [])
            ],
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

    @staticmethod
    def _apply_snapshot_fact_overrides(
        durable_snapshot,
        *,
        sandbox_overrides: Optional[Dict[str, Any]],
    ):
        raw = (sandbox_overrides or {}).get("fact_overrides")
        effective = apply_overrides(durable_snapshot.entries, raw)
        return replace(
            durable_snapshot,
            user_facts=tuple(item for item in effective if item.scope == FactScope.USER and item.status.value == "confirmed"),
            tenant_facts=tuple(item for item in effective if item.scope == FactScope.TENANT and item.status.value == "confirmed"),
        )


def _resolve_sandbox_branch_id(sandbox_overrides: Optional[Dict[str, Any]]) -> Optional[UUID]:
    raw = (sandbox_overrides or {}).get("sandbox_branch_id")
    if not raw:
        return None
    try:
        return UUID(str(raw))
    except (TypeError, ValueError):
        return None


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
