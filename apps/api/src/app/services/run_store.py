"""RunStore - Service for logging agent execution runs and steps.

Supports three logging levels (copied from Agent.logging_level at run start):
- none:  No steps are recorded, only the run envelope (start/finish/status).
- brief: Metadata-only steps (step type, counts, slugs, durations). No payloads.
- full:  Everything including LLM messages, tool arguments/results, prompt text.

IMPORTANT: RunStore uses its OWN dedicated DB sessions for writes.
This isolates logging from the main business transaction so that errors
in logging never poison the primary session (no FK violations, no
MissingGreenlet from shared session expiry, etc.).
Read operations (list_runs, get_run) accept an explicit session parameter
because they are typically called from admin endpoints with their own session.

Usage:
    store = RunStore()                              # uses global session factory
    run_id = await store.start_run(tenant_id=..., agent_slug=..., logging_level="brief")
    await store.add_step(run_id, "llm_request", {"model": "gpt-4", ...})
    await store.finish_run(run_id, status="completed")
"""
import hashlib
import json
import uuid
import time
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncIterator, Optional, Dict, Any, List
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger
from app.models.agent_run import AgentRun, AgentRunStep

logger = get_logger(__name__)

# Maximum size for stored payloads in full mode (chars)
_MAX_PAYLOAD_SIZE = 10_000

# Brief mode truncation lengths
_BRIEF_KEEP_TRUNCATED = {
    "user_request:content": 200,
    "final_response:content": 500,
    "llm_request:system_prompt": 100,
    "llm_response:content": 200,
    "operation_call:arguments": 200,
    "operation_result:result": 200,
    "tool_call:arguments": 200,
    "tool_result:result": 200,
}

def _truncate(value: Any, max_len: int = _MAX_PAYLOAD_SIZE) -> Any:
    """Truncate string values to prevent bloated JSONB."""
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_truncate(v, max_len) for v in value]
    if isinstance(value, set):
        return [_truncate(v, max_len) for v in sorted(value, key=str)]
    if isinstance(value, str) and len(value) > max_len:
        return value[:max_len] + f"... [truncated, total {len(value)} chars]"
    if isinstance(value, dict):
        return {k: _truncate(v, max_len) for k, v in value.items()}
    if isinstance(value, list):
        return [_truncate(v, max_len) for v in value]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, (str,)):
        return value
    return str(value)


