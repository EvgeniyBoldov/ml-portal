from uuid import uuid4
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.runtime.memory.effective_scope import (
    EffectiveScopeContext, ScopeIdentity, ScopeSelection, merge_selection, task_scope,
    memory_visible_for_scope, project_memory_context,
)
from app.runtime.orchestrator import GraphOrchestrator, _task_memory_context
from app.runtime.orchestrator_contracts import IterationProposal
from app.runtime.plan_store import PlanValidationError, InMemoryPlanStore
from app.runtime.orchestrator_contracts import PlannerContext, PlanRequest
from app.runtime.input_builders import PlannerInputBuilder
from app.runtime.memory import mechanical_lookup
from app.runtime.memory.mechanical_lookup import MechanicalLookupService
from app.runtime.turn_preflight import TurnPreflightDecision, _canonical_scope_selection
from app.runtime.memory.turn_recall import recall_with_stable_scope
from app.runtime.agent_executor import AgentExecutor
from app.runtime.orchestrator_contracts import TaskRequest


def identity(key, source="chat_focus"):
    return ScopeIdentity(id=str(uuid4()), key=key, type="scope", name=key, source=source)


def test_turn_selection_replaces_flat_set_and_records_mention_separately():
    parent = EffectiveScopeContext(revision=4, selected=[identity("project.a"), identity("team.ops")],
        ceiling_keys=["project.a", "team.ops"])
    identities = {"team.data": identity("team.data", "turn"), "product.core": identity("product.core", "turn")}
    result = merge_selection(parent, ScopeSelection(keys=["team.data"], mentioned_keys=["product.core"]), identities, source="turn")
    assert result.keys == ["team.data"]
    assert [item.key for item in result.mentioned] == ["product.core"]
    assert result.revision == 5


def test_explicit_replace_empty_clears_all_scopes_and_ceiling():
    parent = EffectiveScopeContext(selected=[identity("project.a"), identity("team.ops")],
                                  ceiling_keys=["project.a", "team.ops"])
    result = merge_selection(parent, ScopeSelection(mode="replace"), {}, source="turn")
    assert result.keys == [] and result.ceiling_keys == [] and result.explicit_clear


def test_task_subset_cannot_widen():
    parent = EffectiveScopeContext(selected=[identity("project.a"), identity("project.b"), identity("team.ops")],
        ceiling_keys=["project.a", "project.b", "team.ops"])
    child = task_scope(parent, ScopeSelection(keys=["project.b"]))
    assert child.keys == ["project.b"]
    with pytest.raises(ValueError, match="scope_widening_denied"):
        task_scope(parent, ScopeSelection(keys=["product.core"]))
    clear = task_scope(parent, ScopeSelection(mode="replace"))
    assert clear.keys == [] and clear.explicit_clear


def test_planner_request_exposes_scope_contract_and_task_compiler_persists_subset():
    context = EffectiveScopeContext(selected=[identity("project.a"), identity("team.ops")],
                                    ceiling_keys=["project.a", "team.ops"])
    request = PlanRequest(context=PlannerContext(goal="goal", trigger="initial", execution_ledger={},
                             scope_context=context.model_payload()))
    payload = PlannerInputBuilder().build_graph_request(request)
    assert payload["scope_context"]["ceiling_keys"] == ["project.a", "team.ops"]
    proposal = IterationProposal.model_validate({"terminal": "planner", "tasks": [{
        "task_id": "t", "executor": "worker", "intent": "compare", "instructions": "Compare projects",
        "scope_keys": ["project.a"], "scope_reason": "The task only compares project A.",
    }]})
    compiled = GraphOrchestrator._compile(proposal, [{"slug": "worker", "supports_dynamic_contracts": True}],
        {"tasks": [], "needs": [], "bindings": [], "resolutions": []}, context.model_payload())
    assert compiled.tasks[0].scope_context["keys"] == ["project.a"]


