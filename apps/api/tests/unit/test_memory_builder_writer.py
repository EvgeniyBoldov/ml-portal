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
from app.runtime.memory.builder import MemoryBuilder
from app.runtime.memory.components import (
    ConversationMemoryComponent,
    FactMemoryComponent,
    MemoryAssembler,
    MemoryBudget,
    MemoryBundle,
    MemoryComponentRegistry,
    MemoryItem,
    MemoryPromptRenderer,
    MemoryQueryContext,
    MemorySection,
)
from app.runtime.memory.dto import FactDTO, SummaryDTO
from app.runtime.memory.transport import TurnMemory
from app.runtime.memory.writer import MemoryWriter, _looks_non_retryable_limit_error, _rebuild_raw_tail


# ============================================================== MemoryBuilder


@pytest.mark.asyncio
async def test_fact_memory_component_selects_query_relevant_facts():
    user_id, tenant_id = uuid4(), uuid4()
    relevant = FactDTO(
        scope=FactScope.USER,
        subject="project.runtime",
        value="Нужно чинить MCP memory runtime",
        source=FactSource.USER_UTTERANCE,
        user_id=user_id,
    )
    irrelevant = FactDTO(
        scope=FactScope.TENANT,
        subject="office.coffee",
        value="Кофемашина на кухне",
        source=FactSource.SYSTEM,
        tenant_id=tenant_id,
    )
    fact_store = MagicMock()
    fact_store.retrieve = AsyncMock(side_effect=[[relevant], [irrelevant], []])

    component = FactMemoryComponent(fact_store=fact_store, fact_limit=1)
    section = await component.collect(
        MemoryQueryContext(
            goal="проверь runtime memory mcp",
            chat_id=uuid4(),
            user_id=user_id,
            tenant_id=tenant_id,
            summary=SummaryDTO.empty(uuid4()),
            budget=MemoryBudget(max_items_per_section=1, default_section_chars=500),
        )
    )

    assert section.name == "facts"
    assert len(section.items) == 1
    assert section.items[0].subject == "project.runtime"
    assert section.omitted_count == 1


@pytest.mark.asyncio
async def test_fact_memory_component_emits_contradiction_notice_and_scope_labels():
    user_id, tenant_id = uuid4(), uuid4()
    user_fact = FactDTO(
        scope=FactScope.USER,
        subject="incident.owner",
        value="team-alpha",
        source=FactSource.USER_UTTERANCE,
        user_id=user_id,
    )
    company_fact = FactDTO(
        scope=FactScope.TENANT,
        subject="incident.owner",
        value="team-bravo",
        source=FactSource.SYSTEM,
        tenant_id=None,
    )
    fact_store = MagicMock()
    fact_store.retrieve = AsyncMock(side_effect=[[user_fact], [], [company_fact]])

    component = FactMemoryComponent(fact_store=fact_store, fact_limit=5)
    section = await component.collect(
        MemoryQueryContext(
            goal="кто владелец incident owner",
            chat_id=uuid4(),
            user_id=user_id,
            tenant_id=tenant_id,
            summary=SummaryDTO.empty(uuid4()),
            budget=MemoryBudget(max_items_per_section=5, default_section_chars=1200),
        )
    )

    assert any(item.source == "memory.conflict" for item in section.items)
    rendered = [item.text for item in section.items]
    assert any("[user] incident.owner: team-alpha" in text for text in rendered)
    assert any("[company] incident.owner: team-bravo" in text for text in rendered)


@pytest.mark.asyncio
async def test_conversation_memory_component_returns_bounded_facets():
    summary = SummaryDTO(
        chat_id=uuid4(),
        goals=["g1", "g2"],
        done=["d1"],
        open_questions=["q1"],
        entities={"repo": "ml-portal"},
        raw_tail="x" * 2000,
    )

    section = await ConversationMemoryComponent().collect(
        MemoryQueryContext(
            goal="runtime",
            chat_id=summary.chat_id,
            user_id=None,
            tenant_id=None,
            summary=summary,
            budget=MemoryBudget(max_items_per_section=4, default_section_chars=200),
        )
    )

    assert section.name == "conversation"
    assert len(section.items) <= 4
    assert section.budget_used_chars <= 200
    assert section.omitted_count > 0


