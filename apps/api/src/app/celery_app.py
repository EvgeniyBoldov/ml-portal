from __future__ import annotations
from app.core.logging import get_logger
from app.core.config import get_settings
from celery import Celery
from kombu import Queue

settings = get_settings()
BROKER_URL = settings.CELERY_BROKER_URL
RESULT_BACKEND = settings.CELERY_RESULT_BACKEND

app = Celery(
    "backend",
    broker=BROKER_URL,
    backend=RESULT_BACKEND,
    include=[
        # RAG ingest pipeline tasks
        "app.workers.tasks_rag_ingest",
        # Collection vectorization tasks
        "app.workers.tasks_collection_vectorize",
        # Membership reconcile tasks
        "app.workers.tasks_membership_reconcile",
        # RAG model/status reconcile tasks
        "app.workers.tasks_rag_model_reconcile",
        # Periodic model health checks
        "app.workers.tasks_health_check",
        # Cleanup tasks for retention policies
        "app.workers.tasks_cleanup",
    ],
    autodiscover_tasks=False,  # Отключаем автообнаружение задач
)

# Alias for compatibility
celery_app = app

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
    
    # RAG ingest pipeline queues
    Queue('ingest.extract', routing_key='ingest.extract', priority=7),
    Queue('ingest.normalize', routing_key='ingest.normalize', priority=6),
    Queue('ingest.chunk', routing_key='ingest.chunk', priority=5),
    Queue('ingest.embed', routing_key='ingest.embed', priority=4),
    Queue('ingest.index', routing_key='ingest.index', priority=3),
    # Reindex queues
    Queue('reindex.default', routing_key='reindex.default', priority=2),
    
    # Maintenance queues
    Queue('maintenance.default', routing_key='maintenance.default', priority=1),
    
    # Dead letter queue
    Queue('dlq', routing_key='dlq', priority=0),
)

# Маршрутизация задач по очередям
app.conf.task_routes = {
    # RAG ingest pipeline tasks
    "app.workers.tasks_rag_ingest.extract.extract_document": {"queue": "ingest.extract", "priority": 7},
    "app.workers.tasks_rag_ingest.normalize.normalize_document": {"queue": "ingest.normalize", "priority": 6},
    "app.workers.tasks_rag_ingest.chunk.chunk_document": {"queue": "ingest.chunk", "priority": 5},
    "app.workers.tasks_rag_ingest.embed.embed_chunks_model": {"queue": "ingest.embed", "priority": 4},
    "app.workers.tasks_rag_ingest.index.index_model": {"queue": "ingest.index", "priority": 3},
    # Collection vectorization tasks
    "app.workers.tasks_collection_vectorize.vectorize_collection_rows": {"queue": "ingest.embed", "priority": 4},
    "app.workers.tasks_collection_vectorize.reconcile_collection_vectorization": {"queue": "maintenance.default", "priority": 1},
    "app.workers.tasks_rag_model_reconcile.reconcile_rag_statuses_for_embedding_model": {
        "queue": "maintenance.default",
        "priority": 1,
    },
    "app.workers.tasks_health_check.health_check_all_models": {"queue": "maintenance.default", "priority": 1},
    "app.workers.tasks_health_check.health_check_single_model": {"queue": "maintenance.default", "priority": 1},

    # Reindex tasks
    "app.workers.tasks_reindex.reindex_source": {"queue": "reindex.default", "priority": 2},
    "app.workers.tasks_reindex.reindex_by_model": {"queue": "reindex.default", "priority": 2},
}

app.conf.update(
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    
    # Reliability settings
    task_acks_late=True,
    task_acks_on_failure_or_timeout=False,
    worker_prefetch_multiplier=1,
    
    # Connection settings
    broker_heartbeat=20,
    broker_pool_limit=10,
    broker_connection_retry_on_startup=True,
    
    # Time limits
    task_time_limit=60 * 60,  # 1 hour
    task_soft_time_limit=55 * 60,  # 55 minutes
    
    # Retry settings
    task_default_retry_delay=60,  # 1 minute
    task_max_retries=3,
    
    # Dead letter queue
    task_reject_on_worker_lost=True,
    task_ignore_result=False,
    
    # Monitoring
    worker_send_task_events=True,
    task_send_sent_event=True,
)

# RAG ingest tasks are now imported from tasks_rag_ingest module

if settings.BEAT == 1:
    app.conf.beat_schedule = {
        "models-health-check": {
            "task": "app.workers.tasks_health_check.health_check_all_models",
            "schedule": 300.0,  # 5 minutes
        },
        "collections-vectorization-reconcile": {
            "task": "app.workers.tasks_collection_vectorize.reconcile_collection_vectorization",
            "schedule": 120.0,  # 2 minutes
        },
        "document-membership-reconcile": {
            "task": "app.workers.tasks_membership_reconcile.reconcile_document_collection_memberships",
            "schedule": 600.0,  # 10 minutes
        },
    }

# Инициализация задач эмбеддингов
# Временно отключено из-за зависимости от torch
# from app.tasks.embedding_worker import create_embedding_worker_tasks
# from app.services.embedding_dispatcher import create_dispatcher_tasks

# Регистрируем задачи
# create_embedding_worker_tasks(app)
# create_dispatcher_tasks(app)

# Worker sessions are created lazily per task via get_worker_session().
