"""
Тесты для улучшенных фоновых задач
"""
import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime
from uuid import uuid4

from app.tasks.bg_tasks_enhanced import (
    process_document,
    extract_and_normalize_text,
    chunk_document,
    generate_embeddings,
    finalize_document,
    analyze_document,
    cleanup_old_documents
)
from app.tasks.task_manager import TaskManager
from app.tasks.periodic_tasks import (
    cleanup_old_documents_daily,
    system_health_check,
    update_system_statistics,
    cleanup_temp_files,
    reindex_failed_documents,
    monitor_queue_health
)

class TestBackgroundTasks:
    """Тесты для фоновых задач"""
    
    @pytest.mark.asyncio
    async def test_process_document_success(self):
        """Тест успешной обработки документа"""
        document_id = str(uuid4())
        
        with patch('app.tasks.bg_tasks_enhanced.extract_and_normalize_text.delay') as mock_extract, \
             patch('app.tasks.bg_tasks_enhanced.chunk_document.delay') as mock_chunk, \
             patch('app.tasks.bg_tasks_enhanced.generate_embeddings.delay') as mock_embed, \
             patch('app.tasks.bg_tasks_enhanced.finalize_document.delay') as mock_finalize, \
             patch('app.tasks.bg_tasks_enhanced.update_document_status') as mock_update:
            
            # Настраиваем моки
            mock_extract.return_value.get.return_value = {"success": True, "text": "test text"}
            mock_chunk.return_value.get.return_value = {"success": True, "chunks_count": 5}
            mock_embed.return_value.get.return_value = {"success": True, "embeddings_count": 5}
            mock_finalize.return_value.get.return_value = {"success": True}
            mock_update.return_value = True
            
            # Выполняем задачу
            result = process_document(document_id)
            
            # Проверяем результат
            assert result["success"] is True
            assert result["document_id"] == document_id
            assert result["chunks_count"] == 5
            assert result["embeddings_count"] == 5
            assert result["status"] == "ready"
    
    @pytest.mark.asyncio
    async def test_process_document_failure(self):
        """Тест неудачной обработки документа"""
        document_id = str(uuid4())
        
        with patch('app.tasks.bg_tasks_enhanced.extract_and_normalize_text.delay') as mock_extract, \
             patch('app.tasks.bg_tasks_enhanced.update_document_status') as mock_update:
            
            # Настраиваем моки для неудачи
            mock_extract.return_value.get.return_value = {"success": False, "error": "Extraction failed"}
            mock_update.return_value = True
            
            # Выполняем задачу
            with pytest.raises(Exception):  # Должно вызвать retry
                process_document(document_id)
    
    @pytest.mark.asyncio
    async def test_extract_and_normalize_text_success(self):
        """Тест успешного извлечения и нормализации текста"""
        document_id = str(uuid4())
        source_key = f"{document_id}/original"
        
        with patch('app.tasks.bg_tasks_enhanced.s3_manager') as mock_s3, \
             patch('app.tasks.bg_tasks_enhanced.extract_text') as mock_extract, \
             patch('app.tasks.bg_tasks_enhanced.normalize_text') as mock_normalize:
            
            # Настраиваем моки
            mock_s3.get_object.return_value = b"test file content"
            mock_extract.return_value = Mock(
                text="extracted text",
                tables=[],
                meta={},
                kind="pdf",
                warnings=[]
            )
            mock_normalize.return_value = "normalized text"
            mock_s3.put_object.return_value = True
            
            # Выполняем задачу
            result = extract_and_normalize_text(document_id, source_key)
            
            # Проверяем результат
            assert result["success"] is True
            assert result["document_id"] == document_id
            assert result["text"] == "normalized text"
            assert result["text_length"] == len("normalized text")
    
    def test_chunk_document_success(self):
        """Тест успешного чанкинга документа"""
        document_id = str(uuid4())
        text = "This is a test document with multiple sentences. " * 100  # Длинный текст
        
        with patch('app.tasks.bg_tasks_enhanced.save_document_chunks') as mock_save:
            mock_save.return_value = 5
            
            # Выполняем задачу
            result = chunk_document(document_id, text, chunk_size=100, chunk_overlap=20)
            
            # Проверяем результат
            assert result["success"] is True
            assert result["document_id"] == document_id
            assert result["chunks_count"] == 5
            assert result["chunk_size"] == 100
            assert result["chunk_overlap"] == 20
    
    def test_generate_embeddings_success(self):
        """Тест успешной генерации эмбеддингов"""
        document_id = str(uuid4())
        
        with patch('app.tasks.bg_tasks_enhanced.get_document_chunks') as mock_get_chunks, \
             patch('app.tasks.bg_tasks_enhanced.generate_batch_embeddings') as mock_generate, \
             patch('app.tasks.bg_tasks_enhanced.save_chunk_embeddings') as mock_save:
            
            # Настраиваем моки
            mock_chunks = [
                {"text": "chunk 1", "chunk_index": 0, "id": str(uuid4())},
                {"text": "chunk 2", "chunk_index": 1, "id": str(uuid4())}
            ]
            mock_get_chunks.return_value = mock_chunks
            mock_generate.return_value = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
            mock_save.return_value = 2
            
            # Выполняем задачу
            result = generate_embeddings(document_id, model="minilm", batch_size=2)
            
            # Проверяем результат
            assert result["success"] is True
            assert result["document_id"] == document_id
            assert result["embeddings_count"] == 2
            assert result["model"] == "minilm"
    
    def test_finalize_document_success(self):
        """Тест успешной финализации документа"""
        document_id = str(uuid4())
        
        with patch('app.tasks.bg_tasks_enhanced.update_document_status') as mock_update_status, \
             patch('app.tasks.bg_tasks_enhanced.update_document_metadata') as mock_update_meta:
            
            # Настраиваем моки
            mock_update_status.return_value = True
            mock_update_meta.return_value = True
            
            # Выполняем задачу
            result = finalize_document(document_id)
            
            # Проверяем результат
            assert result["success"] is True
            assert result["document_id"] == document_id
            assert result["status"] == "ready"
            assert "finalized_at" in result
    
    def test_analyze_document_success(self):
        """Тест успешного анализа документа"""
        document_id = str(uuid4())
        analysis_type = "summary"
        
        with patch('app.tasks.bg_tasks_enhanced.get_document_text') as mock_get_text, \
             patch('app.tasks.bg_tasks_enhanced.generate_document_analysis') as mock_generate, \
             patch('app.tasks.bg_tasks_enhanced.save_document_analysis') as mock_save:
            
            # Настраиваем моки
            mock_get_text.return_value = "This is a test document for analysis."
            mock_generate.return_value = {
                "type": "summary",
                "content": "This is a summary of the document.",
                "generated_at": datetime.utcnow().isoformat()
            }
            mock_save.return_value = True
            
            # Выполняем задачу
            result = analyze_document(document_id, analysis_type)
            
            # Проверяем результат
            assert result["success"] is True
            assert result["document_id"] == document_id
            assert result["analysis_type"] == analysis_type
            assert "analysis_result" in result
    
    def test_cleanup_old_documents_success(self):
        """Тест успешной очистки старых документов"""
        days_old = 30
        
        with patch('app.tasks.bg_tasks_enhanced.get_old_documents') as mock_get_old, \
             patch('app.tasks.bg_tasks_enhanced.delete_document_from_s3') as mock_delete_s3, \
             patch('app.tasks.bg_tasks_enhanced.delete_document_from_db') as mock_delete_db:
            
            # Настраиваем моки
            old_docs = [str(uuid4()), str(uuid4())]
            mock_get_old.return_value = old_docs
            mock_delete_s3.return_value = True
            mock_delete_db.return_value = True
            
            # Выполняем задачу
            result = cleanup_old_documents(days_old)
            
            # Проверяем результат
            assert result["success"] is True
            assert result["cleaned_count"] == 2
            assert result["total_found"] == 2
            assert "cleanup_date" in result