@pytest.mark.asyncio
async def test_builder_returns_wm_with_existing_summary_and_facts(monkeypatch):
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
    bundle = MemoryBundle(
        sections=[
            MemorySection(
                name="facts",
                priority=20,
                items=[
                    MemoryItem(
                        text="user.name: Anna",
                        source="memory.user",
                        subject="user.name",
                        metadata={"fact_id": str(fact.id)},
                        private_payload=fact,
                    )
                ],
            )
        ],
        total_budget_used_chars=15,
    )
    builder._memory_assembler.assemble = AsyncMock(return_value=bundle)

    wm = await builder.build(
        goal="что я уже сделал?", chat_id=chat_id,
        user_id=user_id, tenant_id=tenant_id,
    )

    assert isinstance(wm, TurnMemory)
    assert wm.goal == "что я уже сделал?"
    assert wm.summary is existing_summary
    assert wm.retrieved_facts == [fact]
    assert wm.memory_bundle is bundle
    assert wm.memory_diagnostics["total_budget_used_chars"] == 15
    assert wm.turn_number == 4  # 3 + 1
    builder._memory_assembler.assemble.assert_awaited_once()


@pytest.mark.asyncio
async def test_builder_empty_summary_for_fresh_chat(monkeypatch):
    chat_id = uuid4()
    builder = MemoryBuilder(session=AsyncMock())
    builder._summary_store.load = AsyncMock(return_value=None)
    builder._memory_assembler.assemble = AsyncMock(return_value=MemoryBundle())

    wm = await builder.build(
        goal="hi", chat_id=chat_id, user_id=None, tenant_id=None,
    )

    assert wm.summary.chat_id == chat_id
    assert wm.summary.goals == []
    assert wm.turn_number == 1


class _StubComponent:
    def __init__(
        self,
        *,
        name: str,
        priority: int,
        char_size: int = 0,
        raises: bool = False,
    ) -> None:
        self.name = name
        self.priority = priority
        self._char_size = char_size
        self._raises = raises

    async def collect(self, ctx):
        if self._raises:
            raise RuntimeError(f"{self.name} boom")
        text = "x" * self._char_size
        items = [MemoryItem(text=text, source=f"stub.{self.name}")]
        return MemorySection(
            name=self.name,
            priority=self.priority,
            items=items,
            budget_used_chars=self._char_size,
            selection_reason="stub",
        )


@pytest.mark.asyncio
async def test_memory_registry_applies_disable_and_order_stability():
    registry = MemoryComponentRegistry(
        components=[
            _StubComponent(name="b", priority=20),
            _StubComponent(name="a", priority=20),
            _StubComponent(name="c", priority=10),
        ]
    )
    bindings = registry.resolve(
        {
            "memory": {
                "disabled_components": ["a"],
                "components": {
                    "b": {"priority": 5},
                },
            }
        }
    )
    assert [item.component.name for item in bindings] == ["b", "c", "a"]
    assert [item.enabled for item in bindings] == [True, True, False]


@pytest.mark.asyncio
async def test_memory_assembler_marks_component_failure_as_degraded():
    registry = MemoryComponentRegistry(
        components=[
            _StubComponent(name="ok", priority=10, char_size=20),
            _StubComponent(name="bad", priority=20, raises=True),
        ]
    )
    assembler = MemoryAssembler(registry=registry)
    bundle = await assembler.assemble(
        MemoryQueryContext(
            goal="x",
            chat_id=uuid4(),
            user_id=None,
            tenant_id=None,
            summary=SummaryDTO.empty(uuid4()),
        )
    )
    assert bundle.section("ok").status == "ok"
    assert bundle.section("bad").status == "degraded"
    assert "bad" in bundle.diagnostics["degraded_components"]


@pytest.mark.asyncio
async def test_memory_assembler_enforces_total_budget():
    registry = MemoryComponentRegistry(
        components=[
            _StubComponent(name="first", priority=10, char_size=90),
            _StubComponent(name="second", priority=20, char_size=90),
        ]
    )
    assembler = MemoryAssembler(registry=registry)
    bundle = await assembler.assemble(
        MemoryQueryContext(
            goal="x",
            chat_id=uuid4(),
            user_id=None,
            tenant_id=None,
            summary=SummaryDTO.empty(uuid4()),
            budget=MemoryBudget(total_chars=100, default_section_chars=100, max_items_per_section=10),
        )
    )
    assert bundle.total_budget_used_chars <= 100
    assert bundle.section("first").items
    assert bundle.section("second").omitted_count >= 1