def _hash_text(text: str) -> str:
    """SHA-256 hash for prompt/content fingerprinting."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class RunStore:
    """
    Manages agent run logging with level-aware step recording.

    Uses a dedicated session factory so logging writes are independent
    of the caller's business transaction.
    """

    def __init__(
        self,
        session: Optional[AsyncSession] = None,
        session_factory: Optional[async_sessionmaker[AsyncSession]] = None,
    ):
        self._session_factory = session_factory
        self._fallback_session = session
        self._step_counters: Dict[uuid.UUID, int] = {}
        self._run_start_times: Dict[uuid.UUID, float] = {}
        self._logging_levels: Dict[uuid.UUID, str] = {}
        self._state_lock = asyncio.Lock()

    # ── session management ──────────────────────────────────

    def _get_factory(self) -> async_sessionmaker[AsyncSession]:
        if self._session_factory is not None:
            return self._session_factory
        # Lazy import to avoid circular deps at module level
        from app.core.db import get_session_factory
        self._session_factory = get_session_factory()
        return self._session_factory

    @asynccontextmanager
    async def _write_session(self) -> AsyncIterator[AsyncSession]:
        """Open a short-lived session for a single logging write + commit."""
        factory = self._get_factory()
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    def _read_session(self, session: Optional[AsyncSession] = None) -> AsyncSession:
        """Return an explicit session for reads (admin API etc.)."""
        if session is not None:
            return session
        if self._fallback_session is not None:
            return self._fallback_session
        raise RuntimeError("RunStore: no session for read operation")
    
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
        Exception: user_request.content and final_response.content are kept truncated
        so the question text and answer are always visible in the run view.
        """
        heavy_keys = {
            "llm_request": {"messages", "system_prompt"},
            "llm_response": {"content", "raw_response"},
            "operation_call": {"arguments", "input"},
            "operation_result": {"result", "output", "tool_logs"},
            "tool_call": {"arguments", "input"},
            "tool_result": {"result", "output", "tool_logs"},
            "user_request": {"content"},
            "final_response": {"content"},
            "routing": set(),
            "error": set(),
        }
        keys_to_strip = heavy_keys.get(step_type, set())
        if not keys_to_strip:
            return data

        stripped = {}
        for k, v in data.items():
            keep_key = f"{step_type}:{k}"
            max_len = _BRIEF_KEEP_TRUNCATED.get(keep_key)
            
            if k in keys_to_strip:
                if max_len is not None and isinstance(v, str):
                    # Keep truncated version (still useful for observability)
                    stripped[k] = v[:max_len] + ("…" if len(v) > max_len else "")
                    stripped[f"{k}_length"] = len(v)
                elif max_len is not None and isinstance(v, (list, dict)):
                    serialized = json.dumps(v, default=str)
                    stripped[k] = serialized[:max_len] + ("…" if len(serialized) > max_len else "")
                    stripped[f"{k}_length"] = len(serialized)
                else:
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
        run_id = uuid.uuid4()
        run = AgentRun(
            id=run_id,
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
        async with self._write_session() as s:
            s.add(run)

        async with self._state_lock:
            self._step_counters[run_id] = 0
            self._run_start_times[run_id] = time.time()
            self._logging_levels[run_id] = logging_level

        return run_id
    
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
        
        async with self._state_lock:
            step_number = self._step_counters.get(run_id, 0)
            self._step_counters[run_id] = step_number + 1
        
        # Apply level-aware data stripping
        if self._is_full(run_id):
            # Truncate very large values but keep everything
            stored_data = {k: _truncate(v) for k, v in data.items()}
        else:
            stored_data = self._strip_for_brief(step_type, data)

        # Normalize input/output aliases for downstream UI
        if self._is_full(run_id):
            if step_type in {"tool_call", "operation_call"}:
                if "input" not in stored_data:
                    if "arguments" in data:
                        stored_data["input"] = _truncate(data["arguments"])
                    elif "parameters" in data:
                        stored_data["input"] = _truncate(data["parameters"])
            if step_type in {"tool_result", "operation_result"}:
                if "output" not in stored_data:
                    if "result" in data:
                        stored_data["output"] = _truncate(data["result"])
                    elif "data" in data:
                        stored_data["output"] = _truncate(data["data"])
                if "result" not in stored_data and "output" in stored_data:
                    stored_data["result"] = stored_data["output"]
        
        # Add human-readable previews
        if step_type in {"tool_call", "operation_call"} and "arguments" in data:
            try:
                args = data["arguments"]
                if isinstance(args, str):
                    stored_data["arguments_preview"] = args[:100] + ("…" if len(args) > 100 else "")
                elif isinstance(args, dict):
                    preview_parts = [f"{k}={str(v)[:20]}" for k, v in args.items()]
                    preview = ", ".join(preview_parts)
                    stored_data["arguments_preview"] = preview[:100] + ("…" if len(preview) > 100 else "")
            except Exception:
                pass
                
        if step_type in {"tool_result", "operation_result"} and "result" in data:
            try:
                res = data["result"]
                if isinstance(res, str):
                    stored_data["result_preview"] = res[:100] + ("…" if len(res) > 100 else "")
                elif isinstance(res, dict):
                    # Try to extract common readable fields
                    if "message" in res:
                        preview = str(res["message"])
                    elif "summary" in res:
                        preview = str(res["summary"])
                    else:
                        preview = str(res)
                    stored_data["result_preview"] = preview[:100] + ("…" if len(preview) > 100 else "")
            except Exception:
                pass
                
        step_id = uuid.uuid4()
        step = AgentRunStep(
            id=step_id,
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
        async with self._write_session() as s:
            s.add(step)

        return step_id
    
    async def finish_run(
        self,
        run_id: uuid.UUID,
        status: str = "completed",
        error: Optional[str] = None,
        tokens_in: Optional[int] = None,
        tokens_out: Optional[int] = None,
    ) -> None:
        """Finalize a run with status and aggregated metrics."""
        async with self._write_session() as s:
            result = await s.execute(
                select(AgentRun).where(AgentRun.id == run_id)
            )
            run = result.scalar_one_or_none()
            if not run:
                return

            run.status = status
            run.error = error
            run.finished_at = datetime.now(timezone.utc)
            async with self._state_lock:
                run.total_steps = self._step_counters.get(run_id, 0)
                start_time = self._run_start_times.get(run_id)
            if start_time:
                run.duration_ms = int((time.time() - start_time) * 1000)

            if self._should_log(run_id):
                counts = await s.execute(
                    select(
                        AgentRunStep.step_type,
                        func.count(),
                    ).where(
                        AgentRunStep.run_id == run_id,
                        AgentRunStep.step_type.in_(["tool_call", "operation_call", "llm_request"]),
                    ).group_by(AgentRunStep.step_type)
                )
                for step_type, cnt in counts.fetchall():
                    if step_type in {"tool_call", "operation_call"}:
                        run.total_tool_calls = cnt
                    elif step_type == "llm_request":
                        run.total_llm_calls = cnt

                token_agg = await s.execute(
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

            if tokens_in is not None:
                run.tokens_in = tokens_in
            if tokens_out is not None:
                run.tokens_out = tokens_out

        # Cleanup local state
        async with self._state_lock:
            self._step_counters.pop(run_id, None)
            self._run_start_times.pop(run_id, None)
            self._logging_levels.pop(run_id, None)
    
    async def get_run(self, run_id: uuid.UUID, session: Optional[AsyncSession] = None) -> Optional[AgentRun]:
        """Get a run by ID with its steps."""
        s = self._read_session(session)
        result = await s.execute(
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
        session: Optional[AsyncSession] = None,
    ) -> tuple[List[AgentRun], int]:
        """List runs with filters and pagination."""
        s = self._read_session(session)
        query = select(AgentRun)
        count_query = select(func.count()).select_from(AgentRun)
        
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
        
        total_result = await s.execute(count_query)
        total = total_result.scalar() or 0
        
        query = query.order_by(AgentRun.started_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        
        result = await s.execute(query)
        runs = list(result.scalars().all())
        
        return runs, total
    
    async def get_run_with_steps(self, run_id: uuid.UUID, session: Optional[AsyncSession] = None) -> Optional[AgentRun]:
        """Get a run with all its steps loaded using eager loading."""
        s = self._read_session(session)
        result = await s.execute(
            select(AgentRun)
            .where(AgentRun.id == run_id)
            .options(selectinload(AgentRun.steps))
        )
        return result.scalar_one_or_none()
    
    async def delete_run(self, run_id: uuid.UUID) -> bool:
        """Delete a run and all its steps (cascade)."""
        async with self._write_session() as s:
            result = await s.execute(
                delete(AgentRun).where(AgentRun.id == run_id)
            )
            return result.rowcount > 0
    
    async def pause_run(
        self,
        run_id: uuid.UUID,
        status: str,
        paused_action: Dict[str, Any],
        paused_context: Dict[str, Any],
    ) -> None:
        """
        Pause a run with frozen action and context for later continuation.
        """
        async with self._write_session() as s:
            result = await s.execute(
                select(AgentRun).where(AgentRun.id == run_id)
            )
            run = result.scalar_one_or_none()
            if not run:
                logger.warning(f"Cannot pause run {run_id}: not found")
                return

            run.status = status
            run.paused_action = paused_action
            run.paused_context = paused_context

        logger.info(f"Run {run_id} paused with status={status}")
    
    async def get_paused_run(
        self, run_id: uuid.UUID, session: Optional[AsyncSession] = None,
    ) -> Optional[AgentRun]:
        """Get a paused run by ID (status = waiting_*)."""
        s = self._read_session(session)
        result = await s.execute(
            select(AgentRun).where(
                AgentRun.id == run_id,
                AgentRun.status.in_(["waiting_confirmation", "waiting_input"]),
            )
        )
        return result.scalar_one_or_none()
    
    async def resume_run(self, run_id: uuid.UUID) -> None:
        """Clear pause state and set status back to running."""
        async with self._write_session() as s:
            result = await s.execute(
                select(AgentRun).where(AgentRun.id == run_id)
            )
            run = result.scalar_one_or_none()
            if not run:
                return

            run.status = "running"
            run.paused_action = None
            run.paused_context = None

        logger.info(f"Run {run_id} resumed")
    
    async def delete_runs_before(self, before_date: datetime, tenant_id: Optional[uuid.UUID] = None) -> int:
        """Delete runs older than a given date. Returns count of deleted runs."""
        async with self._write_session() as s:
            query = delete(AgentRun).where(AgentRun.started_at < before_date)
            if tenant_id:
                query = query.where(AgentRun.tenant_id == tenant_id)
            result = await s.execute(query)
            return result.rowcount
