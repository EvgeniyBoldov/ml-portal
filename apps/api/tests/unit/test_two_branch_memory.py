from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.runtime.memory.effective_scope import memory_visible_for_scope
from app.runtime.memory.search import MemorySearchService, normalize_query_keys
from app.runtime.memory.scope_precedence import apply_scope_precedence, scope_sets_overlap, has_project_override
from app.runtime.memory.shadow_document_study import ShadowStudyOutput
from app.services.chat_context_compactor import FocusCompactionPayload, focus_compaction_payload
from app.runtime.pipeline import _base_scope_context, scope_fact_defaults
from app.models.memory import FactScope


@pytest.mark.parametrize("bound,query,expected", [
    ([], [], True), ([], ["project.a"], False),
    (["team.all"], [], True), (["team.ops"], [], False),
    (["team.ops"], ["team.ops"], True), (["team.ops"], ["team.net"], False),
    (["project.all"], [], False), (["project.all"], ["project.a"], True),
    (["project.a"], ["project.b"], False),
    (["project.a"], ["project.a"], True),
    (["team.all", "project.a"], ["project.a"], True),
    (["team.ops", "project.a"], ["project.a"], False),
    (["team.ops", "project.a"], ["team.ops", "project.a"], True),
    (["team.ops", "project.a"], ["team.ops", "project.b"], False),
    (["team.ops", "project.a", "project.b"], ["team.ops", "project.b"], True),
])
def test_branch_matching_matrix(bound, query, expected):
    assert memory_visible_for_scope({"scope_keys": bound}, query) is expected


@pytest.mark.parametrize("branch,keys", [("team", ["all"]), ("team", ["project.a"]), ("project", [""])])
def test_query_rejects_universal_and_wrong_branch(branch, keys):
    with pytest.raises(ValueError):
        normalize_query_keys(keys, branch)


@pytest.mark.asyncio
async def test_projects_are_separate_and_agent_can_refine_initial_focus():
    service = MemorySearchService(object())
    service._search_context = AsyncMock(side_effect=[
        {"items": [{"id": "a"}], "projects": [{"key": "a"}], "facts": [], "glossary": [], "uncertainties": [], "search_scope": {}},
        {"items": [{"id": "b"}], "projects": [{"key": "b"}], "facts": [], "glossary": [], "uncertainties": [], "search_scope": {}},
    ])
    result = await service.search(query="rules", tenant_id=None, team_keys=["net"], project_keys=["a", "b"],
        context_scope_keys=["team.old", "project.old"], scope_ceiling_keys=["project.old"])
    assert [call.kwargs["scope_keys"] for call in service._search_context.await_args_list] == [
        ["team.net", "project.a"], ["team.net", "project.b"]]
    assert [group["items"] for group in result["groups"]] == [[{"id": "a"}], [{"id": "b"}]]


@pytest.mark.asyncio
async def test_explicit_empty_project_does_not_inherit_chat_project():
    service = MemorySearchService(object())
    service._search_context = AsyncMock(return_value={"items": [], "projects": [], "facts": [], "glossary": [], "uncertainties": [], "search_scope": {}})
    await service.search(query="rules", tenant_id=None, project_keys=[], context_scope_keys=["team.ops", "project.a"])
    assert service._search_context.await_args.kwargs["scope_keys"] == ["team.ops"]


def test_only_proven_conflict_suppresses_universal_rule():
    universal = {"id": "all", "selected_claim_id": "c-all", "scope_keys": ["project.all"], "content": {"statement": "Netbox"}}
    project = {"id": "a", "selected_claim_id": "c-a", "scope_keys": ["project.a"], "content": {"statement": "Customer inventory"}}
    assert apply_scope_precedence([universal, project], [uuid4()])[0] == [universal, project]
    project["overrides_claim_ids"] = ["c-all"]
    assert apply_scope_precedence([universal, project], [uuid4()])[0] == [project]
    assert not scope_sets_overlap({"project.a"}, {"project.b"})
    assert not scope_sets_overlap(set(), {"project.all"})
    assert scope_sets_overlap({"project.a", "team.ops"}, {"project.all", "team.all"})
    assert has_project_override({"project.all"}, {"project.a"})