def test_task_memory_projection_does_not_inherit_planner_search_memory():
    request = type("Task", (), {"scope_context": {"keys": ["project.a", "team.ops"]},
                                "intent": "check", "instructions": "check", "inputs": {}})()
    recall = {"type": "memory_recall", "items": [
        {"id": "a", "scope_keys": ["project.a", "team.ops"]},
        {"id": "b", "scope_keys": ["project.b"]},
        {"id": "c", "scope_keys": ["project.a", "team.other"]},
        {"id": "global"},
    ]}
    assert _task_memory_context(request, [recall]) == []
    fact = {"scope": "user", "subject": "role", "value": "engineer"}
    assert _task_memory_context(request, [fact, recall]) == [fact]


@pytest.mark.asyncio
async def test_mechanical_lookup_resolves_aliases_to_scope_identity_and_respects_ceiling(monkeypatch):
    rows = [
        SimpleNamespace(id=uuid4(), key="team.platform", scope_type="team", name="Platform",
                        aliases=["infra group"], is_all=False),
        SimpleNamespace(id=uuid4(), key="team.support", scope_type="team", name="Support",
                        aliases=[], is_all=False),
    ]
    monkeypatch.setattr(mechanical_lookup, "list_memory_scopes", AsyncMock(return_value=rows))
    session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(all=lambda: [])))
    service = MechanicalLookupService(session)
    service._projects.list_projects = AsyncMock(return_value=[])
    service._glossary.list_confirmed_terms = AsyncMock(return_value=[])

    result = await service.lookup(query="rules for infra group", tenant_id=None,
                                  scope_ceiling_keys=["team.platform"])

    assert [item["key"] for item in result["scope_candidates"]] == ["team.platform"]
    assert result["scope_candidates"][0]["matched_forms"] == ["infra group"]
    assert result["scope_ambiguities"] == []


def test_all_scope_applicability_matches_read_side_semantics():
    item = {"scope_keys": ["project.all", "team.ops"]}
    assert memory_visible_for_scope(item, ["project.a", "team.ops"])
    assert memory_visible_for_scope(item, ["project.all", "team.ops"])
    assert not memory_visible_for_scope(item, ["project.a"])


def test_nested_search_projection_keeps_values_and_sources_in_the_task_scope():
    a = {"id": "a", "scope_keys": ["project.a"], "source_references": [{"document_id": "doc-a"}]}
    b = {"id": "b", "scope_keys": ["project.b"], "source_references": [{"document_id": "doc-b"}]}
    entry = {"type": "planner_memory_result", "result": {"items": [a, b], "count": 2,
        "memory_context": {"type": "memory_recall", "applicable_rules": [a, b],
                           "source_references": [*a["source_references"], *b["source_references"]]}}}
    projected = project_memory_context(entry, ["project.a"])
    assert projected["result"]["count"] == 1
    assert projected["result"]["memory_context"]["applicable_rules"] == [a]
    assert projected["result"]["memory_context"]["source_references"] == [{"document_id": "doc-a"}]
    assert entry["result"]["count"] == 2  # Shared plan evidence is immutable.


def test_task_cannot_restore_parent_selection_when_ceiling_was_explicitly_cleared():
    parent = EffectiveScopeContext(selected=[identity("project.a")], ceiling_keys=[])
    with pytest.raises(ValueError, match="scope_widening_denied"):
        task_scope(parent, ScopeSelection())


def test_store_scope_validation_cannot_be_bypassed_by_skipping_compiler():
    store = InMemoryPlanStore()
    parent = EffectiveScopeContext(selected=[identity("project.a")], ceiling_keys=["project.a"])
    plan = store.create(goal="goal", root_run_id=str(uuid4()), tenant_id=str(uuid4()),
                        scope_context=parent.model_payload())
    proposal = IterationProposal.model_validate({"terminal": "planner", "tasks": [{
        "task_id": "t", "executor": "worker", "intent": "check", "instructions": "check",
        "scope_keys": ["project.b"], "scope_reason": "Try B",
    }]})
    with pytest.raises(PlanValidationError, match="widened"):
        store.apply_iteration(plan["id"], proposal)


