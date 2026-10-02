"""Post-commit index delivery; periodic reconciliation recovers broker outages."""
from __future__ import annotations

import asyncio
from collections.abc import Iterable
from uuid import UUID

from app.core.logging import get_logger

logger = get_logger(__name__)


async def dispatch_memory_index(item_ids: Iterable[UUID]) -> bool:
    ids = [str(id_) for id_ in sorted(set(item_ids), key=str)]
    if not ids:
        return True
    from app.workers.tasks_memory import index_memory_items

    try:
        await asyncio.to_thread(index_memory_items.delay, ids)
        return True
    except Exception:
        logger.exception("Memory publication committed; index delivery awaits reconciliation", extra={"memory_item_ids": ids})
        return False
