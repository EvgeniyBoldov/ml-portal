"""Publication, scope, term and ownership reads against an isolated PostgreSQL schema."""
import os
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.test_memory_candidate_tags import tag_pg, seed
from app.models.document_memory_staging import MemoryExtractionCandidate, DocumentMemorySnapshot
from app.models.memory import MemoryClaim, MemoryItem, Fact, FactScope
from app.models.memory_scope import MemoryScope
from app.models.rag import RAGDocument
from app.runtime.memory.shadow_memory_publication import ShadowMemoryPublicationService
from app.runtime.memory.recall import MemoryRecallService
from app.runtime.memory.semantic_index import MemorySemanticIndex
from app.runtime.memory.fact_store import FactStore

pytestmark = pytest.mark.skipif(os.getenv('MEMORY_WORKFLOW_PG') != '1', reason='requires opt-in PostgreSQL')


async def publish(session, *, term_only=False):
    candidate_id, scope_id, term_id, _ = await seed(session)
    scope = await session.get(MemoryScope, scope_id)
    scope.key, scope.name = 'new', 'New scope'
    candidate = await session.get(MemoryExtractionCandidate, candidate_id)
    candidate.visibility_tenant_id = None
    candidate.subject, candidate.normalized_subject = 'Backup', 'backup'
    candidate.content = {'statement': 'Create backup', 'effect': 'require'}
    publisher = ShadowMemoryPublicationService(session)
    await publisher.update_review_tags(candidate_id=candidate_id, actor_id=None,
        scope_ids=[] if term_only else [scope_id], glossary_term_ids=[term_id], reason='Reviewed')
    await publisher.approve(candidate_id=candidate_id, actor_id=None, reason=None)
    await session.commit()
    claim = await session.scalar(select(MemoryClaim).where(MemoryClaim.approved_candidate_id == candidate_id))
    return candidate, scope, claim


@pytest.mark.asyncio
async def test_memory_card_preserves_candidate_links_and_source_identity(tag_pg):
    from app.api.v1.routers.admin.semantic_memory import get_shadow_candidate, get_semantic_memory_item
    from app.services.semantic_memory_admin_service import SemanticMemoryAdminService
    async with AsyncSession(tag_pg, expire_on_commit=False) as session:
        candidate, scope, claim = await publish(session)
        draft = await get_shadow_candidate(candidate.id, db=session, _=None)
        card = await get_semantic_memory_item(claim.memory_item_id, db=session, _=None)
        assert draft.document_title == 'Synthetic review'
        assert draft.scope_keys == [scope.key]
        assert card.scope_keys == draft.scope_keys
        assert card.related_entities == draft.related_entities
        assert str(card.related_entities[0]['id']) == str(draft.glossary_term_ids[0])
        assert card.claims[0].approved_candidate_id == candidate.id
        assert card.sources[0].document_title == draft.document_title
        page = await SemanticMemoryAdminService(session).list_items(scope_id=scope.id)
        assert page.total == 1
        assert page.rows[0].item.id == card.id


@pytest.mark.asyncio
async def test_owned_fact_lookup_reaches_old_fact_and_keeps_scopes_and_conflict(tag_pg):
    from datetime import datetime, timedelta, timezone
    async with AsyncSession(tag_pg, expire_on_commit=False) as session:
        user, tenant, stranger = uuid4(), uuid4(), uuid4()
        for scope, owner_type, owner_id, value in [('user', 'user', user, 'A'), ('tenant', 'tenant', tenant, 'B'), ('user', 'user', stranger, 'SECRET')]:
            session.add(Fact(scope=scope, owner_type=owner_type, owner_id=owner_id, subject='jira.default_project',
                             value=value, status='confirmed', source='system', observed_at=datetime.now(timezone.utc) - timedelta(days=30)))
        session.add(Fact(scope='user', owner_type='user', owner_id=user, subject='jira.pending', value='PENDING', status='pending', source='system'))
        for index in range(60):
            session.add(Fact(scope='user', owner_type='user', owner_id=user, subject=f'unrelated.{index}', value='new', status='confirmed', source='system'))
        await session.commit()
        result = await FactStore(session).search(query='jira project', user_id=user, tenant_id=tenant,
                                               scopes=[FactScope.USER, FactScope.TENANT], limit=4)
        assert {fact.value for fact in result} == {'A', 'B'}
        assert {fact.scope for fact in result} == {FactScope.USER, FactScope.TENANT}


