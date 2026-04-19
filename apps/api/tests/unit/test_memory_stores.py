"""Unit tests for FactStore and SummaryStore.

Focus areas
-----------
* FactStore.upsert_with_supersede decision logic (insert / refresh /
  supersede) — we mock the three primitive methods it calls.
* FactDTO.matches_key semantics across scopes.
* SummaryStore save path constructs a PG ON CONFLICT upsert.

We do NOT try to assert the generated SQL text — tests that go that
deep become tests of SQLAlchemy, not of our code. Behaviour tests
are strictly about "which primitive was called with which DTO".
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from app.models.memory import FactScope, FactSource
from app.runtime.memory.dto import FactDTO, SummaryDTO
from app.runtime.memory.fact_store import FactStore
from app.runtime.memory.summary_store import SummaryStore


# ----------------------------------------------------- FactDTO.matches_key ---


def _dto(**overrides):
    base = dict(
        scope=FactScope.USER,
        subject="user.name",
        value="Anna",
        source=FactSource.USER_UTTERANCE,
        user_id=uuid4(),
    )
    base.update(overrides)
    return FactDTO(**base)


def test_matches_key_user_scope_matches_on_user_id():
    uid = uuid4()
    a = _dto(user_id=uid)
    b = _dto(user_id=uid, value="AnotherValue")
    assert a.matches_key(b) is True


def test_matches_key_different_user_is_different_slot():
    a = _dto(user_id=uuid4())
    b = _dto(user_id=uuid4())
    assert a.matches_key(b) is False


def test_matches_key_chat_scope_uses_chat_id():
    cid = uuid4()
    a = _dto(scope=FactScope.CHAT, chat_id=cid, user_id=None)
    b = _dto(scope=FactScope.CHAT, chat_id=cid, user_id=None, value="x")
    assert a.matches_key(b) is True


def test_matches_key_different_subject_never_matches():
    uid = uuid4()
    a = _dto(user_id=uid, subject="user.name")
    b = _dto(user_id=uid, subject="user.stack")
    assert a.matches_key(b) is False


# ----------------------------------------------- FactStore.upsert decisions ---


@pytest.fixture
def store() -> FactStore:
    """FactStore with a dummy session — we patch its methods per test."""
    return FactStore(session=AsyncMock())


@pytest.mark.asyncio
async def test_upsert_inserts_when_no_active_row(store: FactStore):
    """No existing slot → straight INSERT, no mark_superseded call."""
    new = _dto(value="Anna")
    store.get_active_by_key = AsyncMock(return_value=None)
    store.add = AsyncMock(return_value=new)
    store.mark_superseded = AsyncMock()

    result = await store.upsert_with_supersede(new)

    assert result is new
    store.add.assert_awaited_once_with(new)
    store.mark_superseded.assert_not_called()


@pytest.mark.asyncio
async def test_upsert_refreshes_when_value_equivalent(store: FactStore):
    """Existing slot with same value → no supersede chain, no new INSERT,
    just a timestamp/confidence refresh on the existing row. Returned DTO
    must carry the *existing* id so callers can tell nothing changed."""
    existing_id = uuid4()
    existing = _dto(value="Anna", confidence=0.6)
    existing = FactDTO(**{**existing.__dict__, "id": existing_id})

    new = _dto(
        value="  Anna  ",  # whitespace differs → still equivalent
        confidence=0.9,
        observed_at=datetime.now(timezone.utc) + timedelta(minutes=1),
    )

    store.get_active_by_key = AsyncMock(return_value=existing)
    store.add = AsyncMock()
    store.mark_superseded = AsyncMock()
    # The refresh path does a raw UPDATE via session.execute — stub it out
    store._session.execute = AsyncMock()

    result = await store.upsert_with_supersede(new)

    assert result.id == existing_id
    assert result.confidence == 0.9  # max(0.6, 0.9)
    store.add.assert_not_called()
    store.mark_superseded.assert_not_called()
    store._session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_upsert_supersedes_on_value_contradiction(store: FactStore):
    """Existing slot with different value → INSERT new + mark old superseded.
    Returned DTO is the new one, not the old."""
    old = FactDTO(
        scope=FactScope.USER,
        subject="user.stack",
        value="Go",
        source=FactSource.USER_UTTERANCE,
        user_id=uuid4(),
        id=uuid4(),
    )
    new = FactDTO(
        scope=FactScope.USER,
        subject="user.stack",
        value="Rust",
        source=FactSource.USER_UTTERANCE,
        user_id=old.user_id,
    )

    store.get_active_by_key = AsyncMock(return_value=old)
    store.add = AsyncMock(return_value=new)
    store.mark_superseded = AsyncMock()

    result = await store.upsert_with_supersede(new)

    assert result is new
    store.add.assert_awaited_once_with(new)
    store.mark_superseded.assert_awaited_once_with(
        old_id=old.id, new_id=new.id
    )


# --------------------------------------------------- FactStore.retrieve ---


@pytest.mark.asyncio
async def test_retrieve_with_empty_scopes_returns_empty_list_without_query(
    store: FactStore,
):
    """Don't bother hitting the DB if the caller asked for zero scopes."""
    store._session.execute = AsyncMock()
    result = await store.retrieve(scopes=[])
    assert result == []
    store._session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_retrieve_executes_query_for_nonempty_scopes(store: FactStore):
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = []
    exec_result = MagicMock()
    exec_result.scalars.return_value = scalars_mock
    store._session.execute = AsyncMock(return_value=exec_result)

    result = await store.retrieve(
        scopes=[FactScope.USER, FactScope.TENANT],
        user_id=uuid4(),
        tenant_id=uuid4(),
        limit=10,
    )
    assert result == []
    store._session.execute.assert_awaited_once()


# --------------------------------------------------------- SummaryStore ---


@pytest.mark.asyncio
async def test_summary_store_load_returns_none_for_missing_chat():
    session = AsyncMock()
    exec_result = MagicMock()
    exec_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=exec_result)

    store = SummaryStore(session)
    result = await store.load(uuid4())

    assert result is None


@pytest.mark.asyncio
async def test_summary_store_load_maps_row_to_dto():
    chat_id = uuid4()
    row = MagicMock()
    row.chat_id = chat_id
    row.goals = ["plan postmortem"]
    row.done = ["collected logs"]
    row.entities = {"incident_id": "INC-42"}
    row.open_questions = ["which node crashed first?"]
    row.raw_tail = "user: hi\nassistant: hey"
    row.last_updated_turn = 3
    row.updated_at = datetime.now(timezone.utc)

    session = AsyncMock()
    exec_result = MagicMock()
    exec_result.scalar_one_or_none.return_value = row
    session.execute = AsyncMock(return_value=exec_result)

    store = SummaryStore(session)
    result = await store.load(chat_id)

    assert isinstance(result, SummaryDTO)
    assert result.chat_id == chat_id
    assert result.goals == ["plan postmortem"]
    assert result.entities == {"incident_id": "INC-42"}
    assert result.last_updated_turn == 3


@pytest.mark.asyncio
async def test_summary_store_save_executes_upsert_and_flushes():
    session = AsyncMock()
    session.execute = AsyncMock()
    session.flush = AsyncMock()

    store = SummaryStore(session)
    await store.save(
        SummaryDTO(
            chat_id=uuid4(),
            goals=["g"],
            last_updated_turn=1,
        )
    )

    session.execute.assert_awaited_once()
    session.flush.assert_awaited_once()
