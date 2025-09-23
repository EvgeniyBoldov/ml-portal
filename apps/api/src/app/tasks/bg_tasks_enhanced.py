"""
Улучшенные фоновые задачи для ML Portal
Интегрированы с новыми сервисами и репозиториями
"""
import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from uuid import UUID

from celery import shared_task
from celery.exceptions import Retry

from app.celery_app import app as celery_app
from app.core.config import settings
from app.core.s3 import s3_manager
from app.core.redis import redis_manager
from app.core.db import get_async_session
from app.services.rag_service_enhanced import RAGDocumentsService, RAGChunksService
from app.services.text_normalizer import normalize_text
from app.services.text_extractor import extract_text
from app.services.clients import embed_texts, llm_chat
from app.tasks.shared import log, RetryableError, FatalError, task_metrics

logger = logging.getLogger(__name__)

# Конфигурация задач
DEFAULT_BATCH_SIZE = 8
DEFAULT_CHUNK_SIZE = 1000
DEFAULT_CHUNK_OVERLAP = 200

@shared_task(
    name="bg_tasks.process_document",
    bind=True,
    autoretry_for=(RetryableError,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3, "countdown": 60},
    soft_time_limit=300,
    time_limit=360
)
def process_document(self, document_id: str, source_key: Optional[str] = None) -> Dict[str, Any]:
    """
    Полный пайплайн обработки документа для RAG
    
    Args:
        document_id: ID документа
        source_key: Ключ файла в S3 (опционально)
    
    Returns:
        Результат обработки документа
    """
    with task_metrics("process_document", "rag_processing"):
        try:
            logger.info(f"Starting document processing for {document_id}")
            
            # 1. Извлечение и нормализация текста
            text_result = extract_and_normalize_text.delay(document_id, source_key).get()
            if not text_result.get("success"):
                raise RetryableError(f"Text extraction failed: {text_result.get('error')}")
            
            # 2. Чанкинг текста
            chunks_result = chunk_document.delay(document_id, text_result["text"]).get()
            if not chunks_result.get("success"):
                raise RetryableError(f"Chunking failed: {chunks_result.get('error')}")
            
            # 3. Генерация эмбеддингов
            embedding_result = generate_embeddings.delay(document_id).get()
            if not embedding_result.get("success"):
                raise RetryableError(f"Embedding generation failed: {embedding_result.get('error')}")
            
            # 4. Финализация индексации
            finalize_result = finalize_document.delay(document_id).get()
            if not finalize_result.get("success"):
                raise RetryableError(f"Finalization failed: {finalize_result.get('error')}")
            
            logger.info(f"Document processing completed for {document_id}")
            return {
                "success": True,
                "document_id": document_id,
                "chunks_count": chunks_result.get("chunks_count", 0),
                "embeddings_count": embedding_result.get("embeddings_count", 0),
                "status": "ready"
            }
            
        except Exception as e:
            logger.error(f"Document processing failed for {document_id}: {e}")
            # Обновляем статус документа на "failed"
            asyncio.run(update_document_status(document_id, "failed", str(e)))
            raise self.retry(exc=e)

