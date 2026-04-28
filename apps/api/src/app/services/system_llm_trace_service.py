"""
Service for SystemLLMTrace operations.

Handles creation and management of system LLM execution traces.
"""
import hashlib
import json
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.system_llm_trace import SystemLLMTrace, SystemLLMTraceType
from app.repositories.system_llm_trace_repository import SystemLLMTraceRepository
from app.core.logging import get_logger
from app.runtime.redactor import RuntimeRedactor

logger = get_logger(__name__)


class SystemLLMTraceService:
    """Service for managing system LLM traces."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = SystemLLMTraceRepository(session)
        self.redactor = RuntimeRedactor()
    
    async def create_trace(
        self,
        trace_type: str,
        role_config: Dict[str, Any],
        structured_input: Dict[str, Any],
        messages_sent: List[Dict[str, str]],
        raw_response: str,
        parsed_response: Optional[Dict[str, Any]],
        validation_status: str,
        duration_ms: int,
        model: str,
        temperature: float,
        max_tokens: int,
        attempt_number: int = 1,
        total_attempts: int = 1,
        tokens_in: Optional[int] = None,
        tokens_out: Optional[int] = None,
        validation_error: Optional[str] = None,
        fallback_applied: bool = False,
        fallback_details: Optional[Dict[str, Any]] = None,
        result_type: Optional[str] = None,
        result_summary: Optional[str] = None,
        chat_id: Optional[uuid.UUID] = None,
        agent_run_id: Optional[uuid.UUID] = None,
        tenant_id: Optional[uuid.UUID] = None,
        user_id: Optional[uuid.UUID] = None,
        error: Optional[str] = None
    ) -> SystemLLMTrace:
        """Create a new system LLM trace."""
        
        redacted_structured_input = self.redactor.redact(structured_input or {})
        redacted_messages = self.redactor.redact(messages_sent or [])
        redacted_raw_response = self.redactor.redact(raw_response or "")
        redacted_parsed_response = self.redactor.redact(parsed_response or {})
        redacted_fallback_details = self.redactor.redact(fallback_details or {})
        redacted_error = self.redactor.redact(error or "") if error else None

        # Extract context variables from structured input
        context_variables = {}
        if trace_type == SystemLLMTraceType.TRIAGE:
            context_variables = {
                "available_agents": redacted_structured_input.get("available_agents", []),
                "policies": redacted_structured_input.get("policies", ""),
                "active_run": redacted_structured_input.get("active_run"),
            }
        elif trace_type == SystemLLMTraceType.PLANNER:
            context_variables = {
                "available_agents": redacted_structured_input.get("available_agents", []),
                "available_operations": redacted_structured_input.get(
                    "available_operations",
                    redacted_structured_input.get("available_tools", []),
                ),
                "policies": redacted_structured_input.get("policies", ""),
            }
        elif trace_type == SystemLLMTraceType.SUMMARY:
            context_variables = {
                "session_state": redacted_structured_input.get("session_state", {}),
            }
        
        # Create role snapshot
        role_snapshot = {
            "role_type": role_config.get("role_type"),
            "identity": role_config.get("identity"),
            "mission": role_config.get("mission"),
            "rules": role_config.get("rules"),
            "safety": role_config.get("safety"),
            "output_requirements": role_config.get("output_requirements"),
            "examples": role_config.get("examples", []),
            "model": role_config.get("model"),
            "temperature": role_config.get("temperature"),
            "max_tokens": role_config.get("max_tokens"),
            "timeout_s": role_config.get("timeout_s"),
            "max_retries": role_config.get("max_retries"),
            "retry_backoff": role_config.get("retry_backoff"),
        }
        
        # Calculate prompt hash
        compiled_prompt = role_config.get("prompt", "")
        compiled_prompt_hash = hashlib.sha256(
            compiled_prompt.encode("utf-8")
        ).hexdigest()[:16]
        
        trace = SystemLLMTrace(
            trace_type=trace_type,
            chat_id=chat_id,
            agent_run_id=agent_run_id,
            tenant_id=tenant_id,
            user_id=user_id,
            role_id=uuid.UUID(role_config["id"]) if role_config.get("id") else None,
            role_snapshot=role_snapshot,
            compiled_prompt=compiled_prompt,
            compiled_prompt_hash=compiled_prompt_hash,
            structured_input=redacted_structured_input,
            context_variables=context_variables,
            model=model or role_config.get("model") or "unknown",
            temperature=temperature,
            max_tokens=max_tokens,
            messages_sent=redacted_messages,
            raw_response=redacted_raw_response,
            parsed_response=redacted_parsed_response,
            validation_status=validation_status,
            validation_error=validation_error,
            fallback_applied=fallback_applied,
            fallback_details=redacted_fallback_details,
            attempt_number=attempt_number,
            total_attempts=total_attempts,
            duration_ms=duration_ms,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            result_type=result_type,
            result_summary=result_summary,
            error=redacted_error
        )
        
        try:
            return await self.repo.create(trace)
        except Exception as e:
            logger.error(f"Failed to create trace: {e}")
            await self.session.rollback()
            return trace
    
    async def get_trace(self, trace_id: uuid.UUID) -> Optional[SystemLLMTrace]:
        """Get a trace by ID."""
        return await self.repo.get_by_id(trace_id)
    
    async def get_chat_traces(
        self,
        chat_id: str,
        trace_type: Optional[str] = None,
        limit: int = 50
    ) -> List[SystemLLMTrace]:
        """Get traces for a specific chat."""
        return await self.repo.get_by_chat_id(chat_id, trace_type, limit)
    
    async def get_recent_traces(
        self,
        tenant_id: str,
        trace_type: Optional[str] = None,
        limit: int = 50
    ) -> List[SystemLLMTrace]:
        """Get recent traces for a tenant."""
        return await self.repo.get_recent_by_tenant_id(tenant_id, trace_type, limit)
    
    async def get_agent_run_traces(
        self,
        agent_run_id: uuid.UUID,
        trace_type: Optional[str] = None
    ) -> List[SystemLLMTrace]:
        """Get traces for an agent run."""
        return await self.repo.get_by_agent_run_id(agent_run_id, trace_type)
    
    async def get_tenant_traces(
        self,
        tenant_id: uuid.UUID,
        trace_type: Optional[str] = None,
        validation_status: Optional[str] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[SystemLLMTrace]:
        """Get traces for a tenant."""
        return await self.repo.get_by_tenant_id(
            tenant_id, trace_type, validation_status, from_date, to_date, limit, offset
        )
    
    async def count_tenant_traces(
        self,
        tenant_id: uuid.UUID,
        trace_type: Optional[str] = None,
        validation_status: Optional[str] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None
    ) -> int:
        """Count traces for a tenant."""
        return await self.repo.count_by_tenant_id(
            tenant_id, trace_type, validation_status, from_date, to_date
        )
    
    async def delete_trace(self, trace_id: uuid.UUID) -> bool:
        """Delete a trace."""
        return await self.repo.delete_by_id(trace_id)
    
    async def cleanup_old_traces(
        self,
        days: int = 14,
        tenant_id: Optional[uuid.UUID] = None
    ) -> int:
        """Delete traces older than specified days."""
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        
        deleted_count = await self.repo.delete_older_than(cutoff_date, tenant_id)
        
        if deleted_count > 0:
            logger.info(
                f"Cleaned up {deleted_count} system LLM traces older than {days} days"
                f"{' for tenant ' + str(tenant_id) if tenant_id else ''}"
            )
        
        return deleted_count
    
    async def get_trace_statistics(
        self,
        tenant_id: uuid.UUID,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Get trace statistics for a tenant."""
        return await self.repo.get_trace_statistics(tenant_id, from_date, to_date)
    
    async def get_failed_traces(
        self,
        tenant_id: uuid.UUID,
        trace_type: Optional[str] = None,
        hours: int = 24
    ) -> List[SystemLLMTrace]:
        """Get failed traces from the last N hours."""
        return await self.repo.get_failed_traces(tenant_id, trace_type, hours)
    
    async def find_similar_traces(
        self,
        prompt_hash: str,
        tenant_id: uuid.UUID,
        limit: int = 10
    ) -> List[SystemLLMTrace]:
        """Find traces with similar prompts."""
        return await self.repo.get_traces_with_prompt_hash(prompt_hash, tenant_id, limit)
    
    def calculate_prompt_hash(self, prompt: str) -> str:
        """Calculate SHA-256 hash of a prompt."""
        return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]
    
    async def create_trace_from_execution(
        self,
        trace_type: str,
        role_config: Dict[str, Any],
        structured_input: Dict[str, Any],
        messages: List[Dict[str, str]],
        llm_response: str,
        parsed_response: Optional[Dict[str, Any]],
        validation_status: str,
        start_time: float,
        model: str,
        temperature: float,
        max_tokens: int,
        **kwargs
    ) -> SystemLLMTrace:
        """Convenience method to create trace from execution data."""
        
        duration_ms = int((time.time() - start_time) * 1000)
        
        return await self.create_trace(
            trace_type=trace_type,
            role_config=role_config,
            structured_input=structured_input,
            messages_sent=messages,
            raw_response=llm_response,
            parsed_response=parsed_response,
            validation_status=validation_status,
            duration_ms=duration_ms,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )
