from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.model_registry import ModelRegistry, ModelStatus, ModelType
from app.repositories.model_registry_repo import AsyncModelRegistryRepository

logger = get_logger(__name__)


class RerankClientError(RuntimeError):
    """Raised when rerank service is unavailable or returns invalid data."""


@dataclass(frozen=True)
class RerankScoredIndex:
    index: int
    score: float


def _resolve_rerank_base_url(
    model: Optional[ModelRegistry],
    fallback_url: Optional[str],
) -> Optional[str]:
    if model:
        if model.base_url:
            return model.base_url
        if model.instance and model.instance.url:
            return model.instance.url
        if isinstance(model.extra_config, dict):
            extra_base_url = model.extra_config.get("base_url")
            if extra_base_url:
                return str(extra_base_url)
    if fallback_url:
        return fallback_url
    return None


def _build_rerank_candidate_urls(
    model: Optional[ModelRegistry],
    fallback_url: Optional[str],
) -> List[str]:
    primary = _resolve_rerank_base_url(model, fallback_url)
    candidates: List[str] = []
    if primary:
        candidates.append(primary)
        if "://reranker:" in primary:
            candidates.append(primary.replace("://reranker:", "://rerank:"))
    if fallback_url:
        candidates.append(fallback_url)

    deduped: List[str] = []
    for url in candidates:
        if url and url not in deduped:
            deduped.append(url)
    return deduped


async def _resolve_active_rerank_model(session: AsyncSession) -> Optional[ModelRegistry]:
    repo = AsyncModelRegistryRepository(session)
    model = await repo.get_global_by_type(ModelType.RERANKER)
    if not model:
        return None
    if not model.enabled or model.status != ModelStatus.AVAILABLE:
        return None
    return model


async def rerank_scores(
    *,
    session: AsyncSession,
    query: str,
    documents: Sequence[str],
    top_k: int,
) -> List[RerankScoredIndex]:
    if not documents:
        return []

    settings = get_settings()
    if not settings.RERANK_ENABLED:
        raise RerankClientError("Rerank is disabled by configuration")

    model = await _resolve_active_rerank_model(session)
    base_urls = _build_rerank_candidate_urls(model, settings.RERANK_SERVICE_URL)
    if not base_urls:
        raise RerankClientError("Rerank base URL is not configured")

    capped_top_k = max(1, min(int(top_k), len(documents)))
    payload = {
        "query": query,
        "documents": list(documents),
        "top_k": capped_top_k,
    }
    timeout_seconds = max(5, int(settings.HTTP_TIMEOUT_SECONDS))

    payload_data = None
    errors: List[str] = []
    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        for base_url in base_urls:
            url = f"{base_url.rstrip('/')}/rerank"
            try:
                response = await client.post(url, json=payload)
            except Exception as exc:
                errors.append(f"{url} -> connection error: {exc}")
                continue
            if response.status_code != 200:
                errors.append(f"{url} -> HTTP {response.status_code}: {response.text[:200]}")
                continue
            try:
                payload_data = response.json()
                break
            except Exception as exc:
                errors.append(f"{url} -> invalid JSON: {exc}")

    if payload_data is None:
        raise RerankClientError(
            "Failed to call rerank service. Attempts: " + " | ".join(errors)
        )

    results_raw = payload_data.get("results", [])
    scored: List[RerankScoredIndex] = []
    for item in results_raw:
        try:
            index = int(item.get("index"))
            score = float(item.get("score"))
        except (TypeError, ValueError):
            continue
        if index < 0 or index >= len(documents):
            continue
        scored.append(RerankScoredIndex(index=index, score=score))

    if not scored:
        raise RerankClientError("Rerank service returned no valid scores")

    scored.sort(key=lambda item: item.score, reverse=True)
    return scored


def apply_rerank_to_items(
    items: Sequence[Dict[str, Any]],
    reranked: Sequence[RerankScoredIndex],
    *,
    score_field: str = "score",
) -> List[Dict[str, Any]]:
    if not items:
        return []
    if not reranked:
        return [dict(item) for item in items]

    ordered: List[Dict[str, Any]] = []
    used_indexes = set()

    for ranked in reranked:
        if ranked.index < 0 or ranked.index >= len(items):
            continue
        item_copy = dict(items[ranked.index])
        item_copy[score_field] = ranked.score
        ordered.append(item_copy)
        used_indexes.add(ranked.index)

    for idx, item in enumerate(items):
        if idx in used_indexes:
            continue
        ordered.append(dict(item))

    return ordered
