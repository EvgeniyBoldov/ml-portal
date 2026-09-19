"""Chat-side adapter for the runtime context outcome port."""
from __future__ import annotations

from app.runtime.context_outcome import RuntimeOutcomeProjection
from app.services.chat_context_contracts import ChatContextApplyReceipt
from app.services.chat_context_reducer import ChatContextReducer
from app.services.chat_context_service import ChatContextService


class ChatContextOutcomeAdapter:
    def __init__(self, service: ChatContextService) -> None:
        self._service = service

    async def apply(self, *, projection: RuntimeOutcomeProjection, expected_context_revision: int, branch_id: str | None, owner_id: str, tenant_id: str) -> ChatContextApplyReceipt:
        return await self._service.apply_outcome(
            projection=projection, expected_revision=expected_context_revision, branch_id=branch_id,
            owner_id=owner_id, tenant_id=tenant_id, reducer=ChatContextReducer(),
        )
