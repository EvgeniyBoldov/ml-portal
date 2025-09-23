from __future__ import annotations
import os
from celery import Celery
from kombu import Queue

BROKER_URL = os.getenv("CELERY_BROKER_URL") or "redis://redis:6379/0"
RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND") or "redis://redis:6379/1"

app = Celery(
    "backend",
    broker=BROKER_URL,
    backend=RESULT_BACKEND,
    include=[
        # Новые улучшенные задачи
        "app.tasks.bg_tasks_enhanced",
        "app.tasks.periodic_tasks",
    ],
)

# Определение очередей с приоритетами
app.conf.task_queues = (
    # Критический приоритет - чат
    Queue('chat_critical', routing_key='chat_critical', priority=10),
    
    # Высокий приоритет - загрузка файлов
    Queue('upload_high', routing_key='upload_high', priority=8),
    
    # Средний приоритет - анализ документов
    Queue('analyze_medium', routing_key='analyze_medium', priority=5),
    Queue('ocr_medium', routing_key='ocr_medium', priority=5),
    
    # Низкий приоритет - RAG индексация
    Queue('rag_low', routing_key='rag_low', priority=2),
    Queue('cleanup_low', routing_key='cleanup_low', priority=1),
    
    # Очереди эмбеддингов (динамически создаются)
    Queue('embed.dispatch', routing_key='embed.dispatch', priority=8),
    Queue('embed.minilm.rt', routing_key='embed.minilm.rt', priority=8),
    Queue('embed.minilm.bulk', routing_key='embed.minilm.bulk', priority=3),
)

# Маршрутизация задач по очередям
app.conf.task_routes = {
    # Новые улучшенные задачи
    "bg_tasks.process_document": {"queue": "upload_high", "priority": 8},
    "bg_tasks.extract_and_normalize_text": {"queue": "upload_high", "priority": 8},
    "bg_tasks.chunk_document": {"queue": "upload_high", "priority": 8},
    "bg_tasks.generate_embeddings": {"queue": "rag_low", "priority": 2},
    "bg_tasks.finalize_document": {"queue": "rag_low", "priority": 2},
    "bg_tasks.analyze_document": {"queue": "analyze_medium", "priority": 5},
    "bg_tasks.cleanup_old_documents": {"queue": "cleanup_low", "priority": 1},
    
    # Периодические задачи
    "periodic_tasks.cleanup_old_documents_daily": {"queue": "cleanup_low", "priority": 1},
    "periodic_tasks.system_health_check": {"queue": "chat_critical", "priority": 10},
    "periodic_tasks.update_system_statistics": {"queue": "rag_low", "priority": 2},
    "periodic_tasks.cleanup_temp_files": {"queue": "cleanup_low", "priority": 1},
    "periodic_tasks.reindex_failed_documents": {"queue": "rag_low", "priority": 2},
    "periodic_tasks.monitor_queue_health": {"queue": "chat_critical", "priority": 10},
}

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    broker_heartbeat=20,
    broker_pool_limit=10,
    task_time_limit=60 * 60,
    task_soft_time_limit=55 * 60,
)

if os.getenv("BEAT") == "1":
    app.conf.beat_schedule = {
        "cleanup-old-documents-daily": {
            "task": "periodic_tasks.cleanup_old_documents_daily",
            "schedule": 86400.0,  # 24 hours
        },
        "system-health-check": {
            "task": "periodic_tasks.system_health_check",
            "schedule": 300.0,  # 5 minutes
        },
        "update-system-statistics": {
            "task": "periodic_tasks.update_system_statistics",
            "schedule": 3600.0,  # 1 hour
        }
    }

# Инициализация задач эмбеддингов
# Временно отключено из-за зависимости от torch
# from app.tasks.embedding_worker import create_embedding_worker_tasks
# from app.services.embedding_dispatcher import create_dispatcher_tasks

# Регистрируем задачи
# create_embedding_worker_tasks(app)
# create_dispatcher_tasks(app)
