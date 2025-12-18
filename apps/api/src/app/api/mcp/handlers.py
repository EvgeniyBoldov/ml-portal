"""
MCP method handlers.

Each handler implements a specific MCP method (initialize, tools/list, etc.)
"""
from __future__ import annotations
import json
from app.core.logging import get_logger
from typing import Any, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.mcp.schemas import (
    MCPErrorCode,
    JSONRPCError,
    # Initialize
    InitializeParams,
    InitializeResult,
    Implementation,
    ServerCapabilities,
    # Tools
    ListToolsResult,
    MCPTool,
    ToolInputSchema,
    CallToolParams,
    CallToolResult,
    TextContent,
    # Prompts
    ListPromptsResult,
    MCPPrompt,
    PromptArgument,
    GetPromptParams,
    GetPromptResult,
    PromptMessage,
)
from app.agents.registry import ToolRegistry
from app.agents.context import ToolContext
from app.repositories.prompt_repository import PromptRepository

logger = get_logger(__name__)

# Protocol version we support
PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "ml-portal"
SERVER_VERSION = "1.0.0"


class MCPHandlers:
    """
    MCP method handlers.
    
    Stateless handlers that process MCP requests.
    Each method returns either a result dict or raises an error.
    """
    
    def __init__(self, session: AsyncSession, tenant_id: str, user_id: str):
        self.session = session
        self.tenant_id = tenant_id
        self.user_id = user_id
        self._initialized = False
    
    async def handle_initialize(self, params: Dict[str, Any]) -> InitializeResult:
        """
        Handle initialize request.
        
        Client sends capabilities, we respond with our capabilities.
        """
        try:
            init_params = InitializeParams(**params)
        except Exception as e:
            logger.warning(f"Invalid initialize params: {e}")
            raise MCPError(MCPErrorCode.INVALID_PARAMS, f"Invalid params: {e}")
        
        logger.info(
            f"MCP initialize from {init_params.clientInfo.name} "
            f"v{init_params.clientInfo.version}, "
            f"protocol {init_params.protocolVersion}"
        )
        
        self._initialized = True
        
        return InitializeResult(
            protocolVersion=PROTOCOL_VERSION,
            capabilities=ServerCapabilities(
                tools={"listChanged": False},
                prompts={"listChanged": False},
                resources=None,  # RAG resources could be added later
                logging={"levels": ["debug", "info", "warning", "error"]},
            ),
            serverInfo=Implementation(
                name=SERVER_NAME,
                version=SERVER_VERSION,
            ),
            instructions=(
                "ML Portal MCP Server. Provides access to company knowledge base (RAG), "
                "system prompts, and remote tools like NetBox, Jira integrations."
            ),
        )
    
    async def handle_tools_list(self, params: Optional[Dict[str, Any]] = None) -> ListToolsResult:
        """
        Handle tools/list request.
        
        Returns all registered tools from ToolRegistry.
        """
        handlers = ToolRegistry.list_all()
        
        tools = []
        for handler in handlers:
            tool = MCPTool(
                name=handler.slug,
                description=handler.description,
                inputSchema=ToolInputSchema(
                    type="object",
                    properties=handler.input_schema.get("properties", {}),
                    required=handler.input_schema.get("required", []),
                ),
                outputSchema=handler.output_schema,
            )
            tools.append(tool)
        
        logger.info(f"tools/list: returning {len(tools)} tools")
        return ListToolsResult(tools=tools)
    
    async def handle_tools_call(self, params: Dict[str, Any]) -> CallToolResult:
        """
        Handle tools/call request.
        
        Executes a tool and returns the result.
        """
        try:
            call_params = CallToolParams(**params)
        except Exception as e:
            raise MCPError(MCPErrorCode.INVALID_PARAMS, f"Invalid params: {e}")
        
        handler = ToolRegistry.get(call_params.name)
        if not handler:
            raise MCPError(
                MCPErrorCode.TOOL_NOT_FOUND,
                f"Tool '{call_params.name}' not found"
            )
        
        # Create tool context
        ctx = ToolContext(
            tenant_id=self.tenant_id,
            user_id=self.user_id,
        )
        
        # Validate arguments
        validation_error = handler.validate_args(call_params.arguments or {})
        if validation_error:
            raise MCPError(MCPErrorCode.INVALID_PARAMS, validation_error)
        
        logger.info(f"tools/call: executing {call_params.name}")
        
        try:
            result = await handler.execute(ctx, call_params.arguments or {})
        except Exception as e:
            logger.error(f"Tool execution failed: {e}", exc_info=True)
            return CallToolResult(
                content=[TextContent(type="text", text=f"Error: {str(e)}")],
                isError=True,
            )
        
        if result.success:
            # Format result as text for LLM consumption
            if isinstance(result.data, dict):
                text = json.dumps(result.data, ensure_ascii=False, indent=2)
            else:
                text = str(result.data)
            
            return CallToolResult(
                content=[TextContent(type="text", text=text)],
                isError=False,
                structuredContent=result.data,
            )
        else:
            return CallToolResult(
                content=[TextContent(type="text", text=f"Error: {result.error}")],
                isError=True,
            )
    
    async def handle_prompts_list(self, params: Optional[Dict[str, Any]] = None) -> ListPromptsResult:
        """
        Handle prompts/list request.
        
        Returns all active prompts from database.
        """
        repo = PromptRepository(self.session)
        prompts_list, _ = await repo.list_prompts(limit=100)
        
        prompts = []
        for prompt in prompts_list:
            if not prompt.is_active:
                continue
            
            # Convert input_variables to PromptArguments
            arguments = []
            for var in (prompt.input_variables or []):
                arguments.append(PromptArgument(
                    name=var,
                    description=f"Variable: {var}",
                    required=True,
                ))
            
            prompts.append(MCPPrompt(
                name=prompt.slug,
                description=prompt.description or prompt.name,
                arguments=arguments,
            ))
        
        logger.info(f"prompts/list: returning {len(prompts)} prompts")
        return ListPromptsResult(prompts=prompts)
    
    async def handle_prompts_get(self, params: Dict[str, Any]) -> GetPromptResult:
        """
        Handle prompts/get request.
        
        Returns a specific prompt with variables substituted.
        """
        try:
            get_params = GetPromptParams(**params)
        except Exception as e:
            raise MCPError(MCPErrorCode.INVALID_PARAMS, f"Invalid params: {e}")
        
        repo = PromptRepository(self.session)
        prompt = await repo.get_by_slug(get_params.name)
        
        if not prompt:
            raise MCPError(
                MCPErrorCode.PROMPT_NOT_FOUND,
                f"Prompt '{get_params.name}' not found"
            )
        
        # Render template with provided arguments
        template = prompt.template
        if get_params.arguments:
            try:
                import jinja2
                env = jinja2.Environment(
                    loader=jinja2.BaseLoader(),
                    autoescape=False,
                    undefined=jinja2.Undefined,  # Don't fail on missing vars
                )
                rendered = env.from_string(template).render(**get_params.arguments)
                template = rendered
            except Exception as e:
                logger.warning(f"Template rendering failed: {e}")
                # Return raw template if rendering fails
        
        logger.info(f"prompts/get: returning prompt '{get_params.name}'")
        
        return GetPromptResult(
            description=prompt.description,
            messages=[
                PromptMessage(
                    role="user",
                    content=TextContent(type="text", text=template),
                )
            ],
        )
    
    async def handle_ping(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Handle ping request."""
        return {}


class MCPError(Exception):
    """MCP error that will be converted to JSON-RPC error."""
    
    def __init__(self, code: MCPErrorCode, message: str, data: Any = None):
        self.code = code
        self.message = message
        self.data = data
        super().__init__(message)
    
    def to_jsonrpc_error(self) -> JSONRPCError:
        return JSONRPCError(
            code=self.code.value,
            message=self.message,
            data=self.data,
        )
