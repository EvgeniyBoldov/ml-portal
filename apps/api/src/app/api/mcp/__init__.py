"""
MCP (Model Context Protocol) API module.

Implements JSON-RPC 2.0 over HTTP for IDE integration.
Spec: https://modelcontextprotocol.io/specification/2025-06-18
"""
from fastapi import APIRouter
from app.api.mcp.router import router as mcp_router
from app.api.mcp.llm_proxy import router as llm_router

# Combine MCP JSON-RPC router with LLM proxy
# Note: prefix="/mcp" is already in mcp_router, llm_router has no prefix
router = APIRouter(tags=["mcp"])
router.include_router(mcp_router)
router.include_router(llm_router, prefix="/mcp")

__all__ = ["router"]
