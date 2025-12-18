"""
MCP JSON-RPC 2.0 schemas.

Based on: https://modelcontextprotocol.io/specification/2025-06-18
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field
from enum import Enum


# =============================================================================
# JSON-RPC 2.0 Base Types
# =============================================================================

class JSONRPCRequest(BaseModel):
    """JSON-RPC 2.0 request."""
    jsonrpc: str = "2.0"
    id: Union[str, int]
    method: str
    params: Optional[Dict[str, Any]] = None


class JSONRPCNotification(BaseModel):
    """JSON-RPC 2.0 notification (no id, no response expected)."""
    jsonrpc: str = "2.0"
    method: str
    params: Optional[Dict[str, Any]] = None


class JSONRPCError(BaseModel):
    """JSON-RPC 2.0 error object."""
    code: int
    message: str
    data: Optional[Any] = None


class JSONRPCResponse(BaseModel):
    """JSON-RPC 2.0 response."""
    jsonrpc: str = "2.0"
    id: Union[str, int, None]
    result: Optional[Any] = None
    error: Optional[JSONRPCError] = None


# =============================================================================
# MCP Error Codes (JSON-RPC standard + MCP specific)
# =============================================================================

class MCPErrorCode(int, Enum):
    # JSON-RPC standard errors
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603
    
    # MCP specific errors (-32000 to -32099)
    NOT_INITIALIZED = -32002
    ALREADY_INITIALIZED = -32003
    RESOURCE_NOT_FOUND = -32004
    TOOL_NOT_FOUND = -32005
    PROMPT_NOT_FOUND = -32006


# =============================================================================
# MCP Initialize
# =============================================================================

class Implementation(BaseModel):
    """Server/Client implementation info."""
    name: str
    version: str


class ServerCapabilities(BaseModel):
    """Server capabilities advertised during initialization."""
    tools: Optional[Dict[str, Any]] = Field(default_factory=dict)
    prompts: Optional[Dict[str, Any]] = Field(default_factory=dict)
    resources: Optional[Dict[str, Any]] = None
    logging: Optional[Dict[str, Any]] = None


class ClientCapabilities(BaseModel):
    """Client capabilities sent during initialization."""
    roots: Optional[Dict[str, Any]] = None
    sampling: Optional[Dict[str, Any]] = None
    experimental: Optional[Dict[str, Any]] = None


class InitializeParams(BaseModel):
    """Parameters for initialize request."""
    protocolVersion: str
    capabilities: ClientCapabilities = Field(default_factory=ClientCapabilities)
    clientInfo: Implementation


class InitializeResult(BaseModel):
    """Result of initialize request."""
    protocolVersion: str
    capabilities: ServerCapabilities
    serverInfo: Implementation
    instructions: Optional[str] = None


# =============================================================================
# MCP Tools
# =============================================================================

class ToolInputSchema(BaseModel):
    """JSON Schema for tool input."""
    type: str = "object"
    properties: Optional[Dict[str, Any]] = Field(default_factory=dict)
    required: Optional[List[str]] = Field(default_factory=list)


class ToolAnnotations(BaseModel):
    """Optional tool annotations."""
    title: Optional[str] = None
    readOnlyHint: Optional[bool] = None
    destructiveHint: Optional[bool] = None
    idempotentHint: Optional[bool] = None
    openWorldHint: Optional[bool] = None


class MCPTool(BaseModel):
    """Tool definition for MCP."""
    name: str
    description: Optional[str] = None
    inputSchema: ToolInputSchema
    outputSchema: Optional[Dict[str, Any]] = None
    annotations: Optional[ToolAnnotations] = None


class ListToolsResult(BaseModel):
    """Result of tools/list request."""
    tools: List[MCPTool]
    nextCursor: Optional[str] = None


class CallToolParams(BaseModel):
    """Parameters for tools/call request."""
    name: str
    arguments: Optional[Dict[str, Any]] = Field(default_factory=dict)


class TextContent(BaseModel):
    """Text content block."""
    type: str = "text"
    text: str


class CallToolResult(BaseModel):
    """Result of tools/call request."""
    content: List[TextContent]
    isError: Optional[bool] = None
    structuredContent: Optional[Dict[str, Any]] = None


# =============================================================================
# MCP Prompts
# =============================================================================

class PromptArgument(BaseModel):
    """Argument definition for a prompt."""
    name: str
    description: Optional[str] = None
    required: Optional[bool] = False


class MCPPrompt(BaseModel):
    """Prompt definition for MCP."""
    name: str
    description: Optional[str] = None
    arguments: Optional[List[PromptArgument]] = Field(default_factory=list)


class ListPromptsResult(BaseModel):
    """Result of prompts/list request."""
    prompts: List[MCPPrompt]
    nextCursor: Optional[str] = None


class GetPromptParams(BaseModel):
    """Parameters for prompts/get request."""
    name: str
    arguments: Optional[Dict[str, str]] = Field(default_factory=dict)


class PromptMessage(BaseModel):
    """Message in a prompt."""
    role: str  # "user" | "assistant"
    content: TextContent


class GetPromptResult(BaseModel):
    """Result of prompts/get request."""
    description: Optional[str] = None
    messages: List[PromptMessage]


# =============================================================================
# MCP Resources (for RAG)
# =============================================================================

class MCPResource(BaseModel):
    """Resource definition for MCP."""
    uri: str
    name: str
    description: Optional[str] = None
    mimeType: Optional[str] = None


class ListResourcesResult(BaseModel):
    """Result of resources/list request."""
    resources: List[MCPResource]
    nextCursor: Optional[str] = None


class ReadResourceParams(BaseModel):
    """Parameters for resources/read request."""
    uri: str


class ResourceContents(BaseModel):
    """Resource contents."""
    uri: str
    mimeType: Optional[str] = None
    text: Optional[str] = None


class ReadResourceResult(BaseModel):
    """Result of resources/read request."""
    contents: List[ResourceContents]


# =============================================================================
# Pagination
# =============================================================================

class PaginatedParams(BaseModel):
    """Pagination parameters."""
    cursor: Optional[str] = None
