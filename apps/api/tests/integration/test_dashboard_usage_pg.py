"""Run with DASHBOARD_PG=1 against a migrated local database; all inserts roll back."""
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.db import _db_url
from app.models.platform_usage import PlatformUsage
from app.models.collection import Collection
from app.models.rag import RAGDocument
from app.models.rag_ingest import Source, Chunk, RAGStatus, DocumentCollectionMembership
from app.models.tenant import Tenants
from app.models.user import Users
from app.models.tool_instance import ToolInstance
from app.repositories.dashboard_repository import DashboardRepository
from app.repositories.platform_usage_repository import PlatformUsageRepository

pytestmark = [pytest.mark.asyncio, pytest.mark.skipif(os.getenv("DASHBOARD_PG") != "1", reason="requires local PostgreSQL")]


async def test_idempotency_origin_filter_boundaries_and_tokens():
    engine = create_async_engine(_db_url())
    try:
        async with async_sessionmaker(engine)() as session:
            # Isolate the tested range from existing application traffic.
            start = datetime(2040, 1, 1, tzinfo=timezone.utc)
            end = start + timedelta(days=1)
            user_id = uuid4()
            repo = PlatformUsageRepository(session)
            base = dict(run_id=uuid4(), origin="chat", user_id=user_id, status="running",
                started_at=start + timedelta(hours=1))
            request = dict(base, kind="run", entity_id=str(uuid4()))
            await repo.upsert(request, is_start=True)
            completed = {**request, "status": "completed", "finished_at": start + timedelta(hours=1, seconds=2)}
            await repo.upsert(completed, is_start=False)
            await repo.upsert(request, is_start=True)
            await repo.upsert(completed, is_start=False)
            await repo.upsert({**completed, "finished_at": completed["finished_at"] + timedelta(minutes=5)}, is_start=False)
            await repo.upsert(dict(base, kind="run", entity_id=str(uuid4()), origin="sandbox"), is_start=True)
            await repo.upsert(dict(base, kind="run", entity_id=str(uuid4()), origin="shadow", status="failed"), is_start=False)
            await repo.upsert(dict(base, kind="run", entity_id=str(uuid4()), started_at=end), is_start=True)
            llm = dict(base, kind="llm", entity_id=str(uuid4()), model_alias="dashboard-pg-test", tokens_in=100,
                tokens_out=20, token_source="provider", status="completed", finished_at=start + timedelta(hours=1, seconds=1))
            await repo.upsert(llm, is_start=False)
            await repo.upsert(llm, is_start=False)
            reader = DashboardRepository(session)
            summary = await reader.summary(start, end)
            assert summary["requests"] == 2 and summary["active_users"] == 1
            assert summary["chat_requests"] == 1 and summary["shadow_requests"] == 1
            assert summary["completed_requests"] == 1 and summary["failed_requests"] == 1
            usage = await reader.model_usage(start, end)
            assert len(usage) == 1 and usage[0]["calls"] == 1
            assert usage[0]["tokens_in"] == 100 and usage[0]["tokens_out"] == 20
            stored = await session.scalar(select(PlatformUsage).where(PlatformUsage.kind == "run", PlatformUsage.entity_id == request["entity_id"]))
            assert stored.status == "completed"
            assert stored.duration_ms == 2000
            await session.rollback()
    finally:
        await engine.dispose()


