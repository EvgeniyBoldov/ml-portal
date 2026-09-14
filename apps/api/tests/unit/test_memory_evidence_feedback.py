"""Pure unit coverage for evidence-feedback boundaries."""
from __future__ import annotations

from app.runtime.memory.evidence_feedback import bounded_document_evidence


def test_bounded_document_evidence_keeps_only_documentary_fields() -> None:
    evidence = bounded_document_evidence({
        "hits": [{
            "artifact_id": "doc-1", "source_name": "Network standard",
            "text": "x" * 4_000, "internal_trace": "must not persist",
        }]
    })

    assert evidence == [{
        "document_id": "doc-1", "label": "Network standard", "text": "x" * 3_000,
    }]


def test_bounded_document_evidence_rejects_non_document_results() -> None:
    assert bounded_document_evidence({"rows": [{"value": "x"}]}) == []
