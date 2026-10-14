"""
MCP Router - JSON-RPC 2.0 over HTTP.

Single endpoint that handles all MCP methods via JSON-RPC dispatch.
Supports Streamable HTTP transport as per MCP spec.
"""
from __future__ import annotations
from app.core.logging import get_logger
import uuid
from typing import Any, Dict, Optional, Union
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import ValidationError

from app.api.deps import db_session, get_bearer_user, resolve_active_user_tenant_ids
from app.api.mcp.schemas import (
    JSONRPCRequest,
    JSONRPCResponse,
    JSONRPCError,
    MCPErrorCode,
)
from app.api.mcp.handlers import MCPHandlers, MCPError
from app.core.security import UserCtx
from app.services.mcp_audit_service import MCPAuditService

logger = get_logger(__name__)

router = APIRouter(prefix="/mcp", tags=["mcp"])

# Method dispatch table
MCP_METHODS = {
    "initialize": "handle_initialize",
    "initialized": None,  # Notification, no response
    "ping": "handle_ping",
    "tools/list": "handle_tools_list",
    "tools/call": "handle_tools_call",
    "prompts/list": "handle_prompts_list",
    "prompts/get": "handle_prompts_get",
}

def make_error_response(
    request_id: Union[str, int, None],
    code: MCPErrorCode,
    message: str,
    data: Any = None,
) -> JSONRPCResponse:
    """Create a JSON-RPC error response."""
    return JSONRPCResponse(
        id=request_id,
        error=JSONRPCError(code=code.value, message=message, data=data),
    )


def make_success_response(
    request_id: Union[str, int],
    result: Any,
) -> JSONRPCResponse:
    """Create a JSON-RPC success response."""
    # Convert Pydantic models to dict
    if hasattr(result, "model_dump"):
        result = result.model_dump(exclude_none=True)
    return JSONRPCResponse(id=request_id, result=result)


@router.post("")
async def mcp_endpoint(
    request: Request,
    session: AsyncSession = Depends(db_session),
    current_user: UserCtx = Depends(get_bearer_user),
) -> JSONResponse:
    """
    MCP JSON-RPC 2.0 endpoint.
    
    Accepts JSON-RPC requests and dispatches to appropriate handlers.
    Requires a JWT access token or personal API token in Authorization: Bearer.
    """
    # Parse request body
    try:
        body = await request.json()
    except Exception as e:
        logger.warning(f"Failed to parse JSON: {e}")
        response = make_error_response(
            None,
            MCPErrorCode.PARSE_ERROR,
            f"Parse error: {e}",
        )
        return JSONResponse(
            content=response.model_dump(exclude_none=True),
            status_code=200,  # JSON-RPC always returns 200
        )
    
    # Validate JSON-RPC structure
    try:
        rpc_request = JSONRPCRequest(**body)
    except ValidationError as e:
        logger.warning(f"Invalid JSON-RPC request: {e}")
        response = make_error_response(
            body.get("id") if isinstance(body, dict) else None,
            MCPErrorCode.INVALID_REQUEST,
            "Invalid Request",
            str(e),
        )
        return JSONResponse(
            content=response.model_dump(exclude_none=True),
            status_code=200,
        )
    
    # Check if method exists
    if rpc_request.method not in MCP_METHODS:
        logger.warning(f"Unknown method: {rpc_request.method}")
        response = make_error_response(
            rpc_request.id,
            MCPErrorCode.METHOD_NOT_FOUND,
            f"Method not found: {rpc_request.method}",
        )
        return JSONResponse(
            content=response.model_dump(exclude_none=True),
            status_code=200,
        )
    
    handler_name = MCP_METHODS[rpc_request.method]
    
    # Handle notifications (no response expected)
    if handler_name is None:
        return JSONResponse(content={}, status_code=204)
    
    tenant_ids = await resolve_active_user_tenant_ids(session, current_user)
    if not tenant_ids:
        raise HTTPException(403, "An active tenant membership is required")
    tenant_id = str(tenant_ids[0])
    user_id = str(current_user.id)

    # Create handlers and audit service
    handlers = MCPHandlers(session, tenant_id, user_id)
    audit = MCPAuditService(session)
    
    # Extract resource from params for audit
    resource = None
    if rpc_request.params:
        resource = rpc_request.params.get("name") or rpc_request.params.get("slug")
    
    # Get request metadata for audit
    request_id = str(uuid.uuid4())
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent", "")[:500]
    
    # Dispatch to handler with audit logging
    async with audit.log_request(
        action=f"mcp.{rpc_request.method}",
        resource=resource,
        user_id=user_id,
        tenant_id=tenant_id,
        request_data=rpc_request.params,
        ip_address=ip_address,
        user_agent=user_agent,
        request_id=request_id,
    ) as audit_ctx:
        try:
            handler_method = getattr(handlers, handler_name)
            result = await handler_method(rpc_request.params or {})
            
            # Log response to audit
            if hasattr(result, "model_dump"):
                audit_ctx.set_response(result.model_dump(exclude_none=True))
            else:
                audit_ctx.set_response({"result": "ok"})
            
            response = make_success_response(rpc_request.id, result)
            
            logger.info(f"MCP {rpc_request.method} completed successfully")
            
        except MCPError as e:
            logger.warning(f"MCP error: {e.message}")
            audit_ctx.set_error(e.message)
            response = JSONRPCResponse(
                id=rpc_request.id,
                error=e.to_jsonrpc_error(),
            )
        except Exception as e:
            logger.error(f"Internal error handling {rpc_request.method}: {e}", exc_info=True)
            audit_ctx.set_error(str(e))
            response = make_error_response(
                rpc_request.id,
                MCPErrorCode.INTERNAL_ERROR,
                f"Internal error: {str(e)}",
            )
    
    return JSONResponse(
        content=response.model_dump(exclude_none=True),
        status_code=200,
    )


@router.get("")
async def mcp_sse_endpoint(request: Request) -> JSONResponse:
    """
    MCP SSE endpoint for server-initiated messages.
    
    Currently returns 501 Not Implemented as we don't support
    server-initiated notifications yet.
    """
    return JSONResponse(
        content={"error": "SSE not implemented"},
        status_code=501,
    )
