"""Opt-in PostgreSQL checks. Only synthetic rows in a disposable schema.

Run with MEMORY_WORKFLOW_PG=1. Public data and alembic_version are untouched.
"""
import asyncio
import importlib
import os
from uuid import uuid4

import pytest
import pytest_asyncio
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import get_settings
from app.models.document_memory_staging import (
    DocumentMemorySnapshot, DocumentMemoryExtractionAttempt, MemoryExtractionCandidate,
    GlossaryTerm,
)
from app.models.memory_scope import MemoryClaimScope, MemoryScope
from app.models.rag import RAGDocument
from app.runtime.memory.shadow_document_study import ShadowDocumentStudyService, ShadowStudyItem
from app.runtime.memory.shadow_memory_publication import ShadowMemoryPublicationService
from app.workers.tasks_shadow_document_memory import _attempt_message_matches

from tests.integration.test_memory_candidate_tags import tag_pg

pytestmark = pytest.mark.skipif(os.getenv("MEMORY_WORKFLOW_PG") != "1", reason="requires opt-in PostgreSQL")


def migration(conn, revision, action):
    with Operations.context(MigrationContext.configure(conn)):
        getattr(importlib.import_module(f"app.migrations.versions.{revision}"), action)()


@pytest_asyncio.fixture
async def migration_pg():
    """Create the inputs of revisions 0176–0178 independently of the HEAD schema."""
    schema = "memory_migration_" + uuid4().hex
    admin = create_async_engine(get_settings().ASYNC_DB_URL)
    engine = None
    statements = (
        "CREATE TABLE tenants (id uuid PRIMARY KEY)",
        "CREATE TABLE users (id uuid PRIMARY KEY)",
        "CREATE TABLE glossary_terms (id uuid PRIMARY KEY)",
        "CREATE TABLE memory_scopes (id uuid PRIMARY KEY)",
        "CREATE TABLE memory_conflict_cases (status text, kind text)",
        """CREATE TABLE document_memory_snapshots (
            id uuid PRIMARY KEY, document_id uuid NOT NULL, canonical_checksum text NOT NULL,
            status text NOT NULL, metrics jsonb, trace_run_id uuid,
            created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL
        )""",
        "CREATE TABLE memory_extraction_candidates (id uuid PRIMARY KEY, snapshot_id uuid NOT NULL)",
        "CREATE TABLE runtime_plans (id uuid PRIMARY KEY, tenant_id uuid, root_run_id uuid, goal text)",
        """CREATE TABLE runtime_plan_iterations (
            id uuid PRIMARY KEY, plan_id uuid, sequence integer, terminal text
        )""",
        """CREATE TABLE runtime_plan_tasks (
            id uuid PRIMARY KEY, plan_id uuid, iteration_id uuid, task_id text,
            planned_order integer, intent text, instructions text, executor text
        )""",
    )
    try:
        async with admin.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_async_engine(get_settings().ASYNC_DB_URL,
            connect_args={"server_settings": {"search_path": schema + ",public"}})
        async with engine.begin() as conn:
            for statement in statements:
                await conn.execute(text(statement))
            await conn.run_sync(lambda c: migration(c, "0176_memory_scope_proposals", "upgrade"))
        yield engine
    finally:
        if engine:
            await engine.dispose()
        async with admin.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await admin.dispose()


async def upgrade(engine):
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: migration(c, "0177_memory_extraction_attempts", "upgrade"))


async def upgrade_scope_context(engine):
    await upgrade(engine)
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: migration(c, "0178_effective_scope_context", "upgrade"))


