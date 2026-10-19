"""Read bounded pages from the current authorized chat, never the run journal."""
from __future__ import annotations

import uuid
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from app.agents.context import ToolContext, ToolResult
from app.agents.handlers.versioned_tool import VersionedTool, register_tool, tool_version
from app.services.chat_history_service import ChatHistoryService


class ChatHistoryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    before_message_id: uuid.UUID | None = None
    limit: int = Field(default=20, ge=1, le=100)


@register_tool
class ChatHistoryReadTool(VersionedTool):
    tool_slug: ClassVar[str] = "chat.history.read"
    domains: ClassVar[list] = ["system"]
    name: ClassVar[str] = "Read Chat History"
    description: ClassVar[str] = "Read a bounded older page from the current chat using before_message_id."

    @tool_version(version="1.0.0", input_schema=ChatHistoryInput.model_json_schema(),
                  output_schema={"type": "object"}, description=description)
    async def v1_0_0(self, ctx: ToolContext, args: dict) -> ToolResult:
        from app.core.db import get_session_factory
        if not ctx.chat_id or not ctx.user_id:
            return ToolResult.fail("Chat history requires the current chat and user")
        # Sandbox branch history comes from its frozen context/checkpoint, not a shared hidden chat.
        if ctx.extra.get("runtime_branch_id") or ctx.extra.get("sandbox_branch_id") or (ctx.get_runtime_deps().sandbox_overrides or {}).get("sandbox_branch_id"):
            return ToolResult.fail("Use the frozen branch history supplied in the run context")
        request = ChatHistoryInput.model_validate(args)
        async with get_session_factory()() as session:
            try:
                return ToolResult.ok(await ChatHistoryService(session).read(
                    chat_id=str(ctx.chat_id), owner_id=str(ctx.user_id),
                    before_message_id=request.before_message_id, limit=request.limit), delivery="direct")
            except ValueError as exc:
                return ToolResult.fail(str(exc))
