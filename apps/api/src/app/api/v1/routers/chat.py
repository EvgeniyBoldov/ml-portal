from typing import AsyncGenerator, Dict, Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from app.core.sse import format_sse, wrap_sse_stream
from app.core.sse_protocol import EVENT_DONE
from app.api.deps import get_llm_client
from app.core.http.clients import LLMClientProtocol

router = APIRouter(tags=["chat"])

@router.post("/stream")
async def chat_stream(
    payload: Dict[str, Any],
    llm: LLMClientProtocol = Depends(get_llm_client),
) -> StreamingResponse:
    """Server-Sent Events streaming chat endpoint.

    Fix: do **not** emit a second `done` event — `wrap_sse_stream` already sends it.
    """
    messages: List[Dict[str, Any]] = payload.get("messages", [])
    params: Dict[str, Any] = payload.get("params", {})
    model: Optional[str] = payload.get("model")

    async def _gen() -> AsyncGenerator[str, None]:
        async for chunk in wrap_sse_stream(llm.chat_stream(messages, model=model, **params)):
            yield chunk
        # DO NOT yield EVENT_DONE here; wrap_sse_stream already does that.
    return StreamingResponse(_gen(), media_type="text/event-stream")

@router.post("")
async def chat(
    payload: Dict[str, Any],
    llm: LLMClientProtocol = Depends(get_llm_client),
) -> JSONResponse:
    messages: List[Dict[str, Any]] = payload.get("messages", [])
    params: Dict[str, Any] = payload.get("params", {})
    model: Optional[str] = payload.get("model")
    try:
        result = await llm.chat(messages, model=model, **params)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return JSONResponse(result)