@shared_task(
    name="bg_tasks.extract_and_normalize_text",
    bind=True,
    autoretry_for=(RetryableError,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3, "countdown": 30},
    soft_time_limit=120,
    time_limit=150
)
def extract_and_normalize_text(self, document_id: str, source_key: Optional[str] = None) -> Dict[str, Any]:
    """
    Извлечение и нормализация текста из документа
    
    Args:
        document_id: ID документа
        source_key: Ключ файла в S3
    
    Returns:
        Результат извлечения текста
    """
    with task_metrics("extract_and_normalize_text", "text_processing"):
        try:
            logger.info(f"Extracting text for document {document_id}")
            
            # Получаем файл из S3
            if not source_key:
                source_key = f"{document_id}/original"
            
            file_content = s3_manager.get_object(settings.S3_BUCKET_RAG, source_key)
            if not file_content:
                raise RetryableError(f"File not found in S3: {source_key}")
            
            # Извлекаем текст
            filename = source_key.split("/")[-1]
            result = extract_text(file_content, filename=filename)
            
            # Нормализуем текст
            normalized_text = normalize_text(result.text)
            
            # Сохраняем нормализованный текст
            canonical_key = f"{document_id}/canonical.txt"
            canonical_data = {
                "text": normalized_text,
                "tables": [{"name": t.name, "csv": t.csv_data, "rows": t.rows, "cols": t.cols} for t in result.tables],
                "meta": result.meta,
                "original_filename": filename,
                "extractor": result.kind,
                "warnings": result.warnings,
                "processed_at": datetime.utcnow().isoformat()
            }
            
            import json
            s3_manager.put_object(
                settings.S3_BUCKET_RAG,
                canonical_key,
                json.dumps(canonical_data, ensure_ascii=False).encode("utf-8"),
                content_type="application/json; charset=utf-8"
            )
            
            logger.info(f"Text extraction completed for document {document_id}")
            return {
                "success": True,
                "document_id": document_id,
                "text": normalized_text,
                "canonical_key": canonical_key,
                "text_length": len(normalized_text),
                "tables_count": len(result.tables),
                "warnings": result.warnings
            }
            
        except Exception as e:
            logger.error(f"Text extraction failed for document {document_id}: {e}")
            raise self.retry(exc=e)

@shared_task(
    name="bg_tasks.chunk_document",
    bind=True,
    autoretry_for=(RetryableError,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3, "countdown": 30},
    soft_time_limit=60,
    time_limit=90
)
def chunk_document(self, document_id: str, text: str, chunk_size: int = DEFAULT_CHUNK_SIZE, 
                  chunk_overlap: int = DEFAULT_CHUNK_OVERLAP) -> Dict[str, Any]:
    """
    Разбиение текста на чанки
    
    Args:
        document_id: ID документа
        text: Текст для чанкинга
        chunk_size: Размер чанка
        chunk_overlap: Перекрытие между чанками
    
    Returns:
        Результат чанкинга
    """
    with task_metrics("chunk_document", "text_processing"):
        try:
            logger.info(f"Chunking document {document_id}")
            
            # Простой чанкинг по словам
            words = text.split()
            chunks = []
            
            for i in range(0, len(words), chunk_size - chunk_overlap):
                chunk_words = words[i:i + chunk_size]
                chunk_text = " ".join(chunk_words)
                
                if chunk_text.strip():
                    chunks.append({
                        "text": chunk_text,
                        "chunk_index": len(chunks),
                        "start_word": i,
                        "end_word": min(i + chunk_size, len(words)),
                        "length": len(chunk_text)
                    })
            
            # Сохраняем чанки в базу данных
            chunks_created = asyncio.run(save_document_chunks(document_id, chunks))
            
            logger.info(f"Document chunking completed for {document_id}: {chunks_created} chunks")
            return {
                "success": True,
                "document_id": document_id,
                "chunks_count": chunks_created,
                "chunk_size": chunk_size,
                "chunk_overlap": chunk_overlap
            }
            
        except Exception as e:
            logger.error(f"Document chunking failed for {document_id}: {e}")
            raise self.retry(exc=e)

