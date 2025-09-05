from __future__ import annotations
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from fastapi.responses import Response

# API metrics
logins_total = Counter("logins_total", "Logins", ["result"])
refresh_total = Counter("refresh_total", "Refresh", ["result"])
chat_requests_total = Counter("chat_requests_total", "Total chat requests", ["use_rag", "model"])
chat_latency_seconds = Histogram("chat_latency_seconds", "Chat latency", ["use_rag"])
rag_search_total = Counter("rag_search_total", "Total RAG searches", ["model"])
rag_documents_total = Counter("rag_documents_total", "RAG documents by status", ["status"])

# Pipeline counters
rag_ingest_started_total = Counter("rag_ingest_started_total", "RAG ingest pipelines started")
rag_chunks_created_total = Counter("rag_chunks_created_total", "Total chunks created")
rag_vectors_upserted_total = Counter("rag_vectors_upserted_total", "Total vectors upserted to Qdrant")

# Tasks metrics
tasks_started_total = Counter("tasks_started_total", "Tasks started", ["queue", "task"])
tasks_failed_total  = Counter("tasks_failed_total",  "Tasks failed",  ["queue", "task"])
task_duration_seconds = Histogram("task_duration_seconds", "Task duration", ["task"])
embedding_batch_inflight = Gauge("embedding_batch_inflight", "Embedding batches in flight")

# External calls metrics
external_request_total = Counter("external_request_total", "External requests total", ["target", "status"])
external_request_seconds = Histogram("external_request_seconds", "External request latency", ["target"])

qdrant_points = Gauge("qdrant_points", "Qdrant points", ["collection"])

def prometheus_endpoint() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