def test_compactor_changes_one_branch_and_preserves_other():
    payload = focus_compaction_payload({"scope_keys": ["team.ops", "project.a"], "team_keys": ["ops"], "project_keys": ["a"]},
        FocusCompactionPayload(project_keys=["b"]), {"team.ops", "project.a", "project.b"})
    assert payload["team_keys"] == ["ops"]
    assert payload["project_keys"] == ["b"]
    assert payload["scope_keys"] == ["team.ops", "project.b"]
    cleared = focus_compaction_payload(payload, FocusCompactionPayload(project_keys=[]), {"team.ops", "project.b"})
    assert cleared["suppress_project_default"] and cleared["project_keys"] == []
    assert focus_compaction_payload(payload, FocusCompactionPayload(team_keys=["all"]), {"team.ops"}) is None
    assert focus_compaction_payload(payload, FocusCompactionPayload(project_keys=["unknown"]), {"team.ops"}) is None


def test_extraction_accepts_atom_all_but_not_product():
    output = ShadowStudyOutput.model_validate({"items": [{"candidate_type": "rule", "subject": "Учёт", "scope_candidate": "scoped",
        "team_keys": ["all"], "project_keys": ["a"], "content": {"statement": "Вести учёт", "effect": "require"}}]})
    assert output.items[0].scope_keys == ["team.all", "project.a"]
    with pytest.raises(ValidationError):
        ShadowStudyOutput.model_validate({"items": [{"candidate_type": "rule", "subject": "Учёт", "scope_keys": ["product.iaas"],
            "content": {"statement": "Вести учёт", "effect": "require"}}]})


@pytest.mark.asyncio
async def test_two_axis_defaults_use_user_then_tenant_and_explicit_clear(monkeypatch):
    from app.services import memory_scope_catalog
    rows = [SimpleNamespace(id=uuid4(), key=key, scope_type=key.split('.')[0], name=key, is_all=False)
            for key in ["team.ops", "team.net", "project.a", "project.b"]]
    monkeypatch.setattr(memory_scope_catalog, "list_memory_scopes", AsyncMock(return_value=rows))
    facts = [SimpleNamespace(scope=FactScope.TENANT, subject="tenant.team_scope", metadata={"team_keys": ["ops"]}),
             SimpleNamespace(scope=FactScope.TENANT, subject="tenant.project_scope", metadata={"project_keys": ["a"]}),
             SimpleNamespace(scope=FactScope.USER, subject="user.team_scope", metadata={"team_keys": ["net"]})]
    focus = await _base_scope_context(object(), chat_context={}, project_defaults=[], facts=facts)
    assert set(focus.keys) == {"team.net", "project.a"}
    assert scope_fact_defaults(facts, "team") == (["net"], "user_default")
    focus = await _base_scope_context(object(), chat_context={"focus": {"suppress_project_default": True}}, project_defaults=["b"], facts=facts)
    assert focus.keys == ["team.net"]


@pytest.mark.asyncio
async def test_compactor_consumes_question_and_confirmation_and_keeps_revision(monkeypatch):
    from app.services import memory_scope_catalog
    from app.services.chat_context_compactor import ChatContextCompactor, _CompactionOutput
    rows = [SimpleNamespace(key="project.b", name="B", aliases=[], is_all=False)]
    monkeypatch.setattr(memory_scope_catalog, "list_memory_scopes", AsyncMock(return_value=rows))
    compactor = ChatContextCompactor.__new__(ChatContextCompactor)
    compactor._session = object()
    compactor._structured = SimpleNamespace(
        role_service=SimpleNamespace(get_role_config=AsyncMock(return_value={})),
        _compile_role_prompt=lambda config, override, schema: "base",
        invoke=AsyncMock(return_value=SimpleNamespace(value=_CompactionOutput.model_validate({"operations": [{
            "kind": "scope", "action": "update", "item_key": "current_scope", "source_ids": ["message:answer"],
            "payload": {"project_keys": ["project.b"]}}]}))))
    dialogue = [{"role": "assistant", "content": "Вы имеете в виду проект B?"}, {"role": "user", "content": "Да"}]
    operations = await compactor.propose(snapshot={"focus": {"team_keys": ["ops"], "scope_keys": ["team.ops"]}},
        recent_dialogue=dialogue, outcome={}, valid_source_ids=["message:answer"], expected_revision=7,
        chat_id=str(uuid4()), user_id=str(uuid4()), tenant_id=str(uuid4()))
    assert operations[0].expected_revision == 7
    assert operations[0].payload["project_keys"] == ["b"]
    assert operations[0].payload["team_keys"] == ["ops"]
    assert compactor._structured.invoke.await_args.kwargs["payload"]["recent_dialogue"] == dialogue


