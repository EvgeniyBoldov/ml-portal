"""Canonical MCP failure contract shared by Portal API and MCP adapters."""

from .failure import MCPFailure, MCPFailureCategory, MCPFailureKind, is_sensitive_key, normalize_failure, public_user_message, safe_diagnostic

__all__ = ["MCPFailure", "MCPFailureCategory", "MCPFailureKind", "is_sensitive_key", "normalize_failure", "public_user_message", "safe_diagnostic"]
