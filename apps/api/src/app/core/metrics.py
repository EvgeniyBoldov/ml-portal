# apps/api/src/app/core/metrics.py
"""
Metrics collection system for monitoring Celery queues and emb-gateway performance
"""
import time
from app.core.logging import get_logger
from typing import Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime, timezone
import asyncio
import httpx
from celery import Celery
from celery.events.state import State
from celery.events import EventReceiver

logger = get_logger(__name__)

@dataclass
class QueueMetrics:
    """Queue metrics data structure"""
    queue_name: str
    depth: int
    active_tasks: int
    scheduled_tasks: int
    reserved_tasks: int
    completed_tasks: int
    failed_tasks: int
    retry_tasks: int
    avg_processing_time: float
    last_updated: datetime

@dataclass
class EmbeddingMetrics:
    """Embedding service metrics data structure"""
    model_alias: str
    p95_latency_ms: float
    avg_latency_ms: float
    batch_size: int
    queue_depth: int
    success_rate: float
    error_rate: float
    requests_per_minute: float
    last_updated: datetime

class CeleryMetricsCollector:
    """Collect metrics from Celery queues"""
    
    def __init__(self, celery_app: Celery):
        self.celery_app = celery_app
        self.state = State()
        self.metrics_cache: Dict[str, QueueMetrics] = {}
    
    def collect_queue_metrics(self) -> Dict[str, QueueMetrics]:
        """Collect metrics for all queues"""
        metrics = {}
        
        try:
            # Get queue stats from Celery
            inspect = self.celery_app.control.inspect()
            
            # Get active tasks
            active_tasks = inspect.active()
            if active_tasks:
                for worker, tasks in active_tasks.items():
                    for task in tasks:
                        queue_name = task.get('delivery_info', {}).get('routing_key', 'default')
                        if queue_name not in metrics:
                            metrics[queue_name] = QueueMetrics(
                                queue_name=queue_name,
                                depth=0,
                                active_tasks=0,
                                scheduled_tasks=0,
                                reserved_tasks=0,
                                completed_tasks=0,
                                failed_tasks=0,
                                retry_tasks=0,
                                avg_processing_time=0.0,
                                last_updated=datetime.now(timezone.utc)
                            )
                        metrics[queue_name].active_tasks += 1
            
            # Get scheduled tasks
            scheduled_tasks = inspect.scheduled()
            if scheduled_tasks:
                for worker, tasks in scheduled_tasks.items():
                    for task in tasks:
                        queue_name = task.get('delivery_info', {}).get('routing_key', 'default')
                        if queue_name not in metrics:
                            metrics[queue_name] = QueueMetrics(
                                queue_name=queue_name,
                                depth=0,
                                active_tasks=0,
                                scheduled_tasks=0,
                                reserved_tasks=0,
                                completed_tasks=0,
                                failed_tasks=0,
                                retry_tasks=0,
                                avg_processing_time=0.0,
                                last_updated=datetime.now(timezone.utc)
                            )
                        metrics[queue_name].scheduled_tasks += 1
            
            # Get reserved tasks
            reserved_tasks = inspect.reserved()
            if reserved_tasks:
                for worker, tasks in reserved_tasks.items():
                    for task in tasks:
                        queue_name = task.get('delivery_info', {}).get('routing_key', 'default')
                        if queue_name not in metrics:
                            metrics[queue_name] = QueueMetrics(
                                queue_name=queue_name,
                                depth=0,
                                active_tasks=0,
                                scheduled_tasks=0,
                                reserved_tasks=0,
                                completed_tasks=0,
                                failed_tasks=0,
                                retry_tasks=0,
                                avg_processing_time=0.0,
                                last_updated=datetime.now(timezone.utc)
                            )
                        metrics[queue_name].reserved_tasks += 1
            
            # Calculate queue depth
            for queue_name, metric in metrics.items():
                metric.depth = metric.active_tasks + metric.scheduled_tasks + metric.reserved_tasks
            
            # Cache metrics
            self.metrics_cache.update(metrics)
            
        except Exception as e:
            logger.error(f"Failed to collect Celery metrics: {e}")
        
        return metrics
    
    def get_queue_depth(self, queue_name: str) -> int:
        """Get depth of specific queue"""
        if queue_name in self.metrics_cache:
            return self.metrics_cache[queue_name].depth
        return 0
    
    def get_total_queue_depth(self) -> int:
        """Get total depth across all queues"""
        return sum(metric.depth for metric in self.metrics_cache.values())

