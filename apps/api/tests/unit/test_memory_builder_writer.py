"""Unit tests for MemoryBuilder and MemoryWriter.

These are the thin wiring layers. Their job is to:
  * MemoryBuilder: call SummaryStore.load + FactStore.retrieve with
    the right scopes, produce a WorkingMemory transport.
  * MemoryWriter: on finalize, drive FactExtractor + FactStore +
    SummaryCompactor + SummaryStore; maintain raw_tail locally;
    no-op for chat_id=None; swallow any exception.

We mock the stores/helpers and test the wiring, not the inner logic
(inner logic has its own test files).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.models.memory import FactScope, FactSource
from app.runtime.memory.builder import MemoryBuilder, _scopes_for
from app.runtime.memory.dto import FactDTO, SummaryDTO
from app.runtime.memory.transport import TurnMemory
from app.runtime.memory.writer import MemoryWriter, _rebuild_raw_tail


# =============================================================== _scopes_for


def test_scopes_for_picks_only_scopes_with_ids():
    assert _scopes_for(chat_id=None, user_id=None, tenant_id=None) == []
    assert _scopes_for(chat_id=uuid4(), user_id=None, tenant_id=None) == [
        FactScope.CHAT
    ]
    assert set(
        _scopes_for(chat_id=uuid4(), user_id=uuid4(), tenant_id=uuid4())
    ) == {FactScope.USER, FactScope.TENANT, FactScope.CHAT}


# ============================================================== MemoryBuilder


@pytest.mark.asyncio
async def test_builder_returns_wm_with_existing_summary_and_facts():
    chat_id, user_id, tenant_id = uuid4(), uuid4(), uuid4()
    existing_summary = SummaryDTO(
        chat_id=chat_id,
        goals=["plan postmortem"],
        last_updated_turn=3,
    )
    fact = FactDTO(
        scope=FactScope.USER, subject="user.name", value="Anna",
        source=FactSource.USER_UTTERANCE, user_id=user_id,
    )

    builder = MemoryBuilder(session=AsyncMock())
    builder._summary_store.load = AsyncMock(return_value=existing_summary)
    builder._fact_store.retrieve = AsyncMock(return_value=[fact])

    wm = await builder.build(
        goal="что я уже сделал?", chat_id=chat_id,
        user_id=user_id, tenant_id=tenant_id,
    )

    assert isinstance(wm, TurnMemory)
    assert wm.goal == "что я уже сделал?"
    assert wm.summary is existing_summary
    assert wm.retrieved_facts == [fact]
    assert wm.turn_number == 4  # 3 + 1
    builder._fact_store.retrieve.assert_awaited_once()


@pytest.mark.asyncio
async def test_builder_empty_summary_for_fresh_chat():
    chat_id = uuid4()
    builder = MemoryBuilder(session=AsyncMock())
    builder._summary_store.load = AsyncMock(return_value=None)
    builder._fact_store.retrieve = AsyncMock(return_value=[])

    wm = await builder.build(
        goal="hi", chat_id=chat_id, user_id=None, tenant_id=None,
    )

    assert wm.summary.chat_id == chat_id
    assert wm.summary.goals == []
    assert wm.turn_number == 1


@pytest.mark.asyncio
async def test_builder_no_chat_id_uses_throwaway_summary_and_no_retrieve():
    """Sandbox-style call: no chat_id, no user_id, no tenant_id → retrieve
    short-circuits via empty scopes list; summary is an in-memory stub."""
    builder = MemoryBuilder(session=AsyncMock())
    builder._summary_store.load = AsyncMock()
    builder._fact_store.retrieve = AsyncMock(return_value=[])

    wm = await builder.build(
        goal="sandbox", chat_id=None, user_id=None, tenant_id=None,
    )

    builder._summary_store.load.assert_not_called()  # no chat_id → no load
    builder._fact_store.retrieve.assert_awaited_once()
    call_kwargs = builder._fact_store.retrieve.await_args.kwargs
    assert call_kwargs["scopes"] == []  # _scopes_for returned empty
    assert wm.retrieved_facts == []
    assert wm.summary.goals == []


# =============================================================== MemoryWriter


@pytest.fixture
def _writer() -> MemoryWriter:
    w = MemoryWriter(session=AsyncMock(), llm_client=AsyncMock())
    w._extractor.extract = AsyncMock(return_value=[])
    w._compactor.compact = AsyncMock()
    w._fact_store.upsert_with_supersede = AsyncMock()
    w._summary_store.save = AsyncMock()
    return w


@pytest.mark.asyncio
async def test_writer_noop_without_chat_id(_writer):
    wm = TurnMemory(
        chat_id=None, user_id=uuid4(), tenant_id=uuid4(),
        turn_number=1, goal="x", summary=SummaryDTO.empty(uuid4()),
    )
    await _writer.finalize(memory=wm, user_message="hi", assistant_final="yo")

    _writer._extractor.extract.assert_not_called()
    _writer._compactor.compact.assert_not_called()
    _writer._summary_store.save.assert_not_called()


@pytest.mark.asyncio
async def test_writer_persists_extracted_facts(_writer):
    chat_id, user_id = uuid4(), uuid4()
    f1 = FactDTO(
        scope=FactScope.USER, subject="user.name", value="Anna",
        source=FactSource.USER_UTTERANCE, user_id=user_id,
    )
    _writer._extractor.extract = AsyncMock(return_value=[f1])
    _writer._compactor.compact = AsyncMock(
        return_value=SummaryDTO(chat_id=chat_id, last_updated_turn=2)
    )

    wm = TurnMemory(
        chat_id=chat_id, user_id=user_id, tenant_id=None,
        turn_number=2, goal="hi",
        summary=SummaryDTO(chat_id=chat_id, last_updated_turn=1),
    )
    await _writer.finalize(memory=wm, user_message="меня зовут Анна", assistant_final="ок")

    _writer._fact_store.upsert_with_supersede.assert_awaited_once_with(f1)
    _writer._summary_store.save.assert_awaited_once()


@pytest.mark.asyncio
async def test_writer_raw_tail_appended_and_carried_to_save(_writer):
    chat_id = uuid4()
    compacted = SummaryDTO(chat_id=chat_id, goals=["g"], last_updated_turn=2)
    _writer._compactor.compact = AsyncMock(return_value=compacted)

    wm = TurnMemory(
        chat_id=chat_id, user_id=None, tenant_id=None,
        turn_number=2, goal="",
        summary=SummaryDTO(chat_id=chat_id, raw_tail="prev tail", last_updated_turn=1),
    )
    await _writer.finalize(memory=wm, user_message="hey", assistant_final="ho")

    saved = _writer._summary_store.save.await_args.args[0]
    assert "prev tail" in saved.raw_tail
    assert "user: hey" in saved.raw_tail
    assert "assistant: ho" in saved.raw_tail


@pytest.mark.asyncio
async def test_writer_swallows_extractor_exception(_writer):
    """Memory-write errors must never propagate — worst case we lose one
    turn of updates, not the user's answer."""
    chat_id = uuid4()
    _writer._extractor.extract = AsyncMock(side_effect=RuntimeError("boom"))

    wm = TurnMemory(
        chat_id=chat_id, user_id=uuid4(), tenant_id=None,
        turn_number=1, goal="", summary=SummaryDTO.empty(chat_id),
    )
    # Must NOT raise.
    await _writer.finalize(memory=wm, user_message="x", assistant_final="y")

    _writer._summary_store.save.assert_not_called()


# ============================================================= _rebuild_raw_tail


def test_rebuild_raw_tail_simple_concat():
    out = _rebuild_raw_tail("", "hi", "hello")
    assert out == "user: hi\nassistant: hello"


def test_rebuild_raw_tail_appends_to_existing():
    out = _rebuild_raw_tail("user: a\nassistant: b", "c", "d")
    assert out == "user: a\nassistant: b\nuser: c\nassistant: d"


def test_rebuild_raw_tail_clips_from_front_when_over_budget():
    huge = "x" * 5000
    out = _rebuild_raw_tail(huge, "new", "answer")
    assert len(out) <= 2000
    # Most recent content preserved at the tail.
    assert out.endswith("assistant: answer")
