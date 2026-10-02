from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.runtime.memory.index_dispatch import dispatch_memory_index
from app.runtime.memory.service import MemorySnapshot
from app.runtime.memory.dto import FactDTO
from app.models.memory import FactScope, FactSource
from app.runtime.memory.search import _memory_context
from app.runtime.agent_executor import _render_memory_recall
from app.runtime.memory.effective_scope import project_memory_context


@pytest.mark.asyncio
async def test_index_dispatch_handles_broker_outage_and_retries_without_losing_ids(monkeypatch):
    from app.workers.tasks_memory import index_memory_items
    delay = Mock(side_effect=ConnectionError('broker offline'))
    monkeypatch.setattr(index_memory_items, 'delay', delay)
    id_ = uuid4()
    assert await dispatch_memory_index([id_]) is False
    delay.side_effect = None
    assert await dispatch_memory_index([id_, id_]) is True
    assert delay.call_args.args == ([str(id_)],)


def test_large_user_profile_keeps_relevant_tenant_fact_in_planner_profile():
    users = tuple(FactDTO(scope=FactScope.USER, subject=f'unrelated.{index}', value='new', source=FactSource.SYSTEM) for index in range(20))
    tenant = FactDTO(scope=FactScope.TENANT, subject='jira.default_project', value='OPS', source=FactSource.SYSTEM)
    selected = MemorySnapshot(user_facts=users, tenant_facts=(tenant,)).planner_context(query='jira project', limit=4)
    assert any(item['scope'] == 'tenant' and item['value'] == 'OPS' for item in selected)
    assert len(selected) == 4


def test_owned_fact_conflict_survives_task_handoff_and_does_not_require_document_rag():
    facts = [{'scope': 'user', 'subject': 'jira.default_project', 'value': 'A'},
             {'scope': 'tenant', 'subject': 'jira.default_project', 'value': 'B'}]
    context = _memory_context([], [], facts, [], ['fact_conflict:jira.default_project'])
    assert context['clarification_required'] and not context['rag_required']
    projected = project_memory_context(context, [])
    assert projected['clarification_required'] and not projected['rag_required']
    rendered = _render_memory_recall(projected)
    assert any('Confirmed user fact' in line and ': A' in line for line in rendered)
    assert any('Confirmed tenant fact' in line and ': B' in line for line in rendered)


@pytest.mark.asyncio
async def test_vector_search_is_restricted_to_published_applicable_ids(monkeypatch):
    from app.runtime.memory.semantic_index import MemorySemanticIndex
    from app.adapters.embeddings import EmbeddingServiceFactory
    from app.services.embedding_model_config_service import EmbeddingModelConfigService
    monkeypatch.setattr(EmbeddingModelConfigService, 'ensure_registered', AsyncMock())
    monkeypatch.setattr(EmbeddingServiceFactory, 'get_service', lambda _: NS(embed_text=lambda _: [1.0]))
    item = uuid4()
    store = NS(search=AsyncMock(return_value=[{'id': str(item)}]))
    index = MemorySemanticIndex(None, vector_store=store)
    index._global_embedding_model = AsyncMock(return_value=NS(alias='synthetic'))
    index._read_collection = AsyncMock(return_value='synthetic')
    assert await index.search_ids('query', eligible_ids=[item]) == [item]
    assert store.search.await_args.kwargs['filter']['must']['memory_item_id'] == [str(item)]
    store.search.reset_mock()
    assert await index.search_ids('query', eligible_ids=[]) == []
    store.search.assert_not_awaited()


@pytest.mark.asyncio
async def test_approval_dispatches_index_after_commit_and_queue_failure_keeps_publication(monkeypatch):
    from app.api.v1.routers.admin import semantic_memory as api
    committed = False
    item = uuid4()
    candidate = NS(id=uuid4(), snapshot_id=uuid4(), visibility_tenant_id=None, candidate_type='rule',
                   subject='Backup', normalized_subject='backup', content={'statement': 'Backup', 'effect': 'require'},
                   evidence_section_ids=['s1'], content_text='Backup', aliases=[], related_entities=[], related_project_keys=[],
                   scope_candidate='scoped', resolution_status='resolved', extraction_confidence=0.8)
    publisher = NS(approve=AsyncMock(return_value=candidate), published_item_ids={item})
    monkeypatch.setattr(api, 'ShadowMemoryPublicationService', lambda _: publisher)
    async def commit():
        nonlocal committed
        committed = True
    async def dispatch(ids):
        assert committed
        assert ids == {item}
        return False
    monkeypatch.setattr(api, 'dispatch_memory_index', dispatch)
    db = NS(commit=commit, rollback=AsyncMock())
    response = await api.approve_shadow_candidate(candidate.id, api.ShadowCandidateDecisionRequest(), db, NS(id=str(uuid4())))
    assert response.resolution_status == 'resolved'
    db.rollback.assert_not_awaited()
