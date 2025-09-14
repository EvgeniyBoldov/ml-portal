from __future__ import annotations

import json
from typing import Dict, Any, List
from celery import shared_task
from app.core.config import settings
from app.core.db import SessionLocal
from app.core.metrics import chat_rag_usage_total, chat_rag_fallback_total
from .shared import log, RetryableError, task_metrics

@shared_task(name="app.tasks.chat.process_message", bind=True, autoretry_for=(RetryableError,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def process_chat_message(self, chat_id: str, message: str, use_rag: bool = False) -> Dict[str, Any]:
    """
    Обработка сообщения чата (критический приоритет)
    """
    with task_metrics("chat.process_message", "chat"):
        session = SessionLocal()
        try:
            # Логика обработки сообщения чата
            log.info(f"Processing chat message for chat_id={chat_id}, use_rag={use_rag}")
            
            # Если используется RAG, выполняем поиск
            rag_context = ""
            if use_rag:
                try:
                    from app.services.rag_service import search
                    results = search(message, limit=5)
                    if results:
                        rag_context = "\n".join([r.get("text", "") for r in results])
                        log.info(f"RAG context found: {len(rag_context)} characters")
                    chat_rag_usage_total.labels(model="gpt-4", has_context="true").inc()
                except Exception as e:
                    log.warning(f"RAG search failed: {e}")
                    chat_rag_fallback_total.labels(reason="search_failed").inc()
                    chat_rag_usage_total.labels(model="gpt-4", has_context="false").inc()
            else:
                chat_rag_usage_total.labels(model="gpt-4", has_context="false").inc()
            
            # Формируем ответ
            response = {
                "chat_id": chat_id,
                "message": message,
                "rag_context": rag_context,
                "use_rag": use_rag,
                "processed": True
            }
            
            return response
            
        except Exception as e:
            log.error(f"Chat message processing failed: {e}")
            chat_rag_fallback_total.labels(reason="processing_failed").inc()
            raise RetryableError(f"Chat message processing failed: {e}")
        finally:
            session.close()

@shared_task(name="app.tasks.chat.generate_response", bind=True, autoretry_for=(RetryableError,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def generate_chat_response(self, chat_id: str, message: str, rag_context: str = "") -> Dict[str, Any]:
    """
    Генерация ответа чата (критический приоритет)
    """
    with task_metrics("chat.generate_response", "chat"):
        try:
            # Логика генерации ответа через LLM
            log.info(f"Generating response for chat_id={chat_id}")
            
            # Здесь будет вызов LLM API
            response_text = f"Ответ на сообщение: {message}"
            if rag_context:
                response_text += f"\n\nКонтекст из RAG: {rag_context[:200]}..."
            
            response = {
                "chat_id": chat_id,
                "response": response_text,
                "rag_used": bool(rag_context),
                "generated": True
            }
            
            return response
            
        except Exception as e:
            log.error(f"Chat response generation failed: {e}")
            chat_rag_fallback_total.labels(reason="generation_failed").inc()
            raise RetryableError(f"Chat response generation failed: {e}")

@shared_task(name="app.tasks.chat.process_rag_query", bind=True, autoretry_for=(RetryableError,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def process_rag_query(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Обработка RAG запроса (средний приоритет)
    """
    with task_metrics("chat.process_rag_query", "rag"):
        try:
            from app.services.rag_service import search
            
            log.info(f"Processing RAG query: {query[:100]}...")
            
            results = search(query, limit=limit)
            
            log.info(f"RAG query returned {len(results)} results")
            return results
            
        except Exception as e:
            log.error(f"RAG query processing failed: {e}")
            raise RetryableError(f"RAG query processing failed: {e}")

@shared_task(name="app.tasks.chat.cleanup_old_messages", bind=True)
def cleanup_old_messages(self, days_old: int = 30) -> Dict[str, Any]:
    """
    Очистка старых сообщений чата (низкий приоритет)
    """
    with task_metrics("chat.cleanup_old_messages", "cleanup"):
        session = SessionLocal()
        try:
            from datetime import datetime, timedelta
            from app.models.chat import ChatMessage
            
            cutoff_date = datetime.utcnow() - timedelta(days=days_old)
            
            # Удаляем старые сообщения
            old_messages = session.query(ChatMessage).filter(
                ChatMessage.created_at < cutoff_date
            ).all()
            
            count = len(old_messages)
            for message in old_messages:
                session.delete(message)
            
            session.commit()
            
            log.info(f"Cleaned up {count} old chat messages")
            
            return {
                "cleaned_messages": count,
                "cutoff_date": cutoff_date.isoformat(),
                "success": True
            }
            
        except Exception as e:
            log.error(f"Chat cleanup failed: {e}")
            session.rollback()
            raise RetryableError(f"Chat cleanup failed: {e}")
        finally:
            session.close()
