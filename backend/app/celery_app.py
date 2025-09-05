from __future__ import annotations
import os
from celery import Celery

BROKER_URL = os.getenv("CELERY_BROKER_URL") or os.getenv("REDIS_URL", "redis://redis:6379/0")
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
    ],
)

# Queues & routing
app.conf.task_routes = {
    "app.tasks.normalize.*": {"queue": "normalize"},
    "app.tasks.chunk.*": {"queue": "chunk"},
    "app.tasks.embed.*": {"queue": "embed"},
    "app.tasks.index.*": {"queue": "index"},
    "app.tasks.analyze.*": {"queue": "analyze"},
    "app.tasks.upload.*": {"queue": "watch"},
    "app.tasks.upload_watch.*": {"queue": "watch"},
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