def test_planner_search_history_keeps_facts_and_all_original_passages():
    store = InMemoryPlanStore()
    core = [{"scope": "user", "subject": "role", "value": "engineer"},
            {"type": "project_context"}, {"type": "memory_recall"}]
    plan = store.create(goal="goal", root_run_id=str(uuid4()), tenant_id=str(uuid4()), memory_context=core)
    store.update_memory_context(plan["id"], [{"type": "planner_memory_result", "query_key": str(i),
        "result": {"groups": [{"scope_slug": "company", "success": True, "items": [{"text": f"passage {i}"}]}]}}
        for i in range(35)])
    assert plan["memory_context"][:2] == core[:2]
    from app.runtime.memory.document_memory import document_memory
    [memory] = document_memory(plan["memory_context"])
    assert len(memory["groups"][0]["items"]) == 35
    assert memory["groups"][0]["items"][0]["text"] == "passage 0"



def test_agent_receives_planner_search_statements_even_after_many_user_facts():
    recall = {"type": "memory_recall", "applicable_rules": [
        {"subject": "deploy", "scope_keys": ["team.ops"], "content": {"statement": "Approval required"}}
    ]}
    task = TaskRequest(task_id="t", executor="worker", intent="check", instructions="Check deploy",
        scope_context={"keys": ["team.ops"]}, memory_context=[
            *[{"scope": "user", "subject": f"fact{i}", "value": "value"} for i in range(15)],
            {"type": "planner_memory_result", "result": {"memory_context": recall}},
        ])
    text = AgentExecutor._build_sub_messages([], task, "goal")[-1]["content"]
    assert "Approval required" in text
    assert "scopes=team.ops" in text
    assert "[Task scope]" in text


def test_shared_and_legacy_scope_selections_must_agree():
    def decision(shared, legacy):
        return TurnPreflightDecision.model_validate({"route": "planner", "scope_selection": shared,
            "task_brief": {"goal": "goal", "direction": "check", "expected_result": "result", **legacy}})
    with pytest.raises(ValueError, match="conflicting_scope_selection"):
        _canonical_scope_selection(decision({"keys": ["team.ops"]}, {"scope_keys": ["team.data"]}))
    with pytest.raises(ValueError, match="conflicting_scope_selection"):
        _canonical_scope_selection(decision({"mode": "replace", "keys": []}, {"scope_keys": ["team.ops"]}))
    assert _canonical_scope_selection(decision({}, {"scope_keys": [" Team.Ops "]})).keys == ["team.ops"]


@pytest.mark.asyncio
async def test_recall_is_repeated_if_final_preflight_changes_scope():
    a = EffectiveScopeContext(selected=[identity("project.a")], ceiling_keys=["project.a"])
    b = EffectiveScopeContext(selected=[identity("project.b")], ceiling_keys=["project.b"])
    first = {"search_scope": {"scope_keys": a.keys}, "items": [{"content": "old answer"}]}
    second = {"search_scope": {"scope_keys": b.keys}, "items": [{"content": "new answer"}]}
    search = AsyncMock(side_effect=[first, second])
    routed = TurnPreflightDecision.model_validate({"route": "planner", "task_brief": {
        "goal": "goal", "direction": "check", "expected_result": "result"}})
    recalled, decision, scope = await recall_with_stable_scope(a, search=search,
        complete=AsyncMock(return_value=routed), select=AsyncMock(return_value=b))
    assert recalled == second and scope.keys == b.keys
    assert search.await_count == 2
    assert search.await_args_list[1].args[0].keys == b.keys


