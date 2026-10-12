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
