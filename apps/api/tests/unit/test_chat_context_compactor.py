from __future__ import annotations

from app.services.chat_context_compactor import (
    FocusCompactionPayload,
    _bounded_payload,
    _canonical_key,
    focus_compaction_payload,
)


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


def test_compactor_replaces_flat_scope_set_and_can_explicitly_clear_it() -> None:
    previous = {"scope_keys": ["company", "dcbox"], "scope_mode": "inherit", "scope_revision": 4}
    updated = focus_compaction_payload(
        previous, FocusCompactionPayload(scope_keys=["nims"]), {"company", "dcbox", "nims"},
    )
    assert updated is not None
    assert updated["scope_keys"] == ["nims"]
    assert updated["scope_mode"] == "replace"
    assert updated["suppress_scope_default"] is False
    assert updated["scope_revision"] == 5

    cleared = focus_compaction_payload(
        updated, FocusCompactionPayload(scope_keys=[]), {"company", "dcbox", "nims"},
    )
    assert cleared is not None
    assert cleared["scope_keys"] == []
    assert cleared["suppress_scope_default"] is True
    assert focus_compaction_payload(
        previous, FocusCompactionPayload(scope_keys=["removed"]), {"company", "dcbox"},
    ) is None