@pytest.mark.asyncio
async def test_recall_rejects_scope_mismatch_before_routing():
    a = EffectiveScopeContext(selected=[identity("project.a")], ceiling_keys=["project.a"])
    complete = AsyncMock()
    with pytest.raises(ValueError, match="recall_scope_mismatch"):
        await recall_with_stable_scope(a, search=AsyncMock(return_value={"search_scope": {"scope_keys": ["project.b"]}}),
                                       complete=complete, select=AsyncMock())
    complete.assert_not_awaited()


def test_user_project_defaults_are_not_promoted_to_explicit_chat_focus():
    from app.services.memory_scope_preferences_service import inherit_scope_context
    rows = [SimpleNamespace(id=uuid4(), key=key, scope_type="project", name=key, is_all=False)
            for key in ["project.a", "project.b"]]
    context = inherit_scope_context(catalog=rows, chat_context={"focus": {
        "scope_keys": ["project.a"], "project_keys": ["a"],
        "scope_origins": {"project.a": "user_default"}}}, user_keys=["project.b"], tenant_keys=[])
    assert context.keys == ["project.b"]
    assert context.selected[0].source == "user_default"


def test_flat_scope_does_not_populate_legacy_project_branches():
    from app.runtime.pipeline import _project_context_payload
    context = EffectiveScopeContext(selected=[identity("ops", "turn")], mode="replace", ceiling_keys=["ops"])
    payload = _project_context_payload(context, {"source": "user_default"})
    assert not payload["suppress_project_default"]
    assert payload["effective_project_keys"] == []
    assert payload["effective_team_keys"] == []
    assert payload["scope_context"]["keys"] == ["ops"]
    assert payload["source"] == "explicit"


@pytest.mark.asyncio
async def test_scope_claims_preserve_separate_wording_and_evidence_for_the_same_item():
    from app.runtime.memory.recall import MemoryRecallService
    from datetime import datetime, timezone
    item = SimpleNamespace(id=uuid4(), project_id=None, item_type="rule", subject="deploy",
                           visibility={}, applicability={}, last_verified_at=None)
    claims = [SimpleNamespace(id=uuid4(), confidence=1, updated_at=datetime.now(timezone.utc), applicability={},
              content_text=key, content={"statement": key}, document_id=uuid4(), canonical_checksum="test",
              evidence_section_ids=[key]) for key in ["team.ops", "team.data"]]
    scopes = [SimpleNamespace(scope_type="team", key=key, is_all=False, project_id=None, lifecycle_status="active")
              for key in ["team.ops", "team.data"]]
    session = SimpleNamespace(execute=AsyncMock(side_effect=[
        SimpleNamespace(all=lambda: [(item, claim) for claim in claims]),
        SimpleNamespace(all=lambda: [(claim.id, scope) for claim, scope in zip(claims, scopes)]),
    ]))
    values = await MemoryRecallService(session=session, preparer=None)._accessible_semantic_items(
        project_ids=[], semantic_ids=[item.id], tenant_id=None, context_scope_keys=["team.ops", "team.data"])
    assert [value["content_text"] for value in values] == ["team.ops", "team.data"]
    assert values[0]["source_references"][0]["document_id"] == str(claims[0].document_id)
    assert values[1]["source_references"][0]["document_id"] == str(claims[1].document_id)
    assert all(value["state"] == "active" for value in values)


def test_native_search_projection_preserves_empty_and_failed_scope_groups():
    value = {"type": "planner_memory_result", "result": {"backend": "hipporag", "groups": [
        {"scope_slug": "a", "success": True, "items": []},
        {"scope_slug": "b", "success": False, "items": [], "error_code": "memory_search_failed"},
        {"scope_slug": "c", "success": True, "items": [{"text": "other scope"}]},
    ], "group_count": 3}}
    narrowed = project_memory_context(value, ["a", "b"])
    assert narrowed["result"]["groups"] == value["result"]["groups"][:2]
    assert narrowed["result"]["group_count"] == 2
    assert narrowed["result"]["partial"]
    assert len(value["result"]["groups"]) == 3