@pytest.mark.asyncio
async def test_collection_source_requires_permission_and_can_be_shared_across_tenants(tag_pg):
    async with AsyncSession(tag_pg, expire_on_commit=False) as session:
        candidate, scope, claim = await publish(session)
        doc = await session.get(RAGDocument, claim.document_id)
        doc.scope, doc.tenant_id = 'collection', uuid4()
        claim.visibility_tenant_id = doc.tenant_id
        await session.commit()
        recall = MemoryRecallService(session=session, preparer=None)
        # No authorized membership: matching tenant alone is insufficient.
        rows = await recall._accessible_semantic_items(project_ids=[], semantic_ids=[claim.memory_item_id], tenant_id=doc.tenant_id,
                                                       context_scope_keys=[scope.key], collection_ids=[])
        assert rows == []
        from app.models.rag_ingest import DocumentCollectionMembership
        collection = uuid4()
        session.add(DocumentCollectionMembership(tenant_id=doc.tenant_id, source_id=doc.id, collection_id=collection))
        await session.commit()
        rows = await recall._accessible_semantic_items(project_ids=[], semantic_ids=[claim.memory_item_id], tenant_id=uuid4(),
                                                       context_scope_keys=[scope.key], collection_ids=[collection])
        assert len(rows) == 1


@pytest.mark.asyncio
async def test_hipporag_corpus_is_filtered_before_native_graph_work(tag_pg, monkeypatch):
    from app.runtime.memory import retrieval
    monkeypatch.setattr(retrieval, 'get_settings', lambda: NS(MEMORY_SEARCH_BACKEND='hipporag'))
    graph_search = AsyncMock(return_value=[])
    monkeypatch.setattr(retrieval, 'HippoRAGService', lambda _: NS(search_ids=graph_search))
    async with AsyncSession(tag_pg, expire_on_commit=False) as session:
        _, scope, claim = await publish(session)
        doc = await session.get(RAGDocument, claim.document_id)
        doc.scope, doc.tenant_id = 'collection', uuid4()
        claim.visibility_tenant_id = doc.tenant_id
        await session.commit()
        recall = MemoryRecallService(session=session, preparer=None)
        args = dict(project_ids=[], tenant_id=doc.tenant_id, user_id=uuid4(),
                    context_scope_keys=[scope.key], collection_ids=[])
        eligible = await recall.eligible_item_ids(**args)
        assert await retrieval.retrieve_memory_ids(recall, 'backup', eligible_ids=eligible, read_args=args) == []
        graph_search.assert_not_awaited()
        from app.models.rag_ingest import DocumentCollectionMembership
        collection = uuid4()
        session.add(DocumentCollectionMembership(tenant_id=doc.tenant_id, source_id=doc.id, collection_id=collection))
        await session.commit()
        args['collection_ids'] = [collection]
        eligible = await recall.eligible_item_ids(**args)
        await retrieval.retrieve_memory_ids(recall, 'backup', eligible_ids=eligible, read_args=args)
        items = graph_search.await_args.kwargs['items']
        assert [item['selected_claim_id'] for item in items] == [str(claim.id)]
        graph_search.reset_mock()
        args['context_scope_keys'] = ['other']
        eligible = await recall.eligible_item_ids(**args)
        await retrieval.retrieve_memory_ids(recall, 'backup', eligible_ids=eligible, read_args=args)
        graph_search.assert_not_awaited()