@shared_task(
    name="bg_tasks.generate_embeddings",
    bind=True,
    autoretry_for=(RetryableError,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 5, "countdown": 60},
    soft_time_limit=300,
    time_limit=360
)
def generate_embeddings(self, document_id: str, model: str = "minilm", batch_size: int = DEFAULT_BATCH_SIZE) -> Dict[str, Any]:
    """
    Генерация эмбеддингов для чанков документа
    
    Args:
        document_id: ID документа
        model: Модель для эмбеддингов
        batch_size: Размер батча для обработки
    
    Returns:
        Результат генерации эмбеддингов
    """
    with task_metrics("generate_embeddings", "embedding_processing"):
        try:
            logger.info(f"Generating embeddings for document {document_id} with model {model}")
            
            # Получаем чанки документа
            chunks = asyncio.run(get_document_chunks(document_id))
            if not chunks:
                raise RetryableError(f"No chunks found for document {document_id}")
            
            # Обрабатываем чанки батчами
            total_embeddings = 0
            for i in range(0, len(chunks), batch_size):
                batch = chunks[i:i + batch_size]
                batch_texts = [chunk["text"] for chunk in batch]
                
                # Генерируем эмбеддинги
                embeddings = asyncio.run(generate_batch_embeddings(batch_texts, model))
                if not embeddings:
                    raise RetryableError(f"Failed to generate embeddings for batch {i//batch_size + 1}")
                
                # Сохраняем эмбеддинги
                batch_embeddings_saved = asyncio.run(save_chunk_embeddings(
                    document_id, batch, embeddings, model
                ))
                total_embeddings += batch_embeddings_saved
                
                logger.info(f"Processed batch {i//batch_size + 1}/{(len(chunks) + batch_size - 1)//batch_size}")
            
            logger.info(f"Embedding generation completed for document {document_id}: {total_embeddings} embeddings")
            return {
                "success": True,
                "document_id": document_id,
                "embeddings_count": total_embeddings,
                "model": model,
                "batch_size": batch_size
            }
            
        except Exception as e:
            logger.error(f"Embedding generation failed for document {document_id}: {e}")
            raise self.retry(exc=e)

@shared_task(
    name="bg_tasks.finalize_document",
    bind=True,
    autoretry_for=(RetryableError,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3, "countdown": 30},
    soft_time_limit=60,
    time_limit=90
)
def finalize_document(self, document_id: str) -> Dict[str, Any]:
    """
    Финализация обработки документа
    
    Args:
        document_id: ID документа
    
    Returns:
        Результат финализации
    """
    with task_metrics("finalize_document", "document_processing"):
        try:
            logger.info(f"Finalizing document {document_id}")
            
            # Обновляем статус документа
            success = asyncio.run(update_document_status(document_id, "ready"))
            if not success:
                raise RetryableError(f"Failed to update document status for {document_id}")
            
            # Обновляем метаданные
            asyncio.run(update_document_metadata(document_id))
            
            logger.info(f"Document finalization completed for {document_id}")
            return {
                "success": True,
                "document_id": document_id,
                "status": "ready",
                "finalized_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Document finalization failed for {document_id}: {e}")
            raise self.retry(exc=e)

@shared_task(
    name="bg_tasks.analyze_document",
    bind=True,
    autoretry_for=(RetryableError,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3, "countdown": 60},
    soft_time_limit=180,
    time_limit=240
)
def analyze_document(self, document_id: str, analysis_type: str = "summary") -> Dict[str, Any]:
    """
    Анализ документа с помощью LLM
    
    Args:
        document_id: ID документа
        analysis_type: Тип анализа (summary, topics, recommendations)
    
    Returns:
        Результат анализа
    """
    with task_metrics("analyze_document", "analysis_processing"):
        try:
            logger.info(f"Analyzing document {document_id} with type {analysis_type}")
            
            # Получаем текст документа
            text = asyncio.run(get_document_text(document_id))
            if not text:
                raise RetryableError(f"No text found for document {document_id}")
            
            # Генерируем анализ
            analysis_result = asyncio.run(generate_document_analysis(text, analysis_type))
            if not analysis_result:
                raise RetryableError(f"Failed to generate analysis for document {document_id}")
            
            # Сохраняем результат анализа
            analysis_saved = asyncio.run(save_document_analysis(document_id, analysis_result, analysis_type))
            if not analysis_saved:
                raise RetryableError(f"Failed to save analysis for document {document_id}")
            
            logger.info(f"Document analysis completed for {document_id}")
            return {
                "success": True,
                "document_id": document_id,
                "analysis_type": analysis_type,
                "analysis_result": analysis_result,
                "analyzed_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Document analysis failed for {document_id}: {e}")
            raise self.retry(exc=e)

