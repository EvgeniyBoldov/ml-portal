from __future__ import annotations
import logging, time, uuid, contextlib, os
from datetime import datetime
from app.core.metrics import tasks_started_total, tasks_failed_total, task_duration_seconds

log = logging.getLogger("tasks")
def new_id() -> str: return str(uuid.uuid4())

class RetryableError(RuntimeError): ...
class FatalError(RuntimeError): ...

@contextlib.contextmanager
def task_metrics(task: str, queue: str):
    tasks_started_total.labels(queue=queue, task=task).inc()
    start = time.perf_counter()
    try:
        yield
    except Exception:
        tasks_failed_total.labels(queue=queue, task=task).inc()
        raise
    finally:
        task_duration_seconds.labels(task=task).observe(time.perf_counter() - start)

def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default
