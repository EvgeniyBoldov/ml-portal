"""Scope-free terms: extraction -> review API -> approval -> shared catalogue.

Only synthetic rows in a disposable schema; no application data is read.
"""
import os
from uuid import uuid4

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import get_settings
from app.models.rag import RAGDocument
from app.models.document_memory_staging import DocumentMemorySnapshot, GlossaryTerm, MemoryExtractionCandidate
from app.runtime.memory.shadow_document_study import ShadowDocumentStudyService, ShadowStudyItem
from app.runtime.memory.shadow_memory_publication import ShadowMemoryPublicationService
from app.services.glossary_service import GlossaryService
from app.api.v1.routers.admin.semantic_memory import list_shadow_candidates

pytestmark = pytest.mark.skipif(os.getenv('MEMORY_WORKFLOW_PG') != '1', reason='requires opt-in PostgreSQL')


@pytest.mark.asyncio
async def test_collection_document_term_reaches_review_and_unscoped_catalogue():
    schema = 'term_contract_' + uuid4().hex
    engine = create_async_engine(get_settings().ASYNC_DB_URL)
    scoped = None
    tables = ('ragdocuments', 'document_memory_snapshots', 'document_memory_extraction_attempts',
              'memory_extraction_candidates', 'memory_candidate_decisions', 'glossary_terms',
              'memory_candidate_project_bindings', 'memory_scopes', 'memory_candidate_scopes',
              'memory_scope_proposals', 'memory_candidate_scope_proposals', 'memory_scope_glossary_terms',
              'memory_conflict_cases', 'memory_conflict_members')
    try:
        async with engine.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
            for table in tables:
                await conn.execute(text(f'CREATE TABLE "{schema}".{table} (LIKE public.{table} INCLUDING ALL)'))
            await conn.execute(text(f'ALTER TABLE "{schema}".glossary_terms ADD CONSTRAINT term_source_test '
                f'FOREIGN KEY (approved_candidate_id) REFERENCES "{schema}".memory_extraction_candidates(id) ON DELETE SET NULL'))
        scoped = create_async_engine(get_settings().ASYNC_DB_URL,
            connect_args={'server_settings': {'search_path': f'"{schema}",public'}})
        async with AsyncSession(scoped, expire_on_commit=False) as session:
            document = RAGDocument(user_id=uuid4(), filename='synthetic.txt', title='Synthetic glossary', scope='collection', status='ready')
            session.add(document)
            await session.flush()
            snapshot = DocumentMemorySnapshot(document_id=document.id, canonical_checksum=uuid4().hex, status='studying')
            session.add(snapshot)
            await session.flush()
            study = ShadowDocumentStudyService(session)
            attempt = await study.ensure_active_attempt(snapshot)
            term = ShadowStudyItem(candidate_type='term', subject='Окно работ', aliases=['ОР'],
                content={'definition': 'Период согласованных работ'}, evidence_section_ids=['s1'])
            counts = await study.persist_batch(snapshot=snapshot, attempt=attempt, items=[term],
                section_ids={'s1'}, projects_by_key={}, scopes_by_key={})
            assert counts['created'] == 1 and counts['rejected'] == 0
            await study.finalize(snapshot, attempt)
            await session.flush()
            pending = await list_shadow_candidates(status='pending', candidate_type=None, tenant_id=None,
                limit=200, offset=0, db=session, _=None)
            assert len(pending) == 1 and pending[0].candidate_type == 'term'
            assert pending[0].scope_candidate is None and pending[0].approval_blockers == []
            assert await GlossaryService(session).list_confirmed_terms() == []
            candidate = await session.scalar(select(MemoryExtractionCandidate))
            await ShadowMemoryPublicationService(session).approve(candidate_id=candidate.id, actor_id=None, reason=None)
            await session.flush()
            assert candidate.scope_candidate is None and candidate.resolution_status == 'resolved'
            confirmed = await GlossaryService(session).list_confirmed_terms()
            assert len(confirmed) == 1 and confirmed[0]['term'] == 'Окно работ'
            # Source archiving does not revoke the administrator's terminology decision.
            document.status = 'archived'
            snapshot.status = 'superseded'
            await session.flush()
            assert len(await GlossaryService(session).list_confirmed_terms()) == 1
            await session.execute(delete(MemoryExtractionCandidate).where(MemoryExtractionCandidate.id == candidate.id))
            await session.flush()
            confirmed = await GlossaryService(session).list_confirmed_terms()
            assert len(confirmed) == 1 and confirmed[0]['source_references'] == []
            term_record = await session.scalar(select(GlossaryTerm).execution_options(populate_existing=True))
            assert term_record.approved_candidate_id is None
            await session.rollback()
    finally:
        if scoped:
            await scoped.dispose()
        async with engine.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await engine.dispose()
