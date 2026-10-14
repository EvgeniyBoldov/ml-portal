"""Merge encoder rankings without comparing scores from different vector spaces."""
from collections import defaultdict
from typing import Any

from app.core.config import get_settings


def fuse_vector_hits(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_model: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for hit in hits:
        by_model[str((hit.get("payload") or {}).get("embed_model_alias") or "")].append(hit)
    fused: dict[tuple, dict[str, Any]] = {}
    scores: dict[tuple, float] = defaultdict(float)
    rank_constant = get_settings().MULTI_EMBEDDING_RRF_K
    for candidates in by_model.values():
        seen: set[tuple] = set()
        rank = 0
        for hit in sorted(candidates, key=lambda item: float(item.get("score") or 0), reverse=True):
            payload = hit.get("payload") or {}
            key = ((payload.get("source_id"), payload["chunk_id"]) if payload.get("chunk_id")
                   else (payload["row_id"], payload.get("field_name"), payload.get("chunk_idx")) if payload.get("row_id")
                   else (hit.get("id"),))
            if key in seen:
                continue
            seen.add(key)
            rank += 1
            fused.setdefault(key, dict(hit))
            scores[key] += 1 / (rank_constant + rank)
    return sorted([{**hit, "score": scores[key]} for key, hit in fused.items()], key=lambda hit: hit["score"], reverse=True)
