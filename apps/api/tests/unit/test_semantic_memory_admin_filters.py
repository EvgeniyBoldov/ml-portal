"""Administrative memory lists include only approved claims and typed applicability."""
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.models.memory import MemoryItem
from app.services.semantic_memory_admin_service import _approved_item, _scope_filters
from app.runtime.memory.content_contracts import content_contract_error


def _sql(*predicates) -> str:
    return str(select(MemoryItem.id).where(*predicates).compile(dialect=postgresql.dialect()))


def test_approved_memory_requires_resolved_extraction_claim() -> None:
    sql = _sql(_approved_item())
    assert "memory_claims.approved_candidate_id" in sql
    assert "memory_extraction_candidates.resolution_status" in sql
    assert "memory_claims.lifecycle_status" in sql


def test_scope_filters_use_catalog_type_or_exact_scope() -> None:
    type_sql = _sql(*_scope_filters("team", None))
    assert "memory_scopes.scope_type" in type_sql
    assert "memory_claim_scopes" in type_sql
    exact_sql = _sql(*_scope_filters(None, uuid4()))
    assert "memory_scopes.id" in exact_sql
    global_sql = _sql(*_scope_filters("global", None))
    assert "NOT (EXISTS" in global_sql


def test_non_term_candidates_require_typed_content() -> None:
    assert content_contract_error("rule", {}) is not None
    assert content_contract_error("description", {}) is not None
    assert content_contract_error("term", {}) is not None
