"""Administrative memory lists include only approved claims and typed applicability."""
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.dialects import postgresql

from app.models.memory import MemoryClaim, MemoryItem, MemoryItemSource
from app.services.semantic_memory_admin_service import _approved_item, _scope_filters
from app.runtime.memory.content_contracts import content_contract_error


def _sql(*predicates) -> str:
    return str(select(MemoryItem.id).where(*predicates).compile(dialect=postgresql.dialect()))


def test_approved_memory_requires_resolved_extraction_claim() -> None:
    sql = _sql(_approved_item())
    assert "approved_candidate_id" in sql
    assert "memory_extraction_candidates.resolution_status" in sql
    assert "memory_claims_1.lifecycle_status" in sql


def test_approved_memory_list_query_compiles_with_claim_join_and_scope_filter() -> None:
    # The admin list also joins claims to count them. The publication predicate
    # must correlate to its immediate EXISTS, not remove that outer join's FROM.
    stmt = (
        select(MemoryItem.id, func.count(func.distinct(MemoryItemSource.id)),
               func.count(func.distinct(MemoryClaim.id)))
        .outerjoin(MemoryItemSource, MemoryItemSource.memory_item_id == MemoryItem.id)
        .outerjoin(MemoryClaim, (MemoryClaim.memory_item_id == MemoryItem.id)
                   & (MemoryClaim.lifecycle_status == "active"))
        .where(_approved_item(), *_scope_filters("team", None))
        .group_by(MemoryItem.id)
    )
    compiled = stmt.compile(dialect=postgresql.dialect())
    assert "memory_extraction_candidates" in str(compiled)
    assert "memory_scopes.scope_type" in str(compiled)


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
