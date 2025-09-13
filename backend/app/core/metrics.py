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

# Enhanced metrics for observability
llm_request_total = Counter("llm_request_total", "LLM requests total", ["model", "status"])
llm_latency_seconds = Histogram("llm_latency_seconds", "LLM request latency", ["model"], buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0])
llm_tokens_total = Counter("llm_tokens_total", "LLM tokens processed", ["model", "type"])  # type: input/output

embedding_request_total = Counter("embedding_request_total", "Embedding requests total", ["model", "status"])
embedding_latency_seconds = Histogram("embedding_latency_seconds", "Embedding request latency", ["model"], buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0])

document_processing_total = Counter("document_processing_total", "Document processing", ["format", "status"])
document_processing_seconds = Histogram("document_processing_seconds", "Document processing time", ["format"], buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 300.0])

chunking_quality = Histogram("chunking_quality", "Chunk quality metrics", ["metric"], buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0])

reranking_total = Counter("reranking_total", "Reranking operations", ["method", "status"])
reranking_latency_seconds = Histogram("reranking_latency_seconds", "Reranking latency", ["method"])

pipeline_stage_duration = Histogram("pipeline_stage_duration_seconds", "Pipeline stage duration", ["stage"], buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 300.0, 600.0])
pipeline_errors_total = Counter("pipeline_errors_total", "Pipeline errors", ["stage", "error_type"])

qdrant_points = Gauge("qdrant_points", "Qdrant points", ["collection"])
qdrant_operations_total = Counter("qdrant_operations_total", "Qdrant operations", ["operation", "status"])
qdrant_latency_seconds = Histogram("qdrant_latency_seconds", "Qdrant operation latency", ["operation"])

# RAG-specific metrics
rag_ingest_stage_duration = Histogram("rag_ingest_stage_duration_seconds", "RAG ingest stage duration", ["stage"], buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 300.0])
rag_ingest_errors_total = Counter("rag_ingest_errors_total", "RAG ingest errors", ["stage", "error_type"])

rag_vectors_total = Gauge("rag_vectors_total", "Total vectors in Qdrant", ["collection"])
rag_chunks_total = Gauge("rag_chunks_total", "Total chunks in Qdrant", ["collection"])

rag_search_latency_seconds = Histogram("rag_search_latency_seconds", "RAG search latency", ["model"], buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0])
rag_search_top_k = Histogram("rag_search_top_k", "RAG search top_k distribution", ["model"], buckets=[1, 3, 5, 10, 20, 50])
rag_search_scores = Histogram("rag_search_scores", "RAG search score distribution", ["model"], buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0])
rag_search_coverage = Histogram("rag_search_coverage", "RAG search document coverage", ["model"], buckets=[1, 2, 3, 5, 10, 20])

rag_quality_mrr = Histogram("rag_quality_mrr", "RAG quality MRR@K", ["k"], buckets=[1, 3, 5, 10])
rag_quality_ndcg = Histogram("rag_quality_ndcg", "RAG quality nDCG@K", ["k"], buckets=[1, 3, 5, 10])

chat_rag_usage_total = Counter("chat_rag_usage_total", "Chat RAG usage", ["model", "has_context"])
chat_rag_fallback_total = Counter("chat_rag_fallback_total", "Chat RAG fallback", ["reason"])

# System health metrics
memory_usage_bytes = Gauge("memory_usage_bytes", "Memory usage", ["type"])
cpu_usage_percent = Gauge("cpu_usage_percent", "CPU usage percentage")
disk_usage_bytes = Gauge("disk_usage_bytes", "Disk usage", ["path"])

def prometheus_endpoint() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
