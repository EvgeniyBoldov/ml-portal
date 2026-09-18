from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.runtime.memory.shadow_document_study import ShadowScreeningOutput, ShadowStudyItem
from app.runtime.memory.shadow_study_prompts import (
    SHADOW_DOCUMENT_SCREENING_PROMPT,
    SHADOW_DOCUMENT_STUDY_PROMPT,
    SHADOW_MEMORY_CONFLICT_PROMPT,
)
from app.workers.tasks_shadow_document_memory import _source_id


def test_shadow_study_prompts_are_code_owned_and_require_evidence() -> None:
    assert "candidate ledger" in SHADOW_DOCUMENT_STUDY_PROMPT
    assert "evidence_section_id" in SHADOW_DOCUMENT_STUDY_PROMPT
    assert "теневого" in SHADOW_DOCUMENT_SCREENING_PROMPT
    assert "ничего не публикуй" in SHADOW_MEMORY_CONFLICT_PROMPT


def test_shadow_study_output_rejects_invalid_candidate_shape() -> None:
    with pytest.raises(ValidationError):
        ShadowStudyItem(candidate_type="unknown", subject="x")

    item = ShadowStudyItem(
        candidate_type="term", subject="Gateway", content={"definition": "API gateway"},
        evidence_section_ids=["section-1"], existing_candidate_id=uuid4(),
    )
    assert item.operation == "new"
    assert ShadowScreeningOutput(decision="study").document_kind == "unknown"


def test_shadow_study_uses_index_group_source_id_once() -> None:
    assert _source_id([{"source_id": "first"}, {"source_id": "second"}]) == "first"
    assert _source_id({"source_id": "single"}) == "single"
    assert _source_id([]) == ""
