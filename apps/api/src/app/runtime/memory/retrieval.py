"""Select the configured document-memory retriever after authoritative read policy."""
from __future__ import annotations

from typing import Any, TYPE_CHECKING
from uuid import UUID

from app.core.config import get_settings
from app.runtime.memory.semantic_index import MemorySemanticIndex
from app.services.hipporag_service import HippoRAGService

if TYPE_CHECKING:
    from app.runtime.memory.recall import MemoryRecallService


async def retrieve_memory_ids(recall: MemoryRecallService, query: str, *, eligible_ids: list[UUID],
                              read_args: dict[str, Any], limit: int = 48) -> list[UUID]:
    if not eligible_ids:
        return []
    if get_settings().MEMORY_SEARCH_BACKEND == "legacy":
        semantic = await MemorySemanticIndex(recall._session).search_ids(query, limit=limit, eligible_ids=eligible_ids)
        lexical = await recall._lexical_ids(query, limit=limit, eligible_ids=eligible_ids, **read_args)
        return list(dict.fromkeys([*semantic, *lexical]))
    items = await recall._accessible_semantic_items(semantic_ids=eligible_ids, **read_args)
    return await HippoRAGService(recall._session).search_ids(query, items=items, limit=limit)
