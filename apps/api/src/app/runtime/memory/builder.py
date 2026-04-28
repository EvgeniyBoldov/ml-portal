"""MemoryBuilder — query-scoped memory read path at turn start.

The builder assembles a componentized `MemoryBundle` instead of dumping all
stored memory into the prompt. Backward-compatible `TurnMemory.summary` and
`TurnMemory.retrieved_facts` projections remain for the current runtime while
the legacy `WorkingMemory` bridge is being retired.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.runtime.memory.components import (
    AgentRunMemoryComponent,
    AttachmentMemoryComponent,
    CollectionMemoryComponent,
    ConversationMemoryComponent,
    FactMemoryComponent,
    MemoryAssembler,
    MemoryBudget,
    MemoryBundle,
    MemoryComponentRegistry,
    MemoryQueryContext,
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
    ) -> TurnMemory:
        summary = await self._load_summary(chat_id)
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

    async def _load_summary(self, chat_id: Optional[UUID]) -> SummaryDTO:
        """Load the chat's summary, or a fresh empty one if absent.

        Non-chat contexts (sandbox with no chat_id) get an in-memory
        empty summary whose chat_id is a throwaway — it is never
        persisted because the sandbox code path skips MemoryWriter.
        """
        if chat_id is None:
            # We still need a SummaryDTO so downstream code can read
            # structured fields uniformly. It just won't round-trip.
            from uuid import uuid4
            return SummaryDTO.empty(uuid4())

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
