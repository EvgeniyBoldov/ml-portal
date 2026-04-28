from __future__ import annotations

from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.models.memory import FactScope, FactSource
from app.runtime.memory.dto import FactDTO
from app.runtime.memory.user_facts_service import (
    LongTermFactsService,
    PlatformFactsService,
    TenantFactsService,
    UserFactsService,
)


@pytest.mark.asyncio
async def test_user_service_load_and_save():
    user_id = uuid4()
    fact_store = AsyncMock()
    fact_store.retrieve = AsyncMock(return_value=[])
    fact_store.upsert_with_supersede = AsyncMock()
    service = UserFactsService(fact_store=fact_store, user_id=user_id)

    await service.load_for_runtime(limit=10)
    fact_store.retrieve.assert_awaited_once_with(
        scopes=[FactScope.USER],
        user_id=user_id,
        limit=10,
    )

    fact = FactDTO(
        scope=FactScope.USER,
        subject="user.name",
        value="Anna",
        source=FactSource.USER_UTTERANCE,
        user_id=None,
    )
    saved = await service.save_for_runtime(facts=[fact])
    assert saved == 1
    persisted = fact_store.upsert_with_supersede.await_args.args[0]
    assert persisted.user_id == user_id


@pytest.mark.asyncio
async def test_tenant_service_saves_only_tenant_bound_facts():
    tenant_id = uuid4()
    fact_store = AsyncMock()
    fact_store.retrieve = AsyncMock(return_value=[])
    fact_store.upsert_with_supersede = AsyncMock()
    service = TenantFactsService(fact_store=fact_store, tenant_id=tenant_id)

    facts = [
        FactDTO(
            scope=FactScope.TENANT,
            subject="tenant.a",
            value="1",
            source=FactSource.AGENT_RESULT,
            tenant_id=tenant_id,
        ),
        FactDTO(
            scope=FactScope.TENANT,
            subject="platform.a",
            value="2",
            source=FactSource.AGENT_RESULT,
            tenant_id=None,
        ),
    ]
    saved = await service.save_for_runtime(facts=facts)
    assert saved == 1
    fact_store.upsert_with_supersede.assert_awaited_once_with(facts[0])


@pytest.mark.asyncio
async def test_platform_service_reads_null_tenant_scope():
    fact_store = AsyncMock()
    fact_store.retrieve = AsyncMock(return_value=[])
    service = PlatformFactsService(fact_store=fact_store)

    await service.load_for_runtime(limit=25)
    fact_store.retrieve.assert_awaited_once_with(
        scopes=[FactScope.TENANT],
        tenant_id=None,
        limit=25,
    )


@pytest.mark.asyncio
async def test_long_term_service_merges_and_sorts_with_limit():
    user_id = uuid4()
    tenant_id = uuid4()
    now = datetime.now(timezone.utc)

    user_fact = FactDTO(
        id=uuid4(),
        scope=FactScope.USER,
        subject="user.name",
        value="Anna",
        source=FactSource.USER_UTTERANCE,
        user_id=user_id,
        observed_at=now - timedelta(minutes=3),
    )
    tenant_fact = FactDTO(
        id=uuid4(),
        scope=FactScope.TENANT,
        subject="tenant.region",
        value="ru",
        source=FactSource.AGENT_RESULT,
        tenant_id=tenant_id,
        observed_at=now - timedelta(minutes=1),
    )
    platform_fact = FactDTO(
        id=uuid4(),
        scope=FactScope.TENANT,
        subject="platform.policy",
        value="strict",
        source=FactSource.SYSTEM,
        tenant_id=None,
        observed_at=now - timedelta(minutes=2),
    )

    fact_store = AsyncMock()
    fact_store.retrieve = AsyncMock(
        side_effect=[
            [user_fact],
            [tenant_fact],
            [platform_fact],
        ]
    )
    long_term = LongTermFactsService(
        fact_store=fact_store,
        user_id=user_id,
        tenant_id=tenant_id,
    )

    items = await long_term.load_for_runtime(limit=2)

    assert len(items) == 2
    assert items[0].id == tenant_fact.id
    assert items[1].id == platform_fact.id