@pytest.mark.asyncio
async def test_memory_budget_from_platform_config_overrides_component_limits():
    summary = SummaryDTO(chat_id=uuid4(), goals=["g1", "g2", "g3"], raw_tail="x" * 600)
    ctx = MemoryQueryContext(
        goal="runtime",
        chat_id=summary.chat_id,
        user_id=None,
        tenant_id=None,
        summary=summary,
        budget=MemoryBudget.from_platform_config(
            base=MemoryBudget(),
            platform_config={
                "memory": {
                    "components": {
                        "conversation": {"max_items": 1, "max_chars": 80},
                    }
                }
            },
        ),
    )
    section = await ConversationMemoryComponent().collect(ctx)
    assert len(section.items) == 1
    assert section.budget_used_chars <= 80


def test_memory_prompt_renderer_hides_sensitive_and_respects_budget():
    bundle = MemoryBundle(
        sections=[
            MemorySection(
                name="facts",
                priority=10,
                items=[
                    MemoryItem(text="safe item", source="x"),
                    MemoryItem(text="internal item", source="x", redaction_level="internal"),
                    MemoryItem(text="sensitive item", source="x", redaction_level="sensitive"),
                ],
                budget_used_chars=40,
            ),
            MemorySection(
                name="sensitive_section",
                priority=20,
                redaction_level="sensitive",
                items=[MemoryItem(text="hidden", source="x")],
                budget_used_chars=6,
            ),
        ]
    )
    rendered = MemoryPromptRenderer().render(bundle=bundle, max_chars=30, allow_internal=False)
    assert "safe item" in rendered
    assert "internal item" not in rendered
    assert "sensitive item" not in rendered
    assert "sensitive_section" not in rendered
    assert len(rendered) <= 30


@pytest.mark.asyncio
async def test_builder_no_chat_id_uses_throwaway_summary_and_no_retrieve(monkeypatch):
    """Sandbox-style call: no chat_id, no user_id, no tenant_id → retrieve
    from long-term service; summary is an in-memory stub."""
    builder = MemoryBuilder(session=AsyncMock())
    builder._summary_store.load = AsyncMock()
    builder._memory_assembler.assemble = AsyncMock(return_value=MemoryBundle())

    wm = await builder.build(
        goal="sandbox", chat_id=None, user_id=None, tenant_id=None,
    )

    builder._summary_store.load.assert_not_called()  # no chat_id → no load
    builder._memory_assembler.assemble.assert_awaited_once()
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
    assert "memory_write_status" not in wm.memory_diagnostics


@pytest.mark.asyncio
async def test_writer_persists_extracted_facts(_writer, monkeypatch):
    chat_id, user_id = uuid4(), uuid4()
    f1 = FactDTO(
        scope=FactScope.USER, subject="user.name", value="Anna",
        source=FactSource.USER_UTTERANCE, user_id=user_id,
    )
    _writer._extractor.extract = AsyncMock(return_value=[f1])
    _writer._compactor.compact = AsyncMock(
        return_value=SummaryDTO(chat_id=chat_id, last_updated_turn=2)
    )
    long_term = MagicMock()
    long_term.save_for_runtime = AsyncMock(return_value=1)
    long_term_ctor = MagicMock(return_value=long_term)
    monkeypatch.setattr("app.runtime.memory.writer.LongTermFactsService", long_term_ctor)

    wm = TurnMemory(
        chat_id=chat_id, user_id=user_id, tenant_id=None,
        turn_number=2, goal="hi",
        summary=SummaryDTO(chat_id=chat_id, last_updated_turn=1),
    )
    await _writer.finalize(memory=wm, user_message="меня зовут Анна", assistant_final="ок")

    long_term_ctor.assert_called_once()
    long_term.save_for_runtime.assert_awaited_once_with(facts=[f1])
    _writer._fact_store.upsert_with_supersede.assert_not_called()
    _writer._summary_store.save.assert_awaited_once()
    statuses = wm.memory_diagnostics["memory_write_status"]["results"]
    assert any(item["component_name"] == "facts" and item["status"] == "ok" for item in statuses)
    assert any(item["component_name"] == "conversation" and item["status"] == "ok" for item in statuses)


