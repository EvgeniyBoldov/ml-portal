"""Contract coverage for the P0 document-memory staging schema."""
from app.models.document_memory_staging import (
    DocumentMemorySnapshot,
    GlossaryMeaning,
    GlossaryMeaningProjectBinding,
    GlossaryMeaningSource,
    GlossaryTerm,
    MemoryCandidateProjectBinding,
    MemoryCandidateDecision,
    MemoryConflictCase,
    MemoryConflictMember,
    MemoryExtractionCandidate,
)


def _constraint_names(model) -> set[str]:
    return {constraint.name for constraint in model.__table__.constraints if constraint.name}


def test_candidate_keeps_scope_resolution_separate_from_project_bindings() -> None:
    columns = MemoryExtractionCandidate.__table__.c

    assert {"scope_candidate", "resolution_status", "resolution_method", "resolution_rationale"} <= set(columns.keys())
    assert "project_id" not in columns.keys()
    assert "ck_memory_candidate_scope" in _constraint_names(MemoryExtractionCandidate)
    assert "ck_memory_candidate_resolution" in _constraint_names(MemoryExtractionCandidate)

    binding_columns = MemoryCandidateProjectBinding.__table__.c
    assert {"candidate_id", "project_id", "role", "status", "method", "confidence"} <= set(binding_columns.keys())
    assert "ck_memory_candidate_project_binding_role" in _constraint_names(MemoryCandidateProjectBinding)


def test_glossary_term_is_separate_from_its_scoped_meanings_and_evidence() -> None:
    assert {"canonical_term", "normalized_term", "aliases"} <= set(GlossaryTerm.__table__.c.keys())
    assert {"term_id", "definition", "scope_candidate", "resolution_status"} <= set(GlossaryMeaning.__table__.c.keys())
    assert {"meaning_id", "project_id", "status", "method"} <= set(GlossaryMeaningProjectBinding.__table__.c.keys())
    assert {"meaning_id", "candidate_id", "legacy_glossary_observation_id", "evidence_section_ids"} <= set(GlossaryMeaningSource.__table__.c.keys())


def test_snapshot_is_a_document_revision_not_a_public_memory_item() -> None:
    columns = DocumentMemorySnapshot.__table__.c

    assert {"document_id", "canonical_checksum", "extractor_version", "visibility_tenant_id", "status", "metrics"} <= set(columns.keys())
    assert "memory_item_id" not in columns.keys()


def test_staging_visibility_conflicts_and_decisions_are_explicit() -> None:
    assert "visibility_tenant_id" in MemoryExtractionCandidate.__table__.c
    assert {"kind", "status", "visibility_tenant_id", "evidence"} <= set(MemoryConflictCase.__table__.c.keys())
    assert {"conflict_id", "candidate_id", "role"} <= set(MemoryConflictMember.__table__.c.keys())
    assert {"candidate_id", "actor_user_id", "action", "payload"} <= set(MemoryCandidateDecision.__table__.c.keys())
