"""
RunStore - Service for logging agent execution runs and steps.

Supports three logging levels (copied from Agent.logging_level at run start):
- none:  No steps are recorded, only the run envelope (start/finish/status).
- brief: Metadata-only steps (step type, counts, slugs, durations). No payloads.
- full:  Everything including LLM messages, tool arguments/results, prompt text.

Usage:
    store = RunStore(session)
    run_id = await store.start_run(tenant_id=..., agent_slug=..., logging_level="brief")
    await store.add_step(run_id, "llm_request", {"model": "gpt-4", ...})
    await store.finish_run(run_id, status="completed")
"""
import hashlib
import json
import uuid
import time
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger
from app.models.agent_run import AgentRun, AgentRunStep

logger = get_logger(__name__)

# Maximum size for stored payloads in full mode (chars)
_MAX_PAYLOAD_SIZE = 10_000


def _truncate(value: Any, max_len: int = _MAX_PAYLOAD_SIZE) -> Any:
    """Truncate string values to prevent bloated JSONB."""
    if isinstance(value, str) and len(value) > max_len:
        return value[:max_len] + f"... [truncated, total {len(value)} chars]"
    return value


def _hash_text(text: str) -> str:
    """SHA-256 hash for prompt/content fingerprinting."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class RunStore:
    """
    Manages agent run logging with level-aware step recording.
    """
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self._step_counters: Dict[uuid.UUID, int] = {}
        self._run_start_times: Dict[uuid.UUID, float] = {}
        self._logging_levels: Dict[uuid.UUID, str] = {}
    
    # ── helpers ──────────────────────────────────────────────
    
    def _should_log(self, run_id: uuid.UUID) -> bool:
        """Check if this run should record steps at all."""
        return self._logging_levels.get(run_id, "brief") != "none"
    
    def _is_full(self, run_id: uuid.UUID) -> bool:
        """Check if this run uses full logging."""
        return self._logging_levels.get(run_id) == "full"
    
    def _strip_for_brief(self, step_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Strip heavy payloads for brief mode.
        Keeps metadata (counts, slugs, hashes) but removes content bodies.
        """
        heavy_keys = {
            "llm_request": {"messages", "system_prompt"},
            "llm_response": {"content", "raw_response"},
            "tool_call": {"arguments"},
            "tool_result": {"result", "tool_logs"},
            "user_request": {"content"},
            "final_response": {"content"},
            "routing": set(),  # routing metadata is always useful
            "error": set(),
        }
        keys_to_strip = heavy_keys.get(step_type, set())
        if not keys_to_strip:
            return data
        
        stripped = {}
        for k, v in data.items():
            if k in keys_to_strip:
                # Replace with hash + length for traceability
                if isinstance(v, str):
                    stripped[f"{k}_hash"] = _hash_text(v)
                    stripped[f"{k}_length"] = len(v)
                elif isinstance(v, (list, dict)):
                    serialized = json.dumps(v, default=str)
                    stripped[f"{k}_hash"] = _hash_text(serialized)
                    stripped[f"{k}_length"] = len(serialized)
            else:
                stripped[k] = v
        return stripped
    
    # ── run lifecycle ────────────────────────────────────────
    
    @staticmethod
    def _to_uuid(value: Any) -> Optional[uuid.UUID]:
        """Safely convert str or UUID to uuid.UUID, return None on failure."""
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return value
        try:
            return uuid.UUID(str(value))
        except (ValueError, AttributeError):
            return None
    
    async def start_run(
        self,
        tenant_id,
        agent_slug: str,
        logging_level: str = "brief",
        user_id=None,
        chat_id=None,
        message_id=None,
        context_snapshot: Optional[Dict[str, Any]] = None,
    ) -> uuid.UUID:
        """
        Start a new agent run and return its ID.
        
        Args:
            tenant_id: UUID or str — tenant identifier
            logging_level: "none" | "brief" | "full" — copied from Agent at run start
            context_snapshot: Frozen versions/config for reproducibility
        """
        run = AgentRun(
            id=uuid.uuid4(),
            tenant_id=self._to_uuid(tenant_id),
            agent_slug=agent_slug,
            logging_level=logging_level,
            user_id=self._to_uuid(user_id),
            chat_id=self._to_uuid(chat_id),
            message_id=self._to_uuid(message_id),
            status="running",
            context_snapshot=context_snapshot,
            started_at=datetime.now(timezone.utc),
        )
        self.session.add(run)
        await self.session.flush()
        
        self._step_counters[run.id] = 0
        self._run_start_times[run.id] = time.time()
        self._logging_levels[run.id] = logging_level
        
        return run.id
    
    async def add_step(
        self,
        run_id: uuid.UUID,
        step_type: str,
        data: Dict[str, Any],
        tokens_in: Optional[int] = None,
        tokens_out: Optional[int] = None,
        duration_ms: Optional[int] = None,
        error: Optional[str] = None,
    ) -> Optional[uuid.UUID]:
        """
        Add a step to an existing run.
        Returns step ID or None if logging is disabled for this run.
        """
        if not self._should_log(run_id):
            return None
        
        step_number = self._step_counters.get(run_id, 0)
        self._step_counters[run_id] = step_number + 1
        
        # Apply level-aware data stripping
        if self._is_full(run_id):
            # Truncate very large values but keep everything
            stored_data = {k: _truncate(v) for k, v in data.items()}
        else:
            stored_data = self._strip_for_brief(step_type, data)
        
        step = AgentRunStep(
            id=uuid.uuid4(),
            run_id=run_id,
            step_number=step_number,
            step_type=step_type,
            data=stored_data,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            duration_ms=duration_ms,
            error=error,
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(step)
        await self.session.flush()
        
        return step.id
    
    async def finish_run(
        self,
        run_id: uuid.UUID,
        status: str = "completed",
        error: Optional[str] = None,
        tokens_in: Optional[int] = None,
        tokens_out: Optional[int] = None,
    ) -> None:
        """Finalize a run with status and aggregated metrics."""
        result = await self.session.execute(
            select(AgentRun).where(AgentRun.id == run_id)
        )
        run = result.scalar_one_or_none()
        if not run:
            return
        
        run.status = status
        run.error = error
        run.finished_at = datetime.now(timezone.utc)
        run.total_steps = self._step_counters.get(run_id, 0)
        
        # Calculate duration
        start_time = self._run_start_times.get(run_id)
        if start_time:
            run.duration_ms = int((time.time() - start_time) * 1000)
        
        # Count tool calls and LLM calls from steps
        if self._should_log(run_id):
            counts = await self.session.execute(
                select(
                    AgentRunStep.step_type,
                    func.count(),
                ).where(
                    AgentRunStep.run_id == run_id,
                    AgentRunStep.step_type.in_(["tool_call", "llm_request"]),
                ).group_by(AgentRunStep.step_type)
            )
            for step_type, cnt in counts.fetchall():
                if step_type == "tool_call":
                    run.total_tool_calls = cnt
                elif step_type == "llm_request":
                    run.total_llm_calls = cnt
            
            # Aggregate tokens from steps
            token_agg = await self.session.execute(
                select(
                    func.sum(AgentRunStep.tokens_in),
                    func.sum(AgentRunStep.tokens_out),
                ).where(AgentRunStep.run_id == run_id)
            )
            row = token_agg.one()
            if row[0] is not None:
                run.tokens_in = row[0]
            if row[1] is not None:
                run.tokens_out = row[1]
        
        # Override with explicit values if provided
        if tokens_in is not None:
            run.tokens_in = tokens_in
        if tokens_out is not None:
            run.tokens_out = tokens_out
        
        await self.session.flush()
        
        # Cleanup local state
        self._step_counters.pop(run_id, None)
        self._run_start_times.pop(run_id, None)
        self._logging_levels.pop(run_id, None)
    
    async def get_run(self, run_id: uuid.UUID) -> Optional[AgentRun]:
        """Get a run by ID with its steps."""
        result = await self.session.execute(
            select(AgentRun).where(AgentRun.id == run_id)
        )
        return result.scalar_one_or_none()
    
    async def list_runs(
        self,
        tenant_id: Optional[uuid.UUID] = None,
        user_id: Optional[uuid.UUID] = None,
        chat_id: Optional[uuid.UUID] = None,
        agent_slug: Optional[str] = None,
        status: Optional[str] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[List[AgentRun], int]:
        """List runs with filters and pagination."""
        query = select(AgentRun)
        count_query = select(func.count()).select_from(AgentRun)
        
        # Apply filters
        if tenant_id:
            query = query.where(AgentRun.tenant_id == tenant_id)
            count_query = count_query.where(AgentRun.tenant_id == tenant_id)
        if user_id:
            query = query.where(AgentRun.user_id == user_id)
            count_query = count_query.where(AgentRun.user_id == user_id)
        if chat_id:
            query = query.where(AgentRun.chat_id == chat_id)
            count_query = count_query.where(AgentRun.chat_id == chat_id)
        if agent_slug:
            query = query.where(AgentRun.agent_slug == agent_slug)
            count_query = count_query.where(AgentRun.agent_slug == agent_slug)
        if status:
            query = query.where(AgentRun.status == status)
            count_query = count_query.where(AgentRun.status == status)
        if from_date:
            query = query.where(AgentRun.started_at >= from_date)
            count_query = count_query.where(AgentRun.started_at >= from_date)
        if to_date:
            query = query.where(AgentRun.started_at <= to_date)
            count_query = count_query.where(AgentRun.started_at <= to_date)
        
        # Get total count
        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0
        
        # Apply pagination and ordering
        query = query.order_by(AgentRun.started_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        
        result = await self.session.execute(query)
        runs = list(result.scalars().all())
        
        return runs, total
    
    async def get_run_with_steps(self, run_id: uuid.UUID) -> Optional[AgentRun]:
        """Get a run with all its steps loaded using eager loading."""
        result = await self.session.execute(
            select(AgentRun)
            .where(AgentRun.id == run_id)
            .options(selectinload(AgentRun.steps))
        )
        return result.scalar_one_or_none()
    
    async def delete_run(self, run_id: uuid.UUID) -> bool:
        """Delete a run and all its steps (cascade)."""
        result = await self.session.execute(
            delete(AgentRun).where(AgentRun.id == run_id)
        )
        await self.session.flush()
        return result.rowcount > 0
    
    async def delete_runs_before(self, before_date: datetime, tenant_id: Optional[uuid.UUID] = None) -> int:
        """Delete runs older than a given date. Returns count of deleted runs."""
        query = delete(AgentRun).where(AgentRun.started_at < before_date)
        if tenant_id:
            query = query.where(AgentRun.tenant_id == tenant_id)
        
        result = await self.session.execute(query)
        await self.session.flush()
        return result.rowcount
