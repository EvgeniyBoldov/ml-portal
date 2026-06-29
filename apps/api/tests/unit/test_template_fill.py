"""Unit tests for collection.template.fill helpers."""
from __future__ import annotations

import pytest

from app.agents.builtins.template_fill import (
    _fill_text,
    _substitute_placeholders,
    _PLACEHOLDER_RE,
)


def test_substitute_placeholders_basic():
    text = "Hello {{name}}, your code is {{code}}."
    values = {"name": "Alice", "code": "12345"}
    result, keys = _substitute_placeholders(text, values)
    assert result == "Hello Alice, your code is 12345."
    assert keys == {"name", "code"}


def test_substitute_placeholders_missing():
    text = "Hello {{name}}, missing {{undefined}}."
    values = {"name": "Alice"}
    result, keys = _substitute_placeholders(text, values)
    assert result == "Hello Alice, missing {{undefined}}."
    assert keys == {"name"}


def test_fill_text():
    content = b"User: {{user}}\nAmount: {{amount}}"
    values = {"user": "Bob", "amount": "99.50"}
    result = _fill_text(content, values)
    assert result == b"User: Bob\nAmount: 99.50"


def test_fill_text_no_placeholders():
    content = b"Static content"
    result = _fill_text(content, {})
    assert result == b"Static content"


def test_placeholder_regex():
    assert _PLACEHOLDER_RE.findall("{{a}} {{b_1}}") == ["a", "b_1"]
    assert _PLACEHOLDER_RE.findall("no placeholders") == []
    assert _PLACEHOLDER_RE.findall("{{mixed-CASE}}") == ["mixed-CASE"]