class TestTaskManager:
    """Тесты для менеджера задач"""
    
    def test_process_document_async_success(self):
        """Тест асинхронной обработки документа"""
        document_id = str(uuid4())
        
        with patch('app.tasks.bg_tasks_enhanced.process_document.delay') as mock_process, \
             patch('app.tasks.task_manager.TaskManager._save_task_info') as mock_save:
            
            # Настраиваем моки
            mock_task = Mock()
            mock_task.id = "task_123"
            mock_process.return_value = mock_task
            mock_save.return_value = None
            
            # Создаем менеджер задач
            task_manager = TaskManager()
            
            # Выполняем задачу
            result = asyncio.run(task_manager.process_document_async(document_id, priority="normal"))
            
            # Проверяем результат
            assert result["task_id"] == "task_123"
            assert result["document_id"] == document_id
            assert result["status"] == "pending"
            assert result["priority"] == "normal"
    
    def test_get_task_status_success(self):
        """Тест получения статуса задачи"""
        task_id = "task_123"
        
        with patch('app.tasks.task_manager.TaskManager._get_task_info') as mock_get_info, \
             patch('app.tasks.task_manager.AsyncResult') as mock_async_result:
            
            # Настраиваем моки
            mock_task_info = {
                "task_id": task_id,
                "document_id": str(uuid4()),
                "status": "pending",
                "created_at": datetime.utcnow().isoformat()
            }
            mock_get_info.return_value = mock_task_info
            
            mock_result = Mock()
            mock_result.status = "SUCCESS"
            mock_result.successful.return_value = True
            mock_result.result = {"success": True}
            mock_async_result.return_value = mock_result
            
            # Создаем менеджер задач
            task_manager = TaskManager()
            
            # Выполняем задачу
            result = asyncio.run(task_manager.get_task_status(task_id))
            
            # Проверяем результат
            assert result["task_id"] == task_id
            assert result["status"] == "SUCCESS"
            assert result["result"] == {"success": True}
    
    def test_cancel_task_success(self):
        """Тест отмены задачи"""
        task_id = "task_123"
        
        with patch('app.tasks.task_manager.AsyncResult') as mock_async_result, \
             patch('app.tasks.task_manager.TaskManager._get_task_info') as mock_get_info, \
             patch('app.tasks.task_manager.TaskManager._save_task_info') as mock_save:
            
            # Настраиваем моки
            mock_result = Mock()
            mock_result.revoke.return_value = None
            mock_async_result.return_value = mock_result
            
            mock_task_info = {"task_id": task_id, "status": "pending"}
            mock_get_info.return_value = mock_task_info
            mock_save.return_value = None
            
            # Создаем менеджер задач
            task_manager = TaskManager()
            
            # Выполняем задачу
            result = asyncio.run(task_manager.cancel_task(task_id))
            
            # Проверяем результат
            assert result is True
            mock_result.revoke.assert_called_once_with(terminate=True)

