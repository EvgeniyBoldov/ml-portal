"""
MCP Audit Service for tracking MCP requests.

Provides async logging of MCP tool calls, prompt requests, and LLM proxy usage.
"""
from __future__ import annotations
import time
import logging
from typing import Any, Dict, Optional
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog

logger = logging.getLogger(__name__)


class MCPAuditService:
    """
    Service for logging MCP requests.
    
    Usage:
        async with audit.log_request("mcp.tools/call", "rag.search") as ctx:
            result = await handler.execute(...)
            ctx.set_response(result)
    """
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def log(
        self,
        action: str,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        resource: Optional[str] = None,
        request_data: Optional[Dict[str, Any]] = None,
        response_status: str = "success",
        response_data: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
        duration_ms: Optional[int] = None,
        tokens_in: Optional[int] = None,
        tokens_out: Optional[int] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> AuditLog:
        """
        Log an MCP request.
        
        Args:
            action: MCP method (e.g., "mcp.tools/call", "mcp.prompts/get")
            user_id: User who made the request
            tenant_id: Tenant context
            resource: Resource accessed (e.g., tool slug, prompt slug)
            request_data: Sanitized request parameters
            response_status: "success" or "error"
            response_data: Sanitized response (truncated if large)
            error_message: Error message if failed
            duration_ms: Request duration in milliseconds
            tokens_in: Input tokens (for LLM proxy)
            tokens_out: Output tokens (for LLM proxy)
            ip_address: Client IP
            user_agent: Client user agent
            request_id: Request correlation ID
        """
        # Sanitize request data (remove sensitive fields)
        if request_data:
            request_data = self._sanitize_data(request_data)
        
        # Truncate large response data
        if response_data:
            response_data = self._truncate_data(response_data)
        
        audit_log = AuditLog(
            user_id=user_id,
            tenant_id=tenant_id,
            action=action,
            resource=resource,
            request_data=request_data,
            response_status=response_status,
            response_data=response_data,
            error_message=error_message,
            duration_ms=duration_ms,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
        )
        
        self.session.add(audit_log)
        await self.session.flush()
        
        logger.debug(
            f"Audit: {action} resource={resource} user={user_id} "
            f"status={response_status} duration={duration_ms}ms"
        )
        
        return audit_log
    
    @asynccontextmanager
    async def log_request(
        self,
        action: str,
        resource: Optional[str] = None,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        request_data: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_id: Optional[str] = None,
    ):
        """
        Context manager for logging requests with automatic timing.
        
        Usage:
            async with audit.log_request("mcp.tools/call", "rag.search") as ctx:
                result = await do_something()
                ctx.set_response({"hits": result})
        """
        ctx = AuditContext(
            service=self,
            action=action,
            resource=resource,
            user_id=user_id,
            tenant_id=tenant_id,
            request_data=request_data,
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
        )
        
        ctx.start()
        try:
            yield ctx
        except Exception as e:
            ctx.set_error(str(e))
            raise
        finally:
            await ctx.finish()
    
    def _sanitize_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Remove sensitive fields from data."""
        sensitive_keys = {"password", "token", "secret", "api_key", "authorization"}
        
        def sanitize(obj):
            if isinstance(obj, dict):
                return {
                    k: "[REDACTED]" if k.lower() in sensitive_keys else sanitize(v)
                    for k, v in obj.items()
                }
            elif isinstance(obj, list):
                return [sanitize(item) for item in obj]
            return obj
        
        return sanitize(data)
    
    def _truncate_data(self, data: Dict[str, Any], max_size: int = 5000) -> Dict[str, Any]:
        """Truncate large data for storage."""
        import json
        
        serialized = json.dumps(data, default=str)
        if len(serialized) <= max_size:
            return data
        
        return {"_truncated": True, "_size": len(serialized), "_preview": serialized[:500]}


class AuditContext:
    """Context for tracking a single request."""
    
    def __init__(
        self,
        service: MCPAuditService,
        action: str,
        resource: Optional[str] = None,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        request_data: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_id: Optional[str] = None,
    ):
        self.service = service
        self.action = action
        self.resource = resource
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.request_data = request_data
        self.ip_address = ip_address
        self.user_agent = user_agent
        self.request_id = request_id
        
        self._start_time: Optional[float] = None
        self._response_data: Optional[Dict[str, Any]] = None
        self._response_status: str = "success"
        self._error_message: Optional[str] = None
        self._tokens_in: Optional[int] = None
        self._tokens_out: Optional[int] = None
    
    def start(self):
        """Start timing the request."""
        self._start_time = time.time()
    
    def set_response(self, data: Dict[str, Any]):
        """Set successful response data."""
        self._response_data = data
        self._response_status = "success"
    
    def set_error(self, message: str):
        """Set error response."""
        self._error_message = message
        self._response_status = "error"
    
    def set_tokens(self, tokens_in: int, tokens_out: int):
        """Set token usage for LLM requests."""
        self._tokens_in = tokens_in
        self._tokens_out = tokens_out
    
    async def finish(self):
        """Finish and log the request."""
        duration_ms = None
        if self._start_time:
            duration_ms = int((time.time() - self._start_time) * 1000)
        
        await self.service.log(
            action=self.action,
            user_id=self.user_id,
            tenant_id=self.tenant_id,
            resource=self.resource,
            request_data=self.request_data,
            response_status=self._response_status,
            response_data=self._response_data,
            error_message=self._error_message,
            duration_ms=duration_ms,
            tokens_in=self._tokens_in,
            tokens_out=self._tokens_out,
            ip_address=self.ip_address,
            user_agent=self.user_agent,
            request_id=self.request_id,
        )
