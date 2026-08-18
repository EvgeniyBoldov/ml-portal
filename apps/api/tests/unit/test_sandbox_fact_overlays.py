from app.models.memory import FactScope, FactSource, FactStatus
from app.runtime.memory.builder import MemoryBuilder
from app.runtime.memory.dto import FactDTO
from app.runtime.memory.service import MemorySnapshot
from app.runtime.memory.sandbox_overlays import apply_overrides, merge_extracted
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest


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


def test_project_fact_is_kept_in_branch_overlay() -> None:
    overrides = merge_extracted({}, [_fact(FactScope.PROJECT, "project.network.standard", "EVPN")])

    effective = apply_overrides([], overrides)

    assert [(item.scope, item.subject, item.status) for item in effective] == [
        (FactScope.PROJECT, "project.network.standard", FactStatus.CONFIRMED),
    ]


def test_conflicting_sandbox_value_masks_confirmed_base_fact() -> None:
    base = [_fact(FactScope.TENANT, "department.db", "Postgres 15")]
    overrides = merge_extracted({}, [_fact(FactScope.TENANT, "department.db", "Oracle")], base=base)

    effective = apply_overrides(base, overrides)

    assert len(effective) == 1
    assert effective[0].value == "Oracle"
    assert effective[0].status == FactStatus.PENDING
    assert overrides["tenant"]["department.db"]["conflict"] is True


@pytest.mark.asyncio
async def test_memory_builder_reads_confirmed_branch_user_overlay_on_next_run() -> None:
    base = FactDTO(
        scope=FactScope.USER,
        subject="role",
        value="engineer",
        source=FactSource.USER_UTTERANCE,
        status=FactStatus.CONFIRMED,
    )
    override = merge_extracted(
        {},
        [FactDTO(
            scope=FactScope.USER,
            subject="specialization",
            value="network engineer",
            source=FactSource.USER_UTTERANCE,
        )],
        base=[base],
    )
    builder = MemoryBuilder(session=AsyncMock())
    builder._memory_service.read_snapshot = AsyncMock(
        return_value=MemorySnapshot(user_facts=(base,))
    )

    memory = await builder.build(
        goal="network design",
        chat_id=None,
        user_id=uuid4(),
        tenant_id=uuid4(),
        sandbox_overrides={
            "sandbox_branch_id": str(uuid4()),
            "fact_overrides": override,
        },
    )

    assert {(fact.subject, fact.value) for fact in memory.durable_snapshot.user_facts} == {
        ("role", "engineer"),
        ("specialization", "network engineer"),
    }
