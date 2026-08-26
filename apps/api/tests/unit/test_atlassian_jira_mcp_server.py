from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys

import pytest


_HERE = Path(__file__).resolve()
_SERVER_PATH = next(
    (parent / "mcp" / "atlassian" / "server.py" for parent in _HERE.parents if (parent / "mcp" / "atlassian" / "server.py").exists()),
    None,
)
if _SERVER_PATH is None:
    pytest.skip("Atlassian Jira MCP shim is unavailable", allow_module_level=True)
_MCP_ROOT = _SERVER_PATH.parents[1]
if str(_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(_MCP_ROOT))
_SPEC = spec_from_file_location("atlassian_jira_mcp_server_module", _SERVER_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError(f"Cannot load Atlassian Jira MCP shim from {_SERVER_PATH}")
jira_server = module_from_spec(_SPEC)
_SPEC.loader.exec_module(jira_server)


def test_normalize_base_url_removes_jira_rest_api_suffix():
    assert jira_server._normalize_base_url("https://jira.example/rest/api/2/") == "https://jira.example"
    assert jira_server._normalize_base_url("https://jira.example/jira/rest/api/3") == "https://jira.example/jira"


def test_broker_credential_payload_uses_pat_and_never_needs_container_secret():
    headers = jira_server._extract_auth({"pat": "short-lived-pat"})
    assert headers == {"Authorization": "Bearer short-lived-pat"}
    assert jira_server._extract_base_url({"jira_url": "https://jira.example"}, {}) == "https://jira.example"


def test_jira_tools_are_bounded_and_write_tools_are_not_read_only():
    names = {tool["name"]: tool for tool in jira_server.TOOLS}
    assert names["jira_search_issues"]["annotations"]["readOnlyHint"] is True
    assert names["jira_create_issue"]["annotations"]["readOnlyHint"] is False
    assert jira_server._limit(9999) == jira_server.MAX_RESULTS


def test_issue_key_is_url_encoded_before_becoming_a_path_segment():
    assert jira_server._issue_path_key("OPS-1/../../admin") == "OPS-1%2F..%2F..%2Fadmin"


def test_jira_mcp_error_log_message_redacts_credentials():
    message = jira_server._safe_error_message(
        ValueError('Broker failed: token="secret-token" password=secret-password Authorization: Bearer abc123')
    )

    assert "secret-token" not in message
    assert "secret-password" not in message
    assert "abc123" not in message
    assert "token=***" in message
    assert "password=***" in message
