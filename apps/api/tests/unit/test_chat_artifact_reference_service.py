from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.models.chat_artifact_reference import ChatArtifactReference
from app.services.chat_artifact_reference_service import (
    ArtifactTarget,
    ChatArtifactReferenceService,
)


@pytest.mark.asyncio
async def test_register_is_idempotent_for_same_chat_target() -> None:
    session = AsyncMock()
    session.add = MagicMock()
    existing = ChatArtifactReference(
        id=uuid4(),
        chat_id=uuid4(),
        owner_id=uuid4(),
        target_kind="chat_attachment",
        target_id=str(uuid4()),
    )
    session.scalar = AsyncMock(side_effect=[existing])

    result = await ChatArtifactReferenceService(session).register(
        chat_id=existing.chat_id,
        owner_id=existing.owner_id,
        target=ArtifactTarget(kind=existing.target_kind, target_id=existing.target_id),
    )

    assert result is existing
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_register_creates_reference_for_new_target() -> None:
    session = AsyncMock()
    session.add = MagicMock()
    session.scalar = AsyncMock(return_value=None)
    service = ChatArtifactReferenceService(session)

    result = await service.register(
        chat_id=uuid4(),
        owner_id=uuid4(),
        target=ArtifactTarget(
            kind="collection_document",
            target_id=str(uuid4()),
            collection_id=uuid4(),
            display_name="report.txt",
        ),
    )

    assert result.id is not None
    assert result.target_kind == "collection_document"
    session.add.assert_called_once_with(result)
    session.flush.assert_awaited_once()
