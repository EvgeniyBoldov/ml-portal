"""Shared worker resources without importing either API module."""
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, Field

DATA = Path(os.getenv("HIPPO_DATA_DIR", "/data"))
CHUNK_TOKENS = int(os.getenv("HIPPO_CHUNK_TOKENS", "480"))
POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="hipporag")
CLIENT = httpx.Client(timeout=180)


class Document(BaseModel):
    id: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=500_000)
    metadata: dict[str, Any] = Field(default_factory=dict)


from hipporag.utils.misc_utils import Chunk


def split_document(document: Document, llm: Any) -> list[Chunk]:
    # Binary search over character boundaries, with a newline boundary where possible.
    # Unlike heading parsing this preserves comments and fenced code verbatim.
    text = document.content
    chunks = []
    start = 0
    while start < len(text):
        low, high = start + 1, min(len(text), start + CHUNK_TOKENS * 8)
        end = low
        while low <= high:
            mid = (low + high) // 2
            if llm.tokens(text[start:mid]) <= CHUNK_TOKENS:
                end, low = mid, mid + 1
            else:
                high = mid - 1
        if end < len(text):
            boundary = text.rfind("\n", start, end)
            if boundary > start + (end - start) // 2:
                end = boundary + 1
        content = text[start:end]
        chunks.append(Chunk(content=content, source_id=f"{document.id}:{start}:{end}",
                            metadata={**document.metadata, "document_id": document.id, "start": start, "end": end}))
        start = end
    return chunks
