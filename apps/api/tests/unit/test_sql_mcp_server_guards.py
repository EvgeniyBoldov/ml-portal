from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys

import pytest


_HERE = Path(__file__).resolve()
_CANDIDATES = []
for parent in _HERE.parents:
    _CANDIDATES.append(parent / "mcp" / "sql" / "server.py")
_SERVER_PATH = next((path for path in _CANDIDATES if path.exists()), None)
if _SERVER_PATH is None:
    pytest.skip(
        f"SQL MCP shim is unavailable in this test environment: {_CANDIDATES}",
        allow_module_level=True,
    )
_MCP_ROOT = _SERVER_PATH.parents[1]
if str(_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(_MCP_ROOT))
_SPEC = spec_from_file_location("sql_mcp_server_module", _SERVER_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError(f"Cannot load SQL MCP server module from {_SERVER_PATH}")
sql_server = module_from_spec(_SPEC)
_SPEC.loader.exec_module(sql_server)


def test_normalize_sql_blocks_write_statements_under_readonly_guard(monkeypatch):
    monkeypatch.setattr(sql_server, "SQL_MCP_REQUIRE_READONLY", True)

    try:
        sql_server._normalize_sql("insert into users(id) values (1)", None)  # noqa: SLF001
        raise AssertionError("Expected write SQL to be blocked")
    except ValueError as exc:
        assert "sql_write_blocked" in str(exc)

    try:
        sql_server._normalize_sql(
            "with changed as (delete from users where id=1 returning *) select * from changed",
            None,
        )  # noqa: SLF001
        raise AssertionError("Expected CTE write SQL to be blocked")
    except ValueError as exc:
        assert "sql_write_blocked" in str(exc)


def test_normalize_sql_allows_readonly_with_limit(monkeypatch):
    monkeypatch.setattr(sql_server, "SQL_MCP_REQUIRE_READONLY", True)
    normalized = sql_server._normalize_sql("select id from users", 50)  # noqa: SLF001
    assert normalized.lower().endswith("limit 50")


def test_redact_sensitive_text_hides_dsn_password_and_tokens():
    raw = (
        "dsn=postgresql://dbuser:super-secret@db:5432/app "
        "password=hunter2 token=abc123 api_key=qwerty"
    )
    redacted = sql_server._redact_sensitive_text(raw)  # noqa: SLF001
    assert "super-secret" not in redacted
    assert "hunter2" not in redacted
    assert "abc123" not in redacted
    assert "qwerty" not in redacted
    assert "***" in redacted
