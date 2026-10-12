import json

import pytest
from pydantic import ValidationError

from app.runtime.memory.hipporag_document_study import _projection_batches, _relevant_ledger, _section_output_schema


@pytest.mark.parametrize("evidence", [[], ["section-1"], ["invented"]])
def test_projection_rejects_missing_or_foreign_evidence(evidence: list[str]) -> None:
    schema = _section_output_schema(["section-2"])
    item = {"candidate_type": "description", "subject": "DNS",
            "content": {"summary": "DNS uses port 53"}, "evidence_section_ids": evidence}
    with pytest.raises(ValidationError):
        schema.model_validate({"items": [item]})
    item["evidence_section_ids"] = ["section-2"]
    assert schema.model_validate({"items": [item]}).items[0].evidence_section_ids == ["section-2"]


def test_large_ledger_preserves_complete_relevant_candidates_within_budget() -> None:
    relevant = {"id": "dns", "subject": "DNS", "content": {"summary": "DNS",
                "conditions": ["only after approval"]}}
    unrelated = {"id": "other", "subject": "Unrelated", "content": {"summary": "x" * 10000}}
    oversized = {"id": "large", "subject": "DNS", "content": {"summary": "x" * 10000}}
    selected = _relevant_ledger([oversized, unrelated, relevant] * 100, [{"text": "DNS settings"}])
    assert selected
    assert all(item == relevant for item in selected)
    assert sum(len(json.dumps(item, ensure_ascii=False).encode("utf-8")) for item in selected) <= 5000
    assert relevant["content"]["conditions"] == ["only after approval"]


def test_projection_batches_keep_every_passage_and_its_evidence() -> None:
    passages = [{"section_id": "section-2", "text": "текст " * 100, "triples": []} for _ in range(30)]
    batches = _projection_batches(passages)
    assert len(batches) > 1
    assert [passage for batch in batches for passage in batch] == passages
    assert all(sum(len(json.dumps(passage, ensure_ascii=False).encode("utf-8")) for passage in batch) <= 6000
               for batch in batches)


def test_projection_validates_scope_before_combining_batches() -> None:
    schema = _section_output_schema(["section-2"])
    with pytest.raises(ValidationError, match="only team and project"):
        schema.model_validate({"items": [{"candidate_type": "description", "subject": "DNS",
            "content": {"summary": "DNS uses port 53"}, "evidence_section_ids": ["section-2"],
            "scope_keys": ["network.infrastructure"]}]})