class TestPeriodicTasks:
    """Тесты для периодических задач"""
    
    def test_cleanup_old_documents_daily_success(self):
        """Тест ежедневной очистки документов"""
        with patch('app.tasks.bg_tasks_enhanced.cleanup_old_documents.delay') as mock_cleanup:
            # Настраиваем моки
            mock_task = Mock()
            mock_task.id = "cleanup_task_123"
            mock_cleanup.return_value = mock_task
            
            # Выполняем задачу
            result = cleanup_old_documents_daily()
            
            # Проверяем результат
            assert result["success"] is True
            assert result["task_id"] == "cleanup_task_123"
            assert "scheduled_at" in result
    
    def test_system_health_check_success(self):
        """Тест проверки здоровья системы"""
        with patch('app.tasks.periodic_tasks.check_database_health') as mock_db, \
             patch('app.tasks.periodic_tasks.check_redis_health') as mock_redis, \
             patch('app.tasks.periodic_tasks.check_s3_health') as mock_s3, \
             patch('app.tasks.periodic_tasks.check_queue_health') as mock_queue, \
             patch('app.tasks.periodic_tasks.redis_manager') as mock_redis_manager:
            
            # Настраиваем моки
            mock_db.return_value = {"status": "healthy"}
            mock_redis.return_value = {"status": "healthy"}
            mock_s3.return_value = {"status": "healthy"}
            mock_queue.return_value = {"status": "healthy"}
            mock_redis_manager.set_async = AsyncMock(return_value=None)
            
            # Выполняем задачу
            result = system_health_check()
            
            # Проверяем результат
            assert result["overall_status"] == "healthy"
            assert "components" in result
            assert result["components"]["database"]["status"] == "healthy"
            assert result["components"]["redis"]["status"] == "healthy"
    
    def test_update_system_statistics_success(self):
        """Тест обновления статистики системы"""
        with patch('app.tasks.periodic_tasks.gather_system_statistics') as mock_gather, \
             patch('app.tasks.periodic_tasks.redis_manager') as mock_redis_manager:
            
            # Настраиваем моки
            mock_stats = {
                "documents": {"total": 100, "ready": 95, "processing": 3, "failed": 2},
                "chunks": {"total": 1000},
                "collected_at": datetime.utcnow().isoformat()
            }
            mock_gather.return_value = mock_stats
            mock_redis_manager.set_async = AsyncMock(return_value=None)
            
            # Выполняем задачу
            result = update_system_statistics()
            
            # Проверяем результат
            assert result["success"] is True
            assert "statistics" in result
            assert result["statistics"]["documents"]["total"] == 100
    
    def test_cleanup_temp_files_success(self):
        """Тест очистки временных файлов"""
        with patch('app.tasks.periodic_tasks.redis_manager') as mock_redis_manager, \
             patch('app.tasks.periodic_tasks.cleanup_old_task_info') as mock_cleanup:
            
            # Настраиваем моки
            mock_redis_manager.keys_async = AsyncMock(return_value=["temp:file1", "temp:file2"])
            mock_redis_manager.delete_async = AsyncMock(return_value=None)
            mock_cleanup.return_value = 5
            
            # Выполняем задачу
            result = cleanup_temp_files()
            
            # Проверяем результат
            assert result["success"] is True
            assert result["temp_keys_cleaned"] == 2
            assert result["old_tasks_cleaned"] == 5
    
    def test_reindex_failed_documents_success(self):
        """Тест переиндексации неудачных документов"""
        with patch('app.tasks.periodic_tasks.get_failed_documents') as mock_get_failed, \
             patch('app.tasks.periodic_tasks.reset_document_status') as mock_reset, \
             patch('app.tasks.periodic_tasks.task_manager') as mock_task_manager:
            
            # Настраиваем моки
            failed_docs = [str(uuid4()), str(uuid4())]
            mock_get_failed.return_value = failed_docs
            mock_reset.return_value = True
            
            mock_task_info = {"task_id": "task_123", "status": "pending"}
            mock_task_manager.process_document_async = AsyncMock(return_value=mock_task_info)
            
            # Выполняем задачу
            result = reindex_failed_documents()
            
            # Проверяем результат
            assert result["success"] is True
            assert result["reindexed_count"] == 2
            assert result["total_failed"] == 2
    
    def test_monitor_queue_health_success(self):
        """Тест мониторинга здоровья очередей"""
        with patch('app.tasks.periodic_tasks.task_manager') as mock_task_manager, \
             patch('app.tasks.periodic_tasks.redis_manager') as mock_redis_manager:
            
            # Настраиваем моки
            mock_queue_stats = {
                "queues": {
                    "rag_low": {"active": 10, "scheduled": 5, "reserved": 2},
                    "upload_high": {"active": 3, "scheduled": 1, "reserved": 0}
                },
                "total_active": 13,
                "total_scheduled": 6,
                "total_reserved": 2
            }
            mock_task_manager.get_queue_stats = AsyncMock(return_value=mock_queue_stats)
            mock_redis_manager.set_async = AsyncMock(return_value=None)
            
            # Выполняем задачу
            result = monitor_queue_health()
            
            # Проверяем результат
            assert result["status"] == "healthy"
            assert "stats" in result
            assert "alerts" in result
            assert result["stats"]["total_active"] == 13
