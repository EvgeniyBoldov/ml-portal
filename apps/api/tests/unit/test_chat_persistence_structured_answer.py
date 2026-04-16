from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services.chat_persistence_service import ChatPersistenceService


@pytest.mark.asyncio
async def test_create_assistant_message_stores_answer_blocks():
    session = AsyncMock()
    repo = AsyncMock()
    created = SimpleNamespace(id=uuid4(), created_at=None)
    repo.create_message = AsyncMock(return_value=created)

    service = ChatPersistenceService(session=session, messages_repo=repo)

    await service.create_assistant_message(
        chat_id=str(uuid4()),
        content="Hello\n```python\nprint('x')\n```",
        rag_sources=[{"title": "Doc", "uri": "kb://doc-1"}],
        attachments=[{"file_name": "out.txt", "url": "https://example.local/f/1"}],
    )

    assert repo.create_message.await_count == 1
    kwargs = repo.create_message.await_args.kwargs
    meta = kwargs["meta"]
    assert meta["answer_contract"] == "answer_blocks.v1"
    assert isinstance(meta["answer_blocks"], list)
    assert len(meta["answer_blocks"]) >= 3
    assert meta["grounding"]["citations_count"] == 1
