"""Service for storing and updating execution memory for planner/runtime."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.execution_memory import ExecutionMemory

logger = get_logger(__name__)


class ExecutionMemoryService:
    """Persistence helper for orchestration memory."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_run_id(self, run_id: UUID) -> Optional[ExecutionMemory]:
        result = await self.session.execute(
            select(ExecutionMemory).where(ExecutionMemory.run_id == run_id)
        )
        return result.scalar_one_or_none()

    async def get_or_create(
        self,
        *,
        run_id: UUID,
        chat_id: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
        goal: Optional[str] = None,
        question: Optional[str] = None,
        dialogue_summary: Optional[str] = None,
    ) -> ExecutionMemory:
        memory = await self.get_by_run_id(run_id)
        if memory:
            self._merge_context(memory, chat_id=chat_id, tenant_id=tenant_id, goal=goal, question=question, dialogue_summary=dialogue_summary)
            self.session.add(memory)
            await self.session.flush()
            return memory

        memory = ExecutionMemory(
            run_id=run_id,
            chat_id=chat_id,
            tenant_id=tenant_id,
            goal=goal,
            question=question,
            dialogue_summary=dialogue_summary,
        )
        self.session.add(memory)
        await self.session.flush()
        return memory

    async def update_context(
        self,
        run_id: UUID,
        *,
        chat_id: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
        goal: Optional[str] = None,
        question: Optional[str] = None,
        dialogue_summary: Optional[str] = None,
        current_phase_id: Optional[str] = None,
        current_agent_slug: Optional[str] = None,
        state: Optional[Dict[str, Any]] = None,
    ) -> ExecutionMemory:
        memory = await self.get_or_create(
            run_id=run_id,
            chat_id=chat_id,
            tenant_id=tenant_id,
            goal=goal,
            question=question,
            dialogue_summary=dialogue_summary,
        )
        if current_phase_id is not None:
            memory.current_phase_id = current_phase_id
        if current_agent_slug is not None:
            memory.current_agent_slug = current_agent_slug
        if state:
            memory.memory_state = {**(memory.memory_state or {}), **state}
        self.session.add(memory)
        await self.session.flush()
        return memory

    async def record_step(
        self,
        run_id: UUID,
        *,
        step_type: str,
        payload: Dict[str, Any],
        signature: Optional[str] = None,
        chat_id: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
        current_phase_id: Optional[str] = None,
        current_agent_slug: Optional[str] = None,
    ) -> ExecutionMemory:
        memory = await self.get_or_create(
            run_id=run_id,
            chat_id=chat_id,
            tenant_id=tenant_id,
        )
        history = list(memory.step_history or [])
        history.append(
            {
                "step_type": step_type,
                "payload": payload,
                "ts": datetime.now(timezone.utc).isoformat(),
            }
        )
        memory.step_history = history[-50:]
        if signature:
            signatures = list(memory.loop_signatures or [])
            signatures.append(signature)
            memory.loop_signatures = signatures[-50:]
        if current_phase_id is not None:
            memory.current_phase_id = current_phase_id
        if current_agent_slug is not None:
            memory.current_agent_slug = current_agent_slug
        self.session.add(memory)
        await self.session.flush()
        return memory

    async def finish_run(
        self,
        run_id: UUID,
        *,
        status: str,
        final_answer: Optional[str] = None,
        final_error: Optional[str] = None,
        chat_id: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
    ) -> ExecutionMemory:
        memory = await self.get_or_create(
            run_id=run_id,
            chat_id=chat_id,
            tenant_id=tenant_id,
        )
        memory.run_status = status
        memory.final_answer = final_answer
        memory.final_error = final_error
        if status not in {"waiting_input", "waiting_confirmation"}:
            memory.finished_at = datetime.now(timezone.utc)
        self.session.add(memory)
        await self.session.flush()
        return memory

    async def record_agent_result(
        self,
        run_id: UUID,
        *,
        agent_slug: str,
        summary: str,
        chat_id: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
        facts: Optional[List[str]] = None,
        phase_id: Optional[str] = None,
        step_id: Optional[str] = None,
    ) -> ExecutionMemory:
        memory = await self.get_or_create(
            run_id=run_id,
            chat_id=chat_id,
            tenant_id=tenant_id,
        )
        results = list(memory.agent_results or [])
        results.append(
            {
                "agent_slug": agent_slug,
                "summary": summary,
                "facts": facts or [],
                "phase_id": phase_id,
                "step_id": step_id,
                "ts": datetime.now(timezone.utc).isoformat(),
            }
        )
        memory.agent_results = results[-50:]
        if facts:
            combined = list(memory.facts or [])
            combined.extend(facts)
            memory.facts = combined[-100:]
        memory.current_agent_slug = agent_slug
        self.session.add(memory)
        await self.session.flush()
        return memory

    async def add_fact(
        self,
        run_id: UUID,
        fact: str,
        *,
        chat_id: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
    ) -> ExecutionMemory:
        memory = await self.get_or_create(
            run_id=run_id,
            chat_id=chat_id,
            tenant_id=tenant_id,
        )
        facts = list(memory.facts or [])
        facts.append(fact)
        memory.facts = facts[-100:]
        self.session.add(memory)
        await self.session.flush()
        return memory

    async def add_open_question(
        self,
        run_id: UUID,
        question: str,
        *,
        chat_id: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
    ) -> ExecutionMemory:
        memory = await self.get_or_create(
            run_id=run_id,
            chat_id=chat_id,
            tenant_id=tenant_id,
        )
        questions = list(memory.open_questions or [])
        questions.append(question)
        memory.open_questions = questions[-50:]
        self.session.add(memory)
        await self.session.flush()
        return memory

    async def snapshot(self, run_id: UUID, *, max_items: int = 5) -> Dict[str, Any]:
        memory = await self.get_by_run_id(run_id)
        if not memory:
            return {}
        return {
            "run_id": str(memory.run_id),
            "chat_id": str(memory.chat_id) if memory.chat_id else None,
            "tenant_id": str(memory.tenant_id) if memory.tenant_id else None,
            "goal": memory.goal,
            "question": memory.question,
            "dialogue_summary": memory.dialogue_summary,
            "current_phase_id": memory.current_phase_id,
            "current_agent_slug": memory.current_agent_slug,
            "recent_steps": list(memory.step_history or [])[-max_items:],
            "recent_agent_results": list(memory.agent_results or [])[-max_items:],
            "facts": list(memory.facts or [])[-max_items:],
            "open_questions": list(memory.open_questions or [])[-max_items:],
            "loop_signatures": list(memory.loop_signatures or [])[-max_items:],
            "memory_state": memory.memory_state or {},
            "run_status": memory.run_status,
            "final_answer": memory.final_answer,
            "final_error": memory.final_error,
            "finished_at": memory.finished_at.isoformat() if memory.finished_at else None,
        }

    @staticmethod
    def _merge_context(
        memory: ExecutionMemory,
        *,
        chat_id: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
        goal: Optional[str] = None,
        question: Optional[str] = None,
        dialogue_summary: Optional[str] = None,
    ) -> None:
        if chat_id is not None:
            memory.chat_id = chat_id
        if tenant_id is not None:
            memory.tenant_id = tenant_id
        if goal is not None:
            memory.goal = goal
        if question is not None:
            memory.question = question
        if dialogue_summary is not None:
            memory.dialogue_summary = dialogue_summary