@shared_task(
    name="bg_tasks.cleanup_old_documents",
    bind=True,
    autoretry_for=(RetryableError,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 2, "countdown": 300},
    soft_time_limit=600,
    time_limit=720
)
def cleanup_old_documents(self, days_old: int = 30) -> Dict[str, Any]:
    """
    Очистка старых документов и их данных
    
    Args:
        days_old: Возраст документов для удаления в днях
    
    Returns:
        Результат очистки
    """
    with task_metrics("cleanup_old_documents", "maintenance"):
        try:
            logger.info(f"Starting cleanup of documents older than {days_old} days")
            
            # Получаем старые документы
            old_documents = asyncio.run(get_old_documents(days_old))
            if not old_documents:
                logger.info("No old documents found for cleanup")
                return {"success": True, "cleaned_count": 0}
            
            # Удаляем документы и их данные
            cleaned_count = 0
            for doc_id in old_documents:
                try:
                    # Удаляем из S3
                    asyncio.run(delete_document_from_s3(doc_id))
                    
                    # Удаляем из базы данных
                    asyncio.run(delete_document_from_db(doc_id))
                    
                    cleaned_count += 1
                    logger.info(f"Cleaned document {doc_id}")
                    
                except Exception as e:
                    logger.error(f"Failed to clean document {doc_id}: {e}")
                    continue
            
            logger.info(f"Cleanup completed: {cleaned_count} documents cleaned")
            return {
                "success": True,
                "cleaned_count": cleaned_count,
                "total_found": len(old_documents),
                "cleanup_date": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Cleanup failed: {e}")
            raise self.retry(exc=e)

# Вспомогательные функции

async def save_document_chunks(document_id: str, chunks: List[Dict[str, Any]]) -> int:
    """Сохранение чанков документа в базу данных"""
    async with get_async_session() as session:
        rag_chunks_service = RAGChunksService(session)
        chunks_created = 0
        
        for chunk_data in chunks:
            try:
                chunk = await rag_chunks_service.create_chunk(
                    document_id=document_id,
                    text=chunk_data["text"],
                    chunk_index=chunk_data["chunk_index"],
                    metadata={
                        "start_word": chunk_data["start_word"],
                        "end_word": chunk_data["end_word"],
                        "length": chunk_data["length"]
                    }
                )
                if chunk:
                    chunks_created += 1
            except Exception as e:
                logger.error(f"Failed to save chunk {chunk_data['chunk_index']}: {e}")
                continue
        
        return chunks_created

async def get_document_chunks(document_id: str) -> List[Dict[str, Any]]:
    """Получение чанков документа"""
    async with get_async_session() as session:
        rag_chunks_service = RAGChunksService(session)
        chunks = await rag_chunks_service.get_document_chunks(document_id)
        return [{"text": chunk.text, "chunk_index": chunk.chunk_index, "id": str(chunk.id)} for chunk in chunks]

async def generate_batch_embeddings(texts: List[str], model: str) -> List[List[float]]:
    """Генерация эмбеддингов для батча текстов"""
    try:
        embeddings = embed_texts(texts, profile="rt", models=[model])
        return embeddings
    except Exception as e:
        logger.error(f"Failed to generate embeddings: {e}")
        return []

async def save_chunk_embeddings(document_id: str, chunks: List[Dict[str, Any]], 
                               embeddings: List[List[float]], model: str) -> int:
    """Сохранение эмбеддингов чанков"""
    async with get_async_session() as session:
        rag_chunks_service = RAGChunksService(session)
        saved_count = 0
        
        for chunk, embedding in zip(chunks, embeddings):
            try:
                await rag_chunks_service.update_chunk_embedding(
                    chunk_id=chunk["id"],
                    embedding=embedding,
                    model=model
                )
                saved_count += 1
            except Exception as e:
                logger.error(f"Failed to save embedding for chunk {chunk['id']}: {e}")
                continue
        
        return saved_count

async def update_document_status(document_id: str, status: str, error_message: str = None) -> bool:
    """Обновление статуса документа"""
    try:
        async with get_async_session() as session:
            rag_documents_service = RAGDocumentsService(session)
            success = await rag_documents_service.update_document_status(
                document_id=document_id,
                status=status,
                error_message=error_message
            )
            return success
    except Exception as e:
        logger.error(f"Failed to update document status: {e}")
        return False

async def update_document_metadata(document_id: str) -> bool:
    """Обновление метаданных документа"""
    try:
        async with get_async_session() as session:
            rag_documents_service = RAGDocumentsService(session)
            # Получаем статистику по чанкам
            chunks = await rag_documents_service.get_document_chunks(document_id)
            metadata = {
                "chunks_count": len(chunks),
                "last_processed": datetime.utcnow().isoformat()
            }
            success = await rag_documents_service.update_document_metadata(
                document_id=document_id,
                metadata=metadata
            )
            return success
    except Exception as e:
        logger.error(f"Failed to update document metadata: {e}")
        return False

async def get_document_text(document_id: str) -> Optional[str]:
    """Получение текста документа"""
    try:
        # Пытаемся получить из S3
        canonical_key = f"{document_id}/canonical.txt"
        file_content = s3_manager.get_object(settings.S3_BUCKET_RAG, canonical_key)
        if file_content:
            import json
            data = json.loads(file_content.decode("utf-8"))
            return data.get("text")
        
        # Если нет в S3, получаем из базы данных
        async with get_async_session() as session:
            rag_documents_service = RAGDocumentsService(session)
            document = await rag_documents_service.get_document(document_id)
            return document.text if document else None
            
    except Exception as e:
        logger.error(f"Failed to get document text: {e}")
        return None

async def generate_document_analysis(text: str, analysis_type: str) -> Optional[Dict[str, Any]]:
    """Генерация анализа документа с помощью LLM"""
    try:
        prompts = {
            "summary": f"Предоставьте краткое резюме следующего документа:\n\n{text[:4000]}",
            "topics": f"Определите основные темы следующего документа:\n\n{text[:4000]}",
            "recommendations": f"Предоставьте рекомендации на основе следующего документа:\n\n{text[:4000]}"
        }
        
        prompt = prompts.get(analysis_type, prompts["summary"])
        response = llm_chat([{"role": "user", "content": prompt}], temperature=0.3)
        
        return {
            "type": analysis_type,
            "content": response,
            "generated_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to generate document analysis: {e}")
        return None

async def save_document_analysis(document_id: str, analysis_result: Dict[str, Any], analysis_type: str) -> bool:
    """Сохранение результата анализа"""
    try:
        # Сохраняем в S3
        analysis_key = f"{document_id}/analysis_{analysis_type}.json"
        import json
        s3_manager.put_object(
            settings.S3_BUCKET_ANALYSIS,
            analysis_key,
            json.dumps(analysis_result, ensure_ascii=False).encode("utf-8"),
            content_type="application/json; charset=utf-8"
        )
        return True
    except Exception as e:
        logger.error(f"Failed to save document analysis: {e}")
        return False

async def get_old_documents(days_old: int) -> List[str]:
    """Получение старых документов"""
    try:
        async with get_async_session() as session:
            rag_documents_service = RAGDocumentsService(session)
            old_documents = await rag_documents_service.get_old_documents(days_old)
            return [str(doc.id) for doc in old_documents]
    except Exception as e:
        logger.error(f"Failed to get old documents: {e}")
        return []

async def delete_document_from_s3(document_id: str) -> bool:
    """Удаление документа из S3"""
    try:
        # Удаляем все файлы документа
        prefixes = [f"{document_id}/"]
        for prefix in prefixes:
            s3_manager.delete_objects_with_prefix(settings.S3_BUCKET_RAG, prefix)
            s3_manager.delete_objects_with_prefix(settings.S3_BUCKET_ANALYSIS, prefix)
        return True
    except Exception as e:
        logger.error(f"Failed to delete document from S3: {e}")
        return False

async def delete_document_from_db(document_id: str) -> bool:
    """Удаление документа из базы данных"""
    try:
        async with get_async_session() as session:
            rag_documents_service = RAGDocumentsService(session)
            success = await rag_documents_service.delete_document(document_id)
            return success
    except Exception as e:
        logger.error(f"Failed to delete document from database: {e}")
        return False
