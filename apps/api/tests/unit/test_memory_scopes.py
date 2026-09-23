from types import SimpleNamespace
from uuid import uuid4

from app.runtime.memory.recall import _claim_scopes_apply
from app.runtime.memory.search import _apply_project_precedence
from app.runtime.memory.shadow_memory_publication import _scope_signature


def scope(kind: str, key: str, *, project_id=None, is_all: bool = False):
    return SimpleNamespace(scope_type=kind, key=key, project_id=project_id, is_all=is_all)


def test_scope_applicability_ors_within_type_and_ands_between_types() -> None:
    project_a, project_b = uuid4(), uuid4()
    scopes = [
        scope("project", "project.a", project_id=project_a),
        scope("project", "project.b", project_id=project_b),
        scope("team", "team.ops"),
    ]
    assert _claim_scopes_apply(scopes, [project_b], {"team.ops"})
    assert not _claim_scopes_apply(scopes, [project_a], set())
    assert not _claim_scopes_apply(scopes, [], {"team.ops"})


def test_all_scope_is_wildcard_only_for_its_type() -> None:
    scopes = [scope("project", "project.all", is_all=True), scope("team", "team.ops")]
    assert _claim_scopes_apply(scopes, [uuid4()], {"team.ops"})
    assert not _claim_scopes_apply(scopes, [], {"team.ops"})
    assert not _claim_scopes_apply(scopes, [], set())
    assert not _claim_scopes_apply([scope("team", "team.all", is_all=True)], [], set())
    assert _claim_scopes_apply([scope("team", "team.all", is_all=True)], [], {"team.ops"})


def test_divergent_typed_scopes_do_not_select_an_arbitrary_winner() -> None:
    items = [
        {"id": uuid4(), "kind": "rule", "subject": "deploy", "content_text": "A",
         "project_id": None, "scope_keys": ["team.ops"]},
        {"id": uuid4(), "kind": "rule", "subject": "deploy", "content_text": "B",
         "project_id": None, "scope_keys": ["product.core"]},
    ]
    selected, uncertainties = _apply_project_precedence(items, [])
    assert selected == []
    assert uncertainties == ["project_memory_divergence:rule:deploy"]


def test_scope_signature_preserves_distinct_applicability_identities() -> None:
    project, team = SimpleNamespace(id=uuid4()), SimpleNamespace(id=uuid4())
    assert _scope_signature([project, team]) == _scope_signature([team, project])
    assert _scope_signature([project]) != _scope_signature([project, team])
    assert _scope_signature([]) == "legacy"
