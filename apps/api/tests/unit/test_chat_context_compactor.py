from __future__ import annotations

from app.services.chat_context_compactor import _bounded_payload, _canonical_key


def test_compactor_uses_stable_singleton_keys() -> None:
    assert _canonical_key("goal", "add", ["turn:1"], {"text": "continue"}) == ("active_goal", "update")
    assert _canonical_key("scope", "add", ["turn:1"], {"topic": "reports"}) == ("current_scope", "update")
    assert _canonical_key("recent_anchor", "add", ["turn:1"], {"intent": "continue"}) == ("recent_anchor", "update")


def test_compactor_bounds_payload_and_canonicalizes_decision_key() -> None:
    payload = _bounded_payload({"text": "x" * 700, "items": list(range(20)), "nested": {"not": "allowed"}})

    key, action = _canonical_key("decision", "update", ["turn:1"], payload)

    assert len(payload["text"]) == 600
    assert len(payload["items"]) == 10
    assert "nested" not in payload
    assert key.startswith("decision:")
    assert action == "add"