async def test_collection_sizes_do_not_multiply_by_embedding_models_or_memberships():
    engine = create_async_engine(_db_url())
    try:
        async with async_sessionmaker(engine)() as session:
            tenant_id, user_id = uuid4(), uuid4()
            session.add(Tenants(id=tenant_id, name=f"dashboard-test-{tenant_id}"))
            session.add(Users(id=user_id, login=f"dashboard-test-{user_id}"))
            await session.flush()
            instance_id = uuid4()
            session.add(ToolInstance(id=instance_id, slug=f"dashboard-test-{instance_id}", name="Dashboard test source", placement="local", domain="collection.document"))
            await session.flush()
            first = Collection(id=uuid4(), tenant_id=tenant_id, data_instance_id=instance_id, slug=f"test-{uuid4()}", name="Dashboard test A", collection_type="document")
            second = Collection(id=uuid4(), tenant_id=tenant_id, data_instance_id=instance_id, slug=f"test-{uuid4()}", name="Dashboard test B", collection_type="document")
            empty = Collection(id=uuid4(), tenant_id=tenant_id, data_instance_id=instance_id, slug=f"test-{uuid4()}", name="Dashboard test empty", collection_type="document")
            session.add_all([first, second, empty])
            documents = [RAGDocument(id=uuid4(), tenant_id=tenant_id, user_id=user_id, title="Test", filename="test.txt",
                size_bytes=100, status="ready", agg_status=status) for status in ("ready", "partial")]
            session.add_all(documents)
            await session.flush()
            for index, document in enumerate(documents):
                session.add(Source(source_id=document.id, tenant_id=tenant_id))
                await session.flush()
                session.add(DocumentCollectionMembership(tenant_id=tenant_id, source_id=document.id, collection_id=first.id))
                for offset in range(index + 1):
                    session.add(Chunk(chunk_id=str(uuid4()), source_id=document.id, offset=offset, length=10, hash=str(uuid4())))
                for alias in ("embedding-a", "embedding-b"):
                    session.add(RAGStatus(doc_id=document.id, node_type="embedding", node_key=alias, status="completed"))
            session.add(DocumentCollectionMembership(tenant_id=tenant_id, source_id=documents[0].id, collection_id=second.id))
            await session.flush()
            rows = {row["id"]: row for row in await DashboardRepository(session).collections()}
            a, b, zero = (rows[str(collection.id)] for collection in (first, second, empty))
            assert (a["documents"], a["source_bytes"], a["chunks"]) == (2, 200, 3)
            assert (a["ready"], a["processing"], a["partial"], a["failed"]) == (1, 0, 1, 0)
            assert a["embedding_models"] == ["embedding-a", "embedding-b"]
            assert (b["documents"], b["source_bytes"], b["chunks"]) == (1, 100, 1)
            assert (zero["documents"], zero["source_bytes"], zero["chunks"], zero["processing"]) == (0, 0, 0, 0)
            await session.rollback()
    finally:
        await engine.dispose()


async def test_recovered_model_leaves_problems_but_keeps_historical_errors():
    engine = create_async_engine(_db_url())
    try:
        async with async_sessionmaker(engine)() as session:
            start = datetime(2041, 1, 1, tzinfo=timezone.utc)
            end = start + timedelta(days=1)
            repo = PlatformUsageRepository(session)
            base = dict(kind="llm", run_id=uuid4(), origin="chat", user_id=uuid4(),
                model_alias="dashboard-recovery-test", status="failed", error_code="llm_timeout")
            for index in range(3):
                at = start + timedelta(hours=1, minutes=index)
                await repo.upsert(dict(base, entity_id=str(uuid4()), started_at=at, finished_at=at + timedelta(seconds=10)), is_start=False)
            reader = DashboardRepository(session)
            assert (await reader.repeated_errors(start, end, 3))[0]["count"] == 3
            recovered = dict(base, entity_id=str(uuid4()), status="completed", error_code=None,
                started_at=start + timedelta(hours=2), finished_at=start + timedelta(hours=2, seconds=2))
            await repo.upsert({**recovered, "origin": "sandbox"}, is_start=False)
            assert len(await reader.repeated_errors(start, end, 3)) == 1
            await repo.upsert({**recovered, "entity_id": str(uuid4())}, is_start=False)
            assert await reader.repeated_errors(start, end, 3) == []
            usage = await reader.model_usage(start, end)
            assert usage[0]["calls"] == 4 and usage[0]["errors"] == 3
            await session.rollback()
    finally:
        await engine.dispose()
