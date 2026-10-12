from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.agents.context import ToolContext
from app.agents.builtins.collection_doc_search import CollectionDocSearchTool
from app.agents.runtime.rerank_client import RerankScoredIndex


@pytest.mark.asyncio
async def test_doc_search_returns_direct_data_only_after_file_references_commit(monkeypatch):
    import app.agents.builtins.collection_doc_search as module
    tenant, source, reference = uuid4(), uuid4(), uuid4()
    session = AsyncMock()
    session.__aenter__.return_value = session
    result = Mock()
    result.scalars.return_value.all.return_value = [SimpleNamespace(source_id=source, id=uuid4())]
    session.execute.return_value = result
    monkeypatch.setattr('app.core.db.get_session_factory', lambda: lambda: session)
    collection = SimpleNamespace(id=uuid4(), tenant_id=tenant, slug='reglament', collection_type='document',
                                 qdrant_collection_name='reglament', fields=[])
    monkeypatch.setattr('app.services.collection_service.CollectionService', lambda _: SimpleNamespace(get_by_slug=AsyncMock(return_value=collection)))
    monkeypatch.setattr('app.services.collection.vector_lifecycle.CollectionVectorLifecycleService', lambda _: SimpleNamespace(resolve_target_vector_models=AsyncMock(return_value=['emb'])))
    monkeypatch.setattr('app.services.collection.vector_lifecycle.build_model_scoped_qdrant_collections', lambda *args: [('emb', 'reglament_emb')])
    store = SimpleNamespace(collection_exists=AsyncMock(return_value=True), search=AsyncMock(return_value=[
        {'id': 'hit', 'score': 0.9, 'payload': {'source_id': str(source), 'chunk_id': 'chunk', 'text': 'Backup before changes'}}]))
    monkeypatch.setattr('app.adapters.impl.qdrant.QdrantVectorStore', lambda: store)
    monkeypatch.setattr('app.services.embedding_model_config_service.EmbeddingModelConfigService.ensure_registered', AsyncMock())
    monkeypatch.setattr('app.adapters.embeddings.EmbeddingServiceFactory.get_service', lambda _: SimpleNamespace(
        get_model_info=lambda: SimpleNamespace(dimensions=3), embed_texts=lambda _: [[0.1, 0.2, 0.3]]))
    monkeypatch.setattr('app.agents.runtime.rerank_client.rerank_scores', AsyncMock(return_value=[RerankScoredIndex(index=0, score=0.8)]))
    register = AsyncMock(return_value=SimpleNamespace(id=reference))
    monkeypatch.setattr(module, 'ChatArtifactReferenceService', lambda _: SimpleNamespace(register=register))
    tool = CollectionDocSearchTool()
    monkeypatch.setattr(tool, '_get_source_names', AsyncMock(return_value={str(source): 'Regulation'}))
    monkeypatch.setattr(tool, '_get_row_metadata', AsyncMock(return_value={}))
    out = await tool.v1_0_0(ToolContext(user_id=uuid4(), tenant_id=tenant, chat_id=uuid4()),
                            {'collection_slug': 'reglament', 'query': 'backup', 'k': 5})
    assert out.success, out.error
    assert out.delivery == 'direct'
    assert out.data['hits'][0]['artifact_id'] == str(reference)
    register.assert_awaited_once()
    session.commit.assert_awaited_once()
