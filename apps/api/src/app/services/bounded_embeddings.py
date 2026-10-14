"""Apply the selected encoder's input limit without losing a text's suffix."""
from __future__ import annotations

import math

from app.adapters.embeddings import validate_embedding_batch
from app.adapters.interfaces.embeddings import EmbeddingInterface
from app.core.config import get_settings

INPUT_POLICY_VERSION = "utf8-segment-mean-v1"


def split_embedding_text(text: str, max_tokens: int) -> list[str]:
    reserve = get_settings().EMB_INPUT_TOKEN_RESERVE
    if max_tokens <= reserve:
        raise ValueError("Embedding input limit is too small for the reserved special tokens")
    # A byte bound is conservative for the supported text tokenizers. Do not
    # confuse whitespace words or characters with actual model tokens.
    budget = max_tokens - reserve
    segments: list[str] = []
    start = 0
    used = 0
    for position, character in enumerate(text):
        size = len(character.encode("utf-8"))
        if used + size > budget:
            segments.append(text[start:position])
            start, used = position, 0
        used += size
    segments.append(text[start:])
    return segments


def embed_texts_bounded(service: EmbeddingInterface, texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    info = service.get_model_info()
    groups = [split_embedding_text(text, info.max_tokens) for text in texts]
    flattened = [segment for group in groups for segment in group]
    vectors: list[list[float]] = []
    batch_size = get_settings().EMB_REQUEST_BATCH_SIZE
    for start in range(0, len(flattened), batch_size):
        batch = flattened[start:start + batch_size]
        embedded = service.embed_texts(batch)
        validate_embedding_batch(embedded, len(batch), info.dimensions)
        vectors.extend(embedded)
    result: list[list[float]] = []
    offset = 0
    for group in groups:
        parts = vectors[offset:offset + len(group)]
        offset += len(group)
        if len(parts) == 1:
            result.append(parts[0])
            continue
        merged = [sum(vector[column] for vector in parts) / len(parts) for column in range(info.dimensions)]
        norm = math.sqrt(sum(value * value for value in merged))
        result.append([value / norm for value in merged] if norm else merged)
    return result