@pytest.mark.asyncio
async def test_scope_context_migration_preserves_persisted_runtime_context(migration_pg):
    pg = migration_pg
    await upgrade_scope_context(pg)
    plan_id = uuid4()
    async with pg.begin() as conn:
        await conn.execute(text("""
            INSERT INTO runtime_plans (id, tenant_id, root_run_id, goal, scope_context, memory_context)
            VALUES (:id, :tenant, :run, 'synthetic scope test',
                    '{"keys":["project.alpha"]}'::jsonb,
                    '[{"type":"memory_recall","items":[]}]'::jsonb)
        """), {"id": plan_id, "tenant": uuid4(), "run": uuid4()})
        await conn.execute(text("""
            INSERT INTO runtime_plan_iterations (id, plan_id, sequence, terminal)
            VALUES (:id, :plan, 1, 'planner')
        """), {"id": uuid4(), "plan": plan_id})
        await conn.execute(text("""
            INSERT INTO runtime_plan_tasks
                (id, plan_id, iteration_id, task_id, planned_order, intent, instructions, executor, scope_context)
            SELECT :id, :plan, id, 'task-1', 1, 'inspect alpha', 'Inspect alpha', 'worker',
                   '{"keys":["project.alpha"]}'::jsonb
            FROM runtime_plan_iterations WHERE plan_id=:plan
        """), {"id": uuid4(), "plan": plan_id})
    with pytest.raises(Exception, match="discard persisted scope or memory context"):
        async with pg.begin() as conn:
            await conn.run_sync(lambda c: migration(c, "0178_effective_scope_context", "downgrade"))
    async with pg.connect() as conn:
        assert (await conn.execute(text("SELECT scope_context, memory_context FROM runtime_plans WHERE id=:id"),
                                   {"id": plan_id})).one() == ({"keys": ["project.alpha"]},
                                                                  [{"type": "memory_recall", "items": []}])
        assert await conn.scalar(text("SELECT scope_context->>'keys' FROM runtime_plan_tasks WHERE task_id='task-1'")) == '["project.alpha"]'


@pytest.mark.asyncio
async def test_plan_task_scope_and_memory_survive_new_session(tag_pg):
    pg = tag_pg
    from app.runtime.memory.effective_scope import EffectiveScopeContext, ScopeIdentity
    from app.runtime.plan_store import SqlPlanStore
    from app.runtime.orchestrator_contracts import IterationProposal
    scopes = [ScopeIdentity(key=key, source="turn") for key in ("project-a", "project-b", "ops")]
    context = EffectiveScopeContext(selected=scopes, ceiling_keys=[scope.key for scope in scopes])
    core = [
        {"scope": "user", "subject": "role", "value": "engineer"},
        {"scope": "tenant", "subject": "region", "value": "test-region"},
    ]
    async with AsyncSession(pg, expire_on_commit=False) as session:
        store = SqlPlanStore(session)
        plan = await store.create(goal="goal", root_run_id=uuid4(), tenant_id=uuid4(),
                                  scope_context=context.model_payload(), memory_context=core)
        plan_id = plan.id
        proposal = IterationProposal.model_validate({"terminal": "planner", "tasks": [{
            "task_id": "t", "executor": "worker", "intent": "inspect B", "instructions": "Inspect B",
            "scope_keys": ["project-b"], "scope_reason": "This task inspects only B"}]})
        await store.apply_iteration(plan_id, proposal)
        await store.update_memory_context(plan_id, [{"groups": [
            {"scope_slug": "project-b", "success": True, "items": [{"text": f"passage {i}"}]}
        ]} for i in range(35)])
    async with AsyncSession(pg, expire_on_commit=False) as session:
        store = SqlPlanStore(session)
        snapshot = await store.snapshot(plan_id)
        claim = await store.claim_task(plan_id, "t")
        task = await store.task_request(plan_id, "t", expected_attempt_number=claim.attempts)
        assert task["scope_context"]["keys"] == ["project-b"]
        assert task["scope_context"]["ceiling_keys"] == ["project-b"]
        assert snapshot["memory_context"][:2] == core
        from app.runtime.memory.document_memory import document_memory
        [search] = document_memory(snapshot["memory_context"])
        assert [item["text"] for item in search["groups"][0]["items"]] == [f"passage {i}" for i in range(35)]