class EmbeddingMetricsCollector:
    """Collect metrics from emb-gateway service"""
    
    def __init__(self, emb_gateway_url: str = "http://emb:8001"):
        self.emb_gateway_url = emb_gateway_url
        self.metrics_cache: Dict[str, EmbeddingMetrics] = {}
    
    async def collect_metrics(self) -> Dict[str, EmbeddingMetrics]:
        """Collect metrics from emb-gateway"""
        metrics = {}
        
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                # Get metrics from emb-gateway
                response = await client.get(f"{self.emb_gateway_url}/metrics")
                if response.status_code == 200:
                    data = response.json()
                    
                    # Parse metrics for each model
                    for model_alias, model_metrics in data.get("models", {}).items():
                        metrics[model_alias] = EmbeddingMetrics(
                            model_alias=model_alias,
                            p95_latency_ms=model_metrics.get("p95_latency_ms", 0.0),
                            avg_latency_ms=model_metrics.get("avg_latency_ms", 0.0),
                            batch_size=model_metrics.get("batch_size", 0),
                            queue_depth=model_metrics.get("queue_depth", 0),
                            success_rate=model_metrics.get("success_rate", 0.0),
                            error_rate=model_metrics.get("error_rate", 0.0),
                            requests_per_minute=model_metrics.get("requests_per_minute", 0.0),
                            last_updated=datetime.now(timezone.utc)
                        )
                    
                    # Cache metrics
                    self.metrics_cache.update(metrics)
                    
        except Exception as e:
            logger.error(f"Failed to collect embedding metrics: {e}")
        
        return metrics
    
    def get_model_p95_latency(self, model_alias: str) -> float:
        """Get P95 latency for specific model"""
        if model_alias in self.metrics_cache:
            return self.metrics_cache[model_alias].p95_latency_ms
        return 0.0
    
    def get_model_queue_depth(self, model_alias: str) -> int:
        """Get queue depth for specific model"""
        if model_alias in self.metrics_cache:
            return self.metrics_cache[model_alias].queue_depth
        return 0

class MetricsAggregator:
    """Aggregate metrics from all sources"""
    
    def __init__(self, celery_app: Celery, emb_gateway_url: str = "http://emb:8001"):
        self.celery_collector = CeleryMetricsCollector(celery_app)
        self.embedding_collector = EmbeddingMetricsCollector(emb_gateway_url)
        self.last_collection = datetime.now(timezone.utc)
    
    def collect_all_metrics(self) -> Dict[str, Any]:
        """Collect metrics from all sources"""
        metrics = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "celery": {},
            "embedding": {},
            "alerts": []
        }
        
        # Collect Celery metrics
        celery_metrics = self.celery_collector.collect_queue_metrics()
        metrics["celery"]["queues"] = {
            queue_name: {
                "depth": metric.depth,
                "active_tasks": metric.active_tasks,
                "scheduled_tasks": metric.scheduled_tasks,
                "reserved_tasks": metric.reserved_tasks,
                "avg_processing_time": metric.avg_processing_time
            }
            for queue_name, metric in celery_metrics.items()
        }
        
        # Collect embedding metrics
        try:
            embedding_metrics = asyncio.run(self.embedding_collector.collect_metrics())
            metrics["embedding"]["models"] = {
                model_alias: {
                    "p95_latency_ms": metric.p95_latency_ms,
                    "avg_latency_ms": metric.avg_latency_ms,
                    "batch_size": metric.batch_size,
                    "queue_depth": metric.queue_depth,
                    "success_rate": metric.success_rate,
                    "error_rate": metric.error_rate,
                    "requests_per_minute": metric.requests_per_minute
                }
                for model_alias, metric in embedding_metrics.items()
            }
        except Exception as e:
            logger.error(f"Failed to collect embedding metrics: {e}")
            metrics["embedding"]["error"] = str(e)
        
        # Generate alerts
        metrics["alerts"] = self._generate_alerts(metrics)
        
        self.last_collection = datetime.now(timezone.utc)
        return metrics
    
    def _generate_alerts(self, metrics: Dict[str, Any]) -> list:
        """Generate alerts based on metrics"""
        alerts = []
        
        # Check Celery queue depths
        celery_queues = metrics.get("celery", {}).get("queues", {})
        for queue_name, queue_metrics in celery_queues.items():
            depth = queue_metrics.get("depth", 0)
            if depth > 100:  # Alert if queue depth > 100
                alerts.append({
                    "type": "queue_depth_high",
                    "severity": "warning",
                    "message": f"Queue {queue_name} depth is {depth}",
                    "queue_name": queue_name,
                    "depth": depth
                })
        
        # Check embedding P95 latency
        embedding_models = metrics.get("embedding", {}).get("models", {})
        for model_alias, model_metrics in embedding_models.items():
            p95_latency = model_metrics.get("p95_latency_ms", 0)
            if p95_latency > 5000:  # Alert if P95 > 5 seconds
                alerts.append({
                    "type": "embedding_p95_high",
                    "severity": "warning",
                    "message": f"Model {model_alias} P95 latency is {p95_latency}ms",
                    "model_alias": model_alias,
                    "p95_latency_ms": p95_latency
                })
            
            error_rate = model_metrics.get("error_rate", 0)
            if error_rate > 0.1:  # Alert if error rate > 10%
                alerts.append({
                    "type": "embedding_error_rate_high",
                    "severity": "error",
                    "message": f"Model {model_alias} error rate is {error_rate:.2%}",
                    "model_alias": model_alias,
                    "error_rate": error_rate
                })
        
        return alerts

def get_metrics_aggregator(celery_app: Celery, emb_gateway_url: str = "http://emb:8001") -> MetricsAggregator:
    """Get metrics aggregator instance"""
    return MetricsAggregator(celery_app, emb_gateway_url)