@pytest.mark.asyncio
async def test_manual_legacy_attempt_requires_new_publication(tag_pg):
    from app.runtime.memory.shadow_document_study import ShadowDocumentStudyService
    from app.models.document_memory_staging import DocumentMemoryExtractionAttempt
    async with AsyncSession(tag_pg, expire_on_commit=False) as session:
        candidate, scope, claim = await publish(session)
        snapshot = await session.get(DocumentMemorySnapshot, candidate.snapshot_id)
        old_id = snapshot.active_attempt_id
        service = ShadowDocumentStudyService(session)
        attempt = await service.restart_attempt(snapshot)
        await session.commit()
        assert attempt.id != old_id
        assert snapshot.status == 'queued'
        assert (await session.get(DocumentMemoryExtractionAttempt, old_id)).status == 'superseded'
        recall = MemoryRecallService(session=session, preparer=None)
        assert await recall._accessible_semantic_items(project_ids=[], semantic_ids=[claim.memory_item_id],
            tenant_id=None, context_scope_keys=[scope.key], collection_ids=[]) == []


@pytest.mark.asyncio
async def test_collection_rbac_user_deny_overrides_tenant_allow(tag_pg, monkeypatch):
    from app.models.collection import Collection
    from app.models.rbac import RbacRule
    from app.services.platform_settings_service import PlatformSettingsProvider
    from app.runtime.memory.read_policy import allowed_source_collections
    monkeypatch.setattr(PlatformSettingsProvider, 'get_config', AsyncMock(return_value={'default_collection_allow': False}))
    async with AsyncSession(tag_pg, expire_on_commit=False) as session:
        user, tenant = uuid4(), uuid4()
        collection = Collection(tenant_id=tenant, slug='synthetic-memory', name='Synthetic', collection_type='document', data_instance_id=uuid4())
        session.add(collection)
        await session.flush()
        session.add_all([
            RbacRule(level='tenant', owner_tenant_id=tenant, resource_type='collection', resource_id=collection.id, effect='allow'),
            RbacRule(level='user', owner_user_id=user, resource_type='collection', resource_id=collection.id, effect='deny'),
        ])
        await session.commit()
        assert await allowed_source_collections(session, user_id=user, tenant_id=tenant) == []
        assert await allowed_source_collections(session, user_id=uuid4(), tenant_id=tenant) == [collection.id]


@pytest.mark.asyncio
@pytest.mark.parametrize('approved', [True, False])
async def test_index_contains_only_current_approved_claim_wording(tag_pg, monkeypatch, approved):
    from app.adapters.embeddings import EmbeddingServiceFactory
    from app.services.embedding_model_config_service import EmbeddingModelConfigService
    captured = []
    service = NS(embed_texts=lambda texts: captured.extend(texts) or [[1.0] for _ in texts],
                 get_model_info=lambda: NS(dimensions=1))
    monkeypatch.setattr(EmbeddingModelConfigService, 'ensure_registered', AsyncMock())
    monkeypatch.setattr(EmbeddingServiceFactory, 'get_service', lambda _: service)
    store = NS(ensure_collection=AsyncMock(), upsert=AsyncMock())
    async with AsyncSession(tag_pg, expire_on_commit=False) as session:
        candidate, scope, claim = await publish(session)
        item = await session.get(MemoryItem, claim.memory_item_id)
        if not approved:
            claim.approved_candidate_id = None
            await session.commit()
        index = MemorySemanticIndex(session, vector_store=store)
        index._global_embedding_model = AsyncMock(return_value=NS(alias='synthetic'))
        index._write_collection = AsyncMock(return_value='synthetic')
        index.remove_items = AsyncMock()
        assert await index.index_items([item]) == int(approved)
        assert index.remove_items.await_count == int(not approved)
        assert bool(captured) == approved
        assert store.upsert.await_count == int(approved)