@pytest.mark.asyncio
async def test_populated_upgrade_safe_downgrade_and_history_refusal(migration_pg):
    pg = migration_pg
    statuses = ["queued", "screening", "studying", "conflict_checking", "awaiting_review", "approved", "failed", "superseded"]
    async with pg.begin() as conn:
        for status in statuses:
            await conn.execute(text("INSERT INTO document_memory_snapshots (id,document_id,canonical_checksum,status,created_at,updated_at) VALUES (:id,:doc,:checksum,:status,now(),now())"),
                               {"id": uuid4(), "doc": uuid4(), "checksum": status, "status": status})
    await upgrade(pg)
    async with pg.begin() as conn:
        mapped = dict((await conn.execute(text("SELECT s.status,a.status FROM document_memory_snapshots s JOIN document_memory_extraction_attempts a ON a.id=s.active_attempt_id"))).all())
        assert mapped == dict(zip(statuses, ["queued", "queued", "studying", "studying", "awaiting_review", "completed", "failed", "superseded"]))
        await conn.run_sync(lambda c: migration(c, "0177_memory_extraction_attempts", "downgrade"))
    await upgrade(pg)
    async with pg.begin() as conn:
        await conn.execute(text("INSERT INTO document_memory_extraction_attempts (id,snapshot_id,attempt_number) SELECT :id,id,2 FROM document_memory_snapshots LIMIT 1"), {"id": uuid4()})
    with pytest.raises(Exception, match="preserve audit data"):
        async with pg.begin() as conn:
            await conn.run_sync(lambda c: migration(c, "0177_memory_extraction_attempts", "downgrade"))
    async with pg.connect() as conn:
        assert await conn.scalar(text("SELECT count(*) FROM document_memory_extraction_attempts WHERE attempt_number=2")) == 1
        assert await conn.scalar(text("SELECT count(*) FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='memory_scope_proposals' AND column_name='attempt_id'")) == 1


async def new_snapshot(session):
    document = RAGDocument(user_id=uuid4(), filename="test.txt", title="Synthetic test", scope="global", status="ready")
    session.add(document)
    await session.flush()
    snapshot = DocumentMemorySnapshot(document_id=document.id, canonical_checksum=uuid4().hex, status="studying")
    session.add(snapshot)
    await session.flush()
    attempt = await ShadowDocumentStudyService(session).ensure_active_attempt(snapshot)
    await session.flush()
    return snapshot, attempt


@pytest.mark.asyncio
async def test_review_publishes_scope_link_and_reuses_glossary_term(tag_pg):
    async with AsyncSession(tag_pg, expire_on_commit=False) as session:
        scope = MemoryScope(scope_type="project", key="example", name="Example")
        session.add(scope)
        await session.flush()
        study = ShadowDocumentStudyService(session)
        publisher = ShadowMemoryPublicationService(session)
        term = ShadowStudyItem(candidate_type="term", subject="Example", content={"definition": "Example project"},
                              evidence_section_ids=["s1"])
        rule = ShadowStudyItem(candidate_type="rule", subject="Deploy",
                               content={"statement": "Deploy daily", "effect": "require"}, evidence_section_ids=["s1"])
        for subject in ("Deploy", "Deploy safely"):
            snapshot, attempt = await new_snapshot(session)
            await study.persist_batch(snapshot=snapshot, attempt=attempt,
                items=[term, rule.model_copy(update={"subject": subject})],
                section_ids={"s1"}, projects_by_key={}, scopes_by_key={})
            await study.finalize(snapshot, attempt)
            rows = (await session.scalars(select(MemoryExtractionCandidate)
                .where(MemoryExtractionCandidate.snapshot_id == snapshot.id))).all()
            for row in rows:
                if row.candidate_type == "term":
                    await publisher.approve(candidate_id=row.id, actor_id=None, reason=None)
            glossary = (await session.scalars(select(GlossaryTerm))).one()
            memory = next(row for row in rows if row.candidate_type == "rule")
            await publisher.update_review_tags(candidate_id=memory.id, actor_id=None,
                scope_ids=[scope.id], glossary_term_ids=[glossary.id], reason="Reviewed")
            await publisher.approve(candidate_id=memory.id, actor_id=None, reason=None)
            await session.commit()
            assert snapshot.status == "approved" and attempt.status == "completed"

        assert list(await session.scalars(select(MemoryClaimScope.scope_id))) == [scope.id, scope.id]


