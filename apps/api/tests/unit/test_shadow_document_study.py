from uuid import uuid4

import pytest
from pydantic import ValidationError

from types import SimpleNamespace

from app.runtime.memory.shadow_document_study import ShadowScreeningOutput, ShadowStudyItem, _scope_proposal
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


def test_scope_proposal_separates_applicability_mentions_and_unknown_names() -> None:
    scopes = {
        "team.arch": SimpleNamespace(scope_type="team"),
        "product.core": SimpleNamespace(scope_type="product"),
    }
    item = ShadowStudyItem(candidate_type="rule", subject="Deploy", scope_candidate="scoped",
                           scope_keys=["team.arch", "team.new"], mentioned_scope_keys=["product.core"],
                           unmatched_scope_names=["Новая команда"])
    applies, mentions, unmatched, proposed = _scope_proposal(item, scopes, {})
    assert applies == ["team.arch"]
    assert mentions == ["product.core"]
    assert unmatched == ["Новая команда", "team.new"]
    assert proposed == "unknown"
    global_item = item.model_copy(update={"scope_candidate": "global", "scope_keys": []})
    assert _scope_proposal(global_item, scopes, {})[3] == "global"
    project_item = item.model_copy(update={"scope_candidate": "project", "scope_keys": ["project.alpha"],
                                   "mentioned_scope_keys": [], "unmatched_scope_names": []})
    project_scopes = {"project.alpha": SimpleNamespace(scope_type="project")}
    assert _scope_proposal(project_item, project_scopes, {"alpha": object()})[3] == "project"


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
