"""
LLM Proxy for MCP clients.

Provides OpenAI-compatible chat/completions endpoint that proxies to configured LLM.
This allows IDE plugins to use Portal as a unified LLM gateway.
"""
from __future__ import annotations
from app.core.logging import get_logger
import json
from typing import Any, Dict, List, Optional, AsyncGenerator
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, get_current_user, get_llm_client
from app.core.security import UserCtx
from app.core.http.clients import LLMClientProtocol

logger = get_logger(__name__)

router = APIRouter()


class ChatMessage(BaseModel):
    """OpenAI-compatible chat message."""
    role: str
    content: str
    name: Optional[str] = None


class ChatCompletionRequest(BaseModel):
    """OpenAI-compatible chat completion request."""
    model: Optional[str] = None
    messages: List[ChatMessage]
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    stream: Optional[bool] = False
    top_p: Optional[float] = None
    frequency_penalty: Optional[float] = None
    presence_penalty: Optional[float] = None
    stop: Optional[List[str]] = None


class ChatCompletionChoice(BaseModel):
    """OpenAI-compatible choice."""
    index: int = 0
    message: ChatMessage
    finish_reason: Optional[str] = "stop"


class ChatCompletionUsage(BaseModel):
    """Token usage info."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionResponse(BaseModel):
    """OpenAI-compatible chat completion response."""
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[ChatCompletionChoice]
    usage: Optional[ChatCompletionUsage] = None


@router.post("/chat/completions", response_model=None)
async def chat_completions(
    request_body: ChatCompletionRequest,
    request: Request,
    llm: LLMClientProtocol = Depends(get_llm_client),
    current_user: UserCtx = Depends(get_current_user),
) -> StreamingResponse | JSONResponse:
    """
    OpenAI-compatible chat completions endpoint.
    
    Proxies requests to configured LLM provider (Groq, OpenAI, etc.)
    Supports both streaming and non-streaming responses.
    """
    messages = [{"role": m.role, "content": m.content} for m in request_body.messages]
    model = request_body.model
    
    logger.info(
        f"LLM proxy request from user {current_user.id}, "
        f"model={model}, messages={len(messages)}, stream={request_body.stream}"
    )
    
    # Build kwargs for LLM client
    kwargs: Dict[str, Any] = {}
    if request_body.temperature is not None:
        kwargs["temperature"] = request_body.temperature
    if request_body.max_tokens is not None:
        kwargs["max_tokens"] = request_body.max_tokens
    if request_body.top_p is not None:
        kwargs["top_p"] = request_body.top_p
    
    if request_body.stream:
        return await _stream_response(llm, messages, model, kwargs)
    else:
        return await _sync_response(llm, messages, model, kwargs)


async def _sync_response(
    llm: LLMClientProtocol,
    messages: List[Dict[str, Any]],
    model: Optional[str],
    kwargs: Dict[str, Any],
) -> JSONResponse:
    """Non-streaming response."""
    import time
    import uuid
    
    try:
        result = await llm.chat(messages, model=model, **kwargs)
        
        # Extract content from result
        if isinstance(result, dict):
            choices = result.get("choices", [])
            if choices:
                content = choices[0].get("message", {}).get("content", "")
            else:
                content = result.get("content", str(result))
        else:
            content = str(result)
        
        response = ChatCompletionResponse(
            id=f"chatcmpl-{uuid.uuid4().hex[:8]}",
            created=int(time.time()),
            model=model or "default",
            choices=[
                ChatCompletionChoice(
                    index=0,
                    message=ChatMessage(role="assistant", content=content),
                    finish_reason="stop",
                )
            ],
        )
        
        return JSONResponse(content=response.model_dump())
        
    except Exception as e:
        logger.error(f"LLM proxy error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


async def _stream_response(
    llm: LLMClientProtocol,
    messages: List[Dict[str, Any]],
    model: Optional[str],
    kwargs: Dict[str, Any],
) -> StreamingResponse:
    """Streaming response in OpenAI SSE format."""
    import time
    import uuid
    
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:8]}"
    created = int(time.time())
    
    async def generate() -> AsyncGenerator[str, None]:
        try:
            async for chunk in llm.chat_stream(messages, model=model, **kwargs):
                if chunk:
                    # Format as OpenAI SSE
                    data = {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": model or "default",
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"content": chunk},
                                "finish_reason": None,
                            }
                        ],
                    }
                    yield f"data: {json.dumps(data)}\n\n"
            
            # Send final chunk with finish_reason
            final_data = {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model or "default",
                "choices": [
                    {
                        "index": 0,
                        "delta": {},
                        "finish_reason": "stop",
                    }
                ],
            }
            yield f"data: {json.dumps(final_data)}\n\n"
            yield "data: [DONE]\n\n"
            
        except Exception as e:
            logger.error(f"LLM streaming error: {e}", exc_info=True)
            error_data = {"error": {"message": str(e), "type": "server_error"}}
            yield f"data: {json.dumps(error_data)}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/models")
async def list_models(
    current_user: UserCtx = Depends(get_current_user),
) -> JSONResponse:
    """
    List available LLM models.
    
    Returns OpenAI-compatible model list.
    """
    from app.core.config import get_settings
    settings = get_settings()
    
    # Return models based on provider
    models = []
    if settings.LLM_PROVIDER == "groq":
        models = [
            {"id": "llama-3.1-8b-instant", "object": "model", "owned_by": "groq"},
            {"id": "llama-3.1-70b-versatile", "object": "model", "owned_by": "groq"},
            {"id": "mixtral-8x7b-32768", "object": "model", "owned_by": "groq"},
        ]
    elif settings.LLM_PROVIDER == "openai":
        models = [
            {"id": "gpt-4-turbo-preview", "object": "model", "owned_by": "openai"},
            {"id": "gpt-3.5-turbo", "object": "model", "owned_by": "openai"},
        ]
    else:
        models = [
            {"id": "default", "object": "model", "owned_by": settings.LLM_PROVIDER},
        ]
    
    return JSONResponse(content={"object": "list", "data": models})