@pytest.mark.asyncio
async def test_writer_persists_chat_facts_via_fact_store(_writer, monkeypatch):
    chat_id, tenant_id = uuid4(), uuid4()
    f1 = FactDTO(
        scope=FactScope.CHAT, subject="chat.last_topic", value="memory",
        source=FactSource.AGENT_RESULT, chat_id=chat_id,
    )
    _writer._extractor.extract = AsyncMock(return_value=[f1])
    _writer._compactor.compact = AsyncMock(
        return_value=SummaryDTO(chat_id=chat_id, last_updated_turn=2)
    )
    long_term = MagicMock()
    long_term.save_for_runtime = AsyncMock(return_value=0)
    monkeypatch.setattr(
        "app.runtime.memory.writer.LongTermFactsService",
        MagicMock(return_value=long_term),
    )

    wm = TurnMemory(
        chat_id=chat_id, user_id=None, tenant_id=tenant_id,
        turn_number=2, goal="hi",
        summary=SummaryDTO(chat_id=chat_id, last_updated_turn=1),
    )
    await _writer.finalize(memory=wm, user_message="x", assistant_final="ok")

    long_term.save_for_runtime.assert_awaited_once_with(facts=[f1])
    _writer._fact_store.upsert_with_supersede.assert_awaited_once_with(f1)


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

    _writer._summary_store.save.assert_awaited_once()
    payload = wm.memory_diagnostics["memory_write_status"]
    assert "facts" in payload["failed_components"]
    assert "conversation" not in payload["failed_components"]


@pytest.mark.asyncio
async def test_writer_skips_llm_helpers_on_non_retryable_limit_error(_writer):
    chat_id = uuid4()
    wm = TurnMemory(
        chat_id=chat_id,
        user_id=uuid4(),
        tenant_id=None,
        turn_number=3,
        goal="",
        summary=SummaryDTO(chat_id=chat_id, goals=["g"], last_updated_turn=2),
    )
    wm.agent_results = [
        MagicMock(
            agent="mon.net",
            summary=(
                "Error code: 413 - {'error': {'code': 'rate_limit_exceeded', "
                "'message': 'Request too large for model'}}"
            ),
            success=False,
        )
    ]

    await _writer.finalize(memory=wm, user_message="u", assistant_final="a")

    _writer._extractor.extract.assert_not_called()
    _writer._compactor.compact.assert_not_called()
    _writer._summary_store.save.assert_awaited_once()
    statuses = wm.memory_diagnostics["memory_write_status"]["results"]
    assert any(item["component_name"] == "facts" and item["status"] == "skipped" for item in statuses)
    assert any(item["component_name"] == "conversation" and item["status"] == "degraded" for item in statuses)


@pytest.mark.asyncio
async def test_writer_summary_failure_does_not_break_fact_write(_writer, monkeypatch):
    chat_id, user_id = uuid4(), uuid4()
    f1 = FactDTO(
        scope=FactScope.USER,
        subject="user.stack",
        value="python",
        source=FactSource.USER_UTTERANCE,
        user_id=user_id,
    )
    _writer._extractor.extract = AsyncMock(return_value=[f1])
    _writer._compactor.compact = AsyncMock(side_effect=RuntimeError("summary down"))
    long_term = MagicMock()
    long_term.save_for_runtime = AsyncMock(return_value=1)
    monkeypatch.setattr("app.runtime.memory.writer.LongTermFactsService", MagicMock(return_value=long_term))

    wm = TurnMemory(
        chat_id=chat_id,
        user_id=user_id,
        tenant_id=None,
        turn_number=2,
        goal="x",
        summary=SummaryDTO(chat_id=chat_id, last_updated_turn=1),
    )
    await _writer.finalize(memory=wm, user_message="u", assistant_final="a")

    long_term.save_for_runtime.assert_awaited_once_with(facts=[f1])
    payload = wm.memory_diagnostics["memory_write_status"]
    assert "conversation" in payload["failed_components"]
    assert "facts" not in payload["failed_components"]


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


def test_looks_non_retryable_limit_error_detects_tool_protocol_failure():
    assert _looks_non_retryable_limit_error(
        "Error code: 400 tool_use_failed: Tool choice is none, but model called a tool"
    ) is True
