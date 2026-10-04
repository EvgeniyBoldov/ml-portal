"""Review tags round trips in a disposable clone of the current schema."""
import os
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import get_settings
from app.models.document_memory_staging import (
    DocumentMemorySnapshot, GlossaryTerm, MemoryCandidateDecision,
    MemoryCandidateScopeProposal, MemoryExtractionCandidate, MemoryScopeProposal,
)
from app.models.memory import MemoryClaim
from app.models.memory_scope import MemoryCandidateScope, MemoryClaimScope, MemoryScope
from app.models.rag import RAGDocument
from app.runtime.memory.shadow_document_study import ShadowDocumentStudyService
from app.runtime.memory.shadow_memory_publication import ShadowMemoryPublicationService
from app.api.v1.routers.admin.semantic_memory import _shadow_candidate_response

pytestmark = pytest.mark.skipif(os.getenv('MEMORY_WORKFLOW_PG') != '1', reason='requires opt-in PostgreSQL')


@pytest_asyncio.fixture
async def tag_pg():
    schema = 'memory_tag_test_' + uuid4().hex
    admin = create_async_engine(get_settings().ASYNC_DB_URL)
    engine = None
    try:
        async with admin.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
            tables = (await conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public'"))).scalars().all()
            for name in tables:
                quoted = name.replace('"', '""')
                await conn.execute(text(f'CREATE TABLE "{schema}"."{quoted}" (LIKE public."{quoted}" INCLUDING ALL)'))
        engine = create_async_engine(get_settings().ASYNC_DB_URL,
            connect_args={'server_settings': {'search_path': f'"{schema}",public'}})
        yield engine
    finally:
        if engine:
            await engine.dispose()
        async with admin.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await admin.dispose()


async def seed(session):
    document = RAGDocument(user_id=uuid4(), filename='synthetic.txt', title='Synthetic review', scope='global', status='ready')
    session.add(document)
    await session.flush()
    snapshot = DocumentMemorySnapshot(document_id=document.id, canonical_checksum=uuid4().hex, status='awaiting_review')
    session.add(snapshot)
    await session.flush()
    attempt = await ShadowDocumentStudyService(session).ensure_active_attempt(snapshot)
    await session.flush()
    term = MemoryExtractionCandidate(snapshot_id=snapshot.id, attempt_id=attempt.id, ordinal=0, candidate_type='term',
        subject='Network', normalized_subject='network', content={'definition': 'Company network'},
        content_text='Company network', evidence_section_ids=['s1'], resolution_status='needs_review')
    session.add(term)
    await session.flush()
    await ShadowMemoryPublicationService(session).approve(candidate_id=term.id, actor_id=None, reason=None)
    glossary = await session.scalar(select(GlossaryTerm).where(GlossaryTerm.approved_candidate_id == term.id))
    # The pending memory keeps this snapshot open; its source remains tenant local.
    snapshot.status = 'awaiting_review'
    attempt.status = 'awaiting_review'
    visibility = uuid4()
    row = MemoryExtractionCandidate(snapshot_id=snapshot.id, attempt_id=attempt.id, ordinal=1, candidate_type='rule',
        subject='Backup', normalized_subject='backup', content={'statement': 'Create backup', 'effect': 'require'},
        content_text='Create backup', evidence_section_ids=['s1'], resolution_status='needs_review',
        scope_candidate='unknown', visibility_tenant_id=visibility,
        unresolved_scope_references=[{'name': 'Legacy area', 'reason': 'missing_term'}])
    scope = MemoryScope(scope_type='team', key='team.ops', name='Operations', aliases=[], is_all=False)
    session.add_all([row, scope])
    await session.flush()
    session.add(MemoryCandidateScope(candidate_id=row.id, scope_id=scope.id, role='applies_to',
                                    status='suggested', method='llm_suggestion', confidence=0.7))
    proposal = MemoryScopeProposal(snapshot_id=snapshot.id, attempt_id=attempt.id, scope_type='team',
        proposed_key='team.old', normalized_key='old', name='Old', aliases=[], glossary_term_id=glossary.id,
        evidence_section_ids=['s1'], status='needs_review')
    session.add(proposal)
    await session.flush()
    session.add(MemoryCandidateScopeProposal(candidate_id=row.id, scope_proposal_id=proposal.id,
        role='applies_to', status='suggested', method='llm_suggestion', confidence=0.7))
    await session.commit()
    return row.id, scope.id, glossary.id, visibility


@pytest.mark.asyncio
@pytest.mark.parametrize('outside_projects', [False, True])
async def test_manual_applicability_persists_and_publishes_with_term_links(tag_pg, outside_projects):
    async with AsyncSession(tag_pg, expire_on_commit=False) as session:
        candidate_id, scope_id, term_id, visibility = await seed(session)
        await ShadowMemoryPublicationService(session).update_review_tags(
            candidate_id=candidate_id, actor_id=None, scope_ids=[] if outside_projects else [scope_id],
            glossary_term_ids=[term_id], reason='Confirmed against source',
        )
        await session.commit()
    async with AsyncSession(tag_pg, expire_on_commit=False) as session:
        row = await session.get(MemoryExtractionCandidate, candidate_id)
        response = await _shadow_candidate_response(session, row)
        assert response.content_valid and not response.approval_blockers
        assert response.scope_candidate == ('global' if outside_projects else 'scoped')
        assert response.scope_ids == ([] if outside_projects else [scope_id])
        assert response.glossary_term_ids == [term_id]
        assert response.scope_proposals == []
        assert row.visibility_tenant_id == visibility
        assert (await session.scalar(select(MemoryCandidateScopeProposal.status).where(
            MemoryCandidateScopeProposal.candidate_id == candidate_id))) == 'superseded'
        assert (await session.scalar(select(MemoryCandidateDecision).where(
            MemoryCandidateDecision.candidate_id == candidate_id, MemoryCandidateDecision.action == 'edit'))).payload['before']['scope'] == 'unknown'
        await ShadowMemoryPublicationService(session).approve(candidate_id=candidate_id, actor_id=None, reason=None)
        await session.commit()
    async with AsyncSession(tag_pg, expire_on_commit=False) as session:
        row = await session.get(MemoryExtractionCandidate, candidate_id)
        assert row.resolution_status == 'resolved'
        assert row.related_entities[0]['id'] == str(term_id)
        claim = await session.scalar(select(MemoryClaim).where(MemoryClaim.approved_candidate_id == candidate_id))
        assert claim.visibility_tenant_id == visibility
        ids = (await session.scalars(select(MemoryClaimScope.scope_id).where(MemoryClaimScope.claim_id == claim.id))).all()
        assert list(ids) == ([] if outside_projects else [scope_id])


@pytest.mark.asyncio
async def test_term_only_link_publishes_and_invalid_scope_rolls_back(tag_pg):
    async with AsyncSession(tag_pg, expire_on_commit=False) as session:
        candidate_id, scope_id, term_id, _ = await seed(session)
        with pytest.raises(ValueError, match='Unknown memory scope ID'):
            await ShadowMemoryPublicationService(session).update_review_tags(candidate_id=candidate_id, actor_id=None,
                scope_ids=[uuid4()], glossary_term_ids=[], reason='Invalid selection')
        await session.rollback()
        row = await session.get(MemoryExtractionCandidate, candidate_id)
        assert row.unresolved_scope_references
        assert not (await session.scalars(select(MemoryCandidateDecision).where(
            MemoryCandidateDecision.candidate_id == candidate_id, MemoryCandidateDecision.action == 'edit'))).all()
        await ShadowMemoryPublicationService(session).update_review_tags(candidate_id=candidate_id, actor_id=None,
            scope_ids=[], glossary_term_ids=[term_id], reason='Only a term link')
        await session.commit()
    async with AsyncSession(tag_pg, expire_on_commit=False) as session:
        row = await session.get(MemoryExtractionCandidate, candidate_id)
        response = await _shadow_candidate_response(session, row)
        assert response.scope_candidate == 'global' and not response.approval_blockers
        assert response.glossary_term_ids == [term_id]
        await ShadowMemoryPublicationService(session).approve(candidate_id=candidate_id, actor_id=None, reason=None)
        await session.commit()
        assert row.resolution_status == 'resolved'
