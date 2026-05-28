from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from app.runtime.memory.summary_store import _load_v2_payload, _to_v2_payload
from app.runtime.memory.dto import SummaryDTO


def test_to_v2_payload_builds_structured_versioned_shape():
    dto = SummaryDTO(
        chat_id=uuid4(),
        goals=["g1"],
        done=["d1"],
        entities={"incident": "INC-42"},
        open_questions=["q1"],
        raw_tail="user: hi",
        last_updated_turn=7,
    )
    payload = _to_v2_payload(dto)
    assert payload["version"] == 2
    assert payload["last_updated_turn"] == 7
    assert payload["summary"]["goals"][0]["text"] == "g1"
    assert payload["summary"]["done"][0]["status"] == "completed"
    assert payload["summary"]["entities"]["incident"]["text"] == "INC-42"
    assert payload["raw"]["tail_text"] == "user: hi"
    assert payload["raw"]["turns"][0]["role"] == "user"


def test_load_v2_payload_handles_structured_format():
    row = SimpleNamespace(
        goals=[],
        done=[],
        entities={},
        open_questions=[],
        raw_tail="legacy-tail",
        last_updated_turn=2,
        summary_v2={
            "version": 2,
            "summary": {
                "goals": [{"text": "g2"}],
                "done": [{"text": "d2"}],
                "entities": {"incident": {"text": "INC-9"}},
                "open_questions": [{"text": "q2"}],
            },
            "raw": {"tail_text": "new-tail"},
            "last_updated_turn": 11,
        },
    )
    loaded = _load_v2_payload(row)
    assert loaded["goals"] == ["g2"]
    assert loaded["done"] == ["d2"]
    assert loaded["entities"] == {"incident": "INC-9"}
    assert loaded["open_questions"] == ["q2"]
    assert loaded["raw_tail"] == "new-tail"
    assert loaded["last_updated_turn"] == 11


def test_load_v2_payload_falls_back_to_legacy_columns():
    row = SimpleNamespace(
        goals=["g1"],
        done=["d1"],
        entities={"k": "v"},
        open_questions=["q1"],
        raw_tail="legacy",
        last_updated_turn=3,
        summary_v2={},
    )
    loaded = _load_v2_payload(row)
    assert loaded["goals"] == ["g1"]
    assert loaded["done"] == ["d1"]
    assert loaded["entities"] == {"k": "v"}
    assert loaded["open_questions"] == ["q1"]
    assert loaded["raw_tail"] == "legacy"
    assert loaded["last_updated_turn"] == 3