@pytest.mark.asyncio
async def test_two_sessions_refresh_attempt_and_serialize_duplicate_cursor(tag_pg):
    pg = tag_pg
    async with AsyncSession(pg, expire_on_commit=False) as setup:
        snapshot, attempt = await new_snapshot(setup)
        await setup.commit()
        snapshot_id, old_id = snapshot.id, attempt.id
    async with AsyncSession(pg, expire_on_commit=False) as stale:
        cached = await stale.get(DocumentMemorySnapshot, snapshot_id)
        async with AsyncSession(pg, expire_on_commit=False) as writer:
            locked, _ = await ShadowDocumentStudyService(writer).lock_active_attempt(snapshot_id)
            new = DocumentMemoryExtractionAttempt(snapshot_id=snapshot_id, attempt_number=2)
            writer.add(new)
            await writer.flush()
            locked.active_attempt_id = new.id
            await writer.commit()
            new_id = new.id
        fresh, active = await ShadowDocumentStudyService(stale).lock_active_attempt(snapshot_id)
        assert fresh is cached and fresh.active_attempt_id == new_id
        assert not _attempt_message_matches(active, str(old_id))
        await stale.rollback()
    async with AsyncSession(pg, expire_on_commit=False) as first:
        _, active = await ShadowDocumentStudyService(first).lock_active_attempt(snapshot_id)
        async def duplicate():
            async with AsyncSession(pg) as second:
                _, second_attempt = await ShadowDocumentStudyService(second).lock_active_attempt(snapshot_id)
                return _attempt_message_matches(second_attempt, str(new_id), expected_cursor=0)
        task = asyncio.create_task(duplicate())
        await asyncio.sleep(0.1)
        assert not task.done()
        active.next_section = 1
        await first.commit()
        assert await asyncio.wait_for(task, 5) is False


@pytest.mark.asyncio
async def test_retired_extraction_retry_leaves_review_data_intact(tag_pg):
    from fastapi import HTTPException
    from app.api.v1.routers.admin import semantic_memory

    async with AsyncSession(tag_pg, expire_on_commit=False) as session:
        snapshot, attempt = await new_snapshot(session)
        row = MemoryExtractionCandidate(snapshot_id=snapshot.id, attempt_id=attempt.id, ordinal=0,
            candidate_type="rule", subject="Deploy", normalized_subject="deploy",
            content={"statement": "Deploy daily", "effect": "require"}, content_text="Deploy daily",
            evidence_section_ids=["s1"], scope_candidate="global", resolution_status="needs_review")
        session.add(row)
        await session.commit()
        await ShadowMemoryPublicationService(session).reject(
            candidate_id=row.id, actor_id=None, reason="Incorrect extraction")
        await session.commit()

        assert await semantic_memory.list_retryable_shadow_snapshots(_=None) == []
        with pytest.raises(HTTPException) as exc:
            await semantic_memory.reextract_shadow_snapshot(snapshot.id, _=None)
        assert exc.value.status_code == 410
        assert exc.value.detail == "legacy_extraction_disabled"

        await session.refresh(snapshot)
        await session.refresh(row)
        assert snapshot.active_attempt_id == attempt.id
        assert row.resolution_status == "rejected"
        assert (await session.scalars(select(DocumentMemoryExtractionAttempt.id))).all() == [attempt.id]