@pytest.mark.asyncio
async def test_scope_can_be_staged_from_document_without_glossary_term():
    from unittest.mock import Mock
    from app.runtime.memory.shadow_document_study import ShadowDocumentStudyService, ShadowStudyItem
    from app.models.document_memory_staging import MemoryScopeProposal
    db = SimpleNamespace(scalar=AsyncMock(return_value=None),
        scalars=AsyncMock(return_value=SimpleNamespace(all=lambda: [])), add=Mock(), flush=AsyncMock())
    candidate = SimpleNamespace(id=uuid4(), attempt_id=uuid4(), candidate_type="rule", scope_candidate="unknown",
        unresolved_scope_references=[], unmatched_scope_names=[])
    item = ShadowStudyItem(candidate_type="rule", subject="Учёт", scope_proposals=[
        {"scope_type": "project", "name": "Заказчик A", "project_type": "IAAS"}])
    await ShadowDocumentStudyService(db)._persist_scope_proposals(snapshot=SimpleNamespace(id=uuid4(), visibility_tenant_id=None),
        item=item, candidate=candidate, term_candidate_ids={}, section_ids=["s1"])
    proposal = db.add.call_args_list[0].args[0]
    assert isinstance(proposal, MemoryScopeProposal)
    assert proposal.status == "needs_review"
    assert proposal.term_candidate_id is None and proposal.glossary_term_id is None
    assert proposal.evidence_section_ids == ["s1"] and proposal.project_type == "IAAS"
    assert candidate.scope_candidate == "scoped"


@pytest.mark.asyncio
async def test_document_grounded_scope_approval_does_not_require_or_create_term():
    from unittest.mock import Mock
    from app.runtime.memory.shadow_memory_publication import ShadowMemoryPublicationService
    from app.models.document_memory_staging import MemoryScopeProposal
    from app.models.memory_scope import MemoryScopeGlossaryTerm
    proposal = MemoryScopeProposal(id=uuid4(), snapshot_id=uuid4(), scope_type="team", proposed_key="team.net",
        normalized_key="net", name="Сетевики", aliases=[], term_candidate_id=None, glossary_term_id=None, status="needs_review")
    db = SimpleNamespace(scalar=AsyncMock(return_value=None), add=Mock(), flush=AsyncMock(), get=AsyncMock(return_value=None),
        execute=AsyncMock(return_value=SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: []))))
    service = ShadowMemoryPublicationService(db)
    service._required_scope_proposal = AsyncMock(return_value=proposal)
    result = await service.approve_scope_proposal(proposal_id=proposal.id, actor_id=None)
    assert result.status == "approved"
    assert not any(isinstance(call.args[0], MemoryScopeGlossaryTerm) for call in db.add.call_args_list)


@pytest.mark.asyncio
async def test_confirmed_project_from_previous_question_is_not_blocked_by_initial_focus(monkeypatch):
    from app.runtime import turn_preflight
    from app.runtime.turn_preflight import TurnPreflight, TurnPreflightDecision, MemoryRequest
    decision = TurnPreflightDecision(route="recall", memory_request=MemoryRequest(query="rules", direction="project rules"),
        scope_selection={"keys": ["project.b"], "rationale": "User confirmed B"})
    preflight = TurnPreflight.__new__(TurnPreflight)
    preflight._session = object()
    preflight._llm = SimpleNamespace(invoke=AsyncMock(return_value=SimpleNamespace(value=decision)))
    resolve = AsyncMock(return_value=[SimpleNamespace(key="project.b")])
    monkeypatch.setattr(turn_preflight, "resolve_memory_scopes", resolve)
    result = await preflight.decide(user_request="Да", mechanical_lookup={"scope_candidates": []},
        project_context={"effective_scope_keys": ["project.a"]},
        recent_dialogue=[{"role": "assistant", "content": "Вы про проект B?"}, {"role": "user", "content": "Да"}])
    assert result.route == "recall"
    assert result.scope_selection.keys == ["project.b"]
    resolve.assert_awaited_once()
