from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

import app.runtime.memory.search as search
from app.api.v1.routers.admin.semantic_memory import _candidate_approval_blockers
from app.runtime.memory.shadow_document_study import ShadowDocumentStudyService, ShadowStudyItem
from app.runtime.memory.shadow_memory_publication import ShadowMemoryPublicationService
from app.runtime.memory.shadow_memory_review import ShadowMemoryReviewService
from app.runtime.context_outcome import RuntimeOutcomeProjection
from app.services.chat_context_reducer import ChatContextReducer
from app.workers.tasks_shadow_document_memory import _attempt_message_matches, _trace_entity_id


def candidate(kind="rule", scope="global"):
    return NS(id=uuid4(), attempt_id=uuid4(), candidate_type=kind, subject="Example",
              aliases=[], unmatched_scope_names=[], unresolved_scope_references=[], scope_candidate=scope)


def proposal_item(role="applies_to", kind="rule"):
    return ShadowStudyItem(candidate_type=kind, subject="Example", scope_proposals=[
        {"scope_type": "product", "name": "Example", "term_subject": "Example", "role": role}])


def database(*, scalars=(), scalar=None):
    return NS(scalar=AsyncMock(return_value=scalar),
              scalars=AsyncMock(return_value=NS(all=lambda: list(scalars))), add=Mock(), flush=AsyncMock())


@pytest.mark.asyncio
async def test_term_scope_does_not_block_term_or_create_self_binding():
    term = candidate("term", None)
    db = database()
    await ShadowDocumentStudyService(db)._persist_scope_proposals(
        snapshot=NS(id=uuid4(), visibility_tenant_id=None), item=proposal_item(kind="term"),
        candidate=term, term_candidate_ids={"example": term.id}, section_ids=["s1"])
    assert db.add.call_count == 1
    assert db.add.call_args.args[0].status == "awaiting_term"
    assert await _candidate_approval_blockers(db, term.id, "term", None) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("role,blocked", [("applies_to", True), ("mentions", False)])
async def test_missing_term_blocks_only_required_scope(role, blocked):
    row = candidate()
    db = database()
    await ShadowDocumentStudyService(db)._persist_scope_proposals(
        snapshot=NS(id=uuid4(), visibility_tenant_id=None), item=proposal_item(role), candidate=row,
        term_candidate_ids={}, section_ids=["s1"])
    assert bool(row.unresolved_scope_references) == blocked
    assert row.scope_candidate == ("unknown" if blocked else "global")


@pytest.mark.asyncio
async def test_ambiguity_keeps_required_blocker_despite_another_valid_proposal():
    row = candidate(scope="scoped")
    db = database(scalars=[NS(scope_type="product", key="product.a", name="Example", aliases=[]),
                           NS(scope_type="product", key="product.b", name="Other", aliases=["Example"])])
    await ShadowDocumentStudyService(db)._persist_scope_proposals(
        snapshot=NS(id=uuid4(), visibility_tenant_id=None), item=proposal_item(), candidate=row,
        term_candidate_ids={"example": uuid4()}, section_ids=["s1"])
    assert row.scope_candidate == "unknown"
    assert row.unresolved_scope_references[0]["alternatives"] == ["product.a", "product.b"]
    assert not db.add.called


@pytest.mark.asyncio
@pytest.mark.parametrize("status,expected", [("resolved", "needs_review"), ("needs_review", "awaiting_term")])
async def test_published_term_reuse_and_pending_term_dependency(status, expected):
    row = candidate()
    glossary_id, term_id = uuid4(), uuid4()
    db = database()
    db.scalar.side_effect = [glossary_id, status, None, None]
    await ShadowDocumentStudyService(db)._persist_scope_proposals(
        snapshot=NS(id=uuid4(), visibility_tenant_id=None), item=proposal_item(), candidate=row,
        term_candidate_ids={"example": term_id}, section_ids=["s1"])
    proposal = db.add.call_args_list[0].args[0]
    assert proposal.status == expected
    assert proposal.glossary_term_id == (glossary_id if status == "resolved" else None)
    assert proposal.term_candidate_id == (None if status == "resolved" else term_id)
    assert proposal.source_term_candidate_id == term_id


@pytest.mark.asyncio
@pytest.mark.parametrize("params,error", [
    ({"project_keys": ["b"], "scope_ceiling_keys": ["project.a"]}, "scope_widening_denied"),
    ({"scope_keys": ["team.b"], "scope_ceiling_keys": ["team.a"]}, "scope_widening_denied"),
    ({"project_keys": ["b"], "scope_keys": ["project.a"]}, "conflicting_project_scope"),
    ({"project_keys": ["a"], "scope_keys": ["project.all"]}, "conflicting_project_scope"),
])
async def test_invalid_scope_stops_before_recall(monkeypatch, params, error):
    monkeypatch.setattr(search, "GlossaryService", lambda _: NS(list_confirmed_terms=AsyncMock(return_value=[])))
    recall = Mock()
    monkeypatch.setattr(search, "MemoryRecallService", recall)
    result = await search.MemorySearchService(NS()).search(query="rules", tenant_id=None, **params)
    assert result["success"] is False
    assert result["error_code"] == error
    assert not recall.called


