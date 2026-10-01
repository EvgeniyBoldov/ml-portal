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
    MemoryScopeProposal, MemoryCandidateScopeProposal,
)
from app.models.memory_scope import MemoryClaimScope
from app.models.rag import RAGDocument
from app.runtime.memory.shadow_document_study import ShadowDocumentStudyService, ShadowStudyItem
from app.runtime.memory.shadow_memory_publication import ShadowMemoryPublicationService
from app.workers.tasks_shadow_document_memory import _attempt_message_matches

pytestmark = pytest.mark.skipif(os.getenv("MEMORY_WORKFLOW_PG") != "1", reason="requires opt-in PostgreSQL")


def migration(conn, revision, action):
    with Operations.context(MigrationContext.configure(conn)):
        getattr(importlib.import_module(f"app.migrations.versions.{revision}"), action)()


@pytest_asyncio.fixture
async def pg():
    schema = "memory_fix_test_" + uuid4().hex
    admin = create_async_engine(get_settings().ASYNC_DB_URL)
    engine = None
    try:
        async with admin.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
            names = (await conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public'"))).scalars().all()
            for name in names:
                quoted = name.replace('"', '""')
                await conn.execute(text(f'CREATE TABLE "{schema}"."{quoted}" (LIKE public."{quoted}" INCLUDING ALL)'))
        engine = create_async_engine(get_settings().ASYNC_DB_URL,
            connect_args={"server_settings": {"search_path": f'"{schema}",public'}})
        async with engine.begin() as conn:
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
async def test_scope_context_migration_preserves_persisted_runtime_context(pg):
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
async def test_plan_task_scope_and_memory_survive_new_session(pg):
    from app.runtime.memory.effective_scope import EffectiveScopeContext, ScopeIdentity
    from app.runtime.plan_store import SqlPlanStore
    from app.runtime.orchestrator_contracts import IterationProposal
    await upgrade_scope_context(pg)
    scopes = [ScopeIdentity(key=key, type=key.partition(".")[0], source="turn")
              for key in ("project.a", "project.b", "team.ops")]
    context = EffectiveScopeContext(selected=scopes, ceiling_keys=[scope.key for scope in scopes])
    core = [{"scope": "user", "subject": "role", "value": "engineer"}, {"type": "memory_recall"}]
    async with AsyncSession(pg, expire_on_commit=False) as session:
        store = SqlPlanStore(session)
        plan = await store.create(goal="goal", root_run_id=uuid4(), tenant_id=uuid4(),
                                  scope_context=context.model_payload(), memory_context=core)
        plan_id = plan.id
        proposal = IterationProposal.model_validate({"terminal": "planner", "tasks": [{
            "task_id": "t", "executor": "worker", "intent": "inspect B", "instructions": "Inspect B",
            "scope_keys": ["project.b"], "scope_reason": "This task inspects only B"}]})
        await store.apply_iteration(plan_id, proposal)
        await store.update_memory_context(plan_id, [{"type": "planner_memory_result", "query_key": str(i)} for i in range(35)])
    async with AsyncSession(pg, expire_on_commit=False) as session:
        store = SqlPlanStore(session)
        snapshot = await store.snapshot(plan_id)
        await store.claim_task(plan_id, "t")
        task = await store.task_request(plan_id, "t")
        assert task["scope_context"]["keys"] == ["project.b", "team.ops"]
        assert task["scope_context"]["ceiling_keys"] == ["project.b", "team.ops"]
        assert snapshot["memory_context"][:2] == core
        assert len(snapshot["memory_context"]) == 32


@pytest.mark.asyncio
async def test_populated_upgrade_safe_downgrade_and_history_refusal(pg):
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
async def test_term_scope_memory_cycle_and_second_document_reuses_published_term(pg):
    await upgrade(pg)
    async with AsyncSession(pg, expire_on_commit=False) as session:
        snapshot, attempt = await new_snapshot(session)
        service = ShadowDocumentStudyService(session)
        term = ShadowStudyItem(candidate_type="term", subject="Example", scope_type="product",
                              content={"definition": "Example product"}, evidence_section_ids=["s1"])
        memory = ShadowStudyItem(candidate_type="rule", subject="Deploy", content={"statement": "Deploy daily", "effect": "require"},
            evidence_section_ids=["s1"], scope_proposals=[{"scope_type": "product", "name": "Example", "term_subject": "Example"}])
        await service.persist_batch(snapshot=snapshot, attempt=attempt, items=[term, memory], document_scope="global",
                                    section_ids={"s1"}, projects_by_key={}, scopes_by_key={})
        await service.finalize(snapshot, attempt)
        await session.commit()
        rows = (await session.scalars(select(MemoryExtractionCandidate).where(MemoryExtractionCandidate.snapshot_id == snapshot.id).order_by(MemoryExtractionCandidate.ordinal))).all()
        proposal = await session.scalar(select(MemoryScopeProposal).where(MemoryScopeProposal.snapshot_id == snapshot.id))
        bindings = (await session.scalars(select(MemoryCandidateScopeProposal))).all()
        assert len(bindings) == 1 and bindings[0].candidate_id == rows[1].id
        term_id, memory_id = rows[0].id, rows[1].id
        publisher = ShadowMemoryPublicationService(session)
        with pytest.raises(ValueError):
            await publisher.approve(candidate_id=memory_id, actor_id=None, reason=None)
        await session.rollback()
        await publisher.approve(candidate_id=term_id, actor_id=None, reason=None)
        await session.commit()
        await session.refresh(proposal)
        assert proposal.status == "needs_review"
        await publisher.approve_scope_proposal(proposal_id=proposal.id, actor_id=None)
        await session.commit()
        from app.runtime.memory.mechanical_lookup import MechanicalLookupService
        lookup = await MechanicalLookupService(session).lookup(query="Example", tenant_id=None)
        assert any(item["id"] == str(proposal.memory_scope_id) for item in lookup["scope_candidates"])
        await publisher.approve(candidate_id=memory_id, actor_id=None, reason=None)
        await session.commit()
        assert await session.scalar(select(MemoryClaimScope.scope_id)) == proposal.memory_scope_id
        await session.refresh(snapshot)
        await session.refresh(attempt)
        assert snapshot.status == "approved" and attempt.status == "completed"
        snapshot2, attempt2 = await new_snapshot(session)
        # Propose the same scope independently; shared canonical scope is allowed.
        await service.persist_batch(snapshot=snapshot2, attempt=attempt2, items=[term], document_scope="global",
                                    section_ids={"s1"}, projects_by_key={}, scopes_by_key={})
        await session.commit()
        proposals = (await session.scalars(select(MemoryScopeProposal))).all()
        assert len(proposals) == 2
        assert all(p.memory_scope_id == proposal.memory_scope_id for p in proposals)


@pytest.mark.asyncio
async def test_two_sessions_refresh_attempt_and_serialize_duplicate_cursor(pg):
    await upgrade(pg)
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
async def test_rejection_retry_listing_feedback_and_queue_recovery(pg, monkeypatch):
    from fastapi import HTTPException
    from app.api.v1.routers.admin import semantic_memory
    from app.models.rag_ingest import Source
    import app.workers.tasks_shadow_document_memory as worker
    from unittest.mock import Mock
    await upgrade(pg)
    async with AsyncSession(pg, expire_on_commit=False) as session:
        snapshot, attempt = await new_snapshot(session)
        session.add(Source(source_id=snapshot.document_id, tenant_id=uuid4()))
        row = MemoryExtractionCandidate(snapshot_id=snapshot.id, attempt_id=attempt.id, ordinal=0,
            candidate_type="rule", subject="Deploy", normalized_subject="deploy",
            content={"statement": "Deploy daily", "effect": "require"}, content_text="x" * 5000,
            evidence_section_ids=["s1"], scope_candidate="global", resolution_status="needs_review")
        session.add(row)
        await session.commit()
        publisher = ShadowMemoryPublicationService(session)
        await publisher.reject(candidate_id=row.id, actor_id=None, reason="Incorrect extraction")
        await session.commit()
        # A fresh GET derives the retry button from the database after page reload.
        listing = await semantic_memory.list_retryable_shadow_snapshots(db=session, _=None)
        assert listing[0]["snapshot_id"] == str(snapshot.id)
        assert listing[0]["attempt_number"] == 1
        delay = Mock(side_effect=ConnectionError("broker down"))
        monkeypatch.setattr(worker.study_shadow_document_sections, "delay", delay)
        result = await semantic_memory.reextract_shadow_snapshot(snapshot.id, db=session, _=None)
        assert result.attempt_number == 2 and result.status == "queued"
        current = await session.get(DocumentMemoryExtractionAttempt, result.attempt_id)
        assert current.feedback[0]["candidate_id"] == str(row.id)
        assert current.feedback[0]["attempt_id"] == str(attempt.id)
        assert len(current.feedback[0]["content_text"]) == 4000
        assert await semantic_memory.list_retryable_shadow_snapshots(db=session, _=None) == []
        with pytest.raises(HTTPException) as exc:
            await semantic_memory.reextract_shadow_snapshot(snapshot.id, db=session, _=None)
        assert exc.value.status_code == 409
        delay.side_effect = None
        assert await worker.dispatch_pending_shadow_studies(session) == 1
        delay.assert_called_with(str(snapshot.id), str((await session.scalar(select(Source.tenant_id)))), str(current.id), 0)
        old_candidate_id = row.id
        with pytest.raises(ValueError, match="inactive extraction attempt"):
            await publisher.approve(candidate_id=old_candidate_id, actor_id=None, reason=None)
