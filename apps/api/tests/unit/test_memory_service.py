from uuid import uuid4

import pytest

from app.models.memory import FactScope, FactSource
from app.runtime.memory.dto import FactDTO
from app.runtime.memory.service import MemoryService


class _Facts:
    def __init__(self) -> None:
        self.saved: list[FactDTO] = []

    async def retrieve(self, *, scopes, owner_type=None, owner_id=None, limit=20):
        if scopes == [FactScope.USER]:
            return [FactDTO(scope=FactScope.USER, subject="role", value="engineer", source=FactSource.SYSTEM, owner_type=owner_type, owner_id=owner_id)]
        return [FactDTO(scope=FactScope.TENANT, subject="term", value="portal", source=FactSource.SYSTEM, owner_type=owner_type, owner_id=owner_id)]

    async def get_active_by_key(self, **kwargs):
        return None

    async def upsert_with_supersede(self, item: FactDTO) -> FactDTO:
        self.saved.append(item)
        return item


@pytest.mark.asyncio
async def test_memory_service_reads_one_snapshot_and_writes_generic_user_tenant_owners() -> None:
    facts = _Facts()
    service = MemoryService(fact_store=facts)  # type: ignore[arg-type]
    user_id, tenant_id = uuid4(), uuid4()

    snapshot = await service.read_snapshot(user_id=user_id, tenant_id=tenant_id, limit=12)
    assert [entry["scope"] for entry in snapshot.planner_context()] == ["user", "tenant"]

    saved = await service.write_extracted(
        user_id=user_id,
        tenant_id=tenant_id,
        facts=[
            FactDTO(scope=FactScope.USER, subject="role", value="engineer", source=FactSource.USER_UTTERANCE),
            FactDTO(scope=FactScope.TENANT, subject="term", value="portal", source=FactSource.USER_UTTERANCE),
        ],
    )

    assert saved == 2
    assert [(item.owner_type, item.owner_id) for item in facts.saved] == [("user", user_id), ("tenant", tenant_id)]


@pytest.mark.asyncio
async def test_old_scope_defaults_survive_recent_profile_limit():
    from unittest.mock import AsyncMock
    facts = _Facts()
    facts.get_active_by_key = AsyncMock(side_effect=lambda **kwargs: FactDTO(
        scope=kwargs["scope"], subject=kwargs["subject"], value="Scope defaults",
        source=FactSource.SYSTEM, owner_type=kwargs["owner_type"], owner_id=kwargs["owner_id"],
        metadata={"team_keys": ["ops"], "project_keys": ["a"]}))
    snapshot = await MemoryService(fact_store=facts).read_snapshot(user_id=uuid4(), tenant_id=uuid4(), limit=1)
    assert {fact.subject for fact in snapshot.entries} >= {
        "user.team_scope", "user.project_scope", "tenant.team_scope", "tenant.project_scope"}
    assert len(snapshot.user_facts) == len(snapshot.tenant_facts) == 3
