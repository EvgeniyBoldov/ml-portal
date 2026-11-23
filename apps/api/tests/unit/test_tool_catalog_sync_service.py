"""Unit tests for ToolCatalogSyncService (app/services/tool_catalog_sync_service.py)."""
from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.tool import Tool
from app.services.tool_catalog_sync_service import ToolCatalogSyncService


@dataclass
class FakeHandler:
    slug: str
    name: str
    domains: list[str] = field(default_factory=list)


def make_session_with_tools(tools_by_slug: dict[str, Tool]) -> AsyncMock:
    """Session mock whose tool lookup resolves slugs from a dict."""
    session = AsyncMock()
    session.add = MagicMock()  # add() is sync on a real session

    async def execute(stmt, *args, **kwargs):
        compiled = stmt.compile()
        slug = compiled.params.get("slug_1")
        result = MagicMock()
        result.scalar_one_or_none.return_value = tools_by_slug.get(slug)
        return result

    session.execute = AsyncMock(side_effect=execute)
    return session


class TestResolveDomains:
    def setup_method(self):
        self.service = ToolCatalogSyncService(AsyncMock())

    def test_explicit_domains_are_kept(self):
        handler = FakeHandler(slug="memory.search", name="Search", domains=["memory", "search"])
        assert self.service._resolve_domains(handler) == ["memory", "search"]

    def test_domains_are_stripped_and_deduped(self):
        handler = FakeHandler(
            slug="x.y", name="X", domains=[" memory ", "memory", "", "  ", "chat"]
        )
        assert self.service._resolve_domains(handler) == ["memory", "chat"]

    def test_falls_back_to_slug_prefix(self):
        handler = FakeHandler(slug="chat.summarize", name="Summarize")
        assert self.service._resolve_domains(handler) == ["chat"]

    def test_no_domains_and_no_slug(self):
        handler = FakeHandler(slug="", name="Anonymous")
        assert self.service._resolve_domains(handler) == []

    def test_missing_domains_attribute(self):
        handler = object.__new__(FakeHandler)  # no attributes at all
        handler.slug = "docs.read"  # type: ignore[attr-defined]
        assert self.service._resolve_domains(handler) == ["docs"]


class TestSyncTools:
    async def test_creates_missing_tool(self):
        session = make_session_with_tools({})
        handlers = [FakeHandler(slug="memory.search", name="Поиск по памяти", domains=["memory"])]

        with patch("app.services.tool_catalog_sync_service.ToolRegistry") as registry:
            registry.list_all.return_value = handlers
            stats = await ToolCatalogSyncService(session).sync_tools()

        assert stats == {"created": 1, "updated": 0}
        tool = session.add.call_args.args[0]
        assert isinstance(tool, Tool)
        assert tool.slug == "memory.search"
        assert tool.name == "Поиск по памяти"
        assert tool.domains == ["memory"]
        session.commit.assert_awaited_once()

    async def test_updates_changed_fields(self):
        existing = Tool(slug="chat.summarize", name="Old name", domains=["old"])
        session = make_session_with_tools({"chat.summarize": existing})
        handlers = [FakeHandler(slug="chat.summarize", name="New name", domains=["chat", "summary"])]

        with patch("app.services.tool_catalog_sync_service.ToolRegistry") as registry:
            registry.list_all.return_value = handlers
            stats = await ToolCatalogSyncService(session).sync_tools()

        assert stats == {"created": 0, "updated": 1}
        assert existing.name == "New name"
        assert existing.domains == ["chat", "summary"]

    async def test_unchanged_tool_is_not_touched(self):
        existing = Tool(slug="chat.summarize", name="Summary", domains=["chat"])
        session = make_session_with_tools({"chat.summarize": existing})
        handlers = [FakeHandler(slug="chat.summarize", name="Summary", domains=["chat"])]

        with patch("app.services.tool_catalog_sync_service.ToolRegistry") as registry:
            registry.list_all.return_value = handlers
            stats = await ToolCatalogSyncService(session).sync_tools()

        assert stats == {"created": 0, "updated": 0}
        session.add.assert_not_called()
        session.commit.assert_awaited_once()

    async def test_mixed_create_and_update(self):
        existing = Tool(slug="docs.read", name="Read docs", domains=["docs"])
        session = make_session_with_tools({"docs.read": existing})
        handlers = [
            FakeHandler(slug="docs.read", name="Read documents", domains=["docs"]),
            FakeHandler(slug="memory.search", name="Memory search"),
        ]

        with patch("app.services.tool_catalog_sync_service.ToolRegistry") as registry:
            registry.list_all.return_value = handlers
            stats = await ToolCatalogSyncService(session).sync_tools()

        assert stats == {"created": 1, "updated": 1}
        assert existing.name == "Read documents"
        created = session.add.call_args_list[-1].args[0]
        # No explicit domains on the handler: slug prefix is used.
        assert created.slug == "memory.search"
        assert created.domains == ["memory"]
