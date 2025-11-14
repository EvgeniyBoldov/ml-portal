"""
Prometheus metrics for RAG ingest pipeline
"""
from __future__ import annotations
from typing import Optional
from prometheus_client import Counter, Histogram, Gauge, generate_latest
from prometheus_client.registry import CollectorRegistry, REGISTRY
from app.core.logging import get_logger

logger = get_logger(__name__)

# Create a separate registry for our metrics
_registry = REGISTRY

# Task duration metrics
ingest_task_duration_seconds = Histogram(
    'ingest_task_duration_seconds',
    'Duration of ingest tasks by step',
    ['step', 'tenant_id'],
    registry=_registry
)

# Tasks in progress
ingest_tasks_in_progress = Gauge(
    'ingest_tasks_in_progress',
    'Number of ingest tasks currently in progress',
    ['queue', 'step', 'tenant_id'],
    registry=_registry
)

# Failed tasks counter
ingest_tasks_failed_total = Counter(
    'ingest_tasks_failed_total',
    'Total number of failed ingest tasks',
    ['reason', 'step', 'tenant_id'],
    registry=_registry
)

# Events outbox backlog
events_outbox_backlog = Gauge(
    'events_outbox_backlog',
    'Number of undelivered events in outbox',
    ['event_type'],
    registry=_registry
)

# SSE clients
sse_clients = Gauge(
    'rag_sse_clients',
    'Number of active SSE clients connected to RAG events stream',
    registry=_registry
)

# SSE delivery lag
sse_delivery_lag_seconds = Histogram(
    'rag_sse_delivery_lag_seconds',
    'Time lag between event creation and SSE delivery',
    ['event_type'],
    registry=_registry
)

# Model progress ratio
model_progress_ratio = Gauge(
    'rag_model_progress_ratio',
    'Embedding progress ratio per model (0.0-1.0)',
    ['model_alias', 'document_id', 'tenant_id'],
    registry=_registry
)


def record_task_duration(step: str, duration: float, tenant_id: Optional[str] = None):
    """Record task duration"""
    ingest_task_duration_seconds.labels(
        step=step,
        tenant_id=tenant_id or 'unknown'
    ).observe(duration)


def record_task_started(queue: str, step: str, tenant_id: Optional[str] = None):
    """Increment tasks in progress"""
    ingest_tasks_in_progress.labels(
        queue=queue,
        step=step,
        tenant_id=tenant_id or 'unknown'
    ).inc()


def record_task_finished(queue: str, step: str, tenant_id: Optional[str] = None):
    """Decrement tasks in progress"""
    ingest_tasks_in_progress.labels(
        queue=queue,
        step=step,
        tenant_id=tenant_id or 'unknown'
    ).dec()


def record_task_failed(reason: str, step: str, tenant_id: Optional[str] = None):
    """Record failed task"""
    ingest_tasks_failed_total.labels(
        reason=reason,
        step=step,
        tenant_id=tenant_id or 'unknown'
    ).inc()


def record_outbox_backlog(event_type: str, count: int):
    """Update outbox backlog gauge"""
    events_outbox_backlog.labels(event_type=event_type).set(count)


def record_sse_client_connected():
    """Increment SSE clients"""
    sse_clients.inc()


def record_sse_client_disconnected():
    """Decrement SSE clients"""
    sse_clients.dec()


def record_sse_delivery_lag(event_type: str, lag_seconds: float):
    """Record SSE delivery lag"""
    sse_delivery_lag_seconds.labels(event_type=event_type).observe(lag_seconds)


def record_model_progress(model_alias: str, document_id: str, ratio: float, tenant_id: Optional[str] = None):
    """Record model embedding progress (0.0-1.0)"""
    model_progress_ratio.labels(
        model_alias=model_alias,
        document_id=document_id,
        tenant_id=tenant_id or 'unknown'
    ).set(ratio)


def get_metrics_text() -> str:
    """Get Prometheus metrics as text"""
    return generate_latest(_registry).decode('utf-8')

