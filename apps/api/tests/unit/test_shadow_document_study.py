from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.runtime.memory.shadow_document_study import ShadowScreeningOutput, ShadowStudyItem
from app.runtime.memory.shadow_study_prompts import (
    SHADOW_DOCUMENT_SCREENING_PROMPT,
    SHADOW_DOCUMENT_STUDY_PROMPT,
    SHADOW_MEMORY_CONFLICT_PROMPT,
    document_memory_prompt,
)
from app.workers.tasks_shadow_document_memory import _source_id, _trace_entity_id


def test_shadow_study_prompt_defaults_and_operator_overrides_require_evidence() -> None:
    assert "candidate ledger" in SHADOW_DOCUMENT_STUDY_PROMPT
    assert "evidence_section_id" in SHADOW_DOCUMENT_STUDY_PROMPT
    assert "теневого" in SHADOW_DOCUMENT_SCREENING_PROMPT
    assert "ничего не публикуй" in SHADOW_MEMORY_CONFLICT_PROMPT
    assert document_memory_prompt({}, stage="study") == SHADOW_DOCUMENT_STUDY_PROMPT
    operator_prompt = document_memory_prompt({"document_memory_study_prompt": "операторский промпт"}, stage="study")
    assert operator_prompt.startswith("операторский промпт")
    assert "scope_catalog" in operator_prompt


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


def test_shadow_study_trace_entities_are_stable_and_batch_scoped() -> None:
    snapshot_id = uuid4()
    assert _trace_entity_id(snapshot_id, "study_sections", cursor=0, kind="stage") == _trace_entity_id(
        snapshot_id, "study_sections", cursor=0, kind="stage",
    )
    assert _trace_entity_id(snapshot_id, "study_sections", cursor=0, kind="execution") != _trace_entity_id(
        snapshot_id, "study_sections", cursor=0, kind="stage",
    )
    assert _trace_entity_id(snapshot_id, "study_sections", cursor=0, kind="stage") != _trace_entity_id(
        snapshot_id, "study_sections", cursor=2, kind="stage",
    )
