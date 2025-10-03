"""
Интеграционные тесты для Qdrant.
Использует реальный Qdrant для проверки векторного поиска и эмбеддингов.
"""
import pytest
import asyncio
import uuid
import numpy as np
from typing import List, Dict, Any

from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.models import Distance, VectorParams, PointStruct


@pytest.mark.integration
class TestQdrantIntegration:
    """Интеграционные тесты для Qdrant."""

    @pytest.fixture
    def test_collection_name(self):
        """Генерирует уникальное имя коллекции для теста."""
        return f"test_collection_{uuid.uuid4().hex[:8]}"

    @pytest.mark.asyncio
    async def test_collection_operations(self, qdrant_client, clean_qdrant, test_collection_name):
        """Тест операций с коллекциями."""
        # Create collection
        qdrant_client.create_collection(
            collection_name=test_collection_name,
            vectors_config=VectorParams(size=128, distance=Distance.COSINE)
        )
        
        # Check if collection exists
        collections = qdrant_client.get_collections()
        collection_names = [col.name for col in collections.collections]
        assert test_collection_name in collection_names
        
        # Get collection info
        collection_info = qdrant_client.get_collection(test_collection_name)
        assert collection_info.config.params.vectors.size == 128
        assert collection_info.config.params.vectors.distance == Distance.COSINE
        
        # Delete collection
        qdrant_client.delete_collection(test_collection_name)
        
        # Verify collection is deleted
        collections = qdrant_client.get_collections()
        collection_names = [col.name for col in collections.collections]
        assert test_collection_name not in collection_names

    @pytest.mark.asyncio
    async def test_vector_operations(self, qdrant_client, clean_qdrant, test_collection_name):
        """Тест операций с векторами."""
        # Create collection
        qdrant_client.create_collection(
            collection_name=test_collection_name,
            vectors_config=VectorParams(size=128, distance=Distance.COSINE)
        )
        
        try:
            # Generate test vectors
            vectors = np.random.rand(5, 128).tolist()
            points = []
            
            for i, vector in enumerate(vectors):
                point = PointStruct(
                    id=i,  # Use integer ID instead of string
                    vector=vector,
                    payload={
                        "text": f"Document {i}",
                        "category": "test",
                        "metadata": {"index": i, "type": "test_document"}
                    }
                )
                points.append(point)
            
            # Insert points
            qdrant_client.upsert(
                collection_name=test_collection_name,
                points=points
            )
            
            # Wait for indexing
            await asyncio.sleep(1)
            
            # Search for similar vectors
            query_vector = vectors[0]  # Use first vector as query
            search_results = qdrant_client.search(
                collection_name=test_collection_name,
                query_vector=query_vector,
                limit=3
            )
            
            assert len(search_results) == 3
            assert search_results[0].id == 0  # Should find itself first
            
            # Verify payload
            assert search_results[0].payload["text"] == "Document 0"
            assert search_results[0].payload["category"] == "test"
            
        finally:
            # Cleanup
            try:
                qdrant_client.delete_collection(test_collection_name)
            except:
                pass

    @pytest.mark.asyncio
    async def test_filtered_search(self, qdrant_client, clean_qdrant, test_collection_name):
        """Тест поиска с фильтрами."""
        import time
        
        # Create collection with retry logic
        max_retries = 3
        for attempt in range(max_retries):
            try:
                qdrant_client.create_collection(
                    collection_name=test_collection_name,
                    vectors_config=VectorParams(size=64, distance=Distance.COSINE)
                )
                break
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
                else:
                    raise e
        
        try:
            # Insert points with different categories
            points = []
            categories = ["news", "blog", "news", "tutorial", "blog"]
            
            for i in range(5):
                vector = np.random.rand(64).tolist()
                point = PointStruct(
                    id=i,  # Use integer ID
                    vector=vector,
                    payload={
                        "text": f"Document {i}",
                        "category": categories[i],
                        "rating": i + 1,
                        "published": True
                    }
                )
                points.append(point)
            
            qdrant_client.upsert(
                collection_name=test_collection_name,
                points=points
            )
            
            await asyncio.sleep(1)
            
            # Search with category filter
            query_vector = np.random.rand(64).tolist()
            search_results = qdrant_client.search(
                collection_name=test_collection_name,
                query_vector=query_vector,
                query_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="category",
                            match=models.MatchValue(value="news")
                        )
                    ]
                ),
                limit=10
            )
            
            # Should only return news documents
            assert len(search_results) == 2
            for result in search_results:
                assert result.payload["category"] == "news"
            
            # Search with rating filter
            search_results = qdrant_client.search(
                collection_name=test_collection_name,
                query_vector=query_vector,
                query_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="rating",
                            range=models.Range(gte=3)
                        )
                    ]
                ),
                limit=10
            )
            
            # Should only return documents with rating >= 3
            assert len(search_results) == 3
            for result in search_results:
                assert result.payload["rating"] >= 3
            
        finally:
            # Cleanup
            try:
                qdrant_client.delete_collection(test_collection_name)
            except:
                pass

    @pytest.mark.asyncio
    async def test_point_operations(self, qdrant_client, clean_qdrant, test_collection_name):
        """Тест операций с точками."""
        # Create collection
        qdrant_client.create_collection(
            collection_name=test_collection_name,
            vectors_config=VectorParams(size=32, distance=Distance.COSINE)
        )
        
        try:
            # Insert single point
            point_id = 1  # Use integer ID
            vector = np.random.rand(32).tolist()
            payload = {"text": "Test document", "category": "test"}

            qdrant_client.upsert(
                collection_name=test_collection_name,
                points=[PointStruct(id=point_id, vector=vector, payload=payload)]
            )
            
            await asyncio.sleep(1)
            
            # Retrieve point
            retrieved_points = qdrant_client.retrieve(
                collection_name=test_collection_name,
                ids=[point_id]
            )
            
            assert len(retrieved_points) == 1
            assert retrieved_points[0].id == point_id
            assert retrieved_points[0].payload["text"] == "Test document"
            
            # Update point payload
            qdrant_client.set_payload(
                collection_name=test_collection_name,
                payload={"text": "Updated document", "category": "updated"},
                points=[point_id]
            )
            
            await asyncio.sleep(1)
            
            # Verify update
            updated_points = qdrant_client.retrieve(
                collection_name=test_collection_name,
                ids=[point_id]
            )
            
            assert updated_points[0].payload["text"] == "Updated document"
            assert updated_points[0].payload["category"] == "updated"
            
            # Delete point
            qdrant_client.delete(
                collection_name=test_collection_name,
                points_selector=models.PointIdsList(points=[point_id])
            )
            
            await asyncio.sleep(1)
            
            # Verify deletion
            deleted_points = qdrant_client.retrieve(
                collection_name=test_collection_name,
                ids=[point_id]
            )
            
            assert len(deleted_points) == 0
            
        finally:
            # Cleanup
            try:
                qdrant_client.delete_collection(test_collection_name)
            except:
                pass

    @pytest.mark.asyncio
    async def test_batch_operations(self, qdrant_client, clean_qdrant, test_collection_name):
        """Тест batch операций."""
        # Create collection
        qdrant_client.create_collection(
            collection_name=test_collection_name,
            vectors_config=VectorParams(size=64, distance=Distance.COSINE)
        )
        
        try:
            # Batch insert
            points = []
            for i in range(100):
                vector = np.random.rand(64).tolist()
                point = PointStruct(
                    id=i,  # Use integer ID
                    vector=vector,
                    payload={
                        "text": f"Batch document {i}",
                        "batch_id": "test_batch",
                        "index": i
                    }
                )
                points.append(point)
            
            qdrant_client.upsert(
                collection_name=test_collection_name,
                points=points
            )
            
            await asyncio.sleep(2)  # Wait for indexing
            
            # Verify all points were inserted
            collection_info = qdrant_client.get_collection(test_collection_name)
            assert collection_info.points_count == 100
            
            # Batch search
            query_vector = np.random.rand(64).tolist()
            search_results = qdrant_client.search(
                collection_name=test_collection_name,
                query_vector=query_vector,
                limit=10
            )
            
            assert len(search_results) == 10
            
            # Batch delete
            ids_to_delete = list(range(50))  # Delete first 50 points
            qdrant_client.delete(
                collection_name=test_collection_name,
                points_selector=models.PointIdsList(points=ids_to_delete)
            )
            
            await asyncio.sleep(1)
            
            # Verify deletion
            collection_info = qdrant_client.get_collection(test_collection_name)
            assert collection_info.points_count == 50
            
        finally:
            # Cleanup
            try:
                qdrant_client.delete_collection(test_collection_name)
            except:
                pass

    @pytest.mark.asyncio
    async def test_rag_integration(self, qdrant_client, clean_qdrant, test_collection_name):
        """Тест интеграции с RAG системой."""
        # Create collection for RAG documents
        qdrant_client.create_collection(
            collection_name=test_collection_name,
            vectors_config=VectorParams(size=384, distance=Distance.COSINE)  # Sentence-BERT size
        )
        
        try:
            # Simulate RAG document chunks
            documents = [
                {
                    "id": 1,  # Use integer ID
                    "content": "Machine learning is a subset of artificial intelligence.",
                    "metadata": {"document_id": "doc_1", "chunk_index": 0, "page": 1}
                },
                {
                    "id": 2,  # Use integer ID
                    "content": "Deep learning uses neural networks with multiple layers.",
                    "metadata": {"document_id": "doc_1", "chunk_index": 1, "page": 1}
                },
                {
                    "id": 3,  # Use integer ID
                    "content": "Natural language processing helps computers understand text.",
                    "metadata": {"document_id": "doc_2", "chunk_index": 0, "page": 1}
                }
            ]
            
            # Insert document chunks (with mock embeddings)
            points = []
            for doc in documents:
                # Mock embedding (in real app, this would come from embedding model)
                embedding = np.random.rand(384).tolist()
                
                point = PointStruct(
                    id=doc["id"],
                    vector=embedding,
                    payload={
                        "content": doc["content"],
                        "document_id": doc["metadata"]["document_id"],
                        "chunk_index": doc["metadata"]["chunk_index"],
                        "page": doc["metadata"]["page"]
                    }
                )
                points.append(point)
            
            qdrant_client.upsert(
                collection_name=test_collection_name,
                points=points
            )
            
            await asyncio.sleep(1)
            
            # Search for relevant chunks
            query = "What is machine learning?"
            # Mock query embedding
            query_embedding = np.random.rand(384).tolist()
            
            search_results = qdrant_client.search(
                collection_name=test_collection_name,
                query_vector=query_embedding,
                limit=2
            )
            
            assert len(search_results) == 2
            
            # Verify results contain relevant content
            for result in search_results:
                assert "content" in result.payload
                assert "document_id" in result.payload
                assert "chunk_index" in result.payload
            
            # Search within specific document
            search_results = qdrant_client.search(
                collection_name=test_collection_name,
                query_vector=query_embedding,
                query_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="document_id",
                            match=models.MatchValue(value="doc_1")
                        )
                    ]
                ),
                limit=10
            )
            
            # Should only return chunks from doc_1
            assert len(search_results) == 2
            for result in search_results:
                assert result.payload["document_id"] == "doc_1"
            
        finally:
            # Cleanup
            try:
                qdrant_client.delete_collection(test_collection_name)
            except:
                pass

    @pytest.mark.asyncio
    async def test_concurrent_operations(self, qdrant_client, clean_qdrant, test_collection_name):
        """Тест конкурентных операций."""
        # Create collection
        qdrant_client.create_collection(
            collection_name=test_collection_name,
            vectors_config=VectorParams(size=32, distance=Distance.COSINE)
        )
        
        try:
            # Concurrent inserts
            async def insert_point(point_id: int):
                vector = np.random.rand(32).tolist()
                point = PointStruct(
                    id=point_id,  # Use integer ID
                    vector=vector,
                    payload={"concurrent_id": point_id, "type": "concurrent_test"}
                )

                qdrant_client.upsert(
                    collection_name=test_collection_name,
                    points=[point]
                )
                return point_id
            
            # Execute concurrent inserts
            tasks = [insert_point(i) for i in range(20)]
            results = await asyncio.gather(*tasks)
            
            assert len(results) == 20
            
            await asyncio.sleep(2)  # Wait for indexing
            
            # Verify all points were inserted
            collection_info = qdrant_client.get_collection(test_collection_name)
            assert collection_info.points_count == 20
            
        finally:
            # Cleanup
            try:
                qdrant_client.delete_collection(test_collection_name)
            except:
                pass