@pytest.mark.asyncio
async def test_planner_search_retains_passages_and_failure_receipts(monkeypatch):
    from app.runtime.planner import graph_planner
    from app.runtime.planner.graph_planner import GraphPlanner, PlannerStep
    calls = [
        {"tool": "memory.search", "arguments": {"query": "deploy rules"}},
        {"tool": "memory.search", "arguments": {"query": "deploy procedure", "limit": 12}},
        {"tool": "memory.search", "arguments": {"query": "deploy"}},
    ]
    proposal = {"terminal": "planner", "tasks": [{"task_id": "t", "executor": "worker", "intent": "check", "instructions": "Check"}]}
    steps = [PlannerStep(kind="tool_call", tool_call=call) for call in calls]
    steps.append(PlannerStep(kind="proposal", proposal=proposal))
    planner = GraphPlanner(session=object(), llm_client=AsyncMock())
    planner._llm = SimpleNamespace(
        role_service=SimpleNamespace(get_role_config=AsyncMock(return_value={})),
        _compile_role_prompt=Mock(return_value="prompt"),
        invoke=AsyncMock(side_effect=[SimpleNamespace(value=step) for step in steps]),
    )
    records = [{"tool": call["tool"], "arguments": call["arguments"], "result": {"success": index < 2,
        "groups": [{"scope_slug": "team.ops", "success": index < 2,
                    "items": [{"text": f"passage {index}"}] if index < 2 else [],
                    **({"error_code": "memory_search_failed"} if index == 2 else {})}]}}
        for index, call in enumerate(calls)]
    tools = SimpleNamespace(descriptors=AsyncMock(return_value=[{"tool": "memory.search"}]),
                            execute=AsyncMock(side_effect=records))
    factory = lambda **kwargs: tools
    factory.MAX_CALLS = 3
    monkeypatch.setattr(graph_planner, "RoleMemoryTools", factory)
    scope = EffectiveScopeContext(selected=[identity("team.ops")], ceiling_keys=["team.ops"])
    request = PlanRequest(context=PlannerContext(goal="goal", trigger="initial", execution_ledger={}, scope_context=scope.model_payload()))
    await planner.plan(request=request)
    results = request.context.planner_search_results
    assert len(results) == 1
    assert [item["text"] for item in results[0]["groups"][0]["items"]] == ["passage 0", "passage 1"]
    assert results[0]["partial"]
    assert tools.execute.await_count == 3
    from app.runtime.memory.document_memory import search_receipt
    assert planner._llm.invoke.await_args.kwargs["payload"]["memory_tool_results"] == [search_receipt(record) for record in records]


def test_planner_search_recall_requirements_reach_synthesis_guard():
    from app.runtime.orchestrator import _recall_requires_rag, _recall_requires_tool
    context = [{"type": "planner_memory_result", "result": {
        "memory_context": {"type": "memory_recall", "rag_required": True, "tool_required": True}}}]
    assert _recall_requires_rag(context)
    assert _recall_requires_tool(context)


def test_memory_only_synthesis_keeps_original_passages_without_silent_truncation():
    import json
    from app.runtime.synthesis_context import SynthesisContextBuilder
    plan = {"goal": "goal", "scope_context": {"keys": ["company"]}, "tasks": {}, "iterations": [
        {"id": "i", "sequence": 1, "terminal": "synthesis", "synthesis_brief": {"purpose": "answer"}}],
        "memory_context": [{"type": "planner_memory_result", "result": {
            "backend": "hipporag", "groups": [{"scope_slug": "company", "success": True,
            "items": [{"subject": "x", "text": "x" * 2000}]}]}} for _ in range(30)]}
    result = SynthesisContextBuilder(max_chars=4000).build(plan=plan, iteration_id="i")
    assert "memory_context_truncated" not in result
    assert result["memory_context"][0]["result"]["groups"][0]["items"][0]["text"] == "x" * 2000
    assert len(json.dumps(result)) > 4000
    assert len(plan["memory_context"]) == 30
