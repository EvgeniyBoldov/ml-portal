"""ResolvingLLMClient — single choke-point that translates internal model
aliases (slugs) into provider-native `model` names before calling the LLM.

Rationale:
    * In the DB, models are stored by stable alias/slug (e.g.
      `llm.chat.groq.llama4`).
    * Providers (OpenAI, Groq, etc.) accept only their own model names
      (e.g. `meta-llama/llama-4-maverick-17b-128e-instruct`).
    * We had multiple call sites (synthesizer, planner, triage, agent
      runtime, chat_title, health) and only one of them (`SystemLLMExecutor`)
      remembered to call `ModelResolver`. The others shipped slugs straight
      to the provider and got 404 / 400 / "model not found".

This wrapper fixes it once for everyone: it decorates any `LLMClientProtocol`
and resolves `model` on each call via `ModelResolver` (which has its own
5-minute in-memory cache, so the DB is touched at most once per alias).
"""
from __future__ import annotations

from typing import Any, AsyncIterator, Mapping, Optional

from app.core.logging import get_logger

from .clients import LLMClientProtocol

logger = get_logger(__name__)


class ResolvingLLMClient:
    """Decorator around an `LLMClientProtocol` that resolves model aliases."""

    def __init__(self, inner: LLMClientProtocol) -> None:
        self._inner = inner

    async def _resolve(self, model: Optional[str]) -> Optional[str]:
        if not model:
            return model
        # Lazy import to avoid a circular import at module load time.
        from app.core.db import get_session_factory
        from app.services.model_resolver import ModelResolver

        try:
            session_factory = get_session_factory()
        except Exception:
            # DB not initialized yet (e.g. early health probe). Pass through.
            return model

        try:
            async with session_factory() as session:
                resolver = ModelResolver(session)
                resolved = await resolver.resolve(model)
                if resolved and resolved != model:
                    logger.debug("LLM model alias %r → %r", model, resolved)
                return resolved or model
        except Exception as exc:
            # Never break an LLM call because of resolver issues; log and
            # fall back to the original value.
            logger.warning("Model alias resolution failed for %r: %s", model, exc)
            return model

    async def chat(
        self,
        messages: list[Mapping[str, str]],
        *,
        model: Optional[str] = None,
        params: Optional[dict] = None,
    ) -> dict:
        resolved = await self._resolve(model)
        return await self._inner.chat(messages, model=resolved, params=params)

    async def chat_stream(
        self,
        messages: list[Mapping[str, str]],
        *,
        model: Optional[str] = None,
        params: Optional[dict] = None,
    ) -> AsyncIterator[str]:
        resolved = await self._resolve(model)
        async for chunk in self._inner.chat_stream(messages, model=resolved, params=params):
            yield chunk

    # Proxy everything else (aclose, health_check, etc.) to the inner client.
    def __getattr__(self, item: str) -> Any:  # pragma: no cover - thin passthrough
        return getattr(self._inner, item)
