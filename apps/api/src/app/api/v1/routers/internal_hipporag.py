"""Capability-authenticated model callbacks; no user or registry secrets leave the API."""
from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session
from app.adapters.embeddings import EmbeddingServiceFactory
from app.adapters.interfaces.llm import LLMCallOptions
from app.core.di import get_llm_client
from app.core.redis import get_redis
from app.services.embedding_model_config_service import EmbeddingModelConfigService

router = APIRouter(prefix="/internal/hipporag", tags=["internal-hipporag"])


async def capability(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing HippoRAG capability")
    key = "hipporag:capability:" + hashlib.sha256(authorization[7:].encode()).hexdigest()
    value = await get_redis().get(key)
    if value is None:
        raise HTTPException(401, "Expired HippoRAG capability")
    return json.loads(value)


class ChatRequest(BaseModel):
    messages: list[dict[str, str]] = Field(min_length=1, max_length=40)
    max_tokens: int = Field(default=1536, ge=1, le=4096)
    response_format: dict[str, Any] | None = None


class EmbedRequest(BaseModel):
    texts: list[str] = Field(min_length=1, max_length=32)


@router.post("/chat")
async def chat(body: ChatRequest, models: dict[str, Any] = Depends(capability)):
    params: dict[str, Any] = {"temperature": 0}
    if models.get("qwen"):
        params["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}
    if body.response_format:
        params["response_format"] = body.response_format
    return await get_llm_client().chat(body.messages, model=models["llm_alias"], params=params,
                                      options=LLMCallOptions(output_token_cap=body.max_tokens, timeout_s=180))


@router.post("/embed")
async def embed(body: EmbedRequest, models: dict[str, Any] = Depends(capability),
                session: AsyncSession = Depends(db_session)):
    await EmbeddingModelConfigService.ensure_registered(session, models["embedding_alias"])
    service = EmbeddingServiceFactory.get_service(models["embedding_alias"])
    return {"vectors": await asyncio.to_thread(service.embed_texts, body.texts)}
