"""
Интеграционные тесты для полного цикла RAG системы.
Тестирует взаимодействие всех компонентов: загрузка файлов, обработка текста, создание эмбеддингов, поиск.
"""
import pytest
import asyncio
import uuid
import io
from typing import List, Dict, Any

from app.models.user import Users
from app.models.rag import RAGDocument, RAGChunk
from app.repositories.rag_repo import RAGDocumentsRepository, RAGChunksRepository
from app.services.text_extractor import extract_text_from_bytes
from app.services.text_normalizer import normalize_text
from app.core.s3_links import S3LinkFactory


@pytest.mark.integration
class TestRAGSystemIntegration:
    """Интеграционные тесты для полного цикла RAG системы."""

    @pytest.mark.asyncio
    async def test_document_upload_to_s3(
        self, 
        db_session, 
        test_user: Users, 
        minio_client, 
        clean_minio
    ):
        """Тест загрузки документа в S3."""
        bucket_name = "test-rag-documents"
        doc_id = str(uuid.uuid4())
        
        # Create RAG document record
        rag_repo = RAGDocumentsRepository(db_session, test_user.tenant_id)
        
        document_data = {
            "filename": "test_document.txt",
            "content_type": "text/plain",
            "size_bytes": 1024,
            "status": "uploading",
            "user_id": test_user.id
        }
        
        try:
            # Create document record
            created_doc = rag_repo.create(document_data)
            await db_session.commit()
            await db_session.refresh(created_doc)
            
            # Generate presigned URL
            upload_link = S3LinkFactory().for_document_upload(
                doc_id=doc_id,
                tenant_id=test_user.tenant_id,
                content_type="text/plain"
            )
            
            # Upload file content to S3
            test_content = "This is a test document for RAG system integration testing."
            file_data = io.BytesIO(test_content.encode('utf-8'))
            
            minio_client.put_object(
                bucket_name,
                upload_link.key,
                file_data,
                length=len(test_content),
                content_type="text/plain"
            )
            
            # Verify file was uploaded
            objects = list(minio_client.list_objects(bucket_name, prefix=upload_link.key))
            assert len(objects) == 1
            assert objects[0].object_name == upload_link.key
            
            # Update document status
            updated_doc = rag_repo.update(created_doc, {"status": "uploaded"})
            await db_session.commit()
            
            assert updated_doc.status == "uploaded"
            
        finally:
            # Cleanup
            try:
                minio_client.remove_object(bucket_name, upload_link.key)
                await db_session.execute(
                    "DELETE FROM rag_documents WHERE id = :doc_id",
                    {"doc_id": created_doc.id}
                )
                await db_session.commit()
            except:
                pass

    @pytest.mark.asyncio
    async def test_text_extraction_and_processing(
        self, 
        db_session, 
        test_user: Users, 
        minio_client, 
        clean_minio
    ):
        """Тест извлечения и обработки текста из документов."""
        bucket_name = "test-rag-documents"
        doc_id = str(uuid.uuid4())
        
        # Test different file formats
        test_files = [
            {
                "filename": "test.txt",
                "content": "This is a plain text document.\nIt has multiple lines.\nFor testing purposes.",
                "content_type": "text/plain"
            },
            {
                "filename": "test.json",
                "content": '{"title": "Test Document", "content": "This is JSON content", "metadata": {"type": "test"}}',
                "content_type": "application/json"
            },
            {
                "filename": "test.csv",
                "content": "name,age,city\nJohn,25,New York\nJane,30,London\nBob,35,Paris",
                "content_type": "text/csv"
            }
        ]
        
        rag_repo = RAGDocumentsRepository(db_session, test_user.tenant_id)
        
        try:
            for test_file in test_files:
                # Create document record
                document_data = {
                    "filename": test_file["filename"],
                    "content_type": test_file["content_type"],
                    "size_bytes": len(test_file["content"]),
                    "status": "uploaded",
                    "user_id": test_user.id
                }
                
                created_doc = rag_repo.create(document_data)
                await db_session.commit()
                await db_session.refresh(created_doc)
                
                # Upload file to S3
                upload_link = S3LinkFactory().for_document_upload(
                    doc_id=str(created_doc.id),
                    tenant_id=test_user.tenant_id,
                    content_type=test_file["content_type"]
                )
                
                file_data = io.BytesIO(test_file["content"].encode('utf-8'))
                minio_client.put_object(
                    bucket_name,
                    upload_link.key,
                    file_data,
                    length=len(test_file["content"]),
                    content_type=test_file["content_type"]
                )
                
                # Extract text from file
                extracted_result = extract_text_from_bytes(
                    test_file["content"].encode('utf-8'),
                    test_file["filename"]
                )
                
                assert extracted_result is not None
                assert extracted_result.text is not None
                assert len(extracted_result.text) > 0
                
                # Normalize text
                normalized_text = normalize_text(extracted_result.text)
                assert normalized_text is not None
                assert len(normalized_text) > 0
                
                # Update document with extracted text
                updated_doc = rag_repo.update(created_doc, {
                    "status": "processed",
                    "extracted_text": normalized_text
                })
                await db_session.commit()
                
                assert updated_doc.status == "processed"
                assert updated_doc.extracted_text == normalized_text
                
                # Cleanup this document
                minio_client.remove_object(bucket_name, upload_link.key)
                await db_session.execute(
                    "DELETE FROM rag_documents WHERE id = :doc_id",
                    {"doc_id": created_doc.id}
                )
                await db_session.commit()
                
        except Exception as e:
            await db_session.rollback()
            raise e

    @pytest.mark.asyncio
    async def test_chunk_creation_and_storage(
        self, 
        db_session, 
        test_user: Users, 
        qdrant_client, 
        clean_qdrant
    ):
        """Тест создания и хранения чанков."""
        collection_name = f"test_chunks_{uuid.uuid4().hex[:8]}"
        
        # Create Qdrant collection
        qdrant_client.create_collection(
            collection_name=collection_name,
            vectors_config={"size": 384, "distance": "Cosine"}  # Sentence-BERT size
        )
        
        rag_docs_repo = RAGDocumentsRepository(db_session, test_user.tenant_id)
        rag_chunks_repo = RAGChunksRepository(db_session, test_user.tenant_id)
        
        try:
            # Create document
            document_data = {
                "filename": "chunk_test.txt",
                "content_type": "text/plain",
                "size_bytes": 1024,
                "status": "processed",
                "extracted_text": "This is a test document for chunking. It contains multiple sentences. Each sentence should become a separate chunk. This helps with better search and retrieval.",
                "user_id": test_user.id
            }
            
            created_doc = rag_docs_repo.create(document_data)
            await db_session.commit()
            await db_session.refresh(created_doc)
            
            # Split text into chunks
            text = created_doc.extracted_text
            sentences = text.split('. ')
            chunks = [s.strip() + '.' for s in sentences if s.strip()]
            
            # Create chunks
            chunk_points = []
            for i, chunk_text in enumerate(chunks):
                # Create chunk record
                chunk_data = {
                    "document_id": created_doc.id,
                    "content": chunk_text,
                    "chunk_index": i,
                    "metadata": {"page": 1, "section": "main"}
                }
                
                created_chunk = rag_chunks_repo.create(chunk_data)
                await db_session.commit()
                await db_session.refresh(created_chunk)
                
                # Mock embedding (in real app, this would come from embedding model)
                import numpy as np
                embedding = np.random.rand(384).tolist()
                
                # Store in Qdrant
                from qdrant_client.http.models import PointStruct
                point = PointStruct(
                    id=str(created_chunk.id),
                    vector=embedding,
                    payload={
                        "content": chunk_text,
                        "document_id": str(created_doc.id),
                        "chunk_index": i,
                        "metadata": chunk_data["metadata"]
                    }
                )
                
                chunk_points.append(point)
            
            # Batch insert to Qdrant
            qdrant_client.upsert(
                collection_name=collection_name,
                points=chunk_points
            )
            
            await asyncio.sleep(1)  # Wait for indexing
            
            # Verify chunks were created
            chunks_count = await db_session.execute(
                "SELECT COUNT(*) FROM rag_chunks WHERE document_id = :doc_id",
                {"doc_id": created_doc.id}
            )
            chunks_count = chunks_count.scalar()
            assert chunks_count == len(chunks)
            
            # Verify chunks in Qdrant
            collection_info = qdrant_client.get_collection(collection_name)
            assert collection_info.points_count == len(chunks)
            
        finally:
            # Cleanup
            try:
                qdrant_client.delete_collection(collection_name)
                await db_session.execute(
                    "DELETE FROM rag_chunks WHERE document_id = :doc_id",
                    {"doc_id": created_doc.id}
                )
                await db_session.execute(
                    "DELETE FROM rag_documents WHERE id = :doc_id",
                    {"doc_id": created_doc.id}
                )
                await db_session.commit()
            except:
                pass

    @pytest.mark.asyncio
    async def test_vector_search_and_retrieval(
        self, 
        db_session, 
        test_user: Users, 
        qdrant_client, 
        clean_qdrant
    ):
        """Тест векторного поиска и извлечения."""
        collection_name = f"test_search_{uuid.uuid4().hex[:8]}"
        
        # Create Qdrant collection
        qdrant_client.create_collection(
            collection_name=collection_name,
            vectors_config={"size": 384, "distance": "Cosine"}
        )
        
        try:
            # Create test documents and chunks
            documents = [
                {
                    "title": "Machine Learning Basics",
                    "content": "Machine learning is a subset of artificial intelligence that focuses on algorithms and statistical models."
                },
                {
                    "title": "Deep Learning Networks",
                    "content": "Deep learning uses neural networks with multiple layers to process complex patterns in data."
                },
                {
                    "title": "Natural Language Processing",
                    "content": "NLP helps computers understand, interpret, and manipulate human language in a valuable way."
                }
            ]
            
            chunk_points = []
            chunk_id = 0
            
            for doc_idx, doc in enumerate(documents):
                # Create document record
                rag_docs_repo = RAGDocumentsRepository(db_session, test_user.tenant_id)
                document_data = {
                    "filename": f"doc_{doc_idx}.txt",
                    "content_type": "text/plain",
                    "size_bytes": len(doc["content"]),
                    "status": "processed",
                    "extracted_text": doc["content"],
                    "user_id": test_user.id
                }
                
                created_doc = rag_docs_repo.create(document_data)
                await db_session.commit()
                await db_session.refresh(created_doc)
                
                # Create chunk
                rag_chunks_repo = RAGChunksRepository(db_session, test_user.tenant_id)
                chunk_data = {
                    "document_id": created_doc.id,
                    "content": doc["content"],
                    "chunk_index": 0,
                    "metadata": {"title": doc["title"], "document_index": doc_idx}
                }
                
                created_chunk = rag_chunks_repo.create(chunk_data)
                await db_session.commit()
                await db_session.refresh(created_chunk)
                
                # Mock embedding
                import numpy as np
                embedding = np.random.rand(384).tolist()
                
                # Create Qdrant point
                from qdrant_client.http.models import PointStruct
                point = PointStruct(
                    id=str(chunk_id),
                    vector=embedding,
                    payload={
                        "content": doc["content"],
                        "document_id": str(created_doc.id),
                        "chunk_id": str(created_chunk.id),
                        "title": doc["title"],
                        "metadata": chunk_data["metadata"]
                    }
                )
                
                chunk_points.append(point)
                chunk_id += 1
            
            # Insert all points
            qdrant_client.upsert(
                collection_name=collection_name,
                points=chunk_points
            )
            
            await asyncio.sleep(2)  # Wait for indexing
            
            # Test search
            query_text = "What is machine learning?"
            # Mock query embedding
            import numpy as np
            query_embedding = np.random.rand(384).tolist()
            
            # Search in Qdrant
            search_results = qdrant_client.search(
                collection_name=collection_name,
                query_vector=query_embedding,
                limit=3
            )
            
            assert len(search_results) == 3
            
            # Verify search results
            for result in search_results:
                assert "content" in result.payload
                assert "document_id" in result.payload
                assert "chunk_id" in result.payload
                assert "title" in result.payload
            
            # Test filtered search
            search_results = qdrant_client.search(
                collection_name=collection_name,
                query_vector=query_embedding,
                query_filter={
                    "must": [
                        {
                            "key": "title",
                            "match": {"value": "Machine Learning Basics"}
                        }
                    ]
                },
                limit=5
            )
            
            # Should find the specific document
            assert len(search_results) >= 1
            assert search_results[0].payload["title"] == "Machine Learning Basics"
            
        finally:
            # Cleanup
            try:
                qdrant_client.delete_collection(collection_name)
                await db_session.execute("DELETE FROM rag_chunks")
                await db_session.execute("DELETE FROM rag_documents")
                await db_session.commit()
            except:
                pass

    @pytest.mark.asyncio
    async def test_full_rag_pipeline(
        self, 
        db_session, 
        test_user: Users, 
        minio_client, 
        clean_minio,
        qdrant_client, 
        clean_qdrant
    ):
        """Тест полного пайплайна RAG системы."""
        bucket_name = "test-rag-documents"
        collection_name = f"test_pipeline_{uuid.uuid4().hex[:8]}"
        
        # Create Qdrant collection
        qdrant_client.create_collection(
            collection_name=collection_name,
            vectors_config={"size": 384, "distance": "Cosine"}
        )
        
        rag_docs_repo = RAGDocumentsRepository(db_session, test_user.tenant_id)
        rag_chunks_repo = RAGChunksRepository(db_session, test_user.tenant_id)
        
        try:
            # Step 1: Upload document to S3
            doc_id = str(uuid.uuid4())
            test_content = """
            Artificial Intelligence and Machine Learning
            
            Artificial Intelligence (AI) is a broad field of computer science focused on creating intelligent machines.
            Machine Learning (ML) is a subset of AI that enables computers to learn and improve from experience.
            Deep Learning is a subset of ML that uses neural networks with multiple layers.
            
            Applications of AI include:
            - Natural Language Processing
            - Computer Vision
            - Robotics
            - Expert Systems
            
            The future of AI looks promising with advances in quantum computing and neural networks.
            """
            
            # Create document record
            document_data = {
                "filename": "ai_ml_document.txt",
                "content_type": "text/plain",
                "size_bytes": len(test_content),
                "status": "uploading",
                "user_id": test_user.id
            }
            
            created_doc = rag_docs_repo.create(document_data)
            await db_session.commit()
            await db_session.refresh(created_doc)
            
            # Upload to S3
            upload_link = S3LinkFactory().for_document_upload(
                doc_id=str(created_doc.id),
                tenant_id=test_user.tenant_id,
                content_type="text/plain"
            )
            
            file_data = io.BytesIO(test_content.encode('utf-8'))
            minio_client.put_object(
                bucket_name,
                upload_link.key,
                file_data,
                length=len(test_content),
                content_type="text/plain"
            )
            
            # Step 2: Extract and normalize text
            extracted_result = extract_text_from_bytes(
                test_content.encode('utf-8'),
                "ai_ml_document.txt"
            )
            
            normalized_text = normalize_text(extracted_result.text)
            
            # Update document
            updated_doc = rag_docs_repo.update(created_doc, {
                "status": "processed",
                "extracted_text": normalized_text
            })
            await db_session.commit()
            
            # Step 3: Create chunks
            sentences = normalized_text.split('. ')
            chunks = [s.strip() + '.' for s in sentences if s.strip() and len(s.strip()) > 10]
            
            chunk_points = []
            for i, chunk_text in enumerate(chunks):
                # Create chunk record
                chunk_data = {
                    "document_id": created_doc.id,
                    "content": chunk_text,
                    "chunk_index": i,
                    "metadata": {"page": 1, "section": "main"}
                }
                
                created_chunk = rag_chunks_repo.create(chunk_data)
                await db_session.commit()
                await db_session.refresh(created_chunk)
                
                # Mock embedding
                import numpy as np
                embedding = np.random.rand(384).tolist()
                
                # Create Qdrant point
                from qdrant_client.http.models import PointStruct
                point = PointStruct(
                    id=str(created_chunk.id),
                    vector=embedding,
                    payload={
                        "content": chunk_text,
                        "document_id": str(created_doc.id),
                        "chunk_id": str(created_chunk.id),
                        "chunk_index": i,
                        "metadata": chunk_data["metadata"]
                    }
                )
                
                chunk_points.append(point)
            
            # Step 4: Store chunks in Qdrant
            qdrant_client.upsert(
                collection_name=collection_name,
                points=chunk_points
            )
            
            await asyncio.sleep(2)  # Wait for indexing
            
            # Step 5: Test search and retrieval
            query_text = "What is machine learning?"
            import numpy as np
            query_embedding = np.random.rand(384).tolist()
            
            search_results = qdrant_client.search(
                collection_name=collection_name,
                query_vector=query_embedding,
                limit=3
            )
            
            # Verify pipeline worked
            assert len(search_results) == 3
            
            # Verify document status
            final_doc = rag_docs_repo.get_by_id(created_doc.id)
            assert final_doc.status == "processed"
            assert final_doc.extracted_text is not None
            
            # Verify chunks were created
            chunks_count = await db_session.execute(
                "SELECT COUNT(*) FROM rag_chunks WHERE document_id = :doc_id",
                {"doc_id": created_doc.id}
            )
            chunks_count = chunks_count.scalar()
            assert chunks_count == len(chunks)
            
            # Verify chunks in Qdrant
            collection_info = qdrant_client.get_collection(collection_name)
            assert collection_info.points_count == len(chunks)
            
        finally:
            # Cleanup
            try:
                qdrant_client.delete_collection(collection_name)
                minio_client.remove_object(bucket_name, upload_link.key)
                await db_session.execute(
                    "DELETE FROM rag_chunks WHERE document_id = :doc_id",
                    {"doc_id": created_doc.id}
                )
                await db_session.execute(
                    "DELETE FROM rag_documents WHERE id = :doc_id",
                    {"doc_id": created_doc.id}
                )
                await db_session.commit()
            except:
                pass
