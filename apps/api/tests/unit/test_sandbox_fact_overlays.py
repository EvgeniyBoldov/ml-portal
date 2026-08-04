from app.models.memory import FactScope, FactSource
from app.runtime.memory.dto import FactDTO
from app.runtime.memory.sandbox_overlays import apply_overrides, merge_extracted


def _fact(scope: FactScope, subject: str, value: str) -> FactDTO:
    return FactDTO(scope=scope, subject=subject, value=value, source=FactSource.USER_UTTERANCE)


def test_set_override_replaces_only_matching_scope_and_subject() -> None:
    base = [_fact(FactScope.USER, "user.role", "engineer"), _fact(FactScope.TENANT, "user.role", "manager")]
    overrides = merge_extracted({}, [_fact(FactScope.USER, "user.role", "director")])

    effective = {(item.scope.value, item.subject): item.value for item in apply_overrides(base, overrides)}

    assert effective == {
        ("user", "user.role"): "director",
        ("tenant", "user.role"): "manager",
    }


def test_deleted_override_hides_durable_fact_without_mutating_other_facts() -> None:
    base = [_fact(FactScope.USER, "user.age", "39"), _fact(FactScope.TENANT, "department.stack", "Python")]
    overrides = {"user": {"user.age": {"state": "deleted"}}}

    effective = {(item.scope.value, item.subject): item.value for item in apply_overrides(base, overrides)}

    assert effective == {("tenant", "department.stack"): "Python"}


def test_set_override_adds_branch_only_fact() -> None:
    overrides = merge_extracted({}, [_fact(FactScope.TENANT, "department.db", "Postgres 15")])

    effective = apply_overrides([], overrides)

    assert [(item.scope, item.subject, item.value) for item in effective] == [
        (FactScope.TENANT, "department.db", "Postgres 15"),
    ]