def test_attempt_message_and_cursor_reject_stale_and_duplicate_delivery():
    attempt = NS(id=uuid4(), attempt_number=2, next_section=4)
    assert _attempt_message_matches(attempt, str(attempt.id), expected_cursor=4)
    assert not _attempt_message_matches(attempt, str(uuid4()), expected_cursor=4)
    assert not _attempt_message_matches(attempt, str(attempt.id), expected_cursor=0)
    assert not _attempt_message_matches(attempt, None, expected_cursor=4)
    attempt.attempt_number = 1
    assert _attempt_message_matches(attempt, None, expected_cursor=4)
    snapshot_id = uuid4()
    assert _trace_entity_id(snapshot_id, "study_sections", kind="stage", attempt_id=uuid4()) != _trace_entity_id(
        snapshot_id, "study_sections", kind="stage", attempt_id=uuid4())


@pytest.mark.asyncio
async def test_lock_refreshes_cached_snapshot_and_attempt():
    snapshot, attempt = NS(active_attempt_id=uuid4()), NS()
    db = database(scalar=snapshot)
    db.refresh = AsyncMock()
    service = ShadowDocumentStudyService(db)
    service.ensure_active_attempt = AsyncMock(return_value=attempt)
    assert await service.lock_active_attempt(uuid4()) == (snapshot, attempt)
    stmt = db.scalar.await_args.args[0]
    assert stmt.get_execution_options()["populate_existing"] is True
    db.refresh.assert_awaited_once_with(attempt, with_for_update=True)


@pytest.mark.asyncio
async def test_pending_scope_identity_participates_in_conflict_comparison():
    db = database(scalars=["product.proposed"])
    db.execute = AsyncMock(return_value=NS(scalars=lambda: NS(all=lambda: ["team.ops"])))
    assert await ShadowMemoryReviewService(db)._scope_keys(uuid4()) == {"team.ops", "product.proposed"}


@pytest.mark.asyncio
async def test_unresolved_required_scope_cannot_publish_as_global():
    row = candidate()
    row.resolution_status = "needs_review"
    row.snapshot_id = uuid4()
    row.unresolved_scope_references = [{"reason": "missing_term"}]
    db = database()
    db.get = AsyncMock(return_value=NS(document_id=uuid4()))
    publisher = ShadowMemoryPublicationService(db)
    publisher._required_candidate = AsyncMock(return_value=row)
    with pytest.raises(ValueError, match="unresolved required scope"):
        await publisher.approve(candidate_id=row.id, actor_id=None, reason=None)


def test_explicit_empty_replace_is_persisted_and_disables_project_default():
    projection = RuntimeOutcomeProjection(run_id="r", chat_id="c", chat_turn_id="t", terminal_state="completed",
        project_context={"scope_selection_explicit": True, "effective_scope_keys": [],
                         "effective_project_keys": [], "suppress_project_default": True})
    scope = next(op for op in ChatContextReducer().reduce(projection=projection, expected_revision=0) if op.kind == "scope")
    assert scope.payload["scope_keys"] == []
    assert scope.payload["project_keys"] == []
    assert scope.payload["suppress_project_default"] is True


def test_partial_project_selection_preserves_effective_team_focus():
    projection = RuntimeOutcomeProjection(run_id="r", chat_id="c", chat_turn_id="t", terminal_state="completed",
        project_context={"explicit_project_keys": ["a"], "effective_project_keys": ["a"],
                         "effective_scope_keys": ["team.ops", "project.a"]})
    scope = next(op for op in ChatContextReducer().reduce(projection=projection, expected_revision=0) if op.kind == "scope")
    assert scope.payload["scope_keys"] == ["team.ops", "project.a"]


@pytest.mark.asyncio
async def test_dispatch_intent_survives_queue_outage_and_resumes_current_cursor(monkeypatch):
    import app.workers.tasks_shadow_document_memory as worker
    attempt = NS(id=uuid4(), snapshot_id=uuid4(), next_section=3, status="queued")
    tenant = uuid4()
    db = NS(execute=AsyncMock(return_value=NS(all=lambda: [(attempt, tenant)])))
    delay = Mock(side_effect=ConnectionError("broker unavailable"))
    monkeypatch.setattr(worker.study_shadow_document_sections, "delay", delay)
    assert await worker.dispatch_pending_shadow_studies(db) == 0
    assert attempt.status == "queued" and attempt.next_section == 3
    delay.side_effect = None
    assert await worker.dispatch_pending_shadow_studies(db) == 1
    delay.assert_called_with(str(attempt.snapshot_id), str(tenant), str(attempt.id), 3)
