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
        "app.tasks.normalize",
        "app.tasks.chunk",
        "app.tasks.embed",
        "app.tasks.index",
        "app.tasks.analyze",
        "app.tasks.upload_watch",
        "app.tasks.ocr_tables",
        "app.tasks.chat",
        "app.tasks.embedding_worker",
        "app.services.embedding_dispatcher",
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
    # Критический приоритет - чат
    "app.tasks.chat.*": {"queue": "chat_critical", "priority": 10},
    
    # Высокий приоритет - загрузка и нормализация
    "app.tasks.upload_watch.*": {"queue": "upload_high", "priority": 8},
    "app.tasks.normalize.normalize": {"queue": "upload_high", "priority": 8},
    "app.tasks.chunk.split": {"queue": "upload_high", "priority": 8},
    
    # Средний приоритет - анализ документов
    "app.tasks.analyze.*": {"queue": "analyze_medium", "priority": 5},
    "app.tasks.ocr_tables.*": {"queue": "ocr_medium", "priority": 5},
    
    # Низкий приоритет - RAG индексация
    "app.tasks.embed.*": {"queue": "rag_low", "priority": 2},
    "app.tasks.index.*": {"queue": "rag_low", "priority": 2},
    "app.tasks.delete.*": {"queue": "cleanup_low", "priority": 1},
    
    # Эмбеддинги
    "embedding_dispatcher.dispatch": {"queue": "embed.dispatch", "priority": 8},
    "embedding_worker.process_embedding": {"queue": "embed.minilm.rt", "priority": 8},
    "embedding_worker.health_check": {"queue": "embed.minilm.rt", "priority": 8},
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
        "dummy-housekeeping-5m": {
            "task": "app.tasks.index.housekeeping",
            "schedule": 300.0,
        }
    }

# Инициализация задач эмбеддингов
from app.tasks.embedding_worker import create_embedding_worker_tasks
from app.services.embedding_dispatcher import create_dispatcher_tasks

# Регистрируем задачи
create_embedding_worker_tasks(app)
create_dispatcher_tasks(app)
