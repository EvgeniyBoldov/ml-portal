"""
ResumeResolver — owns cross-turn memory bootstrap and paused-run detection.

Responsibilities:
    * Load latest WorkingMemory for a chat (rolling summary + last refs).
    * Enumerate paused runs awaiting user input (for Triage).
    * Seed a fresh WorkingMemory for the current turn from the latest.
    * Swap the current memory with a paused one when Triage decides RESUME.

The pipeline talks to this resolver through the small API below and does
not touch the MemoryPort directly for bootstrap.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional
from uuid import UUID, uuid4

from app.runtime.contracts import PipelineRequest
from app.runtime.memory.working_memory import (
    ChatMessageRef,
    WorkingMemory,
)
from app.runtime.ports import MemoryPort


@dataclass
class TurnBootstrap:
    """Everything a pipeline turn needs before triage runs."""

    memory: WorkingMemory
    latest: Optional[WorkingMemory]
    paused_runs: List[WorkingMemory] = field(default_factory=list)


class ResumeResolver:
    """Seeds WorkingMemory for a turn and handles paused-run resume swaps."""

    def __init__(self, memory_port: MemoryPort) -> None:
        self._memory = memory_port

    # ------------------------------------------------------------------ #
    # Bootstrap                                                          #
    # ------------------------------------------------------------------ #

    async def bootstrap(
        self,
        *,
        request: PipelineRequest,
        chat_id: Optional[UUID],
        user_id: UUID,
        tenant_id: UUID,
    ) -> TurnBootstrap:
        latest: Optional[WorkingMemory] = None
        paused: List[WorkingMemory] = []

        if chat_id is not None:
            latest = await self._memory.load_latest_for_chat(chat_id)
            paused = await self._memory.load_paused_for_chat(chat_id)

        memory = self._seed_fresh(
            run_id=uuid4(),
            request=request,
            user_id=user_id,
            tenant_id=tenant_id,
            chat_id=chat_id,
            latest=latest,
        )
        return TurnBootstrap(memory=memory, latest=latest, paused_runs=paused)

    async def resume(self, run_id: UUID) -> Optional[WorkingMemory]:
        """Load a paused run for continuation. Returns None if missing."""
        resumed = await self._memory.load(run_id)
        if resumed is None:
            return None
        resumed.consume_open_question()
        resumed.status = "running"
        return resumed

    # ------------------------------------------------------------------ #
    # Helpers                                                            #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _seed_fresh(
        *,
        run_id: UUID,
        request: PipelineRequest,
        user_id: UUID,
        tenant_id: UUID,
        chat_id: Optional[UUID],
        latest: Optional[WorkingMemory],
    ) -> WorkingMemory:
        memory = WorkingMemory(
            run_id=run_id,
            chat_id=chat_id,
            tenant_id=tenant_id,
            user_id=user_id,
            goal=request.request_text,
            question=request.request_text,
            status="running",
        )
        if latest is not None:
            # Carry rolling summary + prior recent-message refs forward.
            memory.dialogue_summary = latest.dialogue_summary
            memory.recent_messages = list(latest.recent_messages)

        refs: List[ChatMessageRef] = []
        for m in request.messages[-10:]:
            refs.append(
                ChatMessageRef(
                    message_id=str(m.get("message_id") or m.get("id") or ""),
                    role=str(m.get("role") or "user"),
                    preview=str(m.get("content") or "")[:200],
                )
            )
        memory.set_recent_messages(refs)
        return memory
