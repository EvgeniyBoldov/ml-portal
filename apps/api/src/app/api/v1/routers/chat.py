from __future__ import annotations
from typing import Any, Mapping
from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import StreamingResponse, JSONResponse

from app.api.deps import get_llm_client
from app.core.http.clients import LLMClientProtocol
from app.core.sse import wrap_sse_stream, format_sse
from app.schemas.common import ProblemDetails

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])

@router.post("", response_model=dict)
async def chat(
    body: dict[str, Any],
    llm: LLMClientProtocol = Depends(get_llm_client),
):
    messages: list[Mapping[str, str]] = body.get("messages", [])
    params: dict[str, Any] = body.get("params", {})
    try:
        result = await llm.chat(messages, **params)
        return result
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content=ProblemDetails(title="LLM upstream error", status=502, detail=str(e)).model_dump(),
        )

@router.post("/stream")
async def chat_stream(
    request: Request,
    body: dict[str, Any],
    llm: LLMClientProtocol = Depends(get_llm_client),
):
    messages: list[Mapping[str, str]] = body.get("messages", [])
    params: dict[str, Any] = body.get("params", {})
    async def _gen():
        try:
            upstream = llm.chat_stream(messages, **params)
            async for s in wrap_sse_stream(upstream, heartbeat_sec=15.0):
                # early client disconnect handling
                if await request.is_disconnected():
                    break
                yield s
        except Exception as e:
            yield format_sse({"error": str(e)}, event="error")
    return StreamingResponse(_gen(), media_type="text/event-stream")
