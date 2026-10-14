"""Opt-in real PostgreSQL + Qdrant integration with isolated synthetic records."""
import os
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.adapters.impl.qdrant import QdrantVectorStore
from app.core.config import get_settings
from app.models.model_registry import Model, ModelType, ModelStatus
from app.services.vector_index_service import VectorIndexService

pytestmark = pytest.mark.skipif(os.getenv("VECTOR_MODEL_WORKFLOW") != "1", reason="requires opt-in PostgreSQL/Qdrant")


@pytest.mark.asyncio
async def test_different_dimensions_index_search_and_default_switch():
    engine = create_async_engine(get_settings().ASYNC_DB_URL)
    store = QdrantVectorStore()
    created = []
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                async with AsyncSession(bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint") as session:
                    models = [Model(alias="vector-test-" + uuid4().hex, name="Test encoder", type=ModelType.EMBEDDING,
                                    provider="local", connector="local_emb_http", provider_model_name="test-encoder",
                                    base_url="http://unused", embedding_dimensions=dim, max_input_tokens=8192,
                                    model_version="test-v1", enabled=True, status=ModelStatus.AVAILABLE)
                              for dim in [384, 1024]]
                    session.add_all(models)
                    await session.flush()
                    base = "vector-test-" + uuid4().hex
                    resolver = VectorIndexService(session)
                    targets = await resolver.resolve_many(base, [model.alias for model in models])
                    assert targets[0].collection_name != targets[1].collection_name
                    for target in targets:
                        await store.ensure_collection(target.collection_name, target.dimensions)
                        created.append(target.collection_name)
                        vector = [1.0] + [0.0] * (target.dimensions-1)
                        await store.upsert(target.collection_name, [vector], [{"text":"test", "embed_model_alias":target.model_alias,
                                           "embedding_fingerprint":target.fingerprint}], [str(uuid4())])
                        assert await store.count_by_filter(target.collection_name, {"embed_model_alias":target.model_alias}) == 1
                        hits = await store.search(target.collection_name, vector)
                        assert len(hits) == 1
                        assert hits[0]["payload"]["embed_model_alias"] == target.model_alias
                    models[1].default_for_type = True
                    await session.flush()
                    reordered = await resolver.resolve_many(base, [model.alias for model in reversed(models)])
                    assert [target.collection_name for target in reordered] == [target.collection_name for target in reversed(targets)]
                    models[0].embedding_dimensions = 1024
                    await session.flush()
                    replacement = await resolver.resolve(base, models[0].alias)
                    assert replacement.collection_name != targets[0].collection_name
                    assert await store.vector_dimension(targets[0].collection_name) == 384
                    assert await store.collection_exists(targets[1].collection_name)
            finally:
                await transaction.rollback()
    finally:
        for name in created:
            await store.delete_collection(name)
        await (await store.get_client()).close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_bulk_reindex_detects_dimension_change_and_legacy_same_version():
    from app.models.tenant import Tenants
    from app.models.rag import RAGDocument
    from app.models.rag_ingest import RAGStatus
    from app.services.model_capabilities import embedding_fingerprint
    from app.services.rag_batch_reindex_orchestrator import RAGBatchReindexOrchestrator
    engine = create_async_engine(get_settings().ASYNC_DB_URL)
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                async with AsyncSession(bind=connection, expire_on_commit=False, join_transaction_mode='create_savepoint') as session:
                    tenant = Tenants(name='Vector test ' + uuid4().hex)
                    encoder = Model(alias='vector-test-' + uuid4().hex, name='Test encoder', type=ModelType.EMBEDDING,
                                    provider='local', connector='local_emb_http', provider_model_name='encoder',
                                    base_url='http://unused', embedding_dimensions=384, max_input_tokens=256,
                                    model_version='v1', enabled=True, status=ModelStatus.AVAILABLE)
                    session.add_all([tenant, encoder])
                    await session.flush()
                    doc = RAGDocument(tenant_id=tenant.id, user_id=uuid4(), filename='test.txt', title='test', status='ready')
                    session.add(doc)
                    await session.flush()
                    node = RAGStatus(doc_id=doc.id, node_type='index', node_key=encoder.alias,
                                     status='completed', model_version='v1', metrics_json={'embedding_fingerprint':embedding_fingerprint(encoder)})
                    session.add(node)
                    await session.flush()
                    orchestrator = RAGBatchReindexOrchestrator(session)
                    options = dict(tenant_id=tenant.id, model_alias=encoder.alias, limit=100, dry_run=True)
                    assert (await orchestrator.enqueue_stale_documents(**options)).scanned == 0
                    encoder.embedding_dimensions = 1024
                    await session.flush()
                    stale = await orchestrator.enqueue_stale_documents(**options)
                    assert stale.scanned == 1 and stale.queued == 0
                    assert stale.items[0]['doc_id'] == str(doc.id)
                    node.metrics_json = None
                    await session.flush()
                    assert (await orchestrator.enqueue_stale_documents(**options)).scanned == 1
                    node.status = 'processing'
                    await session.flush()
                    assert (await orchestrator.enqueue_stale_documents(**options)).scanned == 0
                    await session.delete(node)
                    session.add(RAGStatus(doc_id=doc.id, node_type='pipeline', node_key='chunk', status='completed'))
                    await session.flush()
                    assert (await orchestrator.enqueue_stale_documents(**options)).scanned == 1
                    session.add(RAGStatus(doc_id=doc.id, node_type='embedding', node_key=encoder.alias, status='queued'))
                    await session.flush()
                    assert (await orchestrator.enqueue_stale_documents(**options)).scanned == 0
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()


@pytest.mark.skipif(os.getenv('VECTOR_REAL_ENCODERS') != '1', reason='requires running MiniLM/BGE services')
@pytest.mark.asyncio
async def test_real_minilm_and_bge_vectors_index_and_retrieve():
    import asyncio
    import httpx
    from app.services.bounded_embeddings import embed_texts_bounded
    engine = create_async_engine(get_settings().ASYNC_DB_URL)
    store = QdrantVectorStore()
    created = []
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                async with AsyncSession(bind=connection, expire_on_commit=False, join_transaction_mode='create_savepoint') as session:
                    base = 'real-vector-test-' + uuid4().hex
                    async with httpx.AsyncClient(timeout=10) as client:
                        for endpoint in ['http://emb:8001', 'http://emb-bge:8001']:
                            response = await client.get(endpoint + '/description')
                            response.raise_for_status()
                            info = response.json()
                            model = Model(alias='real-vector-test-' + uuid4().hex, name='Test encoder', type=ModelType.EMBEDDING,
                                          provider='local', connector='local_emb_http', provider_model_name=info['alias'], base_url=endpoint,
                                          embedding_dimensions=info['dimensions'], max_input_tokens=info['max_tokens'],
                                          model_version=info['version'], enabled=True, status=ModelStatus.AVAILABLE)
                            session.add(model)
                            await session.flush()
                            target = await VectorIndexService(session).resolve(base, model.alias)
                            texts = ['Настройка маршрутизатора и интерфейсов сети. ' * 15, 'Рецепт приготовления яблочного пирога.']
                            vectors = await asyncio.to_thread(embed_texts_bounded, target.embedding_service, texts)
                            assert len(vectors) == 2
                            assert all(len(vector) == target.dimensions for vector in vectors)
                            assert vectors[0] != vectors[1]
                            await store.ensure_collection(target.collection_name, target.dimensions)
                            created.append(target.collection_name)
                            await store.upsert(target.collection_name, vectors,
                                [{'chunk_id':str(i), 'text':text, 'embed_model_alias':model.alias, 'embedding_fingerprint':target.fingerprint}
                                 for i, text in enumerate(texts)], [str(uuid4()), str(uuid4())])
                            query = await asyncio.to_thread(embed_texts_bounded, target.embedding_service, [texts[0]])
                            hits = await store.search(target.collection_name, query[0], top_k=2)
                            assert hits[0]['payload']['chunk_id'] == '0'
                            assert hits[0]['score'] > 0.99
            finally:
                await transaction.rollback()
    finally:
        for name in created:
            await store.delete_collection(name)
        await (await store.get_client()).close()
        await engine.dispose()
